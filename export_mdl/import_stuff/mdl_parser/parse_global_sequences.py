"""MDL (text) GlobalSequences chunk.

    GlobalSequences 2 {
        Duration 333,
        Duration 1000,
    }

Tracks reference an entry by index (``GlobalSeqId N``), so the parsed list is
published for the track parser to resolve.
"""

import re
from typing import List

from ..global_sequences import set_global_sequences


def parse_global_sequences(data: str) -> List[int]:
    sequences = [int(value) for value in re.findall(r'Duration\s+(\d+)', data)]
    set_global_sequences(sequences)
    return sequences
