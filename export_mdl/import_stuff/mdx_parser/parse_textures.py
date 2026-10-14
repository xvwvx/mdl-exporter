from typing import List

from ... import constants
from ...classes.War3Texture import War3Texture
from . import binary_reader


def parse_textures(data: bytes):
    r = binary_reader.Reader(data)
    data_size = len(data)

    # A(MdxLoader.cs:568-570)：长度不是 268 的整数倍时只记诊断，仍解析完整记录。
    if data_size % 268 != 0:
        print('  TEXS 块长度 %d 不是 268 的整数倍，只解析完整的记录' % data_size)

    textures_count = data_size // 268
    textures: List[War3Texture] = []

    for _ in range(textures_count):
        texture = War3Texture()
        texture.replaceable_id = r.getf('<I')[0]
        texture.texture_path = r.gets(260)
        flags = r.getf('<I')[0]
        # A(MdxLoader.cs:568-591)：WrapFlags&1 = 宽度环绕、&2 = 高度环绕。
        # 旧实现把 flags 读掉就丢，WrapWidth/WrapHeight 永远为 False。
        texture.wrap_flags = flags
        texture.wrap_width = bool(flags & constants.TEXTURE_WRAP_FLAG_WIDTH)
        texture.wrap_height = bool(flags & constants.TEXTURE_WRAP_FLAG_HEIGHT)
        textures.append(texture)

    return textures
