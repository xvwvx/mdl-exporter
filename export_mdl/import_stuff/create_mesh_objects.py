from typing import List, Dict

import bpy

from export_mdl.classes.War3Geoset import War3Geoset
from export_mdl.classes.War3Model import War3Model
from export_mdl.import_stuff.War3BpyMaterial import War3BpyMaterial


def create_mesh_objects(model: War3Model,
                        bpy_armature_object: bpy.types.Object,
                        bpy_materials: Dict[str, War3BpyMaterial]):
    # print("Geosets")
    print(" creating meshes")
    bpy_mesh_objects = []

    for war3_geoset in model.geosets:
        mesh_name = model.name if war3_geoset.name is None else war3_geoset.name
        if mesh_name.isnumeric():
            mesh_name = mesh_name + " " + model.name
        print("  Geoset \"" + mesh_name + "\"")
        # print("  creating mesh for \"" + mesh_name + "\"")
        print("   creating mesh")
        # print("creating geoset: ", mesh_name)
        bpy_mesh = bpy.data.meshes.new(mesh_name)
        # print("new object for ", mesh_name)
        bpy_object = bpy.data.objects.new(mesh_name, bpy_mesh)
        # print("adding ", mesh_name, "to scene")
        bpy.context.scene.collection.objects.link(bpy_object)
        # print("collecting positions for %s verts" % len(war3_geoset.vertices))
        locations = [v.pos for v in war3_geoset.vertices]
        # for l in locations:
        #     print(l)

        # print("creating mesh with %s verts" % len(locations))
        bpy_mesh.from_pydata(locations, (), war3_geoset.triangles)

        # print("applying uvs")
        apply_uvs(bpy_mesh, war3_geoset)

        if "vertex_normals" in bpy_mesh.__dir__():
            for bpy_vert_norm, vertex in zip(bpy_mesh.vertex_normals, war3_geoset.vertices):
                bpy_vert_norm = vertex.normal
        else:
            for bpy_vert, vertex in zip(bpy_mesh.vertices, war3_geoset.vertices):
                bpy_vert.normal = vertex.normal

        bpy_material = bpy_materials.get(war3_geoset.mat_name)
        if bpy_material is None:
            # geoset 没有 MATS 子块时 mat_name 仍是 None（parse_geometry.py:107 只在
            # MATS 里赋值），材质索引也可能越界。参考实现只接受
            # 0 <= MaterialId < 材质数（MdxLoader.cs:1004、1874-1878），其余情况不绑定
            # 材质；这里同样不绑定，而不是抛 KeyError 中断整个导入。
            print("   geoset %r 的材质索引 %r 无效，不绑定材质"
                  % (mesh_name, war3_geoset.mat_name))
        else:
            bpy_mesh.materials.append(bpy_material.bpy_material)

        # print("making bone groups")
        for bone in model.bones:
            bpy_object.vertex_groups.new(name=str(bone.name))

        # print("applying bones")
        print("   skinning")
        for vertex in war3_geoset.vertices:
            influences = [(vertex.bone_list[i], vertex.weight_list[i])
                          for i in range(len(vertex.bone_list))
                          if vertex.weight_list[i] != 0]
            if not influences:
                continue

            # War3 stores up to four bone influences per vertex as relative byte
            # weights that do not necessarily sum to 255 (a vertex bound rigidly
            # to two bones is [255, 255]).  Blender's armature modifier expects
            # the weights of a vertex to sum to 1, so they are normalised here:
            # leaving them unnormalised moves such a vertex by twice the bone
            # transform, which tears the mesh apart into scattered pieces.
            total = sum(weight for _bone, weight in influences)
            if total <= 0:
                continue

            groups: bpy.types.VertexGroups = bpy_object.vertex_groups
            vertex_index = war3_geoset.vertices.index(vertex)
            for bone_name, weight in influences:
                vert_group: bpy.types.VertexGroup = groups.get(bone_name)
                if vert_group is None:
                    continue
                vert_group.add([vertex_index, ], weight / total, 'REPLACE')

        bpy_object.modifiers.new(name='Armature', type='ARMATURE')
        bpy_object.modifiers['Armature'].object = bpy_armature_object
        bpy_mesh_objects.append(bpy_object)
    return bpy_mesh_objects


def apply_uvs(bpy_mesh: bpy.types.Mesh, war3_geoset: War3Geoset):
    # print("applying uvs")
    bpy_mesh.uv_layers.new()
    uv_layer = bpy_mesh.uv_layers.active.data
    for tris in bpy_mesh.polygons:
        for loopIndex in range(tris.loop_start, tris.loop_start + tris.loop_total):
            vertex_index = bpy_mesh.loops[loopIndex].vertex_index
            uv_layer[loopIndex].uv = war3_geoset.vertices[vertex_index].uv
