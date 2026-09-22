import bpy
from bpy.props import StringProperty, BoolProperty, FloatProperty
from bpy.types import Operator
from bpy_extras.io_utils import orientation_helper, ExportHelper, axis_conversion
from mathutils import Matrix

from ..classes.War3ExportSettings import War3ExportSettings


@orientation_helper(axis_forward='Y', axis_up='Z')
class WAR3_OT_export_mdl(Operator, ExportHelper):
    """导出为魔兽争霸3 的 .mdl 文本模型。
贴图路径按魔兽争霸根目录的相对路径写出；模型建议按单位尺寸制作、Z 轴朝上。"""
    bl_idname = 'export.mdl_exporter'
    bl_description = '魔兽争霸3 MDL 导出器'
    bl_label = '导出 .MDL'
    filename_ext = ".mdl"

    filter_glob: StringProperty(
            default="*.mdl", options={'HIDDEN'}
            )

    filepath: StringProperty(
            subtype="FILE_PATH"
            )

    use_selection: BoolProperty(
            name="仅导出选中物体",
            description="只导出当前选中且在可见集合里的物体；不勾选则导出整个场景",
            default=False,
            )

    global_scale: FloatProperty(
            name="缩放",
            min=0.01,
            max=1000.0,
            default=1,
            )

    optimize_animation: BoolProperty(
            name="优化关键帧",
            description="删掉多余关键帧：如果去掉后动作偏差仍小于下面的容差就删掉它，"
                        "可以显著减小文件体积"
            )

    demote_to_helper: BoolProperty(
            name="未使用的骨骼转为辅助体",
            description="没有任何网格蒙皮到它上面的骨骼，导出成辅助体（Helper）而不是骨骼，"
                        "可以减少骨骼数量。从文件导入的模型会记录原始类型，不受此项影响",
            default=True
            )

    use_actions: BoolProperty(
            name="使用 Blender 动作",
            description="用 Blender 的动作（Action）作为动画序列，而不是用时间轴标记。"
                        "实验性功能，暂不支持稀有度与不循环"
            )

    use_skinweights: BoolProperty(
            name="使用蒙皮权重",
            description="按蒙皮权重导出（每个顶点最多 4 根骨骼），而不是只写顶点组。"
                        "需要魔兽争霸3 1.32+ 或重制版才支持"
            )

    optimize_tolerance: FloatProperty(
            name="容差",
            min=0.001,
            soft_max=0.1,
            default=0.05,
            subtype='DISTANCE',
            unit='LENGTH'
            )

    def execute(self, context: bpy.types.Context):
        filepath = self.filepath
        filepath = bpy.path.ensure_ext(filepath, self.filename_ext)

        settings: War3ExportSettings = War3ExportSettings()
        settings.global_matrix = axis_conversion(
            to_forward=self.axis_forward,
            to_up=self.axis_up,
        ).to_4x4() @ Matrix.Scale(self.global_scale, 4)

        settings.scale = self.global_scale
        settings.use_selection = self.use_selection
        settings.optimize_animation = self.optimize_animation
        settings.demote_to_helper = self.demote_to_helper
        settings.optimize_tolerance = self.optimize_tolerance
        settings.use_actions = self.use_actions
        settings.use_skinweights = self.use_skinweights

        from ..export_mdl import export_mdl
        export_mdl.save(self, context, settings, filepath=filepath, mdl_version=800)

        return {'FINISHED'}

    def draw(self, context: bpy.types.Context):
        layout = self.layout

        layout.prop(self, "use_selection")
        layout.prop(self, "global_scale")
        layout.prop(self, "axis_forward")
        layout.prop(self, "axis_up")
        layout.separator()
        layout.prop(self, 'optimize_animation')
        layout.prop(self, 'demote_to_helper')
        layout.prop(self, 'use_actions')
        layout.prop(self, 'use_skinweights')
        if self.optimize_animation:
            box = layout.box()
            box.label(text="实验性功能", icon='ERROR')
            layout.prop(self, 'optimize_tolerance')
        if self.use_actions:
            box = layout.box()
            box.label(text="实验性功能", icon='ERROR')
            box.label(text="将按 Blender 动作导出，而不是按时间轴标记。"
                           "暂不支持稀有度与不循环")
        if self.use_skinweights:
            box = layout.box()
            box.label(text="实验性功能", icon='ERROR')
            box.label(text="将按蒙皮权重导出，顶点组会留空。")
            # layout.prop(self, 'use_actions')
