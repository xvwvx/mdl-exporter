from ..operators.WAR3_OT_create_eventobject import WAR3_OT_create_eventobject
from ..operators.WAR3_OT_create_collision_shape import WAR3_OT_create_collision_shape
from ..operators.WAR3_OT_add_anim_sequence import WAR3_OT_add_anim_sequence
import bpy


class VIEW_MT_war3_add(bpy.types.Menu):
    """添加魔兽争霸3模型用到的辅助物体"""
    bl_idname = "VIEW_MT_war3_add"
    bl_label = "MDL 添加"
    # bl_region_type = 'VIEW3D'

    def draw(self, context):
        layout = self.layout
        # layout.separator()
        layout.operator(WAR3_OT_create_eventobject.bl_idname)
        layout.operator(WAR3_OT_create_collision_shape.bl_idname)
        layout.operator(WAR3_OT_add_anim_sequence.bl_idname)
