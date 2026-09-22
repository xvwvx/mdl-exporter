import os

import bpy
from bpy_extras import io_utils

from export_mdl import constants
from export_mdl.import_stuff.MDXImportProperties import MDXImportProperties
from export_mdl.import_stuff.mdl_parser.load_mdl import load_mdl
from export_mdl.import_stuff.mdx_parser.load_mdx import load_mdx


def set_team_color_property(operator, something):
    operator.teamColor = constants.TEAM_COLORS[operator.setTeamColor]


class WAR3_OT_import_mdlx(bpy.types.Operator, io_utils.ImportHelper):
    """导入魔兽争霸3 的 .mdl / .mdx 模型：骨骼、动画序列、材质图层、"""
    """粒子发射器、飘带、相机、挂点与碰撞体都会一并导入。"""
    bl_idname = 'import.mdl_exporter'
    # bl_idname = 'warcraft_3.import_mdl_mdx'
    bl_label = '导入 *.mdl/*.mdx'
    bl_description = '导入魔兽争霸3 的 .mdl / .mdx 三维模型'
    bl_options = {'UNDO'}

    filename_ext = ['.mdx', '.mdl']
    filter_glob: bpy.props.StringProperty(default='*.mdx;*.mdl', options={'HIDDEN'})
    filepath: bpy.props.StringProperty(name='文件路径', maxlen=1024, default='')
    useCustomFPS: bpy.props.BoolProperty(
        name='自定义帧率',
        description='不按当前场景帧率换算动画，改用下面填的帧率。'
                    '模型里的动画时间戳是毫秒，帧率决定换算成第几帧',
        default=False)
    animationFPS: bpy.props.FloatProperty(
        name='动画帧率',
        description='换算动画时间戳时使用的帧率，魔兽争霸3 模型一般按 30 帧制作',
        default=30.0, min=1.0, max=1000.0)
    boneSize: bpy.props.FloatProperty(
        name='骨骼显示大小',
        description='导入后骨骼在视图里的显示长度。只影响观察，不影响导出结果',
        default=5.0, min=0.0001, max=1000.0)
    teamColor: bpy.props.FloatVectorProperty(
        name='队伍颜色',
        description='可替换贴图（队伍颜色/光晕）用哪种玩家颜色显示',
        default=constants.TEAM_COLORS['RED'],
        min=0.0,
        max=1.0,
        size=3,
        subtype='COLOR',
        precision=3
        )
    setTeamColor: bpy.props.EnumProperty(
        items=[
            ('RED', '红', ''),
            ('DARK_BLUE', '深蓝', ''),
            ('TURQUOISE', '青绿', ''),
            ('VIOLET', '紫罗兰', ''),
            ('YELLOW', '黄', ''),
            ('ORANGE', '橙', ''),
            ('GREEN', '绿', ''),
            ('PINK', '粉', ''),
            ('GREY', '灰', ''),
            ('BLUE', '蓝', ''),
            ('DARK_GREEN', '深绿', ''),
            ('BROWN', '棕', ''),
            ('BLACK', '黑', '')
            ],
        name='设置队伍颜色',
        update=set_team_color_property,
        default='RED'
        )

    def draw(self, context):
        layout = self.layout
        split = layout.split(factor=0.9)
        sub_split = split.split(factor=0.5)
        sub_split.label(text="队伍颜色：")
        sub_split.prop(self, 'setTeamColor', text="")
        split.prop(self, 'teamColor', text="")
        layout.prop(self, 'boneSize')
        layout.prop(self, 'useCustomFPS')
        if self.useCustomFPS:
            layout.prop(self, 'animationFPS')

    def execute(self, context):
        import_properties = MDXImportProperties()
        import_properties.mdx_file_path = self.filepath
        import_properties.team_color = self.setTeamColor
        import_properties.bone_size = self.boneSize
        import_properties.use_custom_fps = self.useCustomFPS
        import_properties.fps = self.animationFPS
        import_properties.calculate_frame_time()
        constants.os_path_separator = os.path
        if ".mdl" in self.filepath:
            load_mdl(import_properties)
        else:
            load_mdx(import_properties)
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
