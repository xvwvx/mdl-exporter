import bpy
from mathutils import Vector
from typing import List

# import export_mdl.classes.animation_curve_utils.get_wc3_animation_curve
from ..War3AnimationCurve import War3AnimationCurve
from ..War3Geoset import War3Geoset
from ..War3GeosetAnim import War3GeosetAnim
from ..War3Model import War3Model
from ..War3Vertex import War3Vertex
from ..animation_curve_utils.get_wc3_animation_curve import get_wc3_animation_curve
from .is_animated_ugg import is_animated_ugg
from .prepare_mesh import prepare_mesh
from .create_bone import create_bone
from .get_visibility import get_visibility
from .register_global_sequence import register_global_sequence
from ..utils.transform_rot import transform_rot
from ..utils.transform_vec import transform_vec
from ...utils import rnd


def make_mesh(war3_model: War3Model, billboard_lock, billboarded, context, mats, bpy_obj, parent, settings):
    visibility = get_visibility(war3_model.sequences, bpy_obj)
    anim_loc, anim_rot, anim_scale, is_animated = is_animated_ugg(war3_model, bpy_obj, settings)
    bpy_mesh = prepare_mesh(bpy_obj, context, settings.global_matrix @ bpy_obj.matrix_world)

    # Geoset Animation
    geoset_anim, geoset_anim_hash = get_geoset_anim(bpy_obj, visibility, war3_model)

    armature = None

    for m in bpy_obj.modifiers:
        if m.type == 'ARMATURE':
            armature = m

    bone_names = set()
    if armature is not None:
        bone_names = set(b.name for b in armature.object.data.bones)

    # Make a list of all bones to use if saving skin weights
    temp_skin_matrices = None
    if settings.use_skinweights and len(bone_names):
        temp_skin_matrices = list([b.name] for b in armature.object.data.bones)

    parent = create_bone_and_stuff(anim_loc, anim_rot, anim_scale, armature, billboard_lock, billboarded, geoset_anim,
                                   is_animated, bpy_obj, parent, settings, war3_model)

    mesh_geosets = set()
    for tri in bpy_mesh.loop_triangles:
        # p = bpy_mesh.polygons[f.index]
        # Textures and materials
        material_name = "default"
        if bpy_obj.material_slots and len(bpy_obj.material_slots):
            bpy_material = bpy_obj.material_slots[tri.material_index].material
            if bpy_material is not None:
                material_name = bpy_material.name
                mats.add(bpy_material)

        if (material_name, geoset_anim_hash) in war3_model.geoset_map.keys():
            geoset = war3_model.geoset_map[(material_name, geoset_anim_hash)]
        else:
            geoset = War3Geoset()
            geoset.mat_name = material_name
            if geoset_anim is not None:
                geoset.geoset_anim = geoset_anim
                geoset_anim.geoset = geoset

            war3_model.geoset_map[(material_name, geoset_anim_hash)] = geoset

        if settings.use_skinweights:
            geoset.skin_matrices = temp_skin_matrices

        # Vertices, faces, and matrices
        vertex_map = {}
        for vert, loop in zip(tri.vertices, tri.loops):
            co = bpy_mesh.vertices[vert].co
            coord = (rnd(co.x), rnd(co.y), rnd(co.z))
            n = bpy_mesh.vertices[vert].normal if tri.use_smooth else tri.normal
            norm = (rnd(n.x), rnd(n.y), rnd(n.z))
            uv = bpy_mesh.uv_layers.active.data[loop].uv if len(bpy_mesh.uv_layers) else Vector((0.0, 0.0))
            uv[1] = 1 - uv[1]  # For some reason, uv Y coordinates appear flipped. This should fix that.
            tvert = (rnd(uv.x), rnd(uv.y))
            groups = None
            skins = None
            bone_list = None
            weight_list = None
            matrix = 0
            if armature is not None:
                vertex_groups = sorted(bpy_mesh.vertices[vert].groups[:], key=lambda x: x.weight, reverse=True)
                # Sort bones by descending weight
                if len(vertex_groups) and not settings.use_skinweights:
                    groups = get_matrice_groups(bone_names, bpy_obj, vertex_groups)
                elif len(vertex_groups) and settings.use_skinweights:
                    # skins = get_skins(bone_names, geoset, bpy_obj, vertex_groups)
                    bone_list, weight_list = get_skins2(bone_names, geoset, bpy_obj, vertex_groups)

            if parent is not None and (groups is None or len(groups) == 0):
                groups = [parent]

            if groups is not None:
                if groups not in geoset.matrices:
                    geoset.matrices.append(groups)
                matrix = geoset.matrices.index(groups)

            if settings.use_skinweights:
                # vertex = (coord, norm, tvert, skins)
                vertex = War3Vertex(coord, norm, tvert, None, bone_list, weight_list, None)
            else:
                # vertex = (coord, norm, tvert, matrix)
                # vertex = War3Vertex(coord, norm, tvert, matrix, None, None)
                vertex = War3Vertex(coord, norm, tvert, matrix, None, None, None)

            if vertex not in geoset.vertices:
                geoset.vertices.append(vertex)

            vertex_map[vert] = geoset.vertices.index(vertex)

        # Triangles, normals, vertices, and UVs
        geoset.triangles.append(
            (vertex_map[tri.vertices[0]], vertex_map[tri.vertices[1]], vertex_map[tri.vertices[2]]))

        mesh_geosets.add(geoset)

    for geoset in mesh_geosets:
        geoset.objects.append(bpy_obj)
        if not len(geoset.matrices) and parent is not None:
            geoset.matrices.append([parent])

    # obj.to_mesh_clear()
    bpy.data.meshes.remove(bpy_mesh)


def get_matrice_groups(bone_names, obj, vertex_groups) -> List[str]:
    # Warcraft 800 does not support vertex weights, so we exclude groups with too small influence
    groups = list(obj.vertex_groups[vg.group].name for vg in vertex_groups if
                  (obj.vertex_groups[vg.group].name in bone_names and vg.weight > 0.25))[:3]
    if not len(groups):
        for vg in vertex_groups:
            # If we didn't find a group, just take the best match (the list is already sorted by weight)
            if obj.vertex_groups[vg.group].name in bone_names:
                groups = [obj.vertex_groups[vg.group].name]
                break
    return groups


def get_matrice_groups1(bone_names, obj, vertex_groups):
    # Warcraft 800 does not support vertex weights, so we exclude groups with too small influence
    groups = list(obj.vertex_groups[vg.group].name for vg in vertex_groups if
                  (obj.vertex_groups[vg.group].name in bone_names and vg.weight > 0.25))[:3]
    if not len(groups):
        for vg in vertex_groups:
            # If we didn't find a group, just take the best match (the list is already sorted by weight)
            if obj.vertex_groups[vg.group].name in bone_names:
                groups = [obj.vertex_groups[vg.group].name]
                break
    return groups


def get_skins(bone_names, geoset, obj, vertex_groups):
    # Warcraft 800+ do support vertex (skin) weights; 4 per vertex which sum up to 255
    bone_list = (list(geoset.skin_matrices.index([obj.vertex_groups[vg.group].name]) for vg in vertex_groups if
                      (obj.vertex_groups[vg.group].name in bone_names)) + [0] * 4)[:4]
    weight_list = (list(vg.weight for vg in vertex_groups if (obj.vertex_groups[vg.group].name in bone_names)) + [
        0] * 4)[:4]
    tot_weight = sum(weight_list)
    w_conv = 255 / tot_weight
    weight_list = [round(i * w_conv) for i in weight_list]
    # Ugly fix to make sure total weight is 255

    weight_adjust = 255 - sum(weight_list)
    weight_list[0] = int(weight_list[0] + weight_adjust)
    skins = bone_list + weight_list
    return skins


def get_skins2(bone_names, geoset, obj, vertex_groups):
    # Warcraft 800+ do support vertex (skin) weights; 4 per vertex which sum up to 255
    bone_list = (list(obj.vertex_groups[vg.group].name for vg in vertex_groups if
                      (obj.vertex_groups[vg.group].name in bone_names)))[:4]
    weight_list = (list(vg.weight for vg in vertex_groups if (obj.vertex_groups[vg.group].name in bone_names)) + [
        0] * 4)[:4]
    tot_weight = sum(weight_list)
    w_conv = 255 / tot_weight
    weight_list = [round(i * w_conv) for i in weight_list]
    # Ugly fix to make sure total weight is 255

    weight_adjust = 255 - sum(weight_list)
    weight_list[0] = int(weight_list[0] + weight_adjust)
    # skins = bone_list + weight_list
    return bone_list, weight_list


def get_geoset_anim(obj, visibility, war3_model):
    vertex_color_anim = get_wc3_animation_curve(obj.animation_data, 'color', 3, war3_model.sequences)
    vertex_color = None
    if any(i < 0.999 for i in obj.color[:3]):
        vertex_color = tuple(obj.color[:3])
    if not any((vertex_color, vertex_color_anim)):
        mat = obj.active_material
        if mat is not None and hasattr(mat, "node_tree") and mat.node_tree is not None:
            node = mat.node_tree.nodes.get("VertexColor")
            if node is not None:
                attr = "outputs" if node.bl_idname == 'ShaderNodeRGB' else "inputs"
                vertex_color = tuple(getattr(node, attr)[0].default_value[:3])
                if hasattr(mat.node_tree, "animation_data"):
                    vertex_color_anim = get_wc3_animation_curve(
                        mat.node_tree.animation_data, 'nodes["VertexColor"].%s[0].default_value' % attr, 3,
                        war3_model.sequences)
    geoset_anim = None
    geoset_anim_hash = 0
    if any((vertex_color, vertex_color_anim, visibility)):
        geoset_anim = War3GeosetAnim(vertex_color, vertex_color_anim, visibility)
        geoset_anim_hash = hash(geoset_anim)  # The hash is a bit complex, so we precompute it
    return geoset_anim, geoset_anim_hash


def create_bone_and_stuff(anim_loc, anim_rot, anim_scale, armature, billboard_lock, billboarded, geoset_anim,
                          is_animated, obj, parent, settings, war3_model):
    bone = None
    if (armature is None and parent is None) or is_animated:
        bone = create_bone(anim_loc, anim_rot, anim_scale, obj, parent, settings)
        # bone = War3Object(obj.name)  # Object is animated or parent is missing - create a bone for it!
        #
        # bone.parent = parent  # Remember to make it the parent - parent is added to matrices further down
        # bone.pivot = settings.global_matrix @ Vector(obj.location)
        # bone.anim_loc = anim_loc
        # bone.anim_rot = anim_rot
        # bone.anim_scale = anim_scale

        if bone.anim_loc is not None:
            register_global_sequence(war3_model.global_seqs, bone.anim_loc)
            transform_vec(bone.anim_loc.keyframes, bone.anim_loc.interpolation, bone.anim_loc.handles_right,
                          bone.anim_loc.handles_left, obj.matrix_world.inverted())
            transform_vec(bone.anim_loc.keyframes, bone.anim_loc.interpolation, bone.anim_loc.handles_right,
                          bone.anim_loc.handles_left, settings.global_matrix)

        if bone.anim_rot is not None:
            register_global_sequence(war3_model.global_seqs, bone.anim_rot)
            transform_rot(bone.anim_rot.keyframes, obj.matrix_world.inverted())
            transform_rot(bone.anim_rot.keyframes, settings.global_matrix)

        register_global_sequence(war3_model.global_seqs, bone.anim_scale)
        bone.billboarded = billboarded
        bone.billboard_lock = billboard_lock

        if geoset_anim is not None:
            war3_model.geoset_anim_map[bone] = geoset_anim
        war3_model.objects['bone'].add(bone)
        parent = bone.name
    return parent
