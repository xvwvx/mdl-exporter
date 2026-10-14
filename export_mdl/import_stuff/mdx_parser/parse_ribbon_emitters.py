"""MDX (binary) RIBB chunk - RibbonEmitter."""

from typing import List

from . import binary_reader
from .parse_node import parse_node
from .parse_timeline import parse_timeline
from .parse_particle_emitters import iter_records
from ... import constants
from ...classes.War3EmitterSettings import War3EmitterSettings
from ...classes.War3RibbonEmitter import War3RibbonEmitter


def parse_ribbon_emitters(data: bytes) -> List[War3RibbonEmitter]:
    emitters: List[War3RibbonEmitter] = []
    for record in iter_records(data):
        record_size = len(record)
        r = binary_reader.Reader(record)
        node = War3RibbonEmitter("")
        parse_node(r, node)

        settings = War3EmitterSettings()
        settings.emitter_type = 'RibbonEmitter'
        settings.height_above = r.get_float()
        settings.height_below = r.get_float()
        settings.alpha = r.get_float()
        settings.ribbon_color = list(r.get_floats(3))
        settings.life_span = r.get_float()
        settings.texture_id = r.get_int()
        settings.emission_rate = r.get_int()
        settings.rows = r.get_int()
        settings.cols = r.get_int()
        settings.material_id = r.get_int()
        settings.gravity = r.get_float()
        node.emitter = settings

        while r.offset < record_size:
            chunk_id = r.getid(constants.SUB_CHUNKS_RIBBON_EMITTER)
            if chunk_id == constants.CHUNK_RIBBON_HEIGHT_ABOVE:
                # A(MdxLoader.cs:1441-1446)：KRHA/KRHB 是两条各自独立的曲线。旧实现
                # 把 KRHA 塞进 scale_anim、KRHB 直接丢弃，"上方高度"与"下方高度"
                # 混为一谈。这里新增 height_above_anim，并保留 scale_anim 的旧赋值，
                # 以免破坏依赖它的下游（不删不改名既有属性）。
                curve = parse_timeline(r, '<f')
                node.height_above_anim = curve
                node.scale_anim = curve
            elif chunk_id == constants.CHUNK_RIBBON_HEIGHT_BELOW:
                node.height_below_anim = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_RIBBON_ALPHA:
                node.alpha_anim = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_RIBBON_COLOR:
                node.ribbon_color_anim = parse_timeline(r, '<3f')
            elif chunk_id == constants.CHUNK_RIBBON_TEXTURE_SLOT:
                # KRTX 的键值是纹理槽（Int1），旧实现读完就丢。
                node.texture_slot_anim = parse_timeline(r, '<I')
            elif chunk_id == constants.CHUNK_RIBBON_VISIBILITY:
                node.visibility = parse_timeline(r, '<f')
            else:
                # A:1441-1446 对未知轨道跳过 4 字节继续；break 会让其后的轨道全丢。
# 注意：A 对未知 tag 只消费 tag 自身的 4 字节（getid 已经消费掉了），
                # 这里不能再额外 skip —— 旧实现多跳 4 字节，未知 tag 之后的所有读取
                # 都整体错位（合成样本 synth_all800.mdx 的层尾填充字节即暴露此错位）。
                print("  unknown RIBB track %r - skipping 4 bytes" % chunk_id)

        emitters.append(node)
    return emitters
