"""Warcraft III BLP1 专用 JPEG 解码器（baseline SOF0/SOF1 与 progressive SOF2）。

本模块是

    D:\\Dev\\C++\\open-realm\\Godot\\addons\\mdx_preview\\core\\Blp\\JpegWarcraft3Decoder.cs

的逐字 Python 移植；而那个 C# 文件本身又是 open-realm C 引擎
renderer/r_blp1.c 中打过补丁的 stb_image（编译开关
STBI_WARCRAFT3_BLP_JPEG_RGBA_BANDS，见 renderer/stb/stb_image.h:3957）的移植。
因此这里的每一步整数运算——stb__idct_block 的整数 IDCT、stb__build_huffman /
stb__build_fast_ac 的码表、stb__jpeg_decode_block(_prog_dc/_prog_ac) 的系数解码、
stb__parse_entropy_coded_data 的扫描状态机、stb__jpeg_finish 的 progressive 收尾——
都与 stb_image 的通用 C 实现逐位一致，输出字节可与 C 参考完全相同。

Warcraft III 把 JPEG 贴图存成 **4 分量** JPEG：四个分量就是原始的 B,G,R,A 波段，
不做任何颜色变换（SOF 的 Nf=4，SOS 的 Ns=4，所有分量都是 1x1 采样）。所以本模块
输出的是把分量交换成 {band2, band1, band0, band3} 之后的 RGBA，绝不经过
YCbCr/YCC 变换。

只实现游戏实际使用的形态：其它 SOF 变体（lossless/arithmetic/differential）、
12 位样本、分量下采样、restart interval、DNL 段、缺失的量化/Huffman 表、
畸形的扫描参数都会抛 JpegError 并给出确切原因，而不是产出一张错误的图。

对外 API：

    class JpegError(Exception)
    def band_count(jpeg: bytes) -> int          # SOF 的 Nf；找不到 SOF 返回 0
    def decode(jpeg: bytes) -> tuple[bytes, int, int]
                                                # (自上而下的 RGBA8 字节, width, height)

纯标准库实现（struct/math/typing），不依赖 numpy / Pillow / bpy。
"""

from __future__ import annotations

import math
import struct
from typing import Sequence, Tuple

__all__ = ["JpegError", "band_count", "decode"]


class JpegError(Exception):
    """Warcraft III JPEG 载荷无法解码时抛出（对应 C# 的 BlpException）。"""


# ------------------------------------------------------------------ 常量

_FAST_BITS = 9                 # C#: FastBits
_MAX_COMPONENTS = 4            # C#: MaxComponents
_MARKER_NONE = 0xFF            # C#: MarkerNone
_MAX_DIMENSION = 16384         # BlpIo.MaxDimension

# renderer/stb stb__jpeg_dezigzag (stb_image.h:2194)。
# C# 版本在后面补了 15 个 63 作为哨兵；完整照抄 79 项，避免任何越界路径的语义差异。
_ZIGZAG: Tuple[int, ...] = (
    0, 1, 8, 16, 9, 2, 3, 10,
    17, 24, 32, 25, 18, 11, 4, 5,
    12, 19, 26, 33, 40, 48, 41, 34,
    27, 20, 13, 6, 7, 14, 21, 28,
    35, 42, 49, 56, 57, 50, 43, 36,
    29, 22, 15, 23, 30, 37, 44, 51,
    58, 59, 52, 45, 38, 31, 39, 46,
    53, 60, 61, 54, 47, 55, 62, 63,
    63, 63, 63, 63, 63, 63, 63, 63,
    63, 63, 63, 63, 63, 63, 63,
)

# C#: BitMask，下标 0..16。
_BIT_MASK: Tuple[int, ...] = (
    0, 1, 3, 7, 15, 31, 63, 127, 255, 511, 1023, 2047, 4095, 8191, 16383, 32767, 65535,
)

# C#: JBias，下标 0..15。
_JBIAS: Tuple[int, ...] = (
    0, -1, -3, -7, -15, -31, -63, -127, -255, -511, -1023, -2047, -4095, -8191, -16383, -32767,
)


def _f32(value: float) -> float:
    """把 Python double 量化成 C# 的 float（IEEE-754 单精度）。"""
    return struct.unpack("<f", struct.pack("<f", value))[0]


def _f2f(literal: float) -> int:
    """复刻 C# 的 (int)(literal_f * 4096 + 0.5)。

    literal_f * 4096 是 float*int → float（4096 是 2 的幂，缩放精确），
    随后 + 0.5 提升为 double，最后向零截断。
    """
    scaled = _f32(_f32(literal) * 4096.0)
    return math.trunc(scaled + 0.5)


def _i16(value: int) -> int:
    """复刻 C# 的 unchecked((short)value)：截断到有符号 16 位。"""
    value &= 0xFFFF
    return value - 0x10000 if value >= 0x8000 else value


def _clamp(value: int) -> int:
    """C#: Clamp(int) —— 输出到 0..255。"""
    if value < 0:
        return 0
    if value > 255:
        return 255
    return value


# stb 的 IDCT 常数：C# 里的 static readonly int F2F_xxx。
_F2F_05411961 = _f2f(0.5411961)
_F2F_NEG1847759065 = _f2f(-1.847759065)
_F2F_0765366865 = _f2f(0.765366865)
_F2F_1175875602 = _f2f(1.175875602)
_F2F_0298631336 = _f2f(0.298631336)
_F2F_2053119869 = _f2f(2.053119869)
_F2F_3072711026 = _f2f(3.072711026)
_F2F_1501321110 = _f2f(1.501321110)
_F2F_NEG0899976223 = _f2f(-0.899976223)
_F2F_NEG2562915447 = _f2f(-2.562915447)
_F2F_NEG1961570560 = _f2f(-1.961570560)
_F2F_NEG0390180644 = _f2f(-0.390180644)


def _idct1d(s0: int, s1: int, s2: int, s3: int, s4: int, s5: int, s6: int, s7: int):
    """STBI__IDCT_1D (renderer/stb stb_image.h:2430) —— 整数、逐位一致。

    返回 (x0, x1, x2, x3, t0, t1, t2, t3)，对应 C# 的同名 out 参数。
    """
    p2 = s2
    p3 = s6
    p1 = (p2 + p3) * _F2F_05411961
    t2 = p1 + p3 * _F2F_NEG1847759065
    t3 = p1 + p2 * _F2F_0765366865
    p2 = s0
    p3 = s4
    t0 = (p2 + p3) * 4096
    t1 = (p2 - p3) * 4096
    x0 = t0 + t3
    x3 = t0 - t3
    x1 = t1 + t2
    x2 = t1 - t2
    t0 = s7
    t1 = s5
    t2 = s3
    t3 = s1
    p3 = t0 + t2
    p4 = t1 + t3
    p1 = t0 + t3
    p2 = t1 + t2
    p5 = (p3 + p4) * _F2F_1175875602
    t0 = t0 * _F2F_0298631336
    t1 = t1 * _F2F_2053119869
    t2 = t2 * _F2F_3072711026
    t3 = t3 * _F2F_1501321110
    p1 = p5 + p1 * _F2F_NEG0899976223
    p2 = p5 + p2 * _F2F_NEG2562915447
    p3 = p3 * _F2F_NEG1961570560
    p4 = p4 * _F2F_NEG0390180644
    t3 += p1 + p4
    t2 += p2 + p3
    t1 += p2 + p4
    t0 += p1 + p3
    return x0, x1, x2, x3, t0, t1, t2, t3


# ------------------------------------------------------------------ 数据结构


class _Component:
    """C#: Component —— 一个 JPEG 分量（波段）。"""

    __slots__ = (
        "id", "h", "v", "tq", "hd", "ha",
        "x", "y", "w2", "h2",
        "coeff_w", "coeff_h", "dc_pred", "plane", "coeff",
    )

    def __init__(self, cid: int) -> None:
        self.id = cid
        self.h = 1
        self.v = 1
        self.tq = 0
        self.hd = 0
        self.ha = 0
        self.x = 0            # 有效样本宽 (stb: img_comp[i].x)
        self.y = 0            # 有效样本高 (stb: img_comp[i].y)
        self.w2 = 0
        self.h2 = 0
        self.coeff_w = 0      # progressive：每行系数块数
        self.coeff_h = 0
        self.dc_pred = 0
        self.plane = bytearray()
        self.coeff = None


class _Huffman:
    """C#: Huffman —— 一张 Huffman 表（含 stb 的 FAST_BITS 加速表）。"""

    __slots__ = ("size", "code", "values", "maxcode", "delta", "fast", "fastac")

    def __init__(self) -> None:
        self.size = bytearray(257)
        self.code = [0] * 256
        self.values = bytearray(256)
        self.maxcode = [0] * 18
        self.delta = [0] * 18
        self.fast = bytearray(b"\xff" * (1 << _FAST_BITS))
        self.fastac = [0] * (1 << _FAST_BITS)


def _build_huffman(h: _Huffman, count: Sequence[int]) -> None:
    """renderer/stb stb__build_huffman，含 FAST_BITS 加速表。"""
    k = 0
    for i in range(16):
        for _ in range(count[i]):
            h.size[k] = i + 1
            k += 1
            if k >= 257:
                raise JpegError("BLP1 JPEG: bad Huffman size list.")
    h.size[k] = 0

    code = 0
    k = 0
    for j2 in range(1, 17):
        h.delta[j2] = k - code
        if h.size[k] == j2:
            while h.size[k] == j2:
                h.code[k] = code & 0xFFFF
                code += 1
                k += 1
            if code - 1 >= (1 << j2):
                raise JpegError("BLP1 JPEG: bad Huffman code lengths.")
        h.maxcode[j2] = (code << (16 - j2)) & 0xFFFFFFFF
        code = (code << 1) & 0xFFFFFFFF
    h.maxcode[17] = 0xFFFFFFFF

    total = k
    fast = h.fast
    for i in range(len(fast)):
        fast[i] = 255
    for i in range(total):
        s = h.size[i]
        if s <= _FAST_BITS:
            c = h.code[i] << (_FAST_BITS - s)
            m = 1 << (_FAST_BITS - s)
            for j3 in range(m):
                fast[c + j3] = i


def _build_fast_ac(h: _Huffman) -> None:
    """renderer/stb stb__build_fast_ac。"""
    fast = h.fast
    fastac = h.fastac
    for i in range(1 << _FAST_BITS):
        fastac[i] = 0
        fi = fast[i]
        if fi >= 255:
            continue

        rs = h.values[fi]
        run = (rs >> 4) & 15
        magbits = rs & 15
        ln = h.size[fi]
        if magbits == 0 or ln + magbits > _FAST_BITS:
            continue

        k = ((i << ln) & ((1 << _FAST_BITS) - 1)) >> (_FAST_BITS - magbits)
        m = 1 << (magbits - 1)
        if k < m:
            # C#: k += (int)(~0u << magbits) + 1  ==  k - (2^magbits - 1)
            k -= (1 << magbits) - 1
        if -128 <= k <= 127:
            fastac[i] = _i16((k * 256) + (run * 16) + (ln + magbits))


def _describe_sof(marker: int) -> str:
    """C#: DescribeSof。"""
    if marker == 0xC2:
        return "progressive"
    if marker == 0xC3:
        return "lossless"
    if marker in (0xC5, 0xC6, 0xC7):
        return "differential"
    if marker in (0xC9, 0xCA, 0xCB):
        return "arithmetic"
    if marker in (0xCD, 0xCE, 0xCF):
        return "arithmetic differential"
    return "unknown"


# ------------------------------------------------------------------ 解码器


class _Decoder:
    """C#: Decoder —— 对应 stb__decode_jpeg_image 的整套状态机。"""

    __slots__ = (
        "_data", "_end", "_pos",
        "_huff_dc", "_huff_ac", "_dequant", "_comp",
        "_img_x", "_img_y", "_img_n", "_h_max", "_v_max", "_mcu_x", "_mcu_y",
        "_scan_n", "_order", "_progressive", "_spec_start", "_spec_end",
        "_succ_high", "_succ_low", "_eob_run",
        "_code_buffer", "_code_bits", "_nomore", "_marker",
        "_block", "_idct",
    )

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._end = len(data)
        self._pos = 0

        self._huff_dc = [None] * 4
        self._huff_ac = [None] * 4
        self._dequant = [None] * 4
        self._comp = [None] * _MAX_COMPONENTS

        self._img_x = 0
        self._img_y = 0
        self._img_n = 0
        self._h_max = 1
        self._v_max = 1
        self._mcu_x = 0
        self._mcu_y = 0

        self._scan_n = 0
        self._order = [0] * _MAX_COMPONENTS

        self._progressive = False
        self._spec_start = 0
        self._spec_end = 0
        self._succ_high = 0
        self._succ_low = 0
        self._eob_run = 0

        self._code_buffer = 0
        self._code_bits = 0
        self._nomore = False
        self._marker = _MARKER_NONE

        self._block = [0] * 64
        self._idct = [0] * 64

    # -------------------------------------------------------------- 输入

    def _get8(self) -> int:
        """stb_image 的 stbi__get8()：到末尾后返回 0 且不再前进。"""
        if self._pos < self._end:
            b = self._data[self._pos]
            self._pos += 1
            return b
        return 0

    def _get16be(self) -> int:
        hi = self._get8()
        lo = self._get8()
        return (hi << 8) | lo

    def _skip(self, count: int) -> None:
        for _ in range(count):
            self._get8()

    def _skip_jpeg_junk_at_end(self) -> int:
        """renderer/stb stb__skip_jpeg_junk_at_end (stb_image.h:3389)。"""
        while self._pos < self._end:
            x = self._get8()
            while x == 0xFF:
                if self._pos >= self._end:
                    return _MARKER_NONE
                x = self._get8()
                if x != 0x00 and x != 0xFF:
                    return x
        return _MARKER_NONE

    def _get_marker(self) -> int:
        """C#: GetMarker —— 先吃缓存，再跳过 0xFF 填充字节。"""
        if self._marker != _MARKER_NONE:
            cached = self._marker
            self._marker = _MARKER_NONE
            return cached

        x = self._get8()
        if x != 0xFF:
            return _MARKER_NONE
        while x == 0xFF:
            x = self._get8()
        return x

    # ------------------------------------------------------------ 主流程

    def run(self):
        """C#: Run —— 解码并输出 (rgba, width, height)。"""
        self._parse_image()
        return self._build_rgba(), self._img_x, self._img_y

    def _parse_image(self) -> None:
        """renderer/stb stb__decode_jpeg_image (stb_image.h:3412)。

        走一遍 marker，解码遇到的每一个扫描。baseline 流有一到多个顺序扫描；
        progressive 流先是 DC 扫描，然后是 spectral-selection /
        successive-approximation 的 AC 扫描。
        """
        marker = self._get_marker()
        if marker != 0xD8:
            raise JpegError("BLP1 JPEG: expected SOI, found 0xFF%02X." % marker)

        have_frame = False
        scan_count = 0

        marker = self._get_marker()
        while marker != 0xD9:
            if marker in (0xC0, 0xC1, 0xC2):
                if have_frame:
                    raise JpegError("BLP1 JPEG: more than one frame header.")
                self._parse_frame_header(marker)
                have_frame = True
            elif 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                raise JpegError(
                    "BLP1 JPEG: marker 0xFF%02X (%s) is not supported; "
                    "only sequential (SOF0/SOF1) and progressive (SOF2) 8-bit streams are decoded."
                    % (marker, _describe_sof(marker))
                )
            elif marker == 0xDB:
                self._parse_quantization_tables()
            elif marker == 0xC4:
                self._parse_huffman_tables()
            elif marker == 0xDD:
                length = self._get16be()
                if length != 4:
                    raise JpegError("BLP1 JPEG: bad DRI length %d." % length)
                interval = self._get16be()
                if interval != 0:
                    raise JpegError("BLP1 JPEG: restart intervals (DRI) are not supported.")
            elif marker == 0xDA:
                if not have_frame:
                    raise JpegError("BLP1 JPEG: scan header before the frame header.")
                self._parse_scan_header()
                self._parse_entropy_coded_data()
                scan_count += 1

                # 熵解码器把下一个 marker 留在缓存里（比特刚好在边界耗尽时为 none）。
                if self._marker == _MARKER_NONE:
                    self._marker = self._skip_jpeg_junk_at_end()
                marker = self._get_marker()
                if 0xD0 <= marker <= 0xD7:
                    marker = self._get_marker()   # RSTn（不可达：DRI 已被拒绝）
                continue
            elif (0xE0 <= marker <= 0xEF) or marker == 0xFE:
                length = self._get16be()
                if length < 2:
                    raise JpegError("BLP1 JPEG: bad APP/COM length %d." % length)
                self._skip(length - 2)
            elif marker == 0xDC:
                raise JpegError("BLP1 JPEG: DNL segments are not supported.")
            elif marker == _MARKER_NONE:
                raise JpegError("BLP1 JPEG: unexpected end of data (expected EOI).")
            else:
                raise JpegError("BLP1 JPEG: unsupported marker 0xFF%02X." % marker)

            marker = self._get_marker()

        if scan_count == 0:
            raise JpegError("BLP1 JPEG: reached EOI before the image scan.")

        if self._progressive:
            self._finish_progressive()

    def _parse_frame_header(self, sof_marker: int) -> None:
        """C#: ParseFrameHeader —— renderer/stb stb__process_frame_header。"""
        self._progressive = sof_marker == 0xC2

        lf = self._get16be()
        if lf < 11:
            raise JpegError("BLP1 JPEG: bad SOF length %d." % lf)

        precision = self._get8()
        if precision != 8:
            raise JpegError("BLP1 JPEG: %d-bit samples are not supported (8-bit only)." % precision)

        self._img_y = self._get16be()
        self._img_x = self._get16be()
        if self._img_x == 0 or self._img_y == 0:
            raise JpegError("BLP1 JPEG: invalid frame size %dx%d." % (self._img_x, self._img_y))
        if self._img_x > _MAX_DIMENSION or self._img_y > _MAX_DIMENSION:
            raise JpegError("BLP1 JPEG: frame size %dx%d is too large." % (self._img_x, self._img_y))

        count = self._get8()
        if count != 4:
            raise JpegError(
                "BLP1 JPEG: expected the Warcraft III 4-component layout, found %d component(s)." % count
            )
        if lf != 8 + 3 * count:
            raise JpegError("BLP1 JPEG: bad SOF length %d for %d components." % (lf, count))

        self._img_n = count
        for i in range(count):
            comp = _Component(self._get8())
            sampling = self._get8()
            comp.h = sampling >> 4
            comp.v = sampling & 15
            comp.tq = self._get8()

            if comp.h != 1 or comp.v != 1:
                raise JpegError(
                    "BLP1 JPEG: component subsampling (%dx%d) is not supported; "
                    "Warcraft III BLP JPEGs use 1x1 sampling." % (comp.h, comp.v)
                )
            if comp.tq > 3:
                raise JpegError("BLP1 JPEG: bad quantization table index %d." % comp.tq)

            self._comp[i] = comp

        self._h_max = 1
        self._v_max = 1
        self._mcu_x = (self._img_x + 7) // 8
        self._mcu_y = (self._img_y + 7) // 8

        for i in range(count):
            # 1x1 采样：每个分量的平面覆盖整块补齐后的 MCU 网格，每像素一个样本
            # (renderer/stb stb__process_frame_header)。
            comp = self._comp[i]
            comp.x = self._img_x
            comp.y = self._img_y
            comp.w2 = self._mcu_x * 8
            comp.h2 = self._mcu_y * 8
            comp.plane = bytearray(comp.w2 * comp.h2)
            if self._progressive:
                comp.coeff_w = comp.w2 // 8
                comp.coeff_h = comp.h2 // 8
                comp.coeff = [0] * (comp.coeff_w * comp.coeff_h * 64)

    def _parse_quantization_tables(self) -> None:
        """C#: ParseQuantizationTables —— stb 把量化表按 de-zigzag 顺序存放。"""
        length = self._get16be() - 2
        while length > 0:
            pq = self._get8()
            precision = pq >> 4
            t = pq & 15
            if precision != 0 and precision != 1:
                raise JpegError("BLP1 JPEG: bad DQT precision %d." % precision)
            if t > 3:
                raise JpegError("BLP1 JPEG: bad DQT table index %d." % t)

            table = [0] * 64
            for i in range(64):
                table[_ZIGZAG[i]] = self._get16be() if precision != 0 else self._get8()
            self._dequant[t] = table
            length -= 129 if precision != 0 else 65

    def _parse_huffman_tables(self) -> None:
        """C#: ParseHuffmanTables。"""
        length = self._get16be() - 2
        while length > 0:
            tc = self._get8()
            th = tc & 15
            tc >>= 4
            if tc > 1 or th > 3:
                raise JpegError("BLP1 JPEG: bad DHT header (tc=%d, th=%d)." % (tc, th))

            counts = [0] * 16
            total = 0
            for i in range(16):
                counts[i] = self._get8()
                total += counts[i]
            if total > 256:
                raise JpegError("BLP1 JPEG: bad DHT symbol count.")
            length -= 17

            table = _Huffman()
            _build_huffman(table, counts)
            for i in range(total):
                table.values[i] = self._get8()
            if tc != 0:
                _build_fast_ac(table)

            if tc == 0:
                self._huff_dc[th] = table
            else:
                self._huff_ac[th] = table
            length -= total

    def _parse_scan_header(self) -> None:
        """C#: ParseScanHeader —— renderer/stb stb__process_scan_header。"""
        ls = self._get16be()
        self._scan_n = self._get8()
        if self._scan_n < 1 or self._scan_n > 4 or self._scan_n > self._img_n:
            raise JpegError("BLP1 JPEG: bad SOS component count %d." % self._scan_n)
        if ls != 6 + 2 * self._scan_n:
            raise JpegError("BLP1 JPEG: bad SOS length %d for %d components." % (ls, self._scan_n))

        for i in range(self._scan_n):
            cid = self._get8()
            q = self._get8()
            which = -1
            for c in range(self._img_n):
                if self._comp[c].id == cid:
                    which = c
                    break
            if which < 0:
                raise JpegError("BLP1 JPEG: SOS references unknown component id %d." % cid)

            comp = self._comp[which]
            comp.hd = q >> 4
            comp.ha = q & 15
            if comp.hd > 3:
                raise JpegError("BLP1 JPEG: bad DC Huffman selector.")
            if comp.ha > 3:
                raise JpegError("BLP1 JPEG: bad AC Huffman selector.")
            self._order[i] = which

        self._spec_start = self._get8()
        self._spec_end = self._get8()
        aa = self._get8()
        self._succ_high = aa >> 4
        self._succ_low = aa & 15

        if self._progressive:
            if (self._spec_start > 63 or self._spec_end > 63
                    or self._spec_start > self._spec_end
                    or self._succ_high > 13 or self._succ_low > 13):
                raise JpegError(
                    "BLP1 JPEG: bad progressive scan parameters (Ss=%d, Se=%d, Ah=%d, Al=%d)."
                    % (self._spec_start, self._spec_end, self._succ_high, self._succ_low)
                )
        else:
            if self._spec_start != 0:
                raise JpegError(
                    "BLP1 JPEG: bad SOS spectral selection Ss=%d for a baseline scan." % self._spec_start
                )
            if self._succ_high != 0 or self._succ_low != 0:
                raise JpegError("BLP1 JPEG: successive approximation in a baseline scan is not valid.")
            self._spec_end = 63

        # 只有本次扫描涉及的分量需要表；DC 扫描完全不需要 AC 表
        # （progressive 的 DC 扫描不携带 AC 码）。
        needs_ac = self._spec_start != 0
        for i in range(self._scan_n):
            comp = self._comp[self._order[i]]
            if needs_ac:
                if self._huff_ac[comp.ha] is None:
                    raise JpegError("BLP1 JPEG: missing AC Huffman table %d." % comp.ha)
            elif self._succ_high == 0 and self._huff_dc[comp.hd] is None:
                raise JpegError("BLP1 JPEG: missing DC Huffman table %d." % comp.hd)

            if self._dequant[comp.tq] is None:
                raise JpegError("BLP1 JPEG: missing quantization table %d." % comp.tq)

    # ------------------------------------------------------------ 比特流

    def _grow_buffer_unsafe(self) -> None:
        """C#: GrowBufferUnsafe —— stb__grow_buffer_unsafe。"""
        while True:
            b = 0 if self._nomore else self._get8()
            if b == 0xFF:
                c = self._get8()
                while c == 0xFF:
                    c = self._get8()
                if c != 0:
                    self._marker = c
                    self._nomore = True
                    return
            self._code_buffer = (self._code_buffer | (b << (24 - self._code_bits))) & 0xFFFFFFFF
            self._code_bits += 8
            if self._code_bits > 24:
                return

    def _huff_decode(self, h: _Huffman) -> int:
        """C#: HuffDecode —— stb__jpeg_huff_decode。"""
        if self._code_bits < 16:
            self._grow_buffer_unsafe()

        c = (self._code_buffer >> (32 - _FAST_BITS)) & ((1 << _FAST_BITS) - 1)
        k = h.fast[c]
        if k < 255:
            s = h.size[k]
            if s > self._code_bits:
                return -1
            self._code_buffer = (self._code_buffer << s) & 0xFFFFFFFF
            self._code_bits -= s
            return h.values[k]

        temp = self._code_buffer >> 16
        k = _FAST_BITS + 1
        while temp >= h.maxcode[k]:
            k += 1
        if k == 17:
            self._code_bits -= 16
            return -1
        if k > self._code_bits:
            return -1

        c = ((self._code_buffer >> (32 - k)) & _BIT_MASK[k]) + h.delta[k]
        if c < 0 or c >= 256:
            return -1

        self._code_bits -= k
        self._code_buffer = (self._code_buffer << k) & 0xFFFFFFFF
        return h.values[c]

    def _extend_receive(self, n: int) -> int:
        """C#: ExtendReceive —— stb__extend_receive (stb_image.h:2207)。"""
        if self._code_bits < n:
            self._grow_buffer_unsafe()
        if self._code_bits < n:
            return 0

        sgn = self._code_buffer >> 31
        # stbi_lrot(code_buffer, n)：循环左移，使低 n 位存放缓冲区的高 n 位。
        k = ((self._code_buffer << n) | (self._code_buffer >> (32 - n))) & 0xFFFFFFFF
        self._code_buffer = k & (~_BIT_MASK[n] & 0xFFFFFFFF)
        k &= _BIT_MASK[n]
        self._code_bits -= n
        return k + (_JBIAS[n] & (sgn - 1))

    def _get_bits(self, n: int) -> int:
        """renderer/stb stb__jpeg_get_bits (stb_image.h:2169)：无符号比特。"""
        if self._code_bits < n:
            self._grow_buffer_unsafe()
        if self._code_bits < n:
            return 0

        k = ((self._code_buffer << n) | (self._code_buffer >> (32 - n))) & 0xFFFFFFFF
        self._code_buffer = k & (~_BIT_MASK[n] & 0xFFFFFFFF)
        k &= _BIT_MASK[n]
        self._code_bits -= n
        return k

    def _get_bit(self) -> int:
        """renderer/stb stb__jpeg_get_bit (stb_image.h:2181)：返回 0 或 0x80000000。"""
        if self._code_bits < 1:
            self._grow_buffer_unsafe()
        if self._code_bits < 1:
            return 0

        k = self._code_buffer
        self._code_buffer = (self._code_buffer << 1) & 0xFFFFFFFF
        self._code_bits -= 1
        return k & 0x80000000

    # ------------------------------------------------------------ 熵解码

    def _reset_entropy_state(self) -> None:
        """renderer/stb stb__jpeg_reset (stb_image.h:2936)，每扫描一次。"""
        self._code_bits = 0
        self._code_buffer = 0
        self._nomore = False
        self._marker = _MARKER_NONE
        self._eob_run = 0
        for i in range(self._img_n):
            self._comp[i].dc_pred = 0

    def _parse_entropy_coded_data(self) -> None:
        """renderer/stb stb__parse_entropy_coded_data (stb_image.h:2949)。

        baseline 是一次顺序扫描（交错或非交错）；progressive 先解一个 DC 扫描，
        再按分量做 spectral-selection 的 AC 扫描。
        """
        self._reset_entropy_state()

        if self._progressive:
            if self._scan_n == 1:
                comp = self._comp[self._order[0]]
                blocks_x = (comp.x + 7) >> 3
                blocks_y = (comp.y + 7) >> 3
                for block_y in range(blocks_y):
                    for block_x in range(blocks_x):
                        data_offset = 64 * (block_x + block_y * comp.coeff_w)
                        if self._spec_start == 0:
                            self._decode_block_prog_dc(comp, data_offset)
                        else:
                            self._decode_block_prog_ac(comp, data_offset)
            else:
                # 交错的 progressive 扫描只携带 DC。
                for mcu_y in range(self._mcu_y):
                    for mcu_x in range(self._mcu_x):
                        for k in range(self._scan_n):
                            comp = self._comp[self._order[k]]
                            block_x = mcu_x * comp.h
                            block_y = mcu_y * comp.v
                            self._decode_block_prog_dc(comp, 64 * (block_x + block_y * comp.coeff_w))
            return

        if self._scan_n == 1:
            comp = self._comp[self._order[0]]
            blocks_x = (comp.x + 7) >> 3
            blocks_y = (comp.y + 7) >> 3
            for block_y in range(blocks_y):
                for block_x in range(blocks_x):
                    self._decode_block(comp)
                    self._idct_block(comp.plane, comp.w2 * (block_y * 8) + block_x * 8,
                                     comp.w2, self._block)
            return

        for mcu_y in range(self._mcu_y):
            for mcu_x in range(self._mcu_x):
                for k in range(self._scan_n):
                    comp = self._comp[self._order[k]]
                    x2 = mcu_x * 8
                    y2 = mcu_y * 8
                    self._decode_block(comp)
                    self._idct_block(comp.plane, comp.w2 * y2 + x2, comp.w2, self._block)

    def _decode_block_prog_dc(self, comp: _Component, data_offset: int) -> None:
        """renderer/stb stb__jpeg_decode_block_prog_dc (stb_image.h:2265)。

        DC 系数以 1 << Al 缩放存储，稍后在 _finish_progressive 里反量化。
        """
        if self._spec_end != 0:
            raise JpegError("BLP1 JPEG: progressive DC scan with Se != 0.")

        if self._code_bits < 16:
            self._grow_buffer_unsafe()

        data = comp.coeff
        if self._succ_high == 0:
            for i in range(64):
                data[data_offset + i] = 0

            t = self._huff_decode(self._huff_dc[comp.hd])
            if t < 0 or t > 15:
                raise JpegError("BLP1 JPEG: bad Huffman DC code.")

            diff = self._extend_receive(t) if t != 0 else 0
            dc = comp.dc_pred + diff
            comp.dc_pred = dc
            data[data_offset] = _i16(dc * (1 << self._succ_low))
        else:
            if self._get_bit() != 0:
                data[data_offset] = _i16(data[data_offset] + (1 << self._succ_low))

    def _decode_block_prog_ac(self, comp: _Component, data_offset: int) -> None:
        """renderer/stb stb__jpeg_decode_block_prog_ac (stb_image.h:2295)。"""
        if self._spec_start == 0:
            raise JpegError("BLP1 JPEG: progressive AC scan with Ss == 0.")

        data = comp.coeff
        hac = self._huff_ac[comp.ha]

        if self._succ_high == 0:
            shift = self._succ_low

            if self._eob_run != 0:
                self._eob_run -= 1
                return

            k = self._spec_start
            while True:
                if self._code_bits < 16:
                    self._grow_buffer_unsafe()
                c = (self._code_buffer >> (32 - _FAST_BITS)) & ((1 << _FAST_BITS) - 1)
                r = hac.fastac[c]
                if r != 0:
                    k += (r >> 4) & 15
                    s = r & 15
                    if s > self._code_bits:
                        raise JpegError("BLP1 JPEG: bad Huffman AC code.")
                    self._code_buffer = (self._code_buffer << s) & 0xFFFFFFFF
                    self._code_bits -= s
                    if k > 63:
                        raise JpegError("BLP1 JPEG: AC coefficient index out of range.")
                    zig = _ZIGZAG[k]
                    k += 1
                    data[data_offset + zig] = _i16((r >> 8) * (1 << shift))
                else:
                    rs = self._huff_decode(hac)
                    if rs < 0:
                        raise JpegError("BLP1 JPEG: bad Huffman AC code.")
                    s = rs & 15
                    run = rs >> 4
                    if s == 0:
                        if run < 15:
                            self._eob_run = 1 << run
                            if run != 0:
                                self._eob_run += self._get_bits(run)
                            self._eob_run -= 1
                            break
                        k += 16
                    else:
                        k += run
                        if k > 63:
                            raise JpegError("BLP1 JPEG: AC coefficient index out of range.")
                        zig = _ZIGZAG[k]
                        k += 1
                        data[data_offset + zig] = _i16(self._extend_receive(s) * (1 << shift))
                if k > self._spec_end:
                    break
        else:
            # 这些 AC 系数的 refinement 扫描。
            bit = 1 << self._succ_low

            if self._eob_run != 0:
                self._eob_run -= 1
                for k in range(self._spec_start, self._spec_end + 1):
                    p = data_offset + _ZIGZAG[k]
                    if data[p] != 0 and self._get_bit() != 0:
                        if (data[p] & bit) == 0:
                            if data[p] > 0:
                                data[p] = _i16(data[p] + bit)
                            else:
                                data[p] = _i16(data[p] - bit)
                return

            k2 = self._spec_start
            while True:
                rs = self._huff_decode(hac)
                if rs < 0:
                    raise JpegError("BLP1 JPEG: bad Huffman AC code.")
                s = rs & 15
                r = rs >> 4
                if s == 0:
                    if r < 15:
                        self._eob_run = (1 << r) - 1
                        if r != 0:
                            self._eob_run += self._get_bits(r)
                        r = 64   # 强制结束本块
                else:
                    if s != 1:
                        raise JpegError("BLP1 JPEG: bad refinement Huffman code.")
                    s = bit if self._get_bit() != 0 else -bit

                while k2 <= self._spec_end:
                    p = data_offset + _ZIGZAG[k2]
                    k2 += 1
                    if data[p] != 0:
                        if self._get_bit() != 0 and (data[p] & bit) == 0:
                            if data[p] > 0:
                                data[p] = _i16(data[p] + bit)
                            else:
                                data[p] = _i16(data[p] - bit)
                    elif r == 0:
                        data[p] = _i16(s)
                        break
                    else:
                        r -= 1
                if k2 > self._spec_end:
                    break

    def _finish_progressive(self) -> None:
        """renderer/stb stb__jpeg_finish (stb_image.h:3080)，只用于 progressive。"""
        for n in range(self._img_n):
            comp = self._comp[n]
            dequant = self._dequant[comp.tq]
            blocks_x = (comp.x + 7) >> 3
            blocks_y = (comp.y + 7) >> 3
            for block_y in range(blocks_y):
                for block_x in range(blocks_x):
                    data_offset = 64 * (block_x + block_y * comp.coeff_w)
                    for i in range(64):
                        comp.coeff[data_offset + i] = _i16(comp.coeff[data_offset + i] * dequant[i])
                    self._idct_block(comp.plane, comp.w2 * (block_y * 8) + block_x * 8,
                                     comp.w2, comp.coeff, data_offset)

    def _decode_block(self, comp: _Component) -> None:
        """C#: DecodeBlock —— renderer/stb stb__jpeg_decode_block (stb_image.h:2230)。"""
        hdc = self._huff_dc[comp.hd]
        hac = self._huff_ac[comp.ha]
        dequant = self._dequant[comp.tq]
        data = self._block

        if self._code_bits < 16:
            self._grow_buffer_unsafe()
        t = self._huff_decode(hdc)
        if t < 0 or t > 15:
            raise JpegError("BLP1 JPEG: bad Huffman DC code.")

        for i in range(64):
            data[i] = 0

        diff = self._extend_receive(t) if t != 0 else 0
        dc = comp.dc_pred + diff
        comp.dc_pred = dc
        data[0] = _i16(dc * dequant[0])

        k = 1
        while True:
            if self._code_bits < 16:
                self._grow_buffer_unsafe()
            c = (self._code_buffer >> (32 - _FAST_BITS)) & ((1 << _FAST_BITS) - 1)
            r = hac.fastac[c]
            if r != 0:
                k += (r >> 4) & 15
                s = r & 15
                if s > self._code_bits:
                    raise JpegError("BLP1 JPEG: bad Huffman AC code.")
                self._code_buffer = (self._code_buffer << s) & 0xFFFFFFFF
                self._code_bits -= s
                if k > 63:
                    raise JpegError("BLP1 JPEG: AC coefficient index out of range.")
                zig = _ZIGZAG[k]
                k += 1
                data[zig] = _i16((r >> 8) * dequant[zig])
            else:
                rs = self._huff_decode(hac)
                if rs < 0:
                    raise JpegError("BLP1 JPEG: bad Huffman AC code.")
                s = rs & 15
                run = rs >> 4
                if s == 0:
                    if rs != 0xF0:
                        break   # EOB
                    k += 16
                else:
                    k += run
                    if k > 63:
                        raise JpegError("BLP1 JPEG: AC coefficient index out of range.")
                    zig = _ZIGZAG[k]
                    k += 1
                    data[zig] = _i16(self._extend_receive(s) * dequant[zig])
            if k >= 64:
                break

    # --------------------------------------------------------------- IDCT

    def _idct_block(self, plane: bytearray, plane_offset: int, stride: int,
                    coefficients: Sequence[int], data_offset: int = 0) -> None:
        """renderer/stb stb__idct_block (stb_image.h:2467)。

        coefficients 要么是共享的 baseline 块缓冲（self._block），要么是
        progressive 分量系数数组在 data_offset 处的切片。
        """
        val = self._idct

        for i in range(8):
            d = data_offset + i
            if (coefficients[d + 8] == 0 and coefficients[d + 16] == 0
                    and coefficients[d + 24] == 0 and coefficients[d + 32] == 0
                    and coefficients[d + 40] == 0 and coefficients[d + 48] == 0
                    and coefficients[d + 56] == 0):
                dcterm = coefficients[d] * 4
                val[i] = val[i + 8] = val[i + 16] = val[i + 24] = dcterm
                val[i + 32] = val[i + 40] = val[i + 48] = val[i + 56] = dcterm
            else:
                x0, x1, x2, x3, t0, t1, t2, t3 = _idct1d(
                    coefficients[d], coefficients[d + 8], coefficients[d + 16],
                    coefficients[d + 24], coefficients[d + 32], coefficients[d + 40],
                    coefficients[d + 48], coefficients[d + 56])
                x0 += 512
                x1 += 512
                x2 += 512
                x3 += 512
                val[i + 0] = (x0 + t3) >> 10
                val[i + 56] = (x0 - t3) >> 10
                val[i + 8] = (x1 + t2) >> 10
                val[i + 48] = (x1 - t2) >> 10
                val[i + 16] = (x2 + t1) >> 10
                val[i + 40] = (x2 - t1) >> 10
                val[i + 24] = (x3 + t0) >> 10
                val[i + 32] = (x3 - t0) >> 10

        bias = 65536 + (128 << 17)
        for i in range(8):
            v = i * 8
            x0, x1, x2, x3, t0, t1, t2, t3 = _idct1d(
                val[v], val[v + 1], val[v + 2], val[v + 3],
                val[v + 4], val[v + 5], val[v + 6], val[v + 7])
            x0 += bias
            x1 += bias
            x2 += bias
            x3 += bias

            o = plane_offset + i * stride
            plane[o + 0] = _clamp((x0 + t3) >> 17)
            plane[o + 7] = _clamp((x0 - t3) >> 17)
            plane[o + 1] = _clamp((x1 + t2) >> 17)
            plane[o + 6] = _clamp((x1 - t2) >> 17)
            plane[o + 2] = _clamp((x2 + t1) >> 17)
            plane[o + 5] = _clamp((x2 - t1) >> 17)
            plane[o + 3] = _clamp((x3 + t0) >> 17)
            plane[o + 4] = _clamp((x3 - t0) >> 17)

    # --------------------------------------------------------------- 输出

    def _build_rgba(self) -> bytes:
        """renderer/stb stb_image.h:3957（STBI_WARCRAFT3_BLP_JPEG_RGBA_BANDS）。

        输出 {band2, band1, band0, band3}，即原始波段、不做 YCbCr 变换。
        1x1 采样下每个分量平面的一行就是输出的一行（stb 的 resample_row_1
        原样返回该行）。
        """
        w = self._img_x
        h = self._img_y
        rgba = bytearray(w * h * 4)
        p0 = self._comp[0].plane
        p1 = self._comp[1].plane
        p2 = self._comp[2].plane
        p3 = self._comp[3].plane
        w2 = self._comp[0].w2

        for y in range(h):
            row = y * w2
            out_row = y * w * 4
            # 等价于逐像素循环 out[x*4+0]=p2[row+x], +1=p1, +2=p0, +3=p3。
            rgba[out_row + 0: out_row + w * 4: 4] = p2[row: row + w]
            rgba[out_row + 1: out_row + w * 4: 4] = p1[row: row + w]
            rgba[out_row + 2: out_row + w * 4: 4] = p0[row: row + w]
            rgba[out_row + 3: out_row + w * 4: 4] = p3[row: row + w]

        return bytes(rgba)


# ------------------------------------------------------------------ 对外 API


def band_count(jpeg: bytes) -> int:
    """返回 SOF 段声明的分量数 Nf；找不到 SOF 时返回 0。

    与 C# 的 BlpIo.ReadJpegBandCount 同义，用段长度做通用 marker 遍历
    （SOF 一定出现在 SOS 之前，遇到 SOS/EOI 即可放弃）。
    """
    n = len(jpeg)
    if n < 4:
        return 0

    p = 2 if (jpeg[0] == 0xFF and jpeg[1] == 0xD8) else 0
    while p + 1 < n:
        if jpeg[p] != 0xFF:
            p += 1
            continue
        marker = jpeg[p + 1]
        if marker == 0xFF:
            p += 1
            continue
        if marker == 0x00:
            p += 2
            continue
        if marker == 0xD8 or 0xD0 <= marker <= 0xD7 or marker == 0x01:
            p += 2
            continue
        if marker == 0xD9 or marker == 0xDA:
            return 0
        if p + 4 > n:
            return 0

        length = (jpeg[p + 2] << 8) | jpeg[p + 3]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            # FF Cx | len(2) | precision(1) | Y(2) | X(2) | Nf(1)
            if p + 10 > n:
                return 0
            return jpeg[p + 9]
        if length < 2:
            return 0
        p += 2 + length
    return 0


def decode(jpeg: bytes) -> Tuple[bytes, int, int]:
    """解码 Warcraft III 风格的 4 分量 JPEG（baseline 或 progressive）。

    返回 (自上而下的 RGBA8 字节, width, height)，其中 R=band2, G=band1,
    B=band0, A=band3，不做任何颜色变换。
    """
    return _Decoder(jpeg).run()
