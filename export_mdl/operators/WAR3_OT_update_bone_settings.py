import bpy

from export_mdl.compat import set_node_type_collection
from export_mdl.properties.War3NodeProperties import NODE_TYPE_COLORS


class WAR3_OT_update_bone_settings(bpy.types.Operator):
    bl_idname = 'warcraft_3.update_bone_settings'
    bl_label = '刷新骨骼节点类型'
    bl_description = '按每根骨骼记录的节点类型，重建对应的骨骼集合（骨骼/辅助体/挂点/事件/碰撞体）'
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
