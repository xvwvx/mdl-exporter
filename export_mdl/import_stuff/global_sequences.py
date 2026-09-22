"""Global sequences of the file currently being parsed, shared by both parsers.

In a Warcraft file a track refers to a global sequence by *index*
(``GlobalSeqId N`` in MDL, a plain uint32 in MDX), while the rest of the addon
works with the sequence duration in milliseconds -- ``write_animation_chunk``
looks the duration up in the model's global sequence list.  The list therefore has
to be reachable from the track parsers.

Both formats put the list before every chunk that carries tracks, so the parser
publishes it as soon as it is read.  ``reset()`` is called at the start of a parse
so files do not leak into each other.
"""

from typing import List, Optional

NONE = 0xFFFFFFFF

_sequences: List[int] = []


def reset() -> None:
    global _sequences
    _sequences = []


def set_global_sequences(values: List[int]) -> None:
    global _sequences
    _sequences = [int(value) for value in values]


def get_global_sequences() -> List[int]:
    return list(_sequences)


def resolve(index: int) -> int:
    """Duration in ms for a global sequence index, or -1 when there is none."""
    if index == NONE or index < 0:
        return -1
    if index < len(_sequences):
        return _sequences[index]
    # An empty list is common (and then any index is meaningless, so stay quiet);
    # a non-empty list with an out of range index is a real inconsistency.
    if _sequences:
        print("  GlobalSeqId %d is out of range (%d sequence(s))"
              % (index, len(_sequences)))
    return -1


def resolve_raw(raw: int) -> int:
    """Same as resolve(), but tolerates the unsigned 'no sequence' sentinel."""
    if raw >= 0x80000000:
        return -1
    return resolve(raw)
