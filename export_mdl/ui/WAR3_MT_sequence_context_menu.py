
import bpy

from ..operators.WAR3_OT_generate_from_actions import WAR3_OT_generate_from_actions


class WAR3_MT_sequence_context_menu(bpy.types.Menu):
    """序列的批量操作：排序、复制、删除、调整顺序"""
    bl_idname = "WAR3_MT_sequence_context_menu"
    bl_label = "序列操作"
    # bl_region_type = 'VIEW3D'

    def draw(self, context):
        layout = self.layout

        print("layout.direction", layout.direction)
        print("layout.alignment", layout.alignment)
        print("layout.use_property_decorate", layout.use_property_decorate)

        layout.operator(WAR3_OT_generate_from_actions.bl_idname)
        layout.operator('war_3.add_sequence_to_armature', icon='SORTALPHA', text="按名称排序")
        layout.operator('war_3.add_sequence_to_armature', icon='ADD', text="新建序列")
        layout.operator('war_3.add_sequence_to_armature', icon='DUPLICATE', text="复制序列")
        layout.operator('war_3.remove_sequence_from_armature', icon='REMOVE', text="移除（保留动作）").type = 'REMOVE'
        layout.operator('war_3.remove_sequence_from_armature', icon='TRASH', text="移除（连同动作一起删除）").type = 'DELETE'

        layout.separator()

        layout.operator('war_3.move_seq_in_list', icon='TRIA_UP_BAR', text="移到最前").direction = 'FIRST'
        layout.operator('war_3.move_seq_in_list', icon='TRIA_UP', text="上移").direction = 'UP'
        layout.operator('war_3.move_seq_in_list', icon='TRIA_DOWN', text="下移").direction = 'DOWN'
        layout.operator('war_3.move_seq_in_list', icon='TRIA_DOWN_BAR', text="移到最后").direction = 'LAST'

