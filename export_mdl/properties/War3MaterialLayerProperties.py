import bpy
from bpy.props import StringProperty, EnumProperty, IntProperty, BoolProperty, FloatProperty, CollectionProperty
from bpy.types import PropertyGroup


class War3MaterialLayerProperties(PropertyGroup):
    # bpy_type = bpy.types.Material
    name: StringProperty(
        name="图层名",
        description="图层的显示名，本身不写进导出文件。但导出时会拿这个名字去材质节点树里"
                    "找同名的 UV Mapping 节点（贴图动画挂在那上面），所以改名后要同步改节点名。",
        default="Layer",
        maxlen=16
        )

    texture_type: EnumProperty(
        name="贴图类型",
        description="这一层用哪张图。「图片」是普通贴图文件；选「队伍颜色」「队伍光晕」"
                    "这类可替换贴图时，游戏会按玩家颜色自动换成对应贴图。",
        items=[('0', "图片", "使用贴图文件", 0, 0),
               ('1', "队伍颜色", "按玩家颜色替换", 0, 1),
               ('2', "队伍光晕", "按玩家颜色替换（发光）", 0, 2),
               ('11', "峭壁", "", 0, 11),
               ('31', "洛丹伦树木", "", 0, 31),
               ('32', "灰谷树木", "", 0, 32),
               ('33', "贫瘠之地树木", "", 0, 33),
               ('34', "诺森德树木", "", 0, 34),
               ('35', "蘑菇树", "", 0, 35),
               ('36', "可替换贴图 ID", "用下面的 ID 指定任意可替换贴图", 0, 36)],
        default='0'
        )

    replaceable_id: IntProperty(
        name="可替换贴图 ID",
        description="可替换贴图的编号：1 是队伍颜色、2 是队伍光晕，其余编号对应游戏内建的"
                    "可替换贴图（树木、峭壁等）。",
        default=100,
        min=0
        )

    filter_mode: EnumProperty(
        name="过滤模式",
        description="这一层的混合方式，决定它和下层怎么叠加。不透明的用「不透明」，"
                    "带透明通道的用「混合」，火焰光效用「叠加」。",
        items=[('None', "不透明", "直接覆盖，不混合"),
               ('Blend', "混合", "按透明度混合"),
               ('Transparent', "透明", ""),
               ('Additive', "叠加", "亮度相加，用于火焰光效"),
               ('AddAlpha', "叠加（带透明度）", ""),
               ('Modulate', "正片叠底", ""),
               ('Modulate2x', "正片叠底 2 倍", "")],
        default='None'
        )

    unshaded: BoolProperty(
        name="不受光",
        description="开启后这一层不参与光照计算，始终按贴图原色显示。特效贴图一般都要开。",
        default=False
        )

    two_sided: BoolProperty(
        name="双面",
        description="开启后正反两面都渲染。布料、树叶、旗帜这类单面片模型必须开，"
                    "否则从背面看不见。",
        default=False
        )

    no_depth_test: BoolProperty(
        name="不参与深度测试",
        description="开启后这一层永远画在最上面，即使被别的物体挡住也可见。用于描边、光晕。",
        default=False
        )

    no_depth_set: BoolProperty(
        name="不写入深度",
        description="开启后这一层不会遮挡后面才画的物体。常用于半透明特效，"
                    "避免把身后的东西挖掉。",
        default=False
        )

    alpha: FloatProperty(
        name="透明度",
        description="整体透明度，只在「混合」「透明」「叠加（带透明度）」模式下生效，"
                    "可以做关键帧动画。",
        default=1.0,
        options={'ANIMATABLE'},
        min=0.0,
        max=1.0
        )
    path: StringProperty(
        name="贴图路径",
        description="相对于魔兽争霸根目录的贴图路径，例如 Textures\\Foo.blp。"
                    "正斜杠反斜杠都行。",
        default="",
        maxlen=256
        )

    @classmethod
    def register(cls):
        bpy.types.Material.mdl_layers = CollectionProperty(type=War3MaterialLayerProperties, options={'HIDDEN'})
        # bpy.types.Material.mdl_layers: CollectionProperty = CollectionProperty(type=War3MaterialLayerProperties, options={'HIDDEN'})
        # bpy.types.Material.mdl_layers
        bpy.types.Material.mdl_layer_index = IntProperty(name="图层索引", description="", default=0, options={'HIDDEN'})
        bpy.types.Material.priority_plane = IntProperty(name="优先级平面",
                      description="材质之间的绘制顺序：数值大的画在上面。用于控制叠加层次",
                      default=0, options={'HIDDEN'})

    @classmethod
    def unregister(cls):
        del bpy.types.Material.mdl_layers
        del bpy.types.Material.mdl_layer_index
        del bpy.types.Material.priority_plane
