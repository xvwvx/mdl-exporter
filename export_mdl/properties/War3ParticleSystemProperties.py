import bpy
from bpy.props import EnumProperty, BoolProperty, IntProperty, FloatProperty, FloatVectorProperty, PointerProperty, \
    StringProperty
from bpy.types import PropertyGroup


class War3ParticleSystemProperties(PropertyGroup):

    emitter_type: EnumProperty(
        name="发射器类型",
        description="决定导出成哪种发射器块。\n"
                    "模型发射器：直接发射另一个 .mdx 模型；\n"
                    "粒子发射器：用精灵图（序列帧）发粒子，最常用；\n"
                    "飘带发射器：拖出一条连续的带子，用于轨迹、拖尾。",
        items=[('ParticleEmitter', "模型发射器", "发射另一个模型文件"),
               ('ParticleEmitter2', "粒子发射器", "用精灵图发粒子，最常用"),
               ('RibbonEmitter', "飘带发射器", "连续带子，用于轨迹拖尾")],
        default='ParticleEmitter2'
        )

    filter_mode: EnumProperty(
        name="过滤模式",
        description="粒子贴图的混合方式。烟、尘用「混合」，火、魔法光效用「叠加」。",
        items=[('None', "不透明", "直接覆盖"),
               ('Blend', "混合", "按透明度混合"),
               ('Transparent', "透明", ""),
               ('Additive', "叠加", "亮度相加，用于火焰光效"),
               ('AddAlpha', "叠加（带透明度）", ""),
               ('Modulate', "正片叠底", ""),
               ('Modulate2x', "正片叠底 2 倍", "")],
        default='Blend'
        )

    unshaded: BoolProperty(
        name="不受光",
        description="开启后粒子不参与光照，始终按贴图原色显示。特效基本都要开。",
        default=False
        )

    unfogged: BoolProperty(
        name="不受雾",
        description="开启后粒子不会被地图雾气影响。远处的特效想保持清晰就开。",
        default=False
        )

    line_emitter: BoolProperty(
        name="线发射",
        description="开启后粒子只在一个平面内运动（而不是一个锥体）。",
        default=False
        )

    sort_far_z: BoolProperty(
        name="按远近排序",
        description="开启后粒子按离镜头的远近决定绘制顺序，避免半透明粒子互相遮挡出错。",
        default=False
        )

    model_space: BoolProperty(
        name="跟随模型空间",
        description="开启后粒子跟随父节点移动（例如跟着武器走）；关闭则发射后留在原地。",
        default=False
        )

    xy_quad: BoolProperty(
        name="水平面片",
        description="开启后粒子是朝上的平面片。用于地面上的光圈、贴花。",
        default=False
        )

    head: BoolProperty(
        name="头部",
        description="是否绘制粒子的头部（通常就是粒子本体）。",
        default=True
        )

    tail: BoolProperty(
        name="尾部",
        description="是否绘制拖尾。拖尾会沿运动方向拉伸，用于火焰、流星。",
        default=False
        )

    emission_rate: FloatProperty(
        name="发射速率",
        description="每秒发射多少个粒子。数值越大越浓密。",
        options={'ANIMATABLE'},
        min=0,
        default=100
        )
    speed: FloatProperty(
        name="速度",
        description="粒子初速度。数值越大飞得越快越远。",
        options={'ANIMATABLE'},
        default=100
        )

    latitude: FloatProperty(
        name="纬度",
        description="粒子偏离发射轴的最大角度（0～180 度）。数值越大喷射越散。",
        options={'ANIMATABLE'},
        # subtype='ANGLE',
        # unit='ROTATION',
        min=0,
        max=180,
        default=0
        )

    longitude: FloatProperty(
        name="经度",
        description="发射锥在水平方向上的张角。",
        default=0
        )

    variation: FloatProperty(
        name="速度变化",
        description="粒子速度的随机浮动比例。0.2 表示速度在基准值上下浮动 20%，让粒子看起来更自然。",
        options={'ANIMATABLE'},
        default=0,
        min=0
        )

    gravity: FloatProperty(
        name="重力",
        description="每秒施加给粒子的向下速度，可以为负（向上飘）。0 表示不受重力。",
        options={'ANIMATABLE'},
        default=0
        )

    start_color: FloatVectorProperty(
        name="",
        description="粒子刚出生时的颜色。",
        subtype='COLOR',
        default=(1.0, 1.0, 1.0)
        )

    mid_color: FloatVectorProperty(
        name="",
        description="粒子存活到中间时刻的颜色。",
        subtype='COLOR',
        default=(1.0, 1.0, 1.0)
        )

    end_color: FloatVectorProperty(
        name="",
        description="粒子即将消失时的颜色。",
        subtype='COLOR',
        default=(1.0, 1.0, 1.0)
        )

    start_alpha: IntProperty(
        name="起始透明度",
        min=0,
        max=255,
        default=255
        )

    mid_alpha: IntProperty(
        name="中间透明度",
        min=0,
        max=255,
        default=255
        )

    end_alpha: IntProperty(
        name="结束透明度",
        min=0,
        max=255,
        default=255
        )

    start_scale: FloatProperty(
        name="起始大小",
        min=0,
        default=1
        )

    mid_scale: FloatProperty(
        name="中间大小",
        min=0,
        default=1
        )

    end_scale: FloatProperty(
        name="结束大小",
        min=0,
        default=1
        )

    rows: IntProperty(
        name="行数",
        min=1,
        default=1
    )

    cols: IntProperty(
        name="列数",
        min=1,
        default=1
    )

    life_span: FloatProperty(
        name="生命周期",
        description="每个粒子存活多少秒。",
        subtype='TIME',
        unit='TIME',
        min=0.0,
        default=1.0
        )

    tail_length: FloatProperty(
        name="拖尾长度",
        description="拖尾长度相对粒子宽度的倍数。",
        min=0
        )

    time: FloatProperty(
        name="过渡时间",
        description="从「起始」渐变到「中间」所占的比例（0～1）。剩下的时间用于渐变到「结束」。",
        min=0.0,
        max=1.0,
        default=0.5
        )

    priority_plane: IntProperty(
        name="优先级",
        description="数值大的粒子画在数值小的上面。用于控制不同特效的叠加顺序。",
        default=0
    )

    ribbon_material: PointerProperty(
        name="飘带材质",
        description="飘带使用的材质，决定贴图和混合方式。",
        type=bpy.types.Material
        )

    ribbon_color: FloatVectorProperty(
        name="飘带颜色",
        subtype='COLOR',
        default=[1.0, 1.0, 1.0]
        )

    texture_path: StringProperty(
        name="贴图路径",
        description="粒子贴图的路径（相对于魔兽争霸根目录），例如 Textures\\\\Smoke.blp。",
        default="",
        maxlen=256
        )

    model_path: StringProperty(
        name="模型路径",
        description="「模型发射器」要发射的 .mdx 模型路径（相对于魔兽争霸根目录）。",
        default="",
        maxlen=100
        )

    head_life_start: IntProperty(
        name="头部·出生·起始格",
        default=0
        )

    head_life_end: IntProperty(
        name="头部·出生·结束格",
        default=0
        )

    head_life_repeat: IntProperty(
        name="头部·出生·循环次数",
        default=1
        )

    head_decay_start: IntProperty(
        name="头部·衰减·起始格",
        default=0
        )

    head_decay_end: IntProperty(
        name="头部·衰减·结束格",
        default=0
        )

    head_decay_repeat: IntProperty(
        name="头部·衰减·循环次数",
        default=1
        )

    tail_life_start: IntProperty(
        name="尾部·出生·起始格",
        default=0
        )

    tail_life_end: IntProperty(
        name="尾部·出生·结束格",
        default=0
        )

    tail_life_repeat: IntProperty(
        name="尾部·出生·循环次数",
        default=1
        )

    tail_decay_start: IntProperty(
        name="尾部·衰减·起始格",
        default=0
        )

    tail_decay_end: IntProperty(
        name="尾部·衰减·结束格",
        default=0
        )

    tail_decay_repeat: IntProperty(
        name="尾部·衰减·循环次数",
        default=1
        )

    alpha: FloatProperty(
        name="透明度",
        description="飘带整体透明度。",
        default=1.0
        )

    @classmethod
    def register(cls):
        bpy.types.ParticleSettings.mdl_particle_sys = PointerProperty(type=War3ParticleSystemProperties)

    @classmethod
    def unregister(cls):
        del bpy.types.ParticleSettings.mdl_particle_sys
