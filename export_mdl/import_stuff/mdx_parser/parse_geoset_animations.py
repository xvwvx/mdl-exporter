from typing import List

from ...classes.War3GeosetAnim import War3GeosetAnim
from ... import constants
from . import binary_reader
from .parse_timeline import parse_timeline


def parse_geoset_animations(data: bytes):
    r = binary_reader.Reader(data)
    data_size = len(data)

    geoset_animations: List[War3GeosetAnim] = []
    while r.offset < data_size:
        inclusive_size = r.offset + r.getf('<I')[0]
        alpha = list(r.getf('<f'))
        flags = r.getf('<I')[0]
        color = list(r.getf('<3f'))
        geoset_id = r.getf('<I')[0]
        # A(MdxLoader.cs:1021-1022)：0xFFFFFFFF 归一为 -1（S14 同族）。
        if geoset_id == 0xFFFFFFFF:
            geoset_id = -1
        animation_color = None
        animation_alpha = None
        while r.offset < inclusive_size:
            chunk_id = r.getid(constants.SUB_CHUNKS_GEOSET_ANIMATION)

            if chunk_id == constants.CHUNK_GEOSET_COLOR:
                animation_color = parse_timeline(r, '<3f')
            elif chunk_id == constants.CHUNK_GEOSET_ALPHA:
                animation_alpha = parse_timeline(r, '<f')
            else:
                # A(MdxLoader.cs:1038-1041)：未知子块只消费 tag 本身的 4 字节后继续。
# 注意：A 对未知 tag 只消费 tag 自身的 4 字节（getid 已经消费掉了），
                # 这里不能再额外 skip —— 旧实现多跳 4 字节，未知 tag 之后的所有读取
                # 都整体错位（合成样本 synth_all800.mdx 的层尾填充字节即暴露此错位）。
                print("  unknown geoset-animation sub-chunk %r - skipping 4 bytes" % chunk_id)

        geoset_animation = War3GeosetAnim(color, alpha, animation_color, animation_alpha)
        geoset_animation.geoset_id = geoset_id
        # 动态属性：GEOA 头的 flags/静态 alpha（mdxdump 的 geosetAnims[].flags/staticAlpha）。
        geoset_animation.flags = flags
        geoset_animation.static_alpha = alpha[0] if alpha else 1.0
        geoset_animations.append(geoset_animation)
    return geoset_animations
