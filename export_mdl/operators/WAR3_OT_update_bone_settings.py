import bpy

from export_mdl.compat import set_node_type_collection
from export_mdl.properties.War3NodeProperties import NODE_TYPE_COLORS


class WAR3_OT_update_bone_settings(bpy.types.Operator):
    bl_idname = 'warcraft_3.update_bone_settings'
    bl_label = 'Warcraft 3 Update Bone Settings'
    bl_description = 'Warcraft 3 Update Bone Settings'
    bl_options = {'UNDO'}

    def execute(self, context):
        curr_object = context.object
        if curr_object is None or curr_object.type != 'ARMATURE':
            return {'CANCELLED'}
        for bone in curr_object.data.bones:
            nodeType = bone.warcraft_3.nodeType
            color = NODE_TYPE_COLORS.get(nodeType)
            collection_name = nodeType.lower() + 's' if color else None
            set_node_type_collection(curr_object, bone.name, collection_name, color)
        return {'FINISHED'}
