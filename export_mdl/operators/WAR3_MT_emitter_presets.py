from bpy.types import Menu


class WAR3_MT_emitter_presets(Menu):
    bl_label = "发射器预设"
    preset_subdir = "mdl_exporter/emitters"
    preset_operator = "script.execute_preset"
    draw = Menu.draw_preset
