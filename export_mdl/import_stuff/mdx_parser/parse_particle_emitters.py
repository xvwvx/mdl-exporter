"""MDX (binary) particle emitter chunks: PREM (ParticleEmitter) and
PRE2 (ParticleEmitter2).

Each record is length prefixed with an inclusive size, so a record that contains
a track id this parser does not know about can be abandoned without desyncing
the outer chunk walk.

参考实现 A = open-realm 的 MdxLoader.cs，行号写在下面的注释里。
"""

from typing import Iterator, List

from . import binary_reader
from .parse_node import parse_node
from .parse_timeline import parse_timeline
from ... import constants
from ...classes.War3EmitterSettings import War3EmitterSettings
from ...classes.War3ParticleEmitter import War3ParticleEmitter
from ...classes.War3ParticleSystem import War3ParticleSystem

# id + keyframe count + interpolation type + 4 reserved bytes
TRACK_HEADER_SIZE = 16


def as_signed_int(value: int) -> int:
    """把按无符号读回来的 32 位整数还原成 C# 里 (int) 转换的结果。

    A 的读法混用 ReadU32/ReadI32：写成 (int)ReadU32() 的地方，0xFFFFFFFF 表示 -1、
    0xFFFFFFFE 表示 -2（补码按位重解释）。Python 的 struct '<I' 读出来是正数，
    直接存下去会让下游把 4294967294 当成一个正常的大数写进 MDL。
    """
    if value >= 0x80000000:
        return value - 0x100000000
    return value


def iter_records(data: bytes) -> Iterator[bytes]:
    """Yield the body of every length-prefixed emitter record."""
    reader = binary_reader.Reader(data)
    data_size = len(data)
    while reader.offset < data_size:
        if reader.offset + 4 > data_size:
            print("  emitter chunk: %d trailing byte(s) are not a record - ignored"
                  % (data_size - reader.offset))
            return
        inclusive_size = reader.getf('<I')[0]
        if inclusive_size < 4:
            print("  emitter record with bad size %d - stopping" % inclusive_size)
            return
        record_size = inclusive_size - 4
        if reader.offset + record_size > data_size:
            print("  emitter record overruns the chunk - stopping")
            return
        record = data[reader.offset: reader.offset + record_size]
        reader.skip(record_size)
        yield record


def find_track_start(record: bytes, offset: int, record_size: int) -> int:
    """Where the PRE2 track list begins (兜底，不是主路径).

    按 A 的布局，静态段读完（含末尾 4 个 uint32）之后轨道就紧跟其后，所以正常情况下
    这个函数直接返回 offset。保留它只为极少数在 PriorityPlane 之后仍多出 4 字节填充的
    文件：那种情况下从头开始找一个合法的轨道头。

    注意：旧实现曾以"真实文件在 PriorityPlane 后多一个 uint32"为由整体使用这个启发式，
    那个"多出来的 uint32"其实是被漏读的 ReplaceableId（见 S11），现在静态段已按 A 的
    4 个 uint32 精确读取。
    """
    candidate = offset
    while candidate + TRACK_HEADER_SIZE <= record_size:
        if is_track_header(record, candidate, record_size):
            return candidate
        candidate += 4
    return record_size


def is_track_header(record: bytes, offset: int, record_size: int) -> bool:
    """True when a track header (id, keyframe count, interpolation type) sits here."""
    try:
        chunk_id = record[offset:offset + 4].decode('ascii')
    except UnicodeDecodeError:
        return False
    if chunk_id not in constants.SUB_CHUNKS_PARTICLE_EMITTER2:
        return False
    count = int.from_bytes(record[offset + 4:offset + 8], 'little')
    if not 0 <= count <= 4096:
        return False
    # id + count + interpolation type + 4 reserved bytes, then count timestamps.
    return offset + TRACK_HEADER_SIZE + count * 4 <= record_size


def parse_particle_emitters(data: bytes) -> List[War3ParticleEmitter]:
    """PREM - the legacy particle emitter."""
    emitters: List[War3ParticleEmitter] = []
    for record in iter_records(data):
        record_size = len(record)
        r = binary_reader.Reader(record)
        node = War3ParticleEmitter("")
        parse_node(r, node)

        settings = War3EmitterSettings()
        settings.emitter_type = 'ParticleEmitter'
        settings.emission_rate = r.get_float()
        settings.gravity = r.get_float()
        settings.longitude = r.get_float()
        settings.latitude = r.get_float()
        # A(MdxLoader.cs:1277-1283 与常量 FileNameLength=260)：模型路径是 260 字节。
        # 旧实现只读 80 字节，并在 Speed 之后多读了一个根本不存在的 flags，
        # 于是静态段整体错位、PREM 的所有轨道都解析失败（S2）。
        settings.model_path = r.gets(260)
        settings.life_span = r.get_float()
        settings.speed = r.get_float()

        # A(MdxModel.cs:63-87)：节点标志里 0x8000/0x10000 在 ParticleEmitter 上的
        # 含义是 EmitterUsesMDL / EmitterUsesTGA，写出 MDL 时对应同名关键字。
        # 语料实测（3381 个 .mdx，68 个 PREM 记录）：65 个是 0x9000
        # （EmitterUsesMDL）、3 个是 0x11000（EmitterUsesTGA）。旧实现不读标志、
        # 无条件写 EmitterUsesMDL，那 3 个模型被改成 MDL 语义。
        settings.unshaded = (node.flags & constants.NODE_FLAG_UNSHADED_OR_EMITTER_USES_MDL) != 0
        settings.sort_far_z = (node.flags & constants.NODE_FLAG_SORT_FAR_Z_OR_EMITTER_USES_TGA) != 0
        node.emitter = settings

        # A(MdxLoader.cs:1297-1303)：PREM 的轨道标签是
        # KPEE/KPEG/KPLN/KPLT/KPEL/KPES/KPEV（见 constants.py 的注释）。
        while r.offset + 4 <= record_size:
            chunk_id = r.getid(constants.SUB_CHUNKS_PARTICLE_EMITTER)
            if chunk_id == constants.CHUNK_PE_EMISSION_RATE:
                node.emission_rate_anim = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_PE_GRAVITY:
                node.gravity_anim = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_PE_LONGITUDE:
                node.longitude_anim = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_PE_LATITUDE:
                node.latitude_anim = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_PE_LIFE_SPAN:
                node.life_span_anim = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_PE_INIT_VELOCITY:
                node.speed_anim = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_PE_VISIBILITY:
                node.visibility = parse_timeline(r, '<f')
            else:
                # A(MdxLoader.cs:1271-1312)：未知轨道跳过 4 字节后继续读后面的轨道。
                # 旧实现用 break，导致该轨道之后的所有轨道全部丢失（S1/S3）。
# 注意：A 对未知 tag 只消费 tag 自身的 4 字节（getid 已经消费掉了），
                # 这里不能再额外 skip —— 旧实现多跳 4 字节，未知 tag 之后的所有读取
                # 都整体错位（合成样本 synth_all800.mdx 的层尾填充字节即暴露此错位）。
                print("  unknown PREM track %r - skipping 4 bytes" % chunk_id)

        emitters.append(node)
    return emitters


def parse_particle_emitters2(data: bytes, version: int = 800) -> List[War3ParticleSystem]:
    """PRE2 - the sprite sheet particle emitter."""
    emitters: List[War3ParticleSystem] = []
    for record in iter_records(data):
        record_size = len(record)
        r = binary_reader.Reader(record)
        node = War3ParticleSystem("")
        parse_node(r, node)

        settings = War3EmitterSettings()
        settings.emitter_type = 'ParticleEmitter2'
        settings.speed = r.get_float()
        settings.variation = r.get_float()
        settings.latitude = r.get_float()
        settings.gravity = r.get_float()
        settings.life_span = r.get_float()
        settings.emission_rate = r.get_float()
        settings.length = r.get_float()
        settings.width = r.get_float()
        # A(MdxLoader.cs:1329-1335) + MdxModel.cs:437-445：PRE2 用的是 5 值专用表
        # {Blend, Additive, Modulate, Modulate2x, AlphaKey}，>=5 回退 Blend；
        # 旧实现用了材质层的 0..6 表，索引整体错位（S18）。
        filter_mode = r.get_int()
        if filter_mode >= len(constants.PARTICLE_EMITTER2_FILTER_MODES):
            print("  PRE2 FilterMode %d 超出 5 值表的范围 - 按 Blend 处理" % filter_mode)
            filter_mode = 0
        settings.filter_mode = constants.PARTICLE_EMITTER2_FILTER_MODES[filter_mode]
        settings.rows = r.get_int()
        settings.cols = r.get_int()

        head_or_tail = r.get_int()
        settings.head = head_or_tail in (constants.HEAD_OR_TAIL_HEAD,
                                         constants.HEAD_OR_TAIL_BOTH)
        settings.tail = head_or_tail in (constants.HEAD_OR_TAIL_TAIL,
                                         constants.HEAD_OR_TAIL_BOTH)
        settings.tail_length = r.get_float()
        settings.time = r.get_float()

        settings.set_colors(r.get_floats(3), r.get_floats(3), r.get_floats(3))
        # Segment alphas are bytes, not floats.
        settings.start_alpha, settings.mid_alpha, settings.end_alpha = r.get_bytes(3)
        settings.start_scale, settings.mid_scale, settings.end_scale = r.get_floats(3)

        (settings.head_life_start, settings.head_life_end,
         settings.head_life_repeat) = r.get_ints(3)
        (settings.head_decay_start, settings.head_decay_end,
         settings.head_decay_repeat) = r.get_ints(3)
        (settings.tail_life_start, settings.tail_life_end,
         settings.tail_life_repeat) = r.get_ints(3)
        (settings.tail_decay_start, settings.tail_decay_end,
         settings.tail_decay_repeat) = r.get_ints(3)

        # A(MdxLoader.cs:1365-1369)：TextureId 之后依次是 Squirt / PriorityPlane /
        # ReplaceableId，共 4 个 uint32。旧实现只读 3 个，而且把 Squirt 当成
        # ReplaceableId、把 ReplaceableId 当成 PriorityPlane，并使读取位置少走
        # 4 字节（S11）。
        # 参考实现这一段的类型是：
        #   TextureId     = textureId == 0xFFFFFFFF ? -1 : (int)textureId
        #   Squirt        = (int)ReadU32()
        #   PriorityPlane = (int)ReadU32()
        #   ReplaceableId = ReadU32()          # 这个在 A 里确实是 uint
        # C# 的 (int) 是按位重解释，所以 0xFFFFFFFE 要还原成 -2，而不是 4294967294。
        # 实测 AnimateDeadTarget.mdx 的第二个发射器 priority_plane 就是 0xFFFFFFFE，
        # 无符号读会让导出的 MDL 写出错误的正数。
        texture_id = r.get_int()
        settings.texture_id = -1 if texture_id == 0xFFFFFFFF else as_signed_int(texture_id)
        settings.squirt = as_signed_int(r.get_int())    # Squirt 是开关，属性组里没有
                                                        # 对应字段，只保存不应用。
        settings.priority_plane = as_signed_int(r.get_int())
        settings.replaceable_id = r.get_int()           # A 里是 uint，保持无符号

        # A(MdxModel.cs:63-87 + MdxParticleSystem.cs:196/364/376-383/513/612-614)：
        # PRE2 的显示标志全部来自节点标志，MDL 写出端也只在这些布尔为真时写关键字
        # （War3ParticleSystem.py:103-119）。旧实现一个都不设，于是
        # SortPrimsFarZ/Unshaded/LineEmitter/Unfogged/ModelSpace/XYQuad 在
        # .mdx → Blender → .mdl 的往返中被永久删除。语料实测 3947 个 PRE2 记录中
        # Unshaded 2908、SortPrimsFarZ 1207、Unfogged 622、XYQuad 295、
        # LineEmitter 277、ModelSpace 226（P0-2）。
        settings.unshaded = (node.flags & constants.NODE_FLAG_UNSHADED_OR_EMITTER_USES_MDL) != 0
        settings.sort_far_z = (node.flags & constants.NODE_FLAG_SORT_FAR_Z_OR_EMITTER_USES_TGA) != 0
        settings.line_emitter = (node.flags & constants.NODE_FLAG_LINE_EMITTER) != 0
        settings.unfogged = (node.flags & constants.NODE_FLAG_UNFOGGED) != 0
        settings.model_space = (node.flags & constants.NODE_FLAG_MODEL_SPACE) != 0
        settings.xy_quad = (node.flags & constants.NODE_FLAG_XY_QUAD) != 0

        node.emitter = settings

        # 正常情况下轨道紧跟静态段；只有在确实不是合法轨道头时才启用兜底搜索。
        if r.offset < record_size and not is_track_header(record, r.offset, record_size):
            r.offset = find_track_start(record, r.offset, record_size)

        while r.offset + 4 <= record_size:
            chunk_id = r.getid(constants.SUB_CHUNKS_PARTICLE_EMITTER2)
            if chunk_id == constants.CHUNK_PE2_SPEED:
                node.speed_anim = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_PE2_VARIATION:
                # A(MdxLoader.cs:1390)：KP2R 才是 Variation。
                node.variation_anim = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_PE2_VISIBILITY:
                # A(MdxLoader.cs:1383)：KP2V 是 Visibility（旧实现把它当 Variation，
                # 并且白名单里没有 KP2R，导致 KP2R 及其后的轨道全丢，S1）。
                node.visibility = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_PE2_LATITUDE:
                node.latitude_anim = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_PE2_GRAVITY:
                node.gravity_anim = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_PE2_EMISSION_RATE:
                node.emission_rate_anim = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_PE2_WIDTH:
                node.scale_anim = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_PE2_LENGTH:
                # Width and Length share one scale curve on export, so only the
                # first one seen is kept.
                if node.scale_anim is None:
                    node.scale_anim = parse_timeline(r, '<f')
                else:
                    parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_PE2_ALPHA:
                node.alpha_anim = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_PE2_COLOR:
                node.ribbon_color_anim = parse_timeline(r, '<3f')
            else:
                # A(MdxLoader.cs:1314-1399)：未知轨道跳过 4 字节后继续。
# 注意：A 对未知 tag 只消费 tag 自身的 4 字节（getid 已经消费掉了），
                # 这里不能再额外 skip —— 旧实现多跳 4 字节，未知 tag 之后的所有读取
                # 都整体错位（合成样本 synth_all800.mdx 的层尾填充字节即暴露此错位）。
                print("  unknown PRE2 track %r - skipping 4 bytes" % chunk_id)

        emitters.append(node)
    return emitters
