import bpy
from bpy.props import PointerProperty
from bpy.types import Panel

from ..properties import War3LightSettings


class WAR3_PT_light_panel(Panel):
    """魔兽争霸3 灯光参数。导出时会写成 Light 块；
衰减范围决定光照到多远，环境光让阴影里也有亮度。"""
    bl_idname = "WAR3_PT_light_panel"
    bl_label = "MDL 灯光设置"
    bl_region_type = 'WINDOW'
    bl_space_type = 'PROPERTIES'
    bl_context = 'data'

    @classmethod
    def register(cls):
        bpy.types.Light.mdl_light = PointerProperty(type=War3LightSettings.War3LightSettings)

    @classmethod
    def unregister(cls):
        del bpy.types.Light.mdl_light

    @classmethod
    def poll(self,context):
        obj = context.active_object
        return obj is not None and obj.type in ('LAMP', 'LIGHT')

    def draw(self, context):
        layout = self.layout
        data = context.active_object.data.mdl_light

        layout.prop(data, "light_type")
        layout.prop(data, "atten_start")
        layout.prop(data, "atten_end")
        if data.light_type != 'Ambient':
            layout.prop(data, "color")
            layout.prop(data, "intensity")
        else:
            layout.prop(data, "amb_color")
            layout.prop(data, "amb_intensity")
