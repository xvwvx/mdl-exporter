from bpy.props import EnumProperty, FloatProperty, FloatVectorProperty
from bpy.types import PropertyGroup


class War3LightSettings(PropertyGroup):
    light_type: EnumProperty(
        name="灯光类型",
        description="决定导出成哪种灯光块：全向灯向四周照，方向灯像太阳一样平行照射，"
                    "环境灯只提供整体环境亮度",
        items=[('Omnidirectional', "全向灯", "向四周均匀照射"),
               ('Directional', "方向灯", "像太阳一样平行照射"),
               ('Ambient', "环境灯", "只提供整体环境亮度")],
        default='Omnidirectional'
        )

    atten_start: FloatProperty(
        name="衰减起点",
        description="亮度开始减弱的位置（距离灯光的距离）。"
                    "起点之内是满亮度，之后逐渐变暗",
        min=0,
        default=80
        )

    atten_end: FloatProperty(
        name="衰减终点",
        description="亮度衰减到 0 的位置，也就是灯光的最大照射范围",
        min=0,
        default=200
        )

    intensity: FloatProperty(
        name="亮度",
        description="灯光的强度。数值越大越亮，魔兽争霸3 里常用 1～50",
        min=0,
        default=10,
        )

    amb_intensity: FloatProperty(
        name="环境光亮度",
        description="灯光附加的环境亮度：即使处于阴影中也能看到的亮度",
        min=0,
        default=0
        )
    color: FloatVectorProperty(
        name="颜色",
        description="灯光本身的颜色",
        subtype='COLOR',
        default=[1.0, 1.0, 1.0],
        )

    amb_color: FloatVectorProperty(
        name="环境光颜色",
        description="环境光部分的颜色，与环境光亮度配合使用",
        subtype='COLOR',
        default=[1.0, 1.0, 1.0],
        )
