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
        items=[
            ('NONE', 'None', ''),
            ('BONE', 'Bone', ''),
            ('HELPER', 'Helper', ''),
            ('ATTACHMENT', 'Attachment', ''),
            ('EVENT', 'Event', ''),
            ('COLLISION_SHAPE', 'Collision Shape', '')
            ],
        name='Node Type',
        update=set_bone_node_type,
        default='NONE'
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

