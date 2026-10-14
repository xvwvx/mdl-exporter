import bpy

from export_mdl.compat import set_node_type_collection

# Bone collection / pose bone group name and palette colour per node type.
NODE_TYPE_COLORS = {
    'BONE': 'THEME04',
    'ATTACHMENT': 'THEME09',
    'COLLISION_SHAPE': 'THEME02',
    'EVENT': 'THEME03',
    'HELPER': 'THEME01',
}


def set_bone_node_type(self, context):
    bone = context.active_bone
    if not bone:
        return
    node_type = bone.warcraft_3.nodeType
    bpy_object = context.object
    if bpy_object is None or bpy_object.type != 'ARMATURE':
        return
    color = NODE_TYPE_COLORS.get(node_type)
    collection_name = node_type.lower() + 's' if color else None
    set_node_type_collection(bpy_object, bone.name, collection_name, color)


NODE_TYPE_BONE = 'BONE'
NODE_TYPE_HELPER = 'HELPER'
NODE_TYPE_ATTACHMENT = 'ATTACHMENT'
NODE_TYPE_EVENT = 'EVENT'
NODE_TYPE_COLLISION_SHAPE = 'COLLISION_SHAPE'
NODE_TYPE_NONE = 'NONE'


class War3NodeProperties(bpy.types.PropertyGroup):
    bpy_type = bpy.types.Bone
    nodeType: bpy.props.EnumProperty(
        description="这个节点原本是哪种魔兽争霸3节点。导入时自动记录，"
                    "导出时据此还原成 Bone / Helper / Attachment 等对应的块，"
                    "所以一般不用手动改。",
        items=[
            ('NONE', '未标记', '不是魔兽争霸3节点，或由灯光/发射器另行处理'),
            ('BONE', '骨骼', '参与蒙皮的骨骼'),
            ('HELPER', '辅助体', '不参与蒙皮，只用来定位'),
            ('ATTACHMENT', '挂点', '武器/特效的附着点'),
            ('EVENT', '事件', '触发音效、脚印等'),
            ('COLLISION_SHAPE', '碰撞体', '点击判定用的碰撞形状')
            ],
        name='节点类型',
        update=set_bone_node_type,
        default='NONE'
        )
    nodeFlags: bpy.props.IntProperty(
        description="这个节点在 MDX 里的原始标志位（MdxNodeFlags）。"
                    "导入时自动记录 Billboarded、锁轴、DontInherit*、CameraAnchored "
                    "等信息，导出时据此还原，一般不用手动改。",
        name='节点标志位',
        default=0
        )

    @classmethod
    def register(cls):
        bpy.types.Bone.warcraft_3 = bpy.props.PointerProperty(
            type=War3NodeProperties, options={'HIDDEN'})

    @classmethod
    def unregister(cls):
        del bpy.types.Bone.warcraft_3


def get_node_type(bone) -> str:
    """The recorded War3 node type of a Bone, or 'NONE' when not set."""
    properties = getattr(bone, "warcraft_3", None)
    if properties is None:
        return NODE_TYPE_NONE
    return properties.nodeType


def set_node_type(bone, node_type: str) -> None:
    properties = getattr(bone, "warcraft_3", None)
    if properties is not None:
        properties.nodeType = node_type


def get_node_flags(bone) -> int:
    """骨骼上记录的 MdxNodeFlags（未记录时为 0）。"""
    properties = getattr(bone, "warcraft_3", None)
    if properties is None:
        return 0
    return int(properties.nodeFlags)


def set_node_flags(bone, flags: int) -> None:
    properties = getattr(bone, "warcraft_3", None)
    if properties is not None:
        properties.nodeFlags = int(flags)


# Custom property marking a node *object* (an empty, light or emitter mesh) with
# the War3 chunk it stands for.  The exporter used to guess this from the object
# name -- which forced the importer to rename attachments to "<name> Ref" and
# helpers to "Bone_<name>" -- so the name is now left alone and the type is
# recorded here instead.
OBJECT_NODE_TYPE_PROPERTY = 'mdl_node_type'


def set_object_node_type(bpy_object, node_type: str) -> None:
    bpy_object[OBJECT_NODE_TYPE_PROPERTY] = node_type


def get_object_node_type(bpy_object) -> str:
    return bpy_object.get(OBJECT_NODE_TYPE_PROPERTY, '')

