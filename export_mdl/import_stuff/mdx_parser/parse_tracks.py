"""MDX (binary) 事件轨道（EVTS 里的 KEVT 子块）。

布局（A:1098-1142）：
    uint32 key_count
    uint32 global_sequence_id   - 0xFFFFFFFF 表示没有全局序列
    int32  keys[key_count]      - 触发时间（毫秒）

旧实现把这些键读掉就丢（函数没有返回值），导入后事件点全部消失。
现在返回一条 War3AnimationCurve 交给 EVTS 解析器保存。
"""

from ..global_sequences import resolve_raw
from ...classes.War3AnimationCurve import War3AnimationCurve


def parse_tracks(r) -> War3AnimationCurve:
    track = War3AnimationCurve()
    track.type = 'Event'
    # 事件轨道是离散的：MDL 的 EventTrack 只写帧号，不写插值行。
    track.interpolation = 'DontInterp'
    tracks_count = r.getf('<I')[0]
    track.global_sequence = resolve_raw(r.getf('<I')[0])

    # A(MdxLoader.cs:1111-1117)：键数组的字节数必须放得进事件块剩余空间。
    data = getattr(r, '_Reader__data', None)
    if data is not None:
        remaining = len(data) - r.offset
        if tracks_count * 4 > remaining:
            raise Exception('KEVT: %d key(s) do not fit the %d byte(s) left in the event chunk'
                            % (tracks_count, remaining))

    # A(MdxLoader.cs:1118) 用 ReadInt32s 读取，键是 int32；A 的 Keys 是数组，
    # 允许出现两个完全相同的时间戳。War3AnimationCurve.keyframes 是 dict，
    # 重复时间戳会被折叠，所以原始列表另外挂在曲线的 event_keys 上（S20）。
    event_keys = []
    for _ in range(tracks_count):
        time = r.getf('<i')[0]
        event_keys.append(time)
        # 事件键没有值，空列表即可（write_animation_chunk 对 Event 只写帧号）。
        track.keyframes[time] = []

    track.event_keys = event_keys
    return track
