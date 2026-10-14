"""把解析出来的魔兽3节点标志写回 Blender 宿主对象。

导入端以前只把 billboarded / billboard_lock 解析到 War3Node 上，从不写回
宿主：挂点/事件/碰撞体/灯光/发射器该写 ``Object.mdl_billboard``，helper 与骨骼
该写 armature 骨骼的 nodeFlags（见 create_armature_object.record_node_types）。
导出端（BpyEmptyNode / BpyEmitter / BpyLight 与 make_bones.get_wc3_bone）
只从宿主读，所以这些标志过去永远是 False，再导出时
Billboarded / BillboardedLock* / DontInherit* / CameraAnchored 被静默删除。
"""

from typing import Any

import bpy

from ..classes.War3Node import War3Node
from .. import node_flags


def apply_node_flags(bpy_object: bpy.types.Object, node: War3Node) -> None:
    """把 node 上的节点标志写到对象宿主的 mdl_billboard 属性组里。

    属性组由 ui/WAR3_PT_billboard_panel.py:24 注册到 Object 上；面板未加载时
    getattr 返回 None，此时什么也不做。
    """
    billboard: Any = getattr(bpy_object, "mdl_billboard", None)
    if billboard is None:
        return

    billboard.billboarded = bool(getattr(node, "billboarded", False))

    lock = getattr(node, "billboard_lock", node_flags.FALSE_LOCK)
    billboard.billboard_lock_z = bool(lock[0])
    billboard.billboard_lock_y = bool(lock[1])
    billboard.billboard_lock_x = bool(lock[2])

    inherit = getattr(node, "dont_inherit", node_flags.FALSE_INHERIT)
    billboard.dont_inherit_translation = bool(inherit[0])
    billboard.dont_inherit_rotation = bool(inherit[1])
    billboard.dont_inherit_scaling = bool(inherit[2])

    billboard.camera_anchored = bool(getattr(node, "camera_anchored", False))
