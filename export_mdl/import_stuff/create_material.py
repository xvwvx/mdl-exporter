import os
import re
import tempfile
from pathlib import Path
from typing import List, Dict

import bpy

from export_mdl import constants
from export_mdl.classes.War3Material import War3Material
from export_mdl.classes.War3Model import War3Model
from export_mdl.classes.War3Texture import War3Texture
from export_mdl.compat import (blend_for_filter_mode, is_additive_filter_mode,
                              set_material_blend, set_material_shadow_method,
                              set_principled_default)
from export_mdl.import_stuff import blp
from export_mdl.import_stuff import mpq
from export_mdl.import_stuff.War3BpyMaterial import War3BpyMaterial
from export_mdl.properties.War3Preferences import War3Preferences
from export_mdl.utils import (LAYER_COUNT_PROPERTY, LAYER_FILTER_MODE_PROPERTY,
                              TEXTURE_STATUS_PROPERTY, set_texture_path)

# Cache of the game archives opened for MPQ fallback lookups.  Rebuilt whenever
# the configured 魔兽3 directory changes.
_mpq_cache_key = None
_mpq_cache: 'mpq.MPQSet | None' = None
MPQ_ARCHIVE_NAMES = ('war3.mpq', 'War3x.mpq', 'War3xLocal.mpq', 'War3Patch.mpq')


def clear_mpq_cache() -> None:
    """Forget the cached archives (called when the preference changes)."""
    global _mpq_cache_key, _mpq_cache
    if _mpq_cache is not None:
        _mpq_cache.close()
    _mpq_cache_key = None
    _mpq_cache = None


def get_mpq_set(war3_folder: str):
    """The game archives in ``war3_folder``, searched as one set.

    Opening war3.mpq means reading a 16K entry hash table, so the result is
    cached until the preference changes.
    """
    global _mpq_cache_key, _mpq_cache

    if not war3_folder or not os.path.isdir(war3_folder):
        return None
    if _mpq_cache is not None and _mpq_cache_key == war3_folder:
        return _mpq_cache

    if _mpq_cache is not None:
        _mpq_cache.close()

    paths = [os.path.join(war3_folder, name) for name in MPQ_ARCHIVE_NAMES]
    found = [p for p in paths if os.path.isfile(p)]
    if not found:
        # The folder may be the parent of the real install.
        for entry in sorted(os.listdir(war3_folder)):
            sub = os.path.join(war3_folder, entry)
            if not os.path.isdir(sub):
                continue
            nested = [os.path.join(sub, name) for name in MPQ_ARCHIVE_NAMES]
            found.extend(p for p in nested if os.path.isfile(p))
            if found:
                break

    _mpq_cache_key = war3_folder
    _mpq_cache = mpq.MPQSet(found) if found else None
    if _mpq_cache:
        print("  已打开 %d 个 MPQ 归档（%s）"
              % (len(_mpq_cache), ", ".join(os.path.basename(p) for p in found)))
    else:
        print("  魔兽3 目录里没有找到 .mpq 归档：%s" % war3_folder)
    return _mpq_cache


def read_from_mpq(war3_folder: str, image_file: str):
    """Texture bytes from the game archives, or None.

    Tried last, after the loose-file folders, so the player's own converted or
    override textures always win.
    """
    archive_set = get_mpq_set(war3_folder)
    if archive_set is None:
        return None
    return archive_set.read(image_file)


def create_material(model: War3Model, team_color: str) -> Dict[str, War3BpyMaterial]:
    bpy_images = load_and_get_textures(model, team_color)

    print(" creating materials")
    bpy_materials: Dict[str, War3BpyMaterial] = {}
    for i, material in enumerate(model.materials):
        print("  material #" + str(i), material)
        bpy_images_of_layer: List[bpy.types.Image] = []
        for layer in material.layers:
            bpy_image = bpy_images.get(layer.texture.texture_path)
            if bpy_image is None:
                # 损坏的 TEXS/图层引用会让贴图根本没被登记；缺一张贴图不该中断
                # 整个模型的导入。
                print("   材质 %r 的贴图 %r 缺失，跳过该图层"
                      % (material.name, layer.texture.texture_path))
                continue
            bpy_images_of_layer.append(bpy_image)

        bpy_material = create_bpy_material(bpy_images_of_layer, material)
        apply_filter_modes(bpy_material.bpy_material, material)

        bpy_materials[str(i)] = bpy_material

    return bpy_materials


def apply_filter_modes(bpy_material, material: War3Material) -> None:
    """Set the blend method from the War3 layer filter modes.

    'Additive' and 'AddAlpha' layers are the effect planes of a model.  The game
    draws them additively, so their black areas vanish; drawn opaque they become
    solid black slabs that hide the model and make a perfectly good import look
    broken.  Blender has no additive blend mode, so those layers get 'BLEND'
    (which at least honours the alpha) and the filter mode is recorded on the
    material so exporting it again writes the original mode back.
    """
    filter_modes = [layer.filter_mode for layer in material.layers]
    if not filter_modes:
        return

    # The material as a whole follows its most transparent layer: any effect
    # layer means the material cannot be drawn opaque.
    blend_methods = [blend_for_filter_mode(mode) for mode in filter_modes]
    if 'BLEND' in blend_methods:
        chosen = 'BLEND'
    elif 'CLIP' in blend_methods:
        chosen = 'CLIP'
    else:
        chosen = 'OPAQUE'

    # Order matters: 'surface_render_method' drives 'blend_method', so setting it
    # to DITHERED after a BLEND would silently reset the material to HASHED and
    # the effect planes would go back to being opaque black slabs.
    set_material_shadow_method(bpy_material, chosen)
    set_material_blend(bpy_material, chosen)

    # Remember what each layer was, so the exporter can restore it.
    for index, mode in enumerate(filter_modes):
        key = '%s%d' % (LAYER_FILTER_MODE_PROPERTY, index)
        bpy_material[key] = mode
    bpy_material[LAYER_COUNT_PROPERTY] = len(filter_modes)

    if any(is_additive_filter_mode(mode) for mode in filter_modes):
        _make_emissive(bpy_material)


def _make_emissive(bpy_material) -> None:
    """Let an effect material glow instead of reading as dark geometry.

    Blender cannot do additive blending on a material, so the effect colour is
    also routed into Emission.  The look is much closer to the game, and more
    importantly the layer no longer renders as a flat black shape.
    """
    if not bpy_material.use_nodes or bpy_material.node_tree is None:
        return
    tree = bpy_material.node_tree
    output = next((n for n in tree.nodes if n.type == 'OUTPUT_MATERIAL'), None)
    if output is None or not output.inputs['Surface'].is_linked:
        return
    bsdf = output.inputs['Surface'].links[0].from_node
    if bsdf.type != 'BSDF_PRINCIPLED':
        return

    base = bsdf.inputs.get('Base Color')
    emission = bsdf.inputs.get('Emission Color')
    strength = bsdf.inputs.get('Emission Strength')
    if base is None or emission is None or not base.is_linked:
        return
    if not emission.is_linked:
        tree.links.new(base.links[0].from_socket, emission)
    if strength is not None and not strength.is_linked:
        strength.default_value = 1.0


def create_bpy_material(bpy_images_of_layer: List[bpy.types.Image], material: War3Material):
    if bpy_images_of_layer:
        material_name = bpy_images_of_layer[-1].filepath.split(os.path.sep)[-1].split('.')[0]
    else:
        # 没有图层的材质（损坏模型把层数写成 0）没有贴图可供命名：用材质名兜底，
        # 而不是让 [-1] 抛 IndexError 中断整个模型的导入。
        material_name = material.name or "material_no_texture"
    war3_bpy_material = War3BpyMaterial(material_name)

    if material.is_hd:

        diffuse = war3_bpy_material.get_new_node(1, 0, 'ShaderNodeMixRGB')
        diffuse.blend_type = 'COLOR'

        for i, bpy_image in enumerate(bpy_images_of_layer):
            texture_mat_node = war3_bpy_material.get_new_node(3, i, 'ShaderNodeTexImage')
            texture_mat_node.image = bpy_image
            if i == 0:
                war3_bpy_material.connect(texture_mat_node.outputs.get("Color"), diffuse.inputs.get("Color1"))
                war3_bpy_material.connect(diffuse.outputs.get("Color"), war3_bpy_material.mix_node.inputs.get("Color2"))
                war3_bpy_material.connect(texture_mat_node.outputs.get("Alpha"), war3_bpy_material.get_input("Alpha"))
            elif i == 1:
                # normal_map = war3_bpy_material.get_new_node(1, i, 'ShaderNodeNormalMap')
                # normal_map.colorspace_settings.name = 'NONCOLOR'
                # war3_bpy_material.connect(texture_mat_node.outputs.get("Color"), normal_map.inputs.get("Color"))
                # war3_bpy_material.connect(normal_map.outputs.get("Normal"), war3_bpy_material.get_input("Normal"))
                texture_mat_node.image.colorspace_settings.is_data = True
                war3_bpy_material.connect(texture_mat_node.outputs.get("Color"), war3_bpy_material.get_input("Normal"))
            elif i == 2:
                orm = war3_bpy_material.get_new_node(2, i, 'ShaderNodeSeparateRGB')

                roughthness_inv = war3_bpy_material.get_new_node(1, i, "ShaderNodeMath")
                roughthness_inv.operation = 'SUBTRACT'
                roughthness_inv.inputs[0].default_value = 1

                war3_bpy_material.connect(texture_mat_node.outputs.get("Color"), orm.inputs.get("Image"))
                # I don't currently know how to do occlusion
                war3_bpy_material.connect(orm.outputs.get("G"), roughthness_inv.inputs[1])
                war3_bpy_material.connect(roughthness_inv.outputs[0], war3_bpy_material.get_input("Roughness"))
                war3_bpy_material.connect(orm.outputs.get("B"), war3_bpy_material.get_input("Metallic"))
                war3_bpy_material.connect(texture_mat_node.outputs.get("Alpha"), diffuse.inputs.get("Fac"))
            elif i == 3:
                emSlot = war3_bpy_material.get_input("Emission")
                if emSlot is None:
                    emSlot = war3_bpy_material.get_input("Emission Color")
                war3_bpy_material.connect(texture_mat_node.outputs.get("Color"), emSlot)
            elif i == 4:
                team_color = war3_bpy_material.get_new_node(2, 0, 'ShaderNodeRGB')
                team_color.name = 'Team Color'
                team_color.outputs[0].default_value = (1, 0, 0, 1)
                war3_bpy_material.connect(team_color.outputs.get("Color"), diffuse.inputs.get("Color2"))
            # else:
            # skip the environmental map, possibly change the world's map to it
            print(bpy_image.filepath, " at place ", i)
    else:
        next_color_input = war3_bpy_material.mix_node.inputs.get("Color2")
        next_alpha_input = war3_bpy_material.geo_alpha_node.inputs[0]
        for i, bpy_image in enumerate(bpy_images_of_layer):
            texture_mat_node = war3_bpy_material.get_new_node(i*2+3, i, 'ShaderNodeTexImage')
            texture_mat_node.image = bpy_image
            mix_node = war3_bpy_material.get_new_node(i*2+1.5, i, "ShaderNodeMixRGB")
            mix_node.inputs.get("Color1").default_value = (1, 1, 1, 1)
            war3_bpy_material.connect(texture_mat_node.outputs.get("Color"), mix_node.inputs.get("Color2"))
            war3_bpy_material.connect(texture_mat_node.outputs.get("Alpha"), mix_node.inputs[0])
            war3_bpy_material.connect(mix_node.outputs.get("Color"), next_color_input)
            next_color_input = mix_node.inputs.get("Color2")

            alpha_node = war3_bpy_material.get_new_node(i*2+1, 4, "ShaderNodeMath")
            alpha_node.inputs[1].default_value = 0.0
            alpha_node.use_clamp = True
            war3_bpy_material.connect(texture_mat_node.outputs.get("Alpha"), alpha_node.inputs[0])
            war3_bpy_material.connect(alpha_node.outputs[0], next_alpha_input)
            next_alpha_input = alpha_node.inputs[1]
    return war3_bpy_material


def get_wc3_base_node(material_name: str):
    bpy_material: bpy.types.Material = bpy.data.materials.new(name=material_name)
    bpy_material.use_nodes = True

    set_material_blend(bpy_material, 'HASHED')
    set_material_shadow_method(bpy_material, 'HASHED')

    bpy_material.diffuse_color = (1.0, 1.0, 1.0, 1.0)
    texture_slot_index = 0
    material_node_tree = bpy_material.node_tree
    # Look the node up by type: Blender localises default node names, so a
    # Chinese UI has '原理化 BSDF' where an English one has 'Principled BSDF'.
    shader_node: bpy.types.Node = None
    for node in material_node_tree.nodes:
        if node.type == 'BSDF_PRINCIPLED':
            shader_node = node
            break
    if shader_node is None:
        shader_node = material_node_tree.nodes.new("ShaderNodeBsdfPrincipled")
    # no specular, full roughness.  Socket order shifts between versions, so
    # address them by name rather than by index.
    set_principled_default(shader_node, 0.0, "Specular IOR Level", "Specular")
    set_principled_default(shader_node, 1.0, "Roughness")


    node_width: float = shader_node.width
    color_input_socket = shader_node.inputs.get("Base Color")
    mix_node = get_new_node(node_width + 20, 0, material_node_tree, "ShaderNodeMixRGB")
    mix_node.blend_type = 'MULTIPLY'
    mix_node.inputs[0].default_value = 1.0
    color_node = get_new_node(node_width + 200, 0, material_node_tree, "ShaderNodeRGB")
    color_node.outputs[0].default_value = (1, 1, 1, 1)
    color_node.name = 'Geoset Anim Color'
    material_node_tree.links.new(color_node.outputs.get("Color"), mix_node.inputs.get("Color1"))
    material_node_tree.links.new(color_node.outputs.get("Color"), mix_node.inputs.get("Color1"))
    material_node_tree.links.new(mix_node.outputs.get("Color"), shader_node.inputs.get("Base Color"))

    diffuse = material_node_tree.nodes.new('ShaderNodeMixRGB')
    diffuse.location.x -= node_width + 50
    diffuse.blend_type = 'COLOR'


def get_new_node(loc_x: float, loc_y: float, material_node_tree: bpy.types.NodeTree, node_type: str):
    new_node = material_node_tree.nodes.new(node_type)
    new_node.location.x -= loc_x
    new_node.location.y += loc_y
    return new_node


def load_and_get_textures(model: War3Model, team_color: str):
    print(" loading textures")
    preferences: War3Preferences = bpy.context.preferences.addons.get('export_mdl').preferences
    folders = get_folders(preferences.alternativeResourceFolder, preferences.resourceFolder, model.file)
    texture_ext = get_texture_ext(preferences.textureExtension)
    bpy_images: Dict[str, bpy.types.Image] = {}
    for texture in model.textures:
        if texture.texture_path not in bpy_images:
            image_file = get_image_file(team_color, texture, texture_ext)
            bpy_image = get_image(folders, image_file, texture.texture_path,
                                  preferences.war3Folder, preferences.useMpq)
            bpy_images[texture.texture_path] = bpy_image
    report_texture_status(bpy_images)
    return bpy_images


def report_texture_status(bpy_images: Dict[str, bpy.types.Image]) -> None:
    """Say how the texture lookup went, so a blank model is easy to explain."""
    decoded = found = failed = from_mpq = 0
    missing: List[str] = []
    for path, image in bpy_images.items():
        status = image.get(TEXTURE_STATUS_PROPERTY, '')
        if status == 'decoded':
            decoded += 1
        elif status == 'mpq':
            from_mpq += 1
        elif status == 'found':
            found += 1
        elif status == 'failed':
            failed += 1
        else:
            missing.append(path)

    print(" 贴图：共 %d 个 —— 解码 %d，MPQ %d，直接读取 %d，解码失败 %d，未找到 %d"
          % (len(bpy_images), decoded, from_mpq, found, failed, len(missing)))
    if missing:
        print("  未找到的贴图（请检查「贴图资源目录」是否指向解包根目录，"
              "或「魔兽3 目录」是否正确）：")
        for path in missing[:10]:
            print("    " + path)
        if len(missing) > 10:
            print("    ... 另有 %d 个" % (len(missing) - 10))


def get_texture_ext(texture_ext: str):
    if texture_ext == '':
        print("   No texture extension to replace blp with set in addon preferences")
        texture_ext = 'png'
    if texture_ext[0] != '.':
        texture_ext = '.' + texture_ext
    return texture_ext


def get_image(folders: List[Path], image_file: str, war3_path: str = '',
              war3_folder: str = '', use_mpq: bool = False):
    """Load one texture, searching loose files first and the game MPQs last."""
    print("  loading:", image_file)
    file_path_parts = image_file.split(os.path.sep)

    file_name = file_path_parts[-1].split('.')[0]
    found = find_file(file_path_parts, folders)

    if found and blp.is_blp_file(found):
        bpy_image = load_blp_image(file_name, found)
        if bpy_image is not None:
            set_texture_path(bpy_image, war3_path)
            bpy_image[TEXTURE_STATUS_PROPERTY] = 'decoded'
            return bpy_image
        bpy_image = bpy.data.images.new(file_name, 0, 0)
        bpy_image.source = 'FILE'
        # filepath_raw：.blp 解不开时把路径记成 filepath 会让 Blender 立刻去读
        # 这个它不认识的格式，控制台刷 "unknown file-format" 并清掉我们写进去的
        # 像素；这里只是留个来源标记，不要求 Blender 去加载。
        bpy_image.filepath_raw = found
        set_texture_path(bpy_image, war3_path)
        bpy_image[TEXTURE_STATUS_PROPERTY] = 'failed'
        return bpy_image

    if not found and use_mpq and war3_folder:
        # Lowest priority: the game's own archives, only reached when no loose
        # file matched.  The player's own textures therefore always win.
        data = read_from_mpq(war3_folder, war3_path or image_file)
        if data:
            bpy_image = load_blp_image(file_name, war3_path or image_file, data)
            if bpy_image is not None:
                set_texture_path(bpy_image, war3_path)
                # A .blp that decodes but yields no pixels is corrupt inside the
                # archive, which is common in trimmed-down repacks; report it as
                # failed rather than pretending the texture loaded.
                if tuple(bpy_image.size)[0]:
                    bpy_image[TEXTURE_STATUS_PROPERTY] = 'mpq'
                    print("    from MPQ: %s" % (war3_path or image_file))
                    return bpy_image
                print("    from MPQ but unusable (damaged in the archive): %s"
                      % (war3_path or image_file))
                bpy.data.images.remove(bpy_image)

    bpy_image = bpy.data.images.new(file_name, 0, 0)
    bpy_image.source = 'FILE'

    bpy_image.filepath = found
    set_texture_path(bpy_image, war3_path)
    bpy_image[TEXTURE_STATUS_PROPERTY] = 'found' if found else 'missing'
    return bpy_image


def load_blp_image(name: str, path: str, data: bytes = None):
    """Decode a .blp into a new Blender image, or None when it cannot be read.

    Blender has no .blp support, so the texture is decoded here: either the JPEG
    that a BLP1 file embeds (handed to Blender's own decoder through a temporary
    file) or the palette / DXT / raw pixels decoded in blp.py.

    ``data`` supplies the bytes directly, which is how textures read out of an
    MPQ archive are passed in; otherwise they are read from ``path``.
    """
    if data is None:
        try:
            with open(path, 'rb') as handle:
                data = handle.read()
        except OSError as exc:
            print("    could not read %s: %s" % (os.path.basename(path), exc))
            return None

    try:
        texture = blp.read_blp(data)
    except blp.BlpError as exc:
        print("    could not decode %s: %s" % (os.path.basename(path), exc))
        return None

    if texture.is_jpeg:
        pixels, size = _decode_embedded_jpeg(texture.jpeg)
        if pixels is None:
            print("    %s: embedded JPEG could not be read"
                  % os.path.basename(path))
            return None
    else:
        size = (texture.width, texture.height)
        pixels = blp.to_blender_pixels(texture.rgba, texture.width,
                                       texture.height)

    bpy_image = bpy.data.images.new(name, size[0], size[1], alpha=True)
    bpy_image.pixels.foreach_set(pixels)
    # pack() has to come *before* any path is set: on an unpacked image, setting
    # filepath makes Blender try to load from that path, and since it cannot read
    # a .blp the pixels it just received are thrown away and the image goes black.
    try:
        bpy_image.pack()
    except RuntimeError:
        pass
    # filepath_raw (not filepath) so the .blp is shown as the source without
    # Blender trying to read it and logging "Image not available".
    bpy_image.filepath_raw = path
    print("    decoded %s: %dx%d" % (os.path.basename(path), size[0], size[1]))
    return bpy_image


def _decode_embedded_jpeg(jpeg_bytes: bytes):
    """Load the JPEG a BLP1 file embeds and return (pixels, (w, h))."""
    handle = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
    temp_path = handle.name
    try:
        handle.write(jpeg_bytes)
        handle.close()
        loaded = bpy.data.images.load(temp_path)
        try:
            size = tuple(loaded.size)
            if size[0] == 0 or size[1] == 0:
                return None, None
            return loaded.pixels[:], size
        finally:
            bpy.data.images.remove(loaded)
    except (OSError, RuntimeError) as exc:
        print("    embedded JPEG failed: %s" % exc)
        return None, None
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass


def classify_replaceable_path(path: str) -> int:
    r"""Recognise the engine's replaceable texture paths.

    Mirrors MdxAssetLibrary.ClassifyReplaceablePath: a layer may leave ReplaceableId at
    0 and still point at "ReplaceableTextures\TeamColor\TeamColorNN.blp", which the game
    never loads from an archive but substitutes with the player colour.
    """
    normalized = (path or '').replace('/', '\\').lower()
    if normalized.startswith('replaceabletextures\\teamcolor\\'):
        return 1
    if normalized.startswith('replaceabletextures\\teamglow\\'):
        return 2
    return 0


def get_image_file(team_color: str, texture: War3Texture, texture_ext: str) -> str:
    repl_id = int(texture.replaceable_id or 0)
    texture_path = texture.texture_path or ''
    if repl_id == 0:
        repl_id = classify_replaceable_path(texture_path)

    if repl_id == 1:
        image_file = get_repl_img(1, team_color)
    elif repl_id == 2:
        image_file = get_repl_img(2, team_color)
    else:
        # ReplaceableId outside 1/2 (equipment slots 31..47, hair colour 99, ...) is only
        # repointed at runtime by SetUnitTexture, so the model's own path is the default
        # look.  Substituting AshenCanopyTree here pointed the layer at a file the
        # archives do not contain, and the material degraded to flat colour.
        image_file = texture_path or 'Textures\\white.blp'

    sub = re.sub("\\.blp$", texture_ext, image_file)
    sub = re.sub("\\.tif$", texture_ext, sub)
    return re.sub("[/\\\\]", re.escape(os.path.sep), sub)


def get_repl_img(repl_id: int, team_color: str):
    if repl_id == 1:
        return constants.TEAM_COLOR_IMAGES[team_color]
    elif repl_id == 2:
        return constants.TEAM_GLOW_IMAGES[team_color]
    else:
        # MdxAssetLibrary.LoadTexture falls back to a plain white texture for an
        # unrecognised replaceable id; the canopy tree path used before is not in the
        # game archives at all.
        return 'Textures\\white.blp'
    # match repl_id:
    #     case 1:
    #         return constants.TEAM_COLOR_IMAGES[team_color]
    #     case 2:
    #         return constants.TEAM_GLOW_IMAGES[team_color]
    #     case _:
    #         return 'ReplaceableTextures\\AshenvaleTree\\AshenCanopyTree.blp'


def find_file(image_path_comps: List[str], folders: List[Path]) -> str:
    image_file = image_path_comps[-1]
    sub_folders = image_path_comps[0:-1]
    sub_folders.append('')
    for i in range(len(image_path_comps)):
        sub_folder1 = '/'.join(image_path_comps[i:-1])
        sub_folder2 = '/'.join(image_path_comps[0:-i])

        for folder in folders:
            file_path = folder / sub_folder1 / image_file
            if is_valid_path(file_path):
                return str(file_path)
            file_path = folder / sub_folder2 / image_file
            if is_valid_path(file_path):
                return str(file_path)
    return ''


def get_folders(alt_folder: str, resource_folder: str, model_file: str) -> List[Path]:
    folders = []
    if resource_folder == '':
        print("    No resource folder set in addon preferences")
    if alt_folder == '':
        print("    No alt resource folder set in addon preferences")
    folders.extend(get_valid_folders(Path(model_file).parent))
    if resource_folder != '':
        folders.extend(get_valid_folders(Path(resource_folder)))
    if alt_folder != '':
        folders.extend(get_valid_folders(Path(alt_folder)))

    return folders


def get_valid_folders(folder_path: Path):
    paths = []
    if folder_path.is_dir():
        paths.append(folder_path)
        sub1: Path = (folder_path / "Textures")
        sub2: Path = (folder_path / "textures")
        if sub1.is_dir():
            paths.append(sub1)
        if sub2.is_dir():
            paths.append(sub2)
    return paths


def is_valid_path(file_path: Path) -> bool:
    try:
        if Path(file_path).exists():
            return True
    except OSError:
        print("bad path:", file_path)
    return False
