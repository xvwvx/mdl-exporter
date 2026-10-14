"""MDX (binary) TXAN chunk - TextureAnims (UV animation).

Each record is length prefixed and holds up to three tracks:

    KTAT  translation (3 floats)
    KTAR  rotation    (4 floats, a quaternion)
    KTAS  scaling     (3 floats)

Material layers reference a record by index through their TextureAnimationId.
"""

from typing import List

from . import binary_reader
from .parse_particle_emitters import iter_records
from .parse_timeline import parse_timeline
from ... import constants
from ...classes.War3TextureAnim import War3TextureAnim


def parse_texture_animations(data: bytes) -> List[War3TextureAnim]:
    animations: List[War3TextureAnim] = []
    for record in iter_records(data):
        record_size = len(record)
        r = binary_reader.Reader(record)
        texture_anim = War3TextureAnim()

        while r.offset < record_size:
            chunk_id = r.getid(constants.SUB_CHUNKS_TEX_ANIM)
            if chunk_id == constants.CHUNK_TEX_ANIM_TRANSLATION:
                texture_anim.translation = parse_timeline(r, '<3f')
                texture_anim.translation.type = 'Translation'
            elif chunk_id == constants.CHUNK_TEX_ANIM_ROTATION:
                texture_anim.rotation = parse_timeline(r, '<4f')
                texture_anim.rotation.type = 'Rotation'
            elif chunk_id == constants.CHUNK_TEX_ANIM_SCALING:
                texture_anim.scale = parse_timeline(r, '<3f')
                texture_anim.scale.type = 'Scale'
            else:
                # A(MdxLoader.cs:750-753)：未知子块跳 4 字节后继续（旧实现直接 break，
                # 该记录后面的轨道全部丢掉）。
# 注意：A 对未知 tag 只消费 tag 自身的 4 字节（getid 已经消费掉了），
                # 这里不能再额外 skip —— 旧实现多跳 4 字节，未知 tag 之后的所有读取
                # 都整体错位（合成样本 synth_all800.mdx 的层尾填充字节即暴露此错位）。
                print("  unknown texture-animation sub-chunk %r - skipping 4 bytes" % chunk_id)

        animations.append(texture_anim)
    return animations
