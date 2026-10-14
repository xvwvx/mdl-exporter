from typing import Dict, List, Set

import bpy
from mathutils import Vector

from ..classes.War3Model import War3Model
from ..classes.War3Node import War3Node
from ..properties.War3NodeProperties import (NODE_TYPE_ATTACHMENT,
                                             NODE_TYPE_BONE,
                                             NODE_TYPE_COLLISION_SHAPE,
                                             NODE_TYPE_EVENT,
                                             NODE_TYPE_HELPER,
                                             set_node_flags,
                                             set_node_type)


def create_armature_object(model: War3Model, bone_size: float) -> bpy.types.Object:
    print(" creating armature")
    war3_nodes = list(model.id_to_object.values())
    bpy_armature_object = get_bpy_armature_object(model.name + ' Nodes')
    bpy.ops.object.mode_set(mode='EDIT')
    bpy_armature: bpy.types.Armature = bpy_armature_object.data
    # bpy_armature.display_type = 'STICK'

    create_edit_bones(bone_size, war3_nodes, bpy_armature)
    bpy.ops.object.mode_set(mode='EDIT')

    set_parents(war3_nodes, bpy_armature)
    connect_bones(bpy_armature)
    ensure_bone_length(bpy_armature)

    if bpy.app.version[0] < 4:
        from export_mdl.import_stuff.create_bone_groups import create_bone_groups
        create_bone_groups(war3_nodes, bpy_armature_object)
    else:
        from export_mdl.import_stuff.create_bone_collections import create_bone_groups
        create_bone_groups(war3_nodes, bpy_armature_object)
    bpy.ops.object.mode_set(mode='POSE')

    for p_bone in bpy_armature_object.pose.bones:
        p_bone.rotation_mode = 'QUATERNION'

    record_node_types(model, bpy_armature)
    record_node_flags(model, bpy_armature)

    return bpy_armature_object


def get_node_type_map(model: War3Model) -> Dict[str, str]:
    """Which War3 chunk each parsed node came from.

    Every node is represented by an armature bone, so without this the
    Bone / Helper / Attachment / Event / CollisionShape distinction is lost and
    the exporter can only guess (see demote_to_helpers).
    """
    node_types: Dict[str, str] = {}
    for node in model.bones:
        node_types[node.name] = NODE_TYPE_BONE
    for node in model.helpers:
        node_types[node.name] = NODE_TYPE_HELPER
    for node in model.attachments:
        node_types[node.name] = NODE_TYPE_ATTACHMENT
    for node in model.event_objects:
        node_types[node.name] = NODE_TYPE_EVENT
    for node in model.collision_shapes:
        node_types[node.name] = NODE_TYPE_COLLISION_SHAPE
    return node_types


def record_node_types(model: War3Model, bpy_armature: bpy.types.Armature) -> None:
    node_types = get_node_type_map(model)
    for bone in bpy_armature.bones:
        node_type = node_types.get(bone.name)
        if node_type is not None:
            set_node_type(bone, node_type)


def record_node_flags(model: War3Model, bpy_armature: bpy.types.Armature) -> None:
    """把每个节点解析出来的 MdxNodeFlags 记在它的骨骼上。

    骨骼（以及被降级成 helper 的骨骼）没有 Object.mdl_billboard 可用，标志位
    只能存在骨骼自己的自定义属性里，导出端 make_bones.get_wc3_bone 再从那里读回。
    """
    nodes_by_name: Dict[str, War3Node] = {}
    for node in model.id_to_object.values():
        nodes_by_name.setdefault(node.name, node)
    for bone in bpy_armature.bones:
        node = nodes_by_name.get(bone.name)
        if node is not None:
            set_node_flags(bone, getattr(node, "flags", 0))


def get_bpy_armature_object(name: str) -> bpy.types.Object:
    bpy_armature: bpy.types.Armature = bpy.data.armatures.new(name)
    bpy_armature_object = bpy.data.objects.new(name, bpy_armature)
    bpy.context.scene.collection.objects.link(bpy_armature_object)
    bpy_armature_object.select_set(True)
    bpy.context.view_layer.objects.active = bpy_armature_object
    # bpy_armature_object.rotation_mode = 'QUATERNION'
    return bpy_armature_object


def create_edit_bones(bone_size: float,
                      nodes: List[War3Node], bpy_armature: bpy.types.Armature):
    bpy.ops.object.mode_set(mode='EDIT')
    edit_bones: bpy.types.ArmatureEditBones = bpy_armature.edit_bones
    bone_names: Set[str] = set()
    for node in nodes:
        # print("  adding node \"%s\" (%i)" % (node.name, node.obj_id))
        if node.name in bone_names:
            for i in range(1, 999):
                temp_name = node.name + (".%03.f" % i)
                if temp_name not in bone_names:
                    node.name = temp_name
                    break
        bone = edit_bones.new(node.name)
        # Blender 会把超过 63 字节的标识符截断（UTF-8 的中文名字很容易超过，例如
        # jn_ds_t13_1.mdx 里 39 个字符的名字有 77 字节），重名时还会自动加后缀。
        # 于是 node.name 与真正的骨骼名对不上，set_parents 按 node.name 查不到骨骼
        # 就抛 'NoneType' object has no attribute 'parent'。统一以 Blender 实际给出的
        # 名字为准（顶点组、节点类型映射等下游都按 node.name 工作，保持一致）。
        if bone.name != node.name:
            print("   骨骼名 %r 被 Blender 改为 %r" % (node.name, bone.name))
            node.name = bone.name
        bone_names.add(bone.name)
        bone.head = node.pivot
        bone.tail = node.pivot
        bone.tail[2] += bone_size


def set_parents(war3_nodes: List[War3Node], bpy_armature: bpy.types.Armature):
    bpy.ops.object.mode_set(mode='EDIT')
    edit_bones: bpy.types.ArmatureEditBones = bpy_armature.edit_bones
    missing_warned = False
    for war3_node in war3_nodes:
        e_bone = edit_bones.get(war3_node.name)
        if e_bone is None:
            # 兜底：名称对不上时不能中断整个导入，跳过这根骨骼的父子关系即可。
            if not missing_warned:
                print("   节点 %r 没有对应的骨骼，跳过它的父子关系" % war3_node.name)
                missing_warned = True
            continue
        if war3_node.parent_node is not None:
            war3_par = war3_node.parent_node
            print("connecting \"%s\" (%i) to parent \"%s\" (%i)" % (war3_node.name, war3_node.obj_id,
                                                                    war3_par.name, war3_par.obj_id))
            e_parent = edit_bones.get(war3_par.name)
            e_bone.parent = e_parent
        else:
            print("no parent found for \"%s\" (%i), par: %s" % (war3_node.name, war3_node.obj_id, war3_node.parent))


def connect_bones(bpy_armature: bpy.types.Armature):
    # needs to be done after parents is set to be able to filter bones who is their parents only child
    bpy.ops.object.mode_set(mode='EDIT')
    edit_bones: List[bpy.types.EditBone] = bpy_armature.edit_bones.values()
    for e_bone in edit_bones:
        e_parent = e_bone.parent
        if e_parent is not None and len(e_parent.children) == 1:
            e_parent.tail = e_bone.head
            if len(e_bone.children) == 0 and e_parent.length < 0:
                v_dir: Vector = Vector(e_bone.head) - Vector(e_parent.head)
                e_bone.tail = e_bone.head + v_dir


def ensure_bone_length(bpy_armature: bpy.types.Armature):
    # bones with length 0 will be dissolved by blender
    bpy.ops.object.mode_set(mode='EDIT')
    edit_bones: bpy.types.ArmatureEditBones = bpy_armature.edit_bones

    tail_offset: Vector = Vector((0, 0, 0.01))  # zero_length_bone_tail_offset
    for bone in edit_bones.values():
        if bone.length < 0.001:
            bone.tail = bone.tail + tail_offset
