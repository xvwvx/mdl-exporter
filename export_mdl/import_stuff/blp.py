"""Warcraft 3 .blp 贴图解码器。

字段偏移与像素规则按 mdx_preview 的 C# 实现重写
（core/Blp/{Blp1Decoder.cs,Blp2Decoder.cs,BlpIo.cs,DxtDecoder.cs}），该 C# 实现是
对 open-realm C 引擎 renderer/r_blp1.c、r_blp2.c 的逐字节验证移植。相对旧实现
修掉了这些差异：

* BLP1 的 offsets 表在 0x1C（旧实现读 0x20）、lengths 表在 0x5C（旧实现读 0x60）；
  BLP2 的 width/height 在 0x0C/0x10（旧实现读 0x10/0x14），表在 0x14/0x54。
* BLP1 的 JPEG 变体按“共享 JPEG 头 + 每个 mip 的熵数据片”拼接，不再靠扫描 FFD8
  猜测（被 SMINAD 重打包过的文件会让扫描取到错的切片）。
* 调色板的 alpha 平面支持 0/1/4/8 位，且 alphaBits == 0 时强制 255（旧实现错用了
  调色板条目里的 alpha 字节）。
* DXT 用 ResolveDxtFormat 精确映射（旧实现按 alphaDepth/alphaEncoding 猜解码器），
  5-6-5 展开用 *255/31 与 *255/63（旧实现用复制位法，数值不同），DXT1 的无 1 位
  alpha 形态固定走 4 色插值。
* 所有 mip 级都会被解码（旧实现只看 mip 0），image.mipmaps 与 C# 的 MipRgba 对应，
  被跳过的级（非方形贴图的尾巴）为 None。

4 分量 JPEG 是 WC3 独有的“B,G,R,A 四个原始分量”，不做 YCbCr 变换，由 wc3_jpeg
模块解码；3 分量的普通 JPEG 原样交回调用方（Blender 自己能解）。
"""

import os
import struct
import sys
from typing import List, Optional, Tuple

try:                                    # 插件内以包的形式加载
    from . import wc3_jpeg
except (ImportError, ValueError):       # 以 export_mdl.* 绝对包名加载
    try:
        from export_mdl.import_stuff import wc3_jpeg
    except ImportError:                 # 直接按路径加载本文件（对照脚本）
        wc3_jpeg = None
        _here = os.path.dirname(os.path.abspath(__file__))
        if _here not in sys.path:
            sys.path.append(_here)
        try:
            import wc3_jpeg
        except ImportError:
            pass

BLP1_MAGIC = b'BLP1'
BLP2_MAGIC = b'BLP2'

BLP1_JPEG = 0
BLP1_PALETTE = 1

BLP2_PALETTE = 1
BLP2_DXT = 2
BLP2_RAW_BGRA = 3

# DXT 形态，取值与 C 的 blp2_convert_dxt() 的 format 参数一致。
DXT1_OPAQUE = 0
DXT1_ALPHA1 = 1
DXT3 = 3
DXT5 = 5

_BLP1_HEADER_SIZE = 0x9C
_BLP1_OFFSETS = 0x1C
_BLP1_LENGTHS = 0x5C
_BLP1_PALETTE = 0x9C        # 调色板，或 jpegHeaderSize
_BLP1_JPEG_HEADER = 0xA0

_BLP2_HEADER_SIZE = 0x494
_BLP2_OFFSETS = 0x14
_BLP2_LENGTHS = 0x54
_BLP2_PALETTE = 0x94

_PALETTE_BYTES = 256 * 4
_MIP_LEVELS = 16
_MAX_DIMENSION = 16384


class BlpError(Exception):
    """无法解码（或不受支持）的 .blp 文件。"""
    pass


class BlpImage:
    """一张 BLP 贴图：要么是待解码的 JPEG，要么是已解码的 RGBA 字节。"""

    def __init__(self, width: int = 0, height: int = 0,
                 jpeg: Optional[bytes] = None,
                 rgba: Optional[bytes] = None,
                 mipmaps: Optional[List[Optional[bytes]]] = None,
                 version: int = 0, encoding: int = 0, alpha_depth: int = 0,
                 alpha_encoding: int = 0, mip_count: int = 1,
                 jpeg_bands: int = 0):
        self.width = width
        self.height = height
        self.jpeg = jpeg
        self.rgba = rgba
        if mipmaps is None:
            mipmaps = [rgba] if rgba is not None else []
        self.mipmaps = mipmaps
        self.version = version
        self.encoding = encoding
        self.alpha_depth = alpha_depth
        self.alpha_encoding = alpha_encoding
        self.mip_count = mip_count
        self.jpeg_bands = jpeg_bands

    @property
    def is_jpeg(self) -> bool:
        return self.jpeg is not None


def is_blp(data: bytes) -> bool:
    return data[:4] in (BLP1_MAGIC, BLP2_MAGIC)


def is_blp_file(path: str) -> bool:
    try:
        with open(path, 'rb') as handle:
            return is_blp(handle.read(4))
    except OSError:
        return False


def read_blp(data: bytes) -> BlpImage:
    if data[:4] == BLP1_MAGIC:
        return _read_blp1(data)
    if data[:4] == BLP2_MAGIC:
        return _read_blp2(data)
    raise BlpError("不是 .blp 文件（magic %r）" % (data[:4],))


# --------------------------------------------------------------------------
# 小工具
# --------------------------------------------------------------------------
def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from('<I', data, offset)[0]


def _count_mip_levels(offsets) -> int:
    """偏移表从头数到第一个 0（r_blp1.c:138、r_blp2.c:130 的做法）。"""
    count = 0
    while count < len(offsets) and offsets[count] != 0:
        count += 1
    return count


def _mip_dimension(base: int, level: int) -> int:
    return base >> level


def _validate_dimensions(name: str, width: int, height: int) -> None:
    if width == 0 or height == 0:
        raise BlpError("%s：贴图尺寸无效 %dx%d" % (name, width, height))
    if width > _MAX_DIMENSION or height > _MAX_DIMENSION:
        raise BlpError("%s：贴图尺寸 %dx%d 超过 %d 像素上限"
                       % (name, width, height, _MAX_DIMENSION))


def _check_mip_slice(data: bytes, offset: int, length: int, level: int,
                     name: str) -> int:
    """校验一个 mip 数据片并返回它的偏移（对应 BlpIo.CheckMipSlice）。"""
    if offset > len(data) or offset + length > len(data):
        raise BlpError("%s：mip %d 数据越界（offset=%d，length=%d，文件 %d 字节）"
                       % (name, level, offset, length, len(data)))
    return offset


def _palette_alpha_bytes(pixel_count: int, alpha_bits: int) -> int:
    if alpha_bits == 0:
        return 0
    if alpha_bits == 1:
        return (pixel_count + 7) // 8
    if alpha_bits == 4:
        return (pixel_count + 1) // 2
    if alpha_bits == 8:
        return pixel_count
    raise BlpError("不支持调色板 alpha 位数 %d（只支持 0/1/4/8）" % alpha_bits)


# --------------------------------------------------------------------------
# BLP1
# --------------------------------------------------------------------------
def _read_blp1(data: bytes) -> BlpImage:
    if len(data) < _BLP1_HEADER_SIZE:
        raise BlpError("BLP1 头被截断（文件 %d 字节，至少需要 %d）"
                       % (len(data), _BLP1_HEADER_SIZE))

    content_type = _u32(data, 4)
    alpha_bits = _u32(data, 8)
    width = _u32(data, 12)
    height = _u32(data, 16)
    offsets = struct.unpack_from('<%dI' % _MIP_LEVELS, data, _BLP1_OFFSETS)
    lengths = struct.unpack_from('<%dI' % _MIP_LEVELS, data, _BLP1_LENGTHS)

    mip_count = _count_mip_levels(offsets)
    if mip_count == 0:
        raise BlpError("BLP1：偏移表全为 0，没有任何 mip 级")
    _validate_dimensions("BLP1", width, height)

    image = BlpImage(width=width, height=height, version=1,
                     encoding=content_type, alpha_depth=alpha_bits,
                     mip_count=mip_count)

    if content_type == BLP1_JPEG:
        _read_blp1_jpeg(data, image, offsets, lengths, mip_count)
    else:
        _read_blp1_paletted(data, image, offsets, lengths, mip_count, alpha_bits)
    return image


def _read_blp1_jpeg(data: bytes, image: BlpImage, offsets, lengths,
                    mip_count: int) -> None:
    """共享 JPEG 头 + mip 0 的熵数据片（r_blp1.c:170-206）。

    jpegHeaderSize == 0 是合法形态，而且很常见（例如 D:\rpg 语料里的
    cb_*_SMINAD.blp）：此时没有共享头，mip 0 自己就是一条完整的 JPEG 流
    （FFD8 ... FFD9，尺寸与头部声明一致）。参考实现 Blp1Decoder.cs:107-110 只在
    jpegHeaderSize > 0 时才拼接共享头，所以这里也只对"共享头越界"报错——旧实现
    多判了一个 header_size == 0，把这类贴图全部误判成"解码失败"（导入后表现为
    整模型没有贴图）。
    """
    header_size = _u32(data, _BLP1_PALETTE)
    if _BLP1_JPEG_HEADER + header_size > len(data):
        raise BlpError("BLP1：共享 JPEG 头越界（jpegHeaderSize=%d，文件 %d 字节）"
                       % (header_size, len(data)))

    mip0 = _check_mip_slice(data, offsets[0], lengths[0], 0, "BLP1")
    jpeg = data[mip0:mip0 + lengths[0]]
    if header_size:
        jpeg = (data[_BLP1_JPEG_HEADER:_BLP1_JPEG_HEADER + header_size] + jpeg)

    bands = _read_jpeg_band_count(jpeg)
    image.jpeg_bands = bands
    image.mipmaps = [None] * mip_count

    if bands == 4:
        rgba, jpeg_width, jpeg_height = _decode_warcraft3_jpeg(jpeg)
        if jpeg_width != image.width or jpeg_height != image.height:
            raise BlpError("BLP1：JPEG 载荷是 %dx%d，但头部声明 %dx%d（mip 0）"
                           % (jpeg_width, jpeg_height, image.width, image.height))
        image.rgba = rgba
        image.mipmaps[0] = rgba
        return

    if bands == 3:
        # 普通 YCbCr JPEG：原样交给调用方（Blender 的 JPEG 解码器能处理）。
        image.jpeg = jpeg
        return

    if bands == 0:
        raise BlpError("BLP1：JPEG 载荷没有可用的 SOF 帧头（0 个分量），"
                       "说明这段是损坏的或用了不受支持的段"
                       "（stb_image 与 renderer/r_blp1.c 同样拒绝它）")
    raise BlpError("BLP1：JPEG 载荷声明了 %d 个分量，只接受 3（YCbCr）或 4"
                   "（WC3 原始分量）" % bands)


def _decode_warcraft3_jpeg(jpeg: bytes) -> Tuple[bytes, int, int]:
    if wc3_jpeg is None:
        raise BlpError("BLP1：需要 wc3_jpeg 模块解码 4 分量 JPEG，但没能导入 "
                       "export_mdl/import_stuff/wc3_jpeg.py")
    try:
        return wc3_jpeg.decode(jpeg)
    except Exception as exc:      # 统一转成 BlpError，调用方只捕这一种
        raise BlpError("BLP1：4 分量 JPEG 解码失败：%s" % (exc,))


def _read_blp1_paletted(data: bytes, image: BlpImage, offsets, lengths,
                        mip_count: int, alpha_bits: int) -> None:
    """256 色调色板 + 索引，alpha 平面可选（r_blp1.c:208-284）。"""
    if len(data) < _BLP1_PALETTE + _PALETTE_BYTES:
        raise BlpError("BLP1：调色板越界（文件 %d 字节，需要 %d）"
                       % (len(data), _BLP1_PALETTE + _PALETTE_BYTES))
    _palette_alpha_bytes(1, alpha_bits)     # alphaBits 不合法时提前失败

    mips: List[Optional[bytes]] = []
    for level in range(mip_count):
        offset = _check_mip_slice(data, offsets[level], lengths[level], level,
                                  "BLP1")
        width = _mip_dimension(image.width, level)
        height = _mip_dimension(image.height, level)
        if width < 1 or height < 1:
            # 非方形贴图的 mip 尾巴（例如 512x128 的第 8/9 级）：C 参考解出 0
            # 个像素，渲染层直接丢掉这次上传（renderer/r_texture.c:275）。
            mips.append(None)
            continue
        mips.append(_decode_paletted_mip(data, _BLP1_PALETTE, offset,
                                         lengths[level], width, height,
                                         alpha_bits, level, "BLP1"))
    image.mipmaps = mips
    image.rgba = mips[0]


# --------------------------------------------------------------------------
# BLP2
# --------------------------------------------------------------------------
def _read_blp2(data: bytes) -> BlpImage:
    if len(data) < _BLP2_HEADER_SIZE:
        raise BlpError("BLP2 头被截断（文件 %d 字节，至少需要 %d）"
                       % (len(data), _BLP2_HEADER_SIZE))

    content_type = _u32(data, 4)
    encoding = data[8]
    alpha_depth = data[9]
    alpha_encoding = data[10]
    has_mip_levels = data[11]
    width = _u32(data, 12)
    height = _u32(data, 16)
    offsets = struct.unpack_from('<%dI' % _MIP_LEVELS, data, _BLP2_OFFSETS)
    lengths = struct.unpack_from('<%dI' % _MIP_LEVELS, data, _BLP2_LENGTHS)

    mip_count = _count_mip_levels(offsets) if has_mip_levels else 1
    if mip_count == 0:
        raise BlpError("BLP2：hasMipLevels 已置位，但偏移表全为 0")
    _validate_dimensions("BLP2", width, height)

    image = BlpImage(width=width, height=height, version=2, encoding=encoding,
                     alpha_depth=alpha_depth, alpha_encoding=alpha_encoding,
                     mip_count=mip_count)

    if content_type == 0:
        # C 参考把 type 0（"JPEG"）丢进 blp2_convert_paletted_no_alpha()，把熵
        # 数据当调色板索引解出一张看似合理但没有意义的图（r_blp2.c:79-81）。
        # 这里直接报错，不产垃圾。
        raise BlpError("BLP2：type 0（JPEG）内容不受支持；C 参考实现会把它当"
                       "调色板索引解出无意义的图（renderer/r_blp2.c:79）")

    if encoding == BLP2_PALETTE:
        _palette_alpha_bytes(1, alpha_depth)
    elif encoding == BLP2_DXT:
        _resolve_dxt_format(alpha_depth, alpha_encoding)
    elif encoding != BLP2_RAW_BGRA:
        raise BlpError("BLP2：不支持的 encoding %d（1=调色板、2=DXT、"
                       "3=原始 BGRA）" % encoding)

    mips: List[Optional[bytes]] = []
    for level in range(mip_count):
        offset = _check_mip_slice(data, offsets[level], lengths[level], level,
                                  "BLP2")
        mip_width = _mip_dimension(width, level)
        mip_height = _mip_dimension(height, level)
        if mip_width < 1 or mip_height < 1:
            mips.append(None)
            continue

        if encoding == BLP2_PALETTE:
            mips.append(_decode_paletted_mip(data, _BLP2_PALETTE, offset,
                                             lengths[level], mip_width,
                                             mip_height, alpha_depth, level,
                                             "BLP2"))
        elif encoding == BLP2_RAW_BGRA:
            mips.append(_decode_raw_bgra_mip(data, offset, lengths[level],
                                             mip_width, mip_height, level))
        else:
            mips.append(_decode_dxt(data, offset, lengths[level], mip_width,
                                    mip_height,
                                    _resolve_dxt_format(alpha_depth,
                                                        alpha_encoding),
                                    level))

    image.mipmaps = mips
    image.rgba = mips[0]
    return image


def _resolve_dxt_format(alpha_depth: int, alpha_encoding: int) -> int:
    """r_blp2.c:78-113 的格式映射（返回 C 的 format 参数）。"""
    if alpha_encoding == 0:                 # BLP_ALPHA_ENCODING_DXT1
        if alpha_depth == 0:
            return DXT1_OPAQUE
        if alpha_depth == 1:
            return DXT1_ALPHA1
    elif alpha_encoding == 1:               # BLP_ALPHA_ENCODING_DXT3
        if alpha_depth == 0:
            return DXT1_ALPHA1              # "DXT3 但没有 alpha"（r_blp2.c:101）
        if alpha_depth in (4, 8):
            return DXT3
    elif alpha_encoding == 7:               # BLP_ALPHA_ENCODING_DXT5
        if alpha_depth == 8:
            return DXT5
    raise BlpError("BLP2：不支持的 DXT 头组合（alphaDepth=%d，alphaEncoding=%d）；"
                   "C 参考实现对此不解出任何像素（renderer/r_blp2.c:111）"
                   % (alpha_depth, alpha_encoding))


def _decode_raw_bgra_mip(data: bytes, offset: int, length: int, width: int,
                         height: int, level: int) -> bytes:
    """r_blp2.c:307：载荷就是 BGRA 像素数组，这里只做通道顺序归一。"""
    pixels = width * height
    if length < pixels * 4:
        raise BlpError("BLP2：原始 BGRA mip %d（%dx%d）被截断（需要 %d 字节，"
                       "只有 %d）" % (level, width, height, pixels * 4, length))
    src = data[offset:offset + pixels * 4]
    out = bytearray(pixels * 4)
    out[0::4] = src[2::4]
    out[1::4] = src[1::4]
    out[2::4] = src[0::4]
    out[3::4] = src[3::4]
    return bytes(out)


# --------------------------------------------------------------------------
# 调色板
# --------------------------------------------------------------------------
def _decode_paletted_mip(data: bytes, palette_offset: int, mip_offset: int,
                         mip_length: int, width: int, height: int,
                         alpha_bits: int, level: int, name: str) -> bytes:
    """把一个调色板 mip 级解成自上而下的 RGBA8（BlpIo.DecodePalettedMip）。"""
    pixels = width * height
    alpha_bytes = _palette_alpha_bytes(pixels, alpha_bits)
    if mip_length < pixels + alpha_bytes:
        raise BlpError("%s：mip %d（%dx%d）被截断（%d 个索引 + %d 字节 alpha "
                       "需要 %d 字节，只有 %d）"
                       % (name, level, width, height, pixels, alpha_bytes,
                          pixels + alpha_bytes, mip_length))

    palette = data[palette_offset:palette_offset + _PALETTE_BYTES]
    if len(palette) < _PALETTE_BYTES:
        raise BlpError("%s：调色板越界" % name)

    # 调色板按 BGRA 存放，alpha 平面在索引平面之后。
    red = bytes(palette[i * 4 + 2] for i in range(256))
    green = bytes(palette[i * 4 + 1] for i in range(256))
    blue = bytes(palette[i * 4 + 0] for i in range(256))

    indices = data[mip_offset:mip_offset + pixels]
    out = bytearray(pixels * 4)
    out[0::4] = indices.translate(red)
    out[1::4] = indices.translate(green)
    out[2::4] = indices.translate(blue)
    out[3::4] = _expand_paletted_alpha(data, mip_offset + pixels, pixels,
                                       alpha_bits)
    return bytes(out)


_ALPHA1_TABLE = tuple(bytes(255 if (b >> k) & 1 else 0 for k in range(8))
                      for b in range(256))
_ALPHA4_TABLE = tuple(bytes((((b & 0x0F) << 4) | (b & 0x0F),
                             ((b >> 4) << 4) | (b >> 4)))
                      for b in range(256))


def _expand_paletted_alpha(data: bytes, alpha_offset: int, pixels: int,
                           alpha_bits: int) -> bytes:
    """展开调色板的 alpha 平面（BlpIo.ExpandPalettedAlpha）。"""
    if alpha_bits == 0:
        # r_blp1.c:224：没有 alpha 平面时强制不透明。
        return b'\xff' * pixels
    if alpha_bits == 8:
        return bytes(data[alpha_offset:alpha_offset + pixels])
    if alpha_bits == 1:
        # r_blp1.c:234：LSB 在前，每字节 8 个像素。
        packed = data[alpha_offset:alpha_offset + (pixels + 7) // 8]
        return b''.join(_ALPHA1_TABLE[b] for b in packed)[:pixels]
    if alpha_bits == 4:
        # r_blp1.c:257：低半字节在前，展开成 (a << 4) | a。
        packed = data[alpha_offset:alpha_offset + (pixels + 1) // 2]
        return b''.join(_ALPHA4_TABLE[b] for b in packed)[:pixels]
    raise BlpError("不支持调色板 alpha 位数 %d（只支持 0/1/4/8）" % alpha_bits)


# --------------------------------------------------------------------------
# DXT / S3TC
# --------------------------------------------------------------------------
def _color565(color: int) -> Tuple[int, int, int]:
    """按 blp2_dxt_color()（r_blp2.c:228）展开 5-6-5。"""
    red = ((color >> 11) & 0x1F) * 255 // 31
    green = ((color >> 5) & 0x3F) * 255 // 63
    blue = (color & 0x1F) * 255 // 31
    return red, green, blue


def _color_block(data: bytes, block: int, four_color: bool) -> List[int]:
    """r_blp2.c:242：16 字节（4 条 RGBA）颜色表。"""
    c0 = data[block] | (data[block + 1] << 8)
    c1 = data[block + 2] | (data[block + 3] << 8)
    r0, g0, b0 = _color565(c0)
    r1, g1, b1 = _color565(c1)

    colors = [r0, g0, b0, 255, r1, g1, b1, 255]
    if four_color or c0 > c1:
        colors += [(2 * r0 + r1) // 3, (2 * g0 + g1) // 3, (2 * b0 + b1) // 3,
                   255,
                   (r0 + 2 * r1) // 3, (g0 + 2 * g1) // 3, (b0 + 2 * b1) // 3,
                   255]
    else:
        # r_blp2.c:268：3 色模式的第 4 项是全透明黑。
        colors += [(r0 + r1) // 2, (g0 + g1) // 2, (b0 + b1) // 2, 255,
                   0, 0, 0, 0]
    return colors


def _alpha_dxt3(data: bytes, block: int) -> bytearray:
    """r_blp2.c:272：16 个显式 4 位 alpha，低半字节在前。"""
    alpha = bytearray(16)
    for i in range(16):
        value = (data[block + i // 2] >> ((i & 1) * 4)) & 0x0F
        alpha[i] = (value << 4) | value
    return alpha


def _alpha_dxt5(data: bytes, block: int) -> bytearray:
    """r_blp2.c:279：插值出来的 DXT5 alpha。"""
    a0 = data[block]
    a1 = data[block + 1]
    table = bytearray(8)
    table[0] = a0
    table[1] = a1
    if a0 > a1:
        for i in range(1, 7):
            table[i + 1] = ((7 - i) * a0 + i * a1) // 7
    else:
        for i in range(1, 5):
            table[i + 1] = ((5 - i) * a0 + i * a1) // 5
        table[6] = 0
        table[7] = 255

    bits = int.from_bytes(data[block + 2:block + 8], 'little')
    alpha = bytearray(16)
    for i in range(16):
        alpha[i] = table[(bits >> (3 * i)) & 7]
    return alpha


def _decode_dxt(data: bytes, offset: int, length: int, width: int, height: int,
                dxt_format: int, level: int) -> bytes:
    """blp2_convert_dxt()（r_blp2.c:311-362）。"""
    blocks_x = (width + 3) // 4
    blocks_y = (height + 3) // 4
    block_size = 16 if dxt_format in (DXT3, DXT5) else 8
    required = blocks_x * blocks_y * block_size
    if length < required:
        raise BlpError("BLP2：DXT%d mip %d（%dx%d）被截断（%dx%d 个块需要 %d "
                       "字节，只有 %d）"
                       % (dxt_format, level, width, height, blocks_x, blocks_y,
                          required, length))

    # format != 1（DXT1 无 1 位 alpha、DXT3、DXT5）一律用 4 色表，只有 DXT1 的
    # 1 位 alpha 形态才按 c0 > c1 判定。
    four_color = dxt_format != DXT1_ALPHA1
    out = bytearray(width * height * 4)

    block = offset
    for by in range(blocks_y):
        for bx in range(blocks_x):
            alpha = None
            if dxt_format == DXT3:
                alpha = _alpha_dxt3(data, block)
                color_block = block + 8
                block += 16
            elif dxt_format == DXT5:
                alpha = _alpha_dxt5(data, block)
                color_block = block + 8
                block += 16
            else:
                color_block = block
                block += 8

            colors = _color_block(data, color_block, four_color)
            indices = _u32(data, color_block + 4)

            for py in range(4):
                y = by * 4 + py
                if y >= height:
                    continue
                row = (y * width) * 4
                for px in range(4):
                    x = bx * 4 + px
                    if x >= width:
                        continue
                    i = py * 4 + px
                    c = ((indices >> (2 * i)) & 3) * 4
                    # r_blp2.c:352：除 1 位 alpha 形态外，颜色表里的 alpha 一律
                    # 被块 alpha 表覆盖；1 位 alpha 形态用颜色表自己那一项（即
                    # 3 色模式的透明项，r_blp2.c:268）。
                    if dxt_format == DXT1_ALPHA1:
                        a = colors[c + 3]
                    elif alpha is not None:
                        a = alpha[i]
                    else:
                        a = 255
                    dst = row + x * 4
                    out[dst] = colors[c]
                    out[dst + 1] = colors[c + 1]
                    out[dst + 2] = colors[c + 2]
                    out[dst + 3] = a
    return bytes(out)


# --------------------------------------------------------------------------
# JPEG 辅助
# --------------------------------------------------------------------------
def _read_jpeg_band_count(jpeg: bytes) -> int:
    """SOF 里的分量数 Nf（BlpIo.ReadJpegBandCount），找不到返回 0。"""
    end = len(jpeg)
    pos = 0
    if pos + 1 < end and jpeg[pos] == 0xFF and jpeg[pos + 1] == 0xD8:
        pos += 2                                        # SOI

    while pos + 3 < end:
        if jpeg[pos] != 0xFF:
            pos += 1
            continue

        while pos < end and jpeg[pos] == 0xFF:           # 填充字节
            pos += 1
        if pos >= end:
            break
        marker = jpeg[pos]
        pos += 1

        if marker == 0xD8 or marker == 0x01 or 0xD0 <= marker <= 0xD7:
            continue
        if marker == 0xD9 or marker == 0xDA:            # EOI 或 SOS
            break

        if pos + 1 >= end:
            break
        segment_length = (jpeg[pos] << 8) | jpeg[pos + 1]

        is_sof = 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC)
        if is_sof:
            # marker, length(2), precision(1), height(2), width(2), Nf(1)
            nf_index = pos + 7
            return jpeg[nf_index] if nf_index < end else 0

        if segment_length < 2:
            break
        pos += segment_length

    return 0


def jpeg_size(data: bytes) -> Optional[Tuple[int, int]]:
    """JPEG 的 SOF 里的 (宽, 高)，取不到返回 None。"""
    if data[:2] != b'\xff\xd8':
        return None
    size = len(data)
    pos = 2
    while pos + 9 < size:
        if data[pos] != 0xFF:
            pos += 1
            continue
        marker = data[pos + 1]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height = (data[pos + 5] << 8) | data[pos + 6]
            width = (data[pos + 7] << 8) | data[pos + 8]
            return width, height
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            pos += 2
            continue
        if pos + 3 >= size:
            break
        segment_length = (data[pos + 2] << 8) | data[pos + 3]
        if segment_length < 2:
            break
        pos += 2 + segment_length
    return None


# --------------------------------------------------------------------------
# Blender 互操作
# --------------------------------------------------------------------------
def to_blender_pixels(rgba: bytes, width: int, height: int) -> List[float]:
    """自上而下的 RGBA 字节 → Blender 需要的自下而上的浮点列表。"""
    scale = 1.0 / 255.0
    pixels: List[float] = [0.0] * (width * height * 4)
    stride = width * 4
    for row in range(height):
        source = (height - 1 - row) * stride
        target = row * stride
        pixels[target:target + stride] = [value * scale
                                          for value in rgba[source:source + stride]]
    return pixels
