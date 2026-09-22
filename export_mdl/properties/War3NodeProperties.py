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

