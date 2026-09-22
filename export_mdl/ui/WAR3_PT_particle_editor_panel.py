import bpy
from bpy.types import Panel


class WAR3_PT_particle_editor_panel(Panel):
    """魔兽争霸3 粒子发射器参数。
导出时按「发射器类型」写成 ParticleEmitter / ParticleEmitter2 / RibbonEmitter 三种块之一。
粒子发射器用精灵图（spritesheet）做序列帧，所以行/列必须和贴图的实际格子数一致。"""
    bl_idname = "WAR3_PT_particle_editor_panel"
    bl_label = "MDL 粒子发射器"
    bl_region_type = 'WINDOW'
    bl_space_type = 'PROPERTIES'
    bl_context = 'particle'

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and len(context.active_object.particle_systems)

    def draw(self, context):
        layout = self.layout

        psys = context.active_object.particle_systems.active.settings.mdl_particle_sys

        row = layout.row(align=True)
        row.menu('WAR3_MT_emitter_presets', text="预设")
        row.operator('particle.emitter_preset_add', text="", icon='ADD')
        row.operator('particle.emitter_preset_add', text="", icon='REMOVE').remove_active = True

        layout.prop(psys, "emitter_type")

        if psys.emitter_type == 'ParticleEmitter':
            layout.prop(psys, "model_path")
            layout.prop(psys, "emission_rate")
            layout.prop(psys, "life_span")
            layout.prop(psys, "speed")
            layout.prop(psys, "gravity")

            layout.separator()

            layout.label(text="发射锥角")
            layout.prop(psys, "longitude")
            layout.prop(psys, "latitude")

        elif psys.emitter_type == 'RibbonEmitter':
            layout.prop_search(psys, "ribbon_material", bpy.data, "materials")
            # layout.prop(psys, "texture_path")

            row = layout.row()
            row.label(text="贴图路径")
            row.operator("object.search_texture", text="", icon='VIEWZOOM').target = 'Emitter'
            row.prop(psys, "texture_path", text="")

            layout.separator()

            layout.prop(psys, "ribbon_color")

            layout.separator()

            layout.prop(psys, "emission_rate")
            layout.prop(psys, "life_span")
            layout.prop(psys, "gravity")

            layout.label(text="精灵图行列")
            row = layout.row()
            col = row.column()
            col.label(text="行")
            col.prop(psys, "rows")
            col = row.column()
            col.label(text="列")
            col.prop(psys, "cols")
        else:
            row = layout.row()
            row.label(text="贴图路径")
            row.operator("object.search_texture", text="", icon='VIEWZOOM').target = 'Emitter'
            row.prop(psys, "texture_path", text="")

            layout.prop(psys, "filter_mode")

            layout.separator()
            layout.operator("war_3.emitter_set_from_bpy", text="按 Blender 粒子系统填充")

            layout.prop(psys, "emission_rate")
            layout.prop(psys, "speed")
            layout.prop(psys, "life_span")
            layout.prop(psys, "gravity")
            layout.prop(psys, "variation")
            layout.prop(psys, "latitude")

            if psys.tail == True:
                layout.prop(psys, "tail_length")

            layout.separator()

            layout.label(text="生命期分段")
            row = layout.row()
            box = row.box()
            box.label(text="颜色")
            box.prop(psys, "start_color")
            box.label(text="透明度")
            box.prop(psys, "start_alpha")
            box.label(text="缩放")
            box.prop(psys, "start_scale")
            box = row.box()
            box.label(text="颜色")
            box.prop(psys, "mid_color")
            box.label(text="透明度")
            box.prop(psys, "mid_alpha")
            box.label(text="缩放")
            box.prop(psys, "mid_scale")
            box = row.box()
            box.label(text="颜色")
            box.prop(psys, "end_color")
            box.label(text="透明度")
            box.prop(psys, "end_alpha")
            box.label(text="缩放")
            box.prop(psys, "end_scale")

            layout.prop(psys, "time")

            layout.separator()

            layout.label(text="精灵图行列")
            row = layout.row()
            col = row.column()
            col.label(text="行")
            col.prop(psys, "rows")
            col = row.column()
            col.label(text="列")
            col.prop(psys, "cols")

            layout.separator()

            if psys.head and psys.rows * psys.cols > 1:
                layout.label(text="头部序列帧")
                row = layout.row()
                col = row.column()
                col.label(text="出生段")
                box = col.box()
                box.label(text="起始")
                box.prop(psys, "head_life_start")
                box.label(text="结束")
                box.prop(psys, "head_life_end")
                box.label(text="重复")
                box.prop(psys, "head_life_repeat")


                col = row.column()
                col.label(text="衰减段")
                box = col.box()
                box.label(text="起始")
                box.prop(psys, "head_decay_start")
                box.label(text="结束")
                box.prop(psys, "head_decay_end")
                box.label(text="重复")
                box.prop(psys, "head_decay_repeat")
                layout.separator()

            if psys.tail and psys.rows * psys.cols > 1:
                layout.label(text="尾部序列帧")
                row = layout.row()
                col = row.column()
                col.label(text="出生段")
                box = col.box()
                box.label(text="起始")
                box.prop(psys, "tail_life_start")
                box.label(text="结束")
                box.prop(psys, "tail_life_end")
                box.label(text="重复")
                box.prop(psys, "tail_life_repeat")


                col = row.column()
                col.label(text="衰减段")
                box = col.box()
                box.label(text="起始")
                box.prop(psys, "tail_decay_start")
                box.label(text="结束")
                box.prop(psys, "tail_decay_end")
                box.label(text="重复")
                box.prop(psys, "tail_decay_repeat")

            row = layout.row()
            col = row.column()
            col.prop(psys, "unshaded")
            col.prop(psys, "unfogged")
            col.prop(psys, "line_emitter")
            col.prop(psys, "sort_far_z")
            col = row.column()
            col.prop(psys, "model_space")
            col.prop(psys, "xy_quad")
            col.prop(psys, "head")
            col.prop(psys, "tail")

