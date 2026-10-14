from bpy.props import BoolProperty
from bpy.types import PropertyGroup


class War3BillboardProperties(PropertyGroup):
    billboarded: BoolProperty(
        name="始终面向镜头",
        description="开启后，该节点在游戏里永远正对镜头（广告牌效果）。"
                    "常用于粒子、光晕、血条挂点这类平面贴图",
        default=False
        )
    billboard_lock_x: BoolProperty(
        name="锁定 X 轴",
        description="只允许绕 X 轴转动，另外两个轴保持固定。"
                    "例如只想让贴图随镜头左右转、但始终保持竖直时勾选",
        default=False,
        )
    billboard_lock_y: BoolProperty(
        name="锁定 Y 轴",
        description="只允许绕 Y 轴转动，另外两个轴保持固定",
        default=False
        )
    billboard_lock_z: BoolProperty(
        name="锁定 Z 轴",
        description="只允许绕 Z 轴转动，另外两个轴保持固定。"
                    "常用于让地面上的贴花只随镜头水平旋转",
        default=False
        )
    dont_inherit_translation: BoolProperty(
        name="不继承平移",
        description="开启后父节点的位移不会带着该节点一起动，"
                    "相当于魔兽3节点标志里的 DontInheritTranslation",
        default=False
        )
    dont_inherit_rotation: BoolProperty(
        name="不继承旋转",
        description="开启后父节点的旋转不会带着该节点一起转，"
                    "相当于魔兽3节点标志里的 DontInheritRotation",
        default=False
        )
    dont_inherit_scaling: BoolProperty(
        name="不继承缩放",
        description="开启后父节点的缩放不会影响该节点，"
                    "相当于魔兽3节点标志里的 DontInheritScaling",
        default=False
        )
    camera_anchored: BoolProperty(
        name="锚定到镜头",
        description="让节点的位置跟随当前镜头（过场动画里的定位点常用），"
                    "相当于魔兽3节点标志里的 CameraAnchored",
        default=False
        )
