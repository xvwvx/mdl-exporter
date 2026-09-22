"""MDX (binary) GLBS chunk - global sequence durations.

    uint32 count
    uint32 duration[count]

Tracks reference an entry by index, so the parsed list is published for the track
parser to resolve.
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
