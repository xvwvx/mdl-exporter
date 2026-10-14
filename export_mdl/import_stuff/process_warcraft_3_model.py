from ..classes.War3Model import War3Model
from ..classes.War3Texture import War3Texture


def process_warcraft_3_model(model: War3Model):
    model.process_nodes()

    dangling_bone_warned = False

    for geoset in model.geosets:
        if geoset.name is None:
            geoset.name = model.name
        elif geoset.name.isnumeric():
            geoset.name = geoset.name + " " + model.name

        for mg in geoset.matrices:
            b_names = []
            for bone in mg:
                # 悬空骨骼 id（模型损坏，或 geoset 引用了不存在的对象，例如
                # CliffDoodadCave.mdx 完全没有节点块却引用了对象 id 0）不能中断整个
                # 导入：参考实现对没有有效骨骼的组按“不绑定”处理
                # （runtime/MdxMeshBuilder.cs:75-110），下面的骨骼组绑定
                # （create_mesh_objects.py:85-87）同样会跳过不存在的名字。
                # 跳过比替换成其他骨骼更安全，不会产生错误变形。
                try:
                    bone_id = int(bone)
                except (TypeError, ValueError):
                    continue
                node = model.id_to_object.get(bone_id)
                if node is None:
                    if not dangling_bone_warned:
                        print("   模型 %r：geoset %r 引用了不存在的骨骼 id %d，"
                              "跳过该骨骼影响" % (model.name, geoset.name, bone_id))
                        dangling_bone_warned = True
                    continue
                b_names.append(node.name)
            mg.clear()
            mg.extend(b_names)

        # for vert in geoset.vertices:
        #     b_names = []
        #     b_ids = []
        #     for bone in vert.bone_list:
        #         if int(bone) in model.id_to_object:
        #             b_names.append(model.id_to_object[int(bone)].name)
        #             b_ids.append(int(bone))
        #     if b_names:
        #         vert.bone_list.clear()
        #         vert.bone_list.extend(b_names)
        #         vert.bone_id_list.clear()
        #         vert.bone_id_list.extend(b_ids)
        #         vert.bone_name_list.clear()
        #         vert.bone_name_list.extend(b_names)

    valid_anims = []
    for geoset_anim in model.geoset_anims:
        if not 0 <= geoset_anim.geoset_id < len(model.geosets):
            # Some tools write a GeosetId that no longer matches the geoset list
            # (for example after dropping an empty geoset), so do not trust it.
            print(" GeosetAnim references missing geoset %s - dropped"
                  % geoset_anim.geoset_id)
            continue
        geoset_anim.geoset = model.geosets[geoset_anim.geoset_id]
        if geoset_anim.geoset and geoset_anim.geoset.name:
            geoset_anim.geoset_name = geoset_anim.geoset.name
        else:
            geoset_anim.geoset_name = "%s" % geoset_anim.geoset_id + " " + model.name
        valid_anims.append(geoset_anim)
    model.geoset_anims = valid_anims

    # print("model.materials:", model.materials)
    if len(model.textures) == 0:
        model.textures.append(War3Texture())
    for material in model.materials:
        for layer in material.layers:
            # A layer points at its UV animation by index (TextureAnimationId /
            # TVertexAnimId); the TextureAnims chunk is parsed after Materials,
            # so the reference is resolved here.
            index = getattr(layer, "textureAnimationId", 0)
            if 0 <= index < len(model.tvertex_anims):
                layer.texture_anim = model.tvertex_anims[index]
            if int(layer.texture_path) < len(model.textures):
                layer.texture = model.textures[int(layer.texture_path)]
            else:
                layer.texture = model.textures[0]

    model.objects_all.extend(model.bones)
    model.objects_all.extend(model.helpers)

