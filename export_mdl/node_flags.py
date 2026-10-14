"""魔兽争霸3 节点标志位（MdxNodeFlags，A MdxModel.cs:63-87）与宿主表示的互转。

二进制解析（mdx_parser/parse_node.py）、导入端回写宿主
（import_stuff/apply_node_flags.py）和导出端读回（model_utils/make_bones.py）
都走这里，避免位定义散落多处后互相对不上。
"""

from typing import Tuple

from . import constants

BillboardLock = Tuple[bool, bool, bool]
DontInherit = Tuple[bool, bool, bool]

# billboard_lock 的顺序是 (Z, Y, X)，与 write_billboard 里
# zip(billboard_lock, ('Z', 'Y', 'X')) 的写法对应。
FALSE_LOCK: BillboardLock = (False, False, False)
# dont_inherit 的顺序是 (Translation, Rotation, Scaling)，与 MDL 关键字的
# 自然顺序一致。
FALSE_INHERIT: DontInherit = (False, False, False)


def flags_to_state(flags: int):
    """把原始 flags 拆成 (billboarded, billboard_lock, dont_inherit, camera_anchored)。"""
    billboarded = (flags & constants.NODE_FLAG_BILLBOARDED) != 0
    billboard_lock: BillboardLock = (
        (flags & constants.NODE_FLAG_BILLBOARDED_LOCK_Z) != 0,
        (flags & constants.NODE_FLAG_BILLBOARDED_LOCK_Y) != 0,
        (flags & constants.NODE_FLAG_BILLBOARDED_LOCK_X) != 0,
    )
    dont_inherit: DontInherit = (
        (flags & constants.NODE_FLAG_DONT_INHERIT_TRANSLATION) != 0,
        (flags & constants.NODE_FLAG_DONT_INHERIT_ROTATION) != 0,
        (flags & constants.NODE_FLAG_DONT_INHERIT_SCALING) != 0,
    )
    camera_anchored = (flags & constants.NODE_FLAG_CAMERA_ANCHORED) != 0
    return billboarded, billboard_lock, dont_inherit, camera_anchored


def state_to_flags(billboarded: bool,
                   billboard_lock: BillboardLock = FALSE_LOCK,
                   dont_inherit: DontInherit = FALSE_INHERIT,
                   camera_anchored: bool = False) -> int:
    """宿主字段 → flags。只覆盖节点自身携带的位，不含类型位（Bone/Attachment 等）。"""
    flags = 0
    if dont_inherit[0]:
        flags |= constants.NODE_FLAG_DONT_INHERIT_TRANSLATION
    if dont_inherit[1]:
        flags |= constants.NODE_FLAG_DONT_INHERIT_ROTATION
    if dont_inherit[2]:
        flags |= constants.NODE_FLAG_DONT_INHERIT_SCALING
    if billboarded:
        flags |= constants.NODE_FLAG_BILLBOARDED
    if billboard_lock[0]:
        flags |= constants.NODE_FLAG_BILLBOARDED_LOCK_Z
    if billboard_lock[1]:
        flags |= constants.NODE_FLAG_BILLBOARDED_LOCK_Y
    if billboard_lock[2]:
        flags |= constants.NODE_FLAG_BILLBOARDED_LOCK_X
    if camera_anchored:
        flags |= constants.NODE_FLAG_CAMERA_ANCHORED
    return flags


def set_node_flags(node, flags: int) -> None:
    """把原始 flags 记到 War3Node 上，并派生宿主字段。"""
    node.flags = flags
    (node.billboarded,
     node.billboard_lock,
     node.dont_inherit,
     node.camera_anchored) = flags_to_state(flags)


def node_state_flags(node) -> int:
    """从宿主字段反推 flags（原始 flags 缺失，例如手工搭的场景）。"""
    return state_to_flags(getattr(node, "billboarded", False),
                          getattr(node, "billboard_lock", FALSE_LOCK),
                          getattr(node, "dont_inherit", FALSE_INHERIT),
                          getattr(node, "camera_anchored", False))
