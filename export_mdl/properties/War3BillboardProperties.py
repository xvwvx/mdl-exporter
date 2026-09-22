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
