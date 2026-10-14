"""MDX (binary) GLBS chunk - global sequence durations.

    uint32 count
    uint32 duration[count]

Tracks reference an entry by index, so the parsed list is published for the track
parser to resolve.

【与参考实现 A 的已知差异，故意不向 A 对齐】
A(MdxLoader.cs:552-556) 以及 C 引擎都把块首的 count 也当成 durations[0] 读取
（int count = r.Length / 4; 循环 Add(r.ReadU32())），这会让全局序列的时长整体
前移一格、并多读一个并不存在的时长。本实现按 MDX 格式规范行事：先读 count，
再读 count 个时长，所以这里保持现状（S22）。
"""

import struct
from typing import List

from ..global_sequences import set_global_sequences


def parse_global_sequences(data: bytes) -> List[int]:
    if len(data) < 4:
        set_global_sequences([])
        return []
    count = struct.unpack_from('<I', data, 0)[0]
    available = (len(data) - 4) // 4
    if count > available:
        print("  GLBS claims %d sequence(s) but only %d fit - truncating"
              % (count, available))
        count = available
    sequences = [struct.unpack_from('<I', data, 4 + index * 4)[0]
                 for index in range(count)]
    set_global_sequences(sequences)
    return sequences
