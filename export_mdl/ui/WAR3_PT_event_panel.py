import bpy
from bpy.types import Panel

from ..properties import War3EventProperties


class WAR3_PT_event_panel(Panel):
    """事件物体：在动画播放到某一帧时让游戏触发效果（放音效、留脚印、生成单位、地面贴花）。
物体名必须保持「类型+序号+事件ID」的形式，导出时靠这个名字识别。"""
    bl_idname = "WAR3_PT_event_panel"
    bl_label = "事件物体"
    bl_region_type = 'WINDOW'
    bl_space_type = 'PROPERTIES'
    bl_context = 'object'

    @classmethod
    def register(cls):
        bpy.types.WindowManager.events = bpy.props.PointerProperty(type=War3EventProperties.War3EventProperties)

    @classmethod
    def unregister(cls):
        del bpy.types.WindowManager.events

    @classmethod
    def poll(cls, context):
        obj = context.active_object

        if obj is None or obj.get('event_type') is None:
            return False

        if obj is not None:
            events = context.window_manager.events
            if events.event_type != obj['event_type']:
                events.event_type = obj['event_type']

            if events.event_id != obj['event_id']:
                events.event_id = obj['event_id']

        return True

    def draw(self, context):
        layout = self.layout

        events = context.window_manager.events

        row = layout.row()
        row.label(text="事件类型")
        op = row.operator("object.search_event_type", text="", icon='VIEWZOOM')
        row.prop(events, "event_type", text="")

        layout.separator()

        row = layout.row()
        row.label(text="事件ID")
        op = row.operator("object.search_eventid", text="", icon='VIEWZOOM')
        row.prop(events, "event_id", text="")
