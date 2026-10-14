from typing import List

from . import binary_reader
from .parse_attachment import parse_attachment
from ...classes.War3Attachment import War3Attachment


def parse_attachments(data: bytes) -> List[War3Attachment]:
    data_size = len(data)
    reader = binary_reader.Reader(data)

    nodes: List[War3Attachment] = []
    while reader.offset < data_size:
        record_start = reader.offset
        if reader.offset + 4 > data_size:
            print("  ATCH：末尾剩 %d 字节，不足一条记录" % (data_size - reader.offset))
            break
        inclusive_size = reader.getf('<I')[0]
        record_end = record_start + inclusive_size
        # 记录长度不可信时绝不能算出负数去 skip（读取位置会回退，进而死循环）。
        if inclusive_size < 4 or record_end > data_size:
            print("  ATCH：偏移 %d 处的记录声明 %d 字节，越界 - 剩余数据忽略"
                  % (record_start, inclusive_size))
            break
        node_data = data[reader.offset: record_end]
        reader.offset = record_end
        # 单条记录的解析（路径 / AttachmentId / KATV 可见性）交给 parse_attachment，
        # 旧实现把 path、node_id 和 visibility 都丢进局部变量（S6）。
        nodes.append(parse_attachment(node_data))
    return nodes
