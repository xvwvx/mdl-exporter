from typing import List

from ...classes.War3AnimationAction import War3AnimationAction
from . import binary_reader


def parse_sequences(data: bytes) -> List[War3AnimationAction]:
    r = binary_reader.Reader(data)
    data_size = len(data)

    # A(MdxLoader.cs:525-527) 对长度不是 132 倍数的 SEQS 只记一条诊断，仍按
    # 完整记录数解析（旧实现直接抛异常，整个模型导入失败）。
    if data_size % 132 != 0:
        print('  SEQS 块长度 %d 不是 132 的整数倍，只解析完整的记录' % data_size)

    sequence_count = data_size // 132

    sequences: List[War3AnimationAction] = []
    for _ in range(sequence_count):
        name = r.gets(80)
        # A(MdxLoader.cs:525-550)：Start/End 是有符号 int32（少数模型用负值表达
        # "从上一段结尾开始"），旧实现按无符号读会得到 40 亿级的时长。
        interval_start = r.getf('<i')[0]
        interval_end = r.getf('<i')[0]
        move_speed = r.getf('<f')[0]
        flags = r.getf('<I')[0]
        rarity = r.getf('<f')[0]
        sync_point = r.getf('<I')[0]
        bounds_radius = r.getf('<f')[0]
        minimum_extent = r.getf('<3f')
        maximum_extent = r.getf('<3f')
        print(" Parsed Sequence: ", name,
              "\tstart:", interval_start, "\tend:", interval_end,
              "\tlen:", (interval_end-interval_start))
        # A(MdxModel.cs:181)：NonLooping = (Flags & 1) != 0，而不是 flags == 1
        # （flags 其它位是循环/瞬移等标记，旧实现只在 flags 恰好等于 1 时才算不循环）。
        sequence = War3AnimationAction(name, interval_start, interval_end,
                                       (flags & 1) != 0, move_speed, rarity)
        # A(MdxModel.cs:169-184) 保留同步点、flags 与包围盒。War3AnimationAction
        # 没有这些字段，而 classes/ 不在本次可改范围，故用动态属性附加（不删不改名）。
        sequence.flags = flags
        sequence.sync_point = sync_point
        sequence.bounds_radius = bounds_radius
        sequence.minimum_extent = list(minimum_extent)
        sequence.maximum_extent = list(maximum_extent)
        sequences.append(sequence)
    return sequences
