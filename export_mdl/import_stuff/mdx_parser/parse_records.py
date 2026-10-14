"""MDX 记录级重同步工具。

参考实现 A(MdxLoader.cs:1622-1710) 在处理"长度前缀"的记录列表时，如果某条记录声明的
长度装不下，会从下一条记录的候选位置重新对齐，而不是停在原地。这里把那段逻辑抽出来，
供 GEOS / MTLS 等块共用。
"""

from typing import Callable, Optional


def find_next_record_start(data: bytes,
                           from_offset: int,
                           container_end: int,
                           minimum_declared_size: int,
                           plausible_record: Optional[Callable] = None) -> int:
    """返回下一条看起来合法的记录偏移；找不到返回 -1（对应 A 的 FindNextRecordStart）。

    从 from_offset + 1 开始逐字节扫描，只接受"声明长度 >= minimum_declared_size
    且整条记录仍落在 container_end 之内"的位置；给了 plausible_record 时还要它点头。
    """
    candidate = from_offset + 1
    while candidate + 4 <= container_end:
        declared = int.from_bytes(data[candidate:candidate + 4], 'little', signed=True)
        if declared >= minimum_declared_size and candidate + declared <= container_end:
            if plausible_record is None or plausible_record(data, candidate):
                return candidate
        candidate += 1
    return -1
