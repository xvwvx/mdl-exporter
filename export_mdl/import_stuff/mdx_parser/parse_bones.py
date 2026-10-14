from typing import List

from ...classes.War3Bone import War3Bone
from . import binary_reader
from .parse_node import parse_node


def parse_bones(data: bytes) -> List[War3Bone]:
    r = binary_reader.Reader(data)
    data_size = len(data)

    nodes: List[War3Bone] = []
    while r.offset < data_size:
        node = War3Bone("")
        parse_node(r, node)
        # A(MdxLoader.cs:1050-1063)：这两个 id 的 0xFFFFFFFF 表示"无"，必须归一为
        # -1（A:674-676/1057-1060），否则下游会拿 4294967295 当索引。
        geoset_id = r.getf('<I')[0]
        node.geoset_id = geoset_id if geoset_id != 0xFFFFFFFF else -1
        # 旧实现把 geoset_animation_id 读掉就丢，骨骼到 geoset 动画的绑定全丢（S23）。
        geoset_animation_id = r.getf('<I')[0]
        node.geoset_animation_id = (geoset_animation_id
                                    if geoset_animation_id != 0xFFFFFFFF else -1)
        nodes.append(node)
    return nodes
