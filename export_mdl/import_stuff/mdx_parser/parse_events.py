from typing import List

from ...classes.War3EventObject import War3EventObject
from ... import constants
from . import binary_reader
from .parse_node import parse_node
from .parse_tracks import parse_tracks


def split_event_name(name: str):
    """从名字里拆出 3 字母事件类型与行键，对应 A:133-151。

    例如 "SNDx,1" -> ("SND", "1")、"FPTx" -> ("FPT", "")。
    """
    if len(name) <= 4:
        return name[:3], ''
    row_key = name[4:].strip(' \t\n\v\f\r')
    return name[:3], row_key


def parse_events(data: bytes) -> List[War3EventObject]:
    data_size = len(data)
    r = binary_reader.Reader(data)

    nodes: List[War3EventObject] = []
    while r.offset < data_size:

        node = War3EventObject("")
        parse_node(r, node)

        if r.offset + 4 <= data_size:
            chunk_id = r.gets(4)

            if chunk_id == constants.CHUNK_EVENT_TRACKS:
                # A(MdxLoader.cs:1098-1142)：KEVT 的键必须保存，旧实现调用了
                # parse_tracks 却不接收返回值，事件触发时间全部丢失（S5）。
                node.track = parse_tracks(r)
                # A(MdxLoader.cs:1118)：Keys 是 int32[]，重复时间戳要保留，
                # 不能用 dict 的键来数键数量（S20）。
                node.keys = node.track.event_keys
                node.global_sequence_id = node.track.global_sequence
            else:
                r.offset -= 4

        # A:1098-1120：事件类型/行键由名字推出（SND/SNDx/SPN/SPL/FPT/UBR/FTP）。
        node.event_type, node.event_data = split_event_name(node.name)

        nodes.append(node)
    return nodes
