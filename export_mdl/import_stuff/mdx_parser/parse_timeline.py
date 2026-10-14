from typing import List

from .binary_reader import Reader
from ..global_sequences import resolve_raw
from ...classes.War3AnimationCurve import War3AnimationCurve
from ... import constants

# format:
# textureId: '<I'
# alpha: '<f'
# scaling, translation: '<3f'
# rotation: '<4f'


def parse_timeline(r: Reader, value_format: str) -> War3AnimationCurve:
    transformation = War3AnimationCurve()
    tracks_count = r.getf('<I')[0]
    interpolation_int = r.getf('<I')[0]
    transformation.interpolation = constants.INTERPOLATION_TYPE_MDL_NAMES.get(interpolation_int, 'DontInterp')
    # The file stores an index into the GLBS list; the rest of the addon uses the
    # duration in milliseconds.
    transformation.global_sequence = resolve_raw(r.getf('<I')[0])

    # A(MdxLoader.cs:1546-1600)：keyFrameSize = 4 + componentBytes * typeSize，
    # 总字节数超过剩余长度说明轨道是坏的 —— 继续读会吃掉后面的记录（S8）。
    component_bytes = {'<f': 4, '<I': 4, '<3f': 12, '<4f': 16}.get(value_format, 4)
    type_size = 1 if interpolation_int <= 1 else (3 if interpolation_int <= 3 else 0)
    key_frame_size = 4 + component_bytes * type_size
    needed_bytes = key_frame_size * tracks_count
    remaining = len(getattr(r, '_Reader__data')) - r.offset
    if needed_bytes > remaining:
        raise Exception('key track: %d key(s) x %d byte(s) = %d byte(s) but only %d remain'
                        % (tracks_count, key_frame_size, needed_bytes, remaining))

    # 已知表示差异（S20）：参考实现的轨道是"可含重复时间戳的键数组"，长度就是
    # tracks_count。这里额外记录原始键数，让重复键造成的丢失可被检出/统计。
    transformation.keyframe_count = tracks_count

    # print("\ttracks_count: ", tracks_count, "interpolation: ", interpolation_int, "global_sequence: ", transformation.global_sequence,)
    for _ in range(tracks_count):
        # A(MdxLoader.cs:1591)：键时间是 ReadI32（有符号）。真实模型里存在负时间戳
        # （例如 "Stand" 里 -1 的键），用 '<I' 会读成 4294967295 这种巨大正数，
        # 导出到 MDL/F-Curve 时就成了 4.29e9 帧的位置（S12 同族）。
        time: int = r.getf('<i')[0]
        values: List[float] = list(r.getf(value_format))    # translation values

        if value_format == '<4f':
            values = [values[3], values[0], values[1], values[2]]  # Quat [xyzw] to [wxyz]
            # print(values)

        # 已知表示差异（j3 的 S20）：参考实现保留同一时间戳上的多条键，这里用时间做
        # dict 键，重复时间戳只会留下最后一条（全语料对比中 events/geosetAnims 的键数
        # 因此可能比参考少几条）。Blender 的 F-Curve 本身也是"每帧一个关键帧"，
        # 保留既有 dict 结构与全部下游代码兼容；若要逐键还原，需要把 keyframes 改成
        # (time, values) 序列并同步所有消费方，属于跨模块改动。
        transformation.keyframes[time] = values

        # A(MdxLoader.cs:1571)：typeSize = interp<=1 ? 1 : (interp<=3 ? 3 : 0)。
        # 也就是说只有 Hermite(2)/Bezier(3) 才带 InTan/OutTan；未知插值(>=4)
        # 必须按 typeSize=0 处理（不读切线），否则会把后面的字节当成切线吃掉，
        # 整条轨道乃至其后的记录全部错位。
        if (constants.INTERPOLATION_TYPE_HERMITE <= interpolation_int
                <= constants.INTERPOLATION_TYPE_BEZIER):
            in_tan: List[float] = list(r.getf(value_format))
            out_tan: List[float] = list(r.getf(value_format))
            transformation.handles_left[time] = in_tan
            transformation.handles_right[time] = out_tan

    return transformation
