r"""MPQ (Mo'PaQ) 归档读取器，用于直接读取魔兽争霸3 自带的数据。

war3.mpq / War3x.mpq / War3Patch.mpq 里没解包成散装文件的贴图从归档里取，
纯 Python 实现，插件不需要额外的 DLL。

语义基准（注释里的行号都指这三份权威参考，它们是 open-realm C 引擎
common/mpq.c 与 vendor/blast/blast.c 的逐字节移植）：
    D:/Dev/C++/open-realm/Godot/addons/mdx_preview/core/Mpq/MpqArchive.cs
    D:/Dev/C++/open-realm/Godot/addons/mdx_preview/core/Mpq/MpqDecompress.cs
    D:/Dev/C++/open-realm/Godot/addons/mdx_preview/core/Mpq/MpqCrypto.cs

覆盖：格式版本 0/1 的头解析、归档基址搜索（.w3x/.w3m 前置头部）、
哈希/块表解密、按名查找（NAME_A/NAME_B 探测 + 全表扫描兜底）、
listfile 预载缓存、名字规范化、未压缩/单块/扇区三条读取路径、
zlib、Blizzard ADPCM(0x40/0x80)、自适应 Huffman(0x01) 及其组合(0x41/0x81)、
PKWare DCL implode(0x08 = Mark Adler 的 blast)，以及本插件保留的
bzip2(0x10) 与 sparse(0x20) 两个 A 没有的扩展分支。
"""

import bz2
import os
import struct
import zlib
from typing import Dict, List, Optional, Tuple

# --------------------------------------------------------------------------
# Storm 密码表
# --------------------------------------------------------------------------
def _gen_crypt_table() -> List[int]:
    """A MpqCrypto.cs:64-84 InitStormBuffer()。"""
    seed = 0x00100001
    table = [0] * 0x500
    for index1 in range(0x100):
        index2 = index1
        for _ in range(5):
            seed = (seed * 125 + 3) % 0x2AAAAB
            temp1 = (seed & 0xFFFF) << 0x10
            seed = (seed * 125 + 3) % 0x2AAAAB
            temp2 = seed & 0xFFFF
            table[index2] = (temp1 | temp2) & 0xFFFFFFFF
            index2 += 0x100
    return table


CRYPT = _gen_crypt_table()

# 哈希类型（A MpqCrypto.cs:10-16 MpqHashType）
HASH_TABLE_OFFSET = 0
HASH_NAME_A = 1
HASH_NAME_B = 2
HASH_FILE_KEY = 3

# 表密钥（A MpqCrypto.cs:48/51 MPQ_KEY_HASH_TABLE / MPQ_KEY_BLOCK_TABLE）
KEY_HASH_TABLE = 0xC3AF3770
KEY_BLOCK_TABLE = 0xEC83B3A3

# --------------------------------------------------------------------------
# 标志位（A MpqCrypto.cs:23-37 MpqFileFlags）
# --------------------------------------------------------------------------
MPQ_FILE_IMPLODE = 0x00000100
MPQ_FILE_COMPRESS = 0x00000200
MPQ_FILE_ENCRYPTED = 0x00010000
MPQ_FILE_FIX_KEY = 0x00020000
MPQ_FILE_KEY_V2 = MPQ_FILE_FIX_KEY
MPQ_FILE_PATCH_FILE = 0x00100000
MPQ_FILE_SINGLE_UNIT = 0x01000000
MPQ_FILE_DELETE_MARKER = 0x02000000
MPQ_FILE_SECTOR_CRC = 0x04000000
MPQ_FILE_EXISTS = 0x80000000

MPQ_FLAG_NAMES = [
    (MPQ_FILE_IMPLODE, 'IMPLODE'),
    (MPQ_FILE_COMPRESS, 'COMPRESS'),
    (MPQ_FILE_ENCRYPTED, 'ENCRYPTED'),
    (MPQ_FILE_FIX_KEY, 'FIX_KEY'),
    (MPQ_FILE_PATCH_FILE, 'PATCH'),
    (MPQ_FILE_SINGLE_UNIT, 'SINGLE_UNIT'),
    (MPQ_FILE_DELETE_MARKER, 'DELETED'),
    (MPQ_FILE_SECTOR_CRC, 'SECTOR_CRC'),
    (MPQ_FILE_EXISTS, 'EXISTS'),
]


def flag_str(flags: int) -> str:
    return '|'.join(n for b, n in MPQ_FLAG_NAMES if flags & b) or '0'


# --------------------------------------------------------------------------
# 名字与哈希
# --------------------------------------------------------------------------
_CANONICAL_KEY_CAPACITY = 1024     # A MpqCrypto.cs:59 char key[1024]


def _ascii_upper(ch: int) -> int:
    """A MpqCrypto.cs:86-92 AsciiToUpper()：a-z 转大写, '/' 折成 '\\'。"""
    if 0x61 <= ch <= 0x7A:
        return ch - 0x20
    if ch == 0x2F:                 # '/'
        return 0x5C                # '\\'
    return ch


def hash_string(name, hash_type: int) -> int:
    """Storm HashString（A MpqCrypto.cs:94-112）。字符按 C# 的 (byte) 强转截到 8 位。"""
    seed1 = 0x7FED7FED
    seed2 = 0xEEEEEEEE
    crypt = CRYPT
    base = hash_type << 8
    for ch in name:
        c = _ascii_upper(ord(ch) & 0xFF)
        seed1 = (crypt[base + c] ^ ((seed1 + seed2) & 0xFFFFFFFF)) & 0xFFFFFFFF
        seed2 = (c + seed1 + seed2 + (seed2 << 5) + 3) & 0xFFFFFFFF
    return seed1


def decrypt(data: bytes, key: int) -> bytes:
    """A MpqCrypto.cs:119-138 DecryptBlock()。

    只处理完整的 32 位字，尾部不足 4 字节的残留按原样保留（与 C 实现一致）。
    """
    seed1 = key & 0xFFFFFFFF
    seed2 = 0xEEEEEEEE
    buf = bytearray(data)
    n = len(buf) // 4
    unpack_from = struct.unpack_from
    pack_into = struct.pack_into
    crypt = CRYPT
    for i in range(n):
        seed2_base = (seed2 + crypt[0x400 + (seed1 & 0xFF)]) & 0xFFFFFFFF
        off = i << 2
        value = unpack_from('<I', buf, off)[0]
        value = (value ^ ((seed1 + seed2_base) & 0xFFFFFFFF)) & 0xFFFFFFFF
        seed1 = ((((~seed1 & 0xFFFFFFFF) << 0x15) + 0x11111111) & 0xFFFFFFFF) | (seed1 >> 0x0B)
        seed1 &= 0xFFFFFFFF
        seed2 = (value + seed2_base + (seed2_base << 5) + 3) & 0xFFFFFFFF
        pack_into('<I', buf, off, value)
    return bytes(buf)


def _normalize_mpq_path(s: str) -> str:
    """A MpqCrypto.cs:166-171 NormalizeMpqPath()：'/' 变成 '\\'。"""
    if not s:
        return s or ''
    if '/' not in s:
        return s
    return s.replace('/', '\\')


def _trim_edge_slashes(s: str) -> str:
    """A MpqCrypto.cs:174-183 TrimEdgeSlashes()：去掉两端的路径分隔符。"""
    if not s:
        return s or ''
    start = 0
    end = len(s)
    while end > start and (s[end - 1] == '\\' or s[end - 1] == '/'):
        end -= 1
    while start < end and (s[start] == '\\' or s[start] == '/'):
        start += 1
    if start == 0 and end == len(s):
        return s
    return s[start:end]


def _canonicalize_key(src: str) -> str:
    """A MpqCrypto.cs:190-206 CanonicalizeKey()：'/'->'\\'、A-Z 折小写、两端去分隔符。

    MPQ 名字大小写不敏感且用反斜杠分隔，所有查找都用这个规范形式。
    """
    if not src:
        return ''
    limit = min(len(src), _CANONICAL_KEY_CAPACITY - 1)
    out = []
    for i in range(limit):
        ch = src[i]
        if ch == '/':
            ch = '\\'
        elif 'A' <= ch <= 'Z':
            ch = chr(ord(ch) + 0x20)
        out.append(ch)
    return _trim_edge_slashes(''.join(out))


def _base_name(path: str) -> str:
    """A MpqCrypto.cs:209-217 BaseNamePtr()：最后一个分隔符之后的部分。

    这里不能用 os.path.basename：Linux/macOS 上它不认 '\\'，会把整条路径当成
    文件名，导致所有 ENCRYPTED 条目的 file key 算错。
    """
    if not path:
        return path or ''
    slash1 = path.rfind('\\')
    slash2 = path.rfind('/')
    if slash2 >= 0 and (slash1 < 0 or slash2 > slash1):
        return path[slash2 + 1:]
    if slash1 >= 0:
        return path[slash1 + 1:]
    return path


# --------------------------------------------------------------------------
# Blizzard ADPCM（A MpqDecompress.cs:297-391）
# --------------------------------------------------------------------------
_ADPCM_INIT_STEP = 44                              # A:300 MPQ_ADPCM_INIT_STEP

# A:303-307 mpq_adpcm_next[32]
_ADPCM_NEXT = [
    -1, 0, -1, 4, -1, 2, -1, 6, -1, 1, -1, 5, -1, 3, -1, 7,
    -1, 1, -1, 5, -1, 3, -1, 7, -1, 2, -1, 4, -1, 6, -1, 8,
]

# A:310-317 mpq_adpcm_step[89]
_ADPCM_STEP = [
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45,
    50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143, 157, 173, 190, 209, 230,
    253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796, 876, 963,
    1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327,
    3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442,
    11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794,
    32767,
]


def _write_short(out: bytearray, value: int) -> None:
    """A MpqDecompress.cs:387-391 Mpq_WriteShort()：小端 PCM16。"""
    out.append(value & 0xFF)
    out.append((value >> 8) & 0xFF)


def adpcm_decode(src: bytes, off: int, size: int, cap: int, channels: int) -> Tuple[bool, bytes]:
    """A MpqDecompress.cs:320-384 Mpq_AdpcmDecode()。

    src/off/size 指向 mask 字节之后的数据（与 A 的调用约定一致：
    入口处 src[off + 1] 是 shift，初始样本从 src[off + 2] 开始）。
    """
    if channels < 1 or channels > 2:
        return False, b''
    if size < 2 + channels * 2 or cap < channels * 2:
        return False, b''

    out = bytearray()
    cur = off + 2
    end = off + size
    shift = src[off + 1]
    channel = channels - 1
    predicted = [0, 0]
    step_index = [_ADPCM_INIT_STEP, _ADPCM_INIT_STEP]

    for i in range(channels):
        sample = src[cur] | (src[cur + 1] << 8)
        if sample >= 0x8000:                       # A 的 (short) 强转要做符号扩展
            sample -= 0x10000
        predicted[i] = sample
        cur += 2
        _write_short(out, predicted[i])

    while cur < end:
        code = src[cur]
        cur += 1
        channel = (channel + 1) % channels

        if code == 0x80:
            if step_index[channel] != 0:
                step_index[channel] -= 1
        elif code == 0x81:
            step_index[channel] += 8
            if step_index[channel] > 88:
                step_index[channel] = 88
            channel = (channel + 1) % channels
            continue
        else:
            step = _ADPCM_STEP[step_index[channel]]
            # A:364 的 step >> shift：C# 的 32 位右移会把位移计数按 32 取模
            # （shift 是原始字节，0..255），所以 shift >= 32 时要回绕成 shift & 31，
            # 否则 Python 会整体清零，与 A 不再一致。
            diff = step >> (shift & 31)
            for bit in range(6):
                if code & (1 << bit):
                    diff += step >> bit

            if code & 0x40:
                predicted[channel] -= diff
            else:
                predicted[channel] += diff
            if predicted[channel] < -32768:
                predicted[channel] = -32768
            if predicted[channel] > 32767:
                predicted[channel] = 32767

            step_index[channel] += _ADPCM_NEXT[code & 0x1F]
            if step_index[channel] < 0:
                step_index[channel] = 0
            if step_index[channel] > 88:
                step_index[channel] = 88

        if cap - len(out) < 2:
            break
        _write_short(out, predicted[channel])

    return (len(out) != 0), bytes(out)


# --------------------------------------------------------------------------
# 自适应 Huffman（A MpqDecompress.cs:393-641）
# --------------------------------------------------------------------------
def _build_profile7() -> List[int]:
    """A MpqDecompress.cs:396-408 mpq_huff_profile7[256]。"""
    table = [0] * 256
    first = [0xC3, 0xD9, 0xEF, 0x3D, 0xF9, 0x7C, 0xE9, 0x1E,
             0xFD, 0xAB, 0xF1, 0x2C, 0xFC, 0x5B, 0xFE, 0x17]
    mid = [0xBD, 0xD9, 0xEC, 0x3D, 0xF5, 0x7D, 0xE8, 0x1D,
           0xFB, 0xAE, 0xF0, 0x2C, 0xFB, 0x5C, 0xFF, 0x18]
    for i, v in enumerate(first):
        table[i] = v
    for i, v in enumerate(mid):
        table[64 + i] = v
    table[128] = 0x70
    table[129] = 0x6C
    return table


_HUFF_PROFILE7 = _build_profile7()

_HUFF_SYMBOL_COUNT = 258       # A:493
_HUFF_NODE_COUNT = 515         # A:494


class _BitReader:
    """A MpqDecompress.cs:453-483 mpqBitReader_t：LSB-first 位流。"""

    __slots__ = ('data', 'pos', 'end', 'bits', 'count')

    def __init__(self, data: bytes, offset: int, size: int):
        self.data = data
        self.pos = offset
        self.end = offset + size
        self.bits = 0
        self.count = 0

    def read(self, want: int) -> Tuple[bool, int]:
        while self.count < want:
            if self.pos >= self.end:
                return False, 0
            self.bits |= self.data[self.pos] << self.count
            self.pos += 1
            self.count += 8
        value = self.bits & ((1 << want) - 1)
        self.bits >>= want
        self.count -= want
        return True, value


class _HuffNode:
    """A MpqDecompress.cs:486-490 mpqHuffNode_t。"""

    __slots__ = ('next', 'prev', 'parent', 'low', 'value', 'weight')

    def __init__(self):
        self.next = None
        self.prev = None
        self.parent = None
        self.low = None
        self.value = 0
        self.weight = 0


class _HuffTree:
    """A MpqDecompress.cs:497-641 mpqHuffTree_t 及其 Mpq_Huff* 辅助函数。"""

    def __init__(self):
        self.head = _HuffNode()
        self._nodes = [_HuffNode() for _ in range(_HUFF_NODE_COUNT)]
        self.symbols = [None] * _HUFF_SYMBOL_COUNT
        self._used = 0

    # A:510-516 Mpq_HuffLink()
    def _link(self, at: _HuffNode, node: _HuffNode) -> None:
        node.next = at.next
        node.prev = at
        at.next.prev = node
        at.next = node

    # A:519-525 Mpq_HuffRemove()
    def _remove(self, node: _HuffNode) -> None:
        if node.next is None:
            return
        node.prev.next = node.next
        node.next.prev = node.prev
        node.next = None
        node.prev = None

    # A:528-537 Mpq_HuffNew()
    def _new(self, value: int, weight: int, at: _HuffNode) -> Optional[_HuffNode]:
        if self._used >= _HUFF_NODE_COUNT:
            return None
        node = self._nodes[self._used]
        self._used += 1
        node.next = node.prev = node.parent = node.low = None
        node.value = value
        node.weight = weight
        self._link(at, node)
        return node

    # A:540-545 Mpq_HuffHigher()
    def _higher(self, node: _HuffNode, weight: int) -> _HuffNode:
        while node is not self.head:
            if node.weight >= weight:
                return node
            node = node.prev
        return self.head

    # A:548-555 Mpq_HuffFix()
    def _fix(self, node: _HuffNode, max_weight: int) -> int:
        if node.weight >= max_weight:
            return node.weight
        higher = self._higher(self.head.prev, node.weight)
        self._remove(node)
        self._link(higher, node)
        return max_weight

    # A:558-596 Mpq_HuffBuild()
    def build(self, profile: int) -> bool:
        if profile != 7:                      # A:560 只支持 profile 7
            return False

        self._used = 0
        for i in range(_HUFF_SYMBOL_COUNT):
            self.symbols[i] = None
        head = self.head
        head.next = head
        head.prev = head
        head.parent = None
        head.low = None
        head.value = 0
        head.weight = 0

        max_weight = 0
        for i in range(256):
            if _HUFF_PROFILE7[i] == 0:
                continue
            node = self._new(i, _HUFF_PROFILE7[i], head)
            if node is None:
                return False
            self.symbols[i] = node
            max_weight = self._fix(node, max_weight)

        self.symbols[256] = self._new(256, 1, head.prev)
        self.symbols[257] = self._new(257, 1, head.prev)

        low = head.prev
        while low is not head:
            high = low.prev
            if high is head:
                break
            parent = self._new(0, high.weight + low.weight, head)
            if parent is None:
                return False
            low.parent = parent
            high.parent = parent
            parent.low = low
            max_weight = self._fix(parent, max_weight)
            low = high.prev

        return True

    # A:599-626 Mpq_HuffRebalance()
    def rebalance(self, node: Optional[_HuffNode]) -> bool:
        while node is not None:
            node.weight += 1
            higher = self._higher(node.prev, node.weight)
            swap = higher.next
            if swap is not node:
                # C 原版无条件解引用这些指针，损坏的树会崩；这里报解码失败。
                if swap is None or swap.parent is None or node.parent is None:
                    return False
                low = swap.parent.low
                parent = node.parent
                self._remove(swap)
                self._link(node, swap)
                self._remove(node)
                self._link(higher, node)

                if parent.low is node:
                    parent.low = swap
                if low is swap:
                    swap.parent.low = node
                node.parent = swap.parent
                swap.parent = parent
            node = node.parent
        return True

    # A:629-640 Mpq_HuffInsert()
    def insert(self, value: int) -> bool:
        escape = self.head.prev
        high = self._new(escape.value, escape.weight, self.head.prev)
        low = self._new(value, 0, self.head.prev)
        if high is None or low is None:
            return False
        high.parent = escape
        low.parent = escape
        escape.low = low
        self.symbols[value] = low
        return self.rebalance(low)


# 单线程运行（Blender 插件），与 A 的 [ThreadStatic] 复用一致：build() 会把整棵树重置。
_huff_tree = _HuffTree()


def huffman_decode(src: bytes, off: int, size: int, cap: int) -> Tuple[bool, bytes]:
    """A MpqDecompress.cs:416-450 Mpq_HuffDecode()：FGK 自适应树 + LSB-first 位流。"""
    out = bytearray()
    if cap <= 0 or size <= 0:
        return False, bytes(out)

    bits = _BitReader(src, off, size)
    ok, profile = bits.read(8)
    if not ok:
        return False, bytes(out)

    tree = _huff_tree
    if not tree.build(profile):
        return False, bytes(out)

    while len(out) < cap:
        node = tree.head.next
        while node.low is not None:
            ok, bit = bits.read(1)
            if not ok:
                return False, bytes(out)
            node = node.low.prev if bit else node.low

        value = node.value
        if value == 256:                       # A:437 结束符
            return True, bytes(out)
        if value == 257:                       # A:438-443 转义符：后面跟 8 位新字节
            ok, value = bits.read(8)
            if not ok or not tree.insert(value):
                return False, bytes(out)
            tree.rebalance(tree.symbols[value])

        out.append(value & 0xFF)

    return True, bytes(out)


def decompress_huffman(data: bytes, expected: int) -> bytes:
    """0x01 Huffman 的独立入口（载荷以 profile 字节开头）。"""
    cap = expected if expected > 0 else max(len(data) * 8, 256)
    return huffman_decode(data, 0, len(data), cap)[1]


# --------------------------------------------------------------------------
# PKWare DCL implode（A MpqDecompress.cs:643-918，即 Mark Adler 的 blast）
# --------------------------------------------------------------------------
_BLAST_MAX_BITS = 13
_BLAST_MAX_WIN = 4096


class _BlastInputExhausted(Exception):
    """A MpqDecompress.cs:682-686 BlastInputExhausted。"""


class _BlastState:
    """A MpqDecompress.cs:688-712 BlastState。"""

    __slots__ = ('src', 'pos', 'left', 'bitbuf', 'bitcnt', 'next', 'first',
                 'window', 'dst', 'dst_cap', 'dst_pos')

    def __init__(self, src, pos, left, dst_cap):
        self.src = src
        self.pos = pos
        self.left = left
        self.bitbuf = 0
        self.bitcnt = 0
        self.next = 0
        self.first = 1
        self.window = bytearray(_BLAST_MAX_WIN)
        self.dst = bytearray(dst_cap)
        self.dst_cap = dst_cap
        self.dst_pos = 0

    def flush(self) -> bool:
        """A MpqDecompress.cs:704-711 outfun 回调 Mpq_BlastOutput()。"""
        length = self.next
        if length > self.dst_cap - self.dst_pos:
            return True
        self.dst[self.dst_pos:self.dst_pos + length] = self.window[:length]
        self.dst_pos += length
        return False


def _blast_bits(s: _BlastState, need: int) -> int:
    """A MpqDecompress.cs:715-729 bits()：LSB-first 读位。"""
    val = s.bitbuf
    while s.bitcnt < need:
        if s.left == 0:
            raise _BlastInputExhausted()
        val |= s.src[s.pos] << s.bitcnt
        s.pos += 1
        s.left -= 1
        s.bitcnt += 8

    s.bitbuf = val >> need
    s.bitcnt -= need
    return val & ((1 << need) - 1)


class _BlastHuffman:
    """A MpqDecompress.cs:731-737 BlastHuffman。"""

    __slots__ = ('count', 'symbol')

    def __init__(self, symbol_count: int):
        self.count = [0] * (_BLAST_MAX_BITS + 1)
        self.symbol = [0] * symbol_count


def _blast_construct(h: _BlastHuffman, rep) -> None:
    """A MpqDecompress.cs:767-805 construct()：由 16 项长度表展开出码表。"""
    length = [0] * 256
    symbol = 0
    n = len(rep)
    idx = 0
    while True:
        v = rep[idx]
        idx += 1
        left = (v >> 4) + 1
        v &= 15
        while True:
            length[symbol] = v
            symbol += 1
            left -= 1
            if left == 0:
                break
        n -= 1
        if n == 0:
            break

    n = symbol
    h.count = [0] * (_BLAST_MAX_BITS + 1)
    for i in range(n):
        h.count[length[i]] += 1
    if h.count[0] == n:
        return

    remaining = 1
    for ln in range(1, _BLAST_MAX_BITS + 1):
        remaining <<= 1
        remaining -= h.count[ln]
        if remaining < 0:
            return

    offs = [0] * (_BLAST_MAX_BITS + 1)
    offs[1] = 0
    for ln in range(1, _BLAST_MAX_BITS):
        offs[ln + 1] = offs[ln] + h.count[ln]

    for i in range(n):
        if length[i] != 0:
            h.symbol[offs[length[i]]] = i
            offs[length[i]] += 1


def _blast_decode(s: _BlastState, h: _BlastHuffman) -> int:
    """A MpqDecompress.cs:808-846 decode()。"""
    bitbuf = s.bitbuf
    left = s.bitcnt
    code = 0
    first = 0
    index = 0
    ln = 1
    nxt = 1

    while True:
        while left != 0:
            left -= 1
            code |= (bitbuf & 1) ^ 1
            bitbuf >>= 1
            if nxt > _BLAST_MAX_BITS:          # 损坏的流：C 会越界读取，这里显式失败
                return -9
            count = h.count[nxt]
            nxt += 1
            if code < first + count:
                s.bitbuf = bitbuf
                s.bitcnt = (s.bitcnt - ln) & 7
                sym = index + (code - first)
                if sym < 0 or sym >= len(h.symbol):
                    return -9
                return h.symbol[sym]
            index += count
            first += count
            first <<= 1
            code <<= 1
            ln += 1

        left = (_BLAST_MAX_BITS + 1) - ln
        if left == 0:
            break
        if s.left == 0:
            raise _BlastInputExhausted()
        bitbuf = s.src[s.pos]
        s.pos += 1
        s.left -= 1
        if left > 8:
            left = 8

    return -9


_BLAST_LIT_CODE = _BlastHuffman(256)
_BLAST_LEN_CODE = _BlastHuffman(16)
_BLAST_DIST_CODE = _BlastHuffman(64)

# A MpqDecompress.cs:746-764 的一次性建表
_BLAST_LITLEN = [
    11, 124, 8, 7, 28, 7, 188, 13, 76, 4, 10, 8, 12, 10, 12, 10, 8, 23, 8,
    9, 7, 6, 7, 8, 7, 6, 55, 8, 23, 24, 12, 11, 7, 9, 11, 12, 6, 7, 22, 5,
    7, 24, 6, 11, 9, 6, 7, 22, 7, 11, 38, 7, 9, 8, 25, 11, 8, 11, 9, 12,
    8, 12, 5, 38, 5, 38, 5, 11, 7, 5, 6, 21, 6, 10, 53, 8, 7, 24, 10, 27,
    44, 253, 253, 253, 252, 252, 252, 13, 12, 45, 12, 45, 12, 61, 12, 45,
    44, 173,
]
_BLAST_LENLEN = [2, 35, 36, 53, 38, 23]
_BLAST_DISTLEN = [2, 20, 53, 230, 247, 151, 248]

_blast_construct(_BLAST_LIT_CODE, _BLAST_LITLEN)
_blast_construct(_BLAST_LEN_CODE, _BLAST_LENLEN)
_blast_construct(_BLAST_DIST_CODE, _BLAST_DISTLEN)

# A MpqDecompress.cs:848-849
_BLAST_BASE = [3, 2, 4, 5, 6, 7, 8, 9, 10, 12, 16, 24, 40, 72, 136, 264]
_BLAST_EXTRA_BITS = [0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8]


def _blast_decomp(s: _BlastState) -> int:
    """A MpqDecompress.cs:852-918 decomp()。"""
    lit = _blast_bits(s, 8)
    if lit > 1:                       # A:855 头部校验：字面量模式只能是 0/1
        return -1
    dct = _blast_bits(s, 8)
    if dct < 4 or dct > 6:            # A:857 字典位数必须是 4..6
        return -2

    while True:
        if _blast_bits(s, 1) != 0:
            symbol = _blast_decode(s, _BLAST_LEN_CODE)
            if symbol < 0 or symbol > 15:
                return symbol if symbol < 0 else -9
            length = _BLAST_BASE[symbol] + _blast_bits(s, _BLAST_EXTRA_BITS[symbol])
            if length == 519:         # A:866 EOS 标记
                break

            symbol = 2 if length == 2 else dct
            dec = _blast_decode(s, _BLAST_DIST_CODE)
            if dec < 0 or dec > 63:
                return dec if dec < 0 else -9
            dist = (dec << symbol) + _blast_bits(s, symbol) + 1
            if dist > _BLAST_MAX_WIN:
                return -3
            if s.first != 0 and dist > s.next:
                return -3

            while True:
                to = s.next
                frm = to - dist
                copy = _BLAST_MAX_WIN
                if s.next < dist:
                    frm += copy
                    copy = dist
                copy -= s.next
                if copy > length:
                    copy = length
                length -= copy
                s.next += copy
                for _ in range(copy):
                    s.window[to] = s.window[frm]
                    to += 1
                    frm += 1

                if s.next == _BLAST_MAX_WIN:
                    if s.flush():
                        return 1
                    s.next = 0
                    s.first = 0
                if length == 0:
                    break
        else:
            symbol = _blast_decode(s, _BLAST_LIT_CODE) if lit != 0 else _blast_bits(s, 8)
            s.window[s.next] = symbol & 0xFF
            s.next += 1
            if s.next == _BLAST_MAX_WIN:
                if s.flush():
                    return 1
                s.next = 0
                s.first = 0

    return 0


def blast(src: bytes, off: int, size: int, capacity: int) -> Tuple[int, bytes]:
    """A MpqDecompress.cs:649-677 blast()：返回 (C 错误码, 已解出的字节)。

    错误码 2 输入耗尽、1 输出溢出、0 成功、负数格式错误。
    """
    s = _BlastState(src, off, size, capacity)
    try:
        err = _blast_decomp(s)
    except _BlastInputExhausted:
        err = 2

    # 与 A:674 的 && 短路顺序一致：err != 0 时也会调用 flush()（副作用计入 outSize）。
    if err != 1 and s.next != 0 and s.flush() and err == 0:
        err = 1
    return err, bytes(s.dst[:s.dst_pos])


def explode(data: bytes, expected: int = 0) -> bytes:
    """0x08 PKWare DCL implode 的独立入口（载荷不含 mask 字节）。"""
    cap = expected if expected > 0 else (max(len(data) * 8, _BLAST_MAX_WIN) + _BLAST_MAX_WIN - 1)
    cap = ((cap + _BLAST_MAX_WIN - 1) // _BLAST_MAX_WIN) * _BLAST_MAX_WIN
    while cap <= (1 << 22):
        err, out = blast(data, 0, len(data), cap)
        if err == 0:
            return out
        if err != 1:
            return out
        cap *= 2
    return out


# --------------------------------------------------------------------------
# sparse（本插件独有扩展，A 没有 0x20 分支）
# --------------------------------------------------------------------------
def decompress_sparse(payload: bytes, expected: int) -> bytes:
    """0x20 sparse：载荷不含 mask 字节，约定与相邻分支一致。

    FF <count> <value> 表示连续 count 个 value，其余字节按字面量输出。
    """
    if expected <= 0:
        return b''
    out = bytearray(expected)
    pos = 0
    i = 0
    n = len(payload)
    while i < n and pos < expected:
        if payload[i] == 0xFF and i + 2 < n:
            count = payload[i + 1]
            value = payload[i + 2]
            i += 3
            for _ in range(count):
                if pos >= expected:
                    break
                out[pos] = value
                pos += 1
        else:
            out[pos] = payload[i]
            pos += 1
            i += 1
    return bytes(out)


# --------------------------------------------------------------------------
# zlib（A MpqDecompress.cs:35-137 与 225-257）
# --------------------------------------------------------------------------
def _adler32(data: bytes) -> int:
    """RFC1950 的 Adler-32；A:274-295 自算的同值实现。"""
    return zlib.adler32(data) & 0xFFFFFFFF


def _verify_zlib_trailer(src: bytes, off: int, size: int, produced: bytes) -> bool:
    """A MpqDecompress.cs:266-271 VerifyZlibTrailer()：输入末尾 4 字节是 Adler-32。"""
    if size < 6:
        return False
    expected = struct.unpack_from('>I', src, off + size - 4)[0]
    return _adler32(produced) == expected


def _inflate_zlib(src: bytes, off: int, size: int, cap: int) -> Tuple[bool, bytes]:
    """zlib 流（带 2 字节头 + Adler-32 尾）解压，等价于 C 的 uncompress()/TryInflate。"""
    if size <= 0 or cap <= 0:
        return False, b''
    try:
        inflater = zlib.decompressobj(15)
    except zlib.error:
        # A:62-73：只有 inflateInit() 本身失败才会退回 raw-deflate，而可用的 zlib
        # 永远不会这样失败。那份代码还明确拒绝“数据错误后再试 raw deflate”，
        # 因为 War3Patch.mpq 里 Maps/Campaign/*.w3m 的存储扇区首字节 0xD5
        # 恰好是合法的 deflate 块头，回退会把它们误判成压缩数据。
        return False, b''                      # 本移植不实现 raw-deflate 回退

    payload = src[off:off + size]
    try:
        out = inflater.decompress(payload, cap)
    except zlib.error:
        return False, b''

    if len(out) == cap:
        # A:115-118 输出刚好填满时，再多出一字节就算失败。
        try:
            if inflater.decompress(b'', 1):
                return False, b''
        except zlib.error:
            return False, b''

    if not inflater.eof:                       # A 要求 Z_STREAM_END
        return False, b''
    if not _verify_zlib_trailer(src, off, size, out):
        return False, b''
    return True, out


def try_inflate_sector(src: bytes, off: int, size: int, cap: int) -> Tuple[bool, bytes]:
    """A MpqDecompress.cs:40-137 TryInflateSector()：可剥掉前导 0x02 的 zlib 快路径。"""
    if size <= 0 or cap <= 0:
        return False, b''
    payload_off = off
    payload_size = size
    if size > 1 and src[off] == 0x02:
        payload_off += 1
        payload_size -= 1
    return _inflate_zlib(src, payload_off, payload_size, cap)


def try_decompress_sector(src: bytes, off: int, size: int, cap: int) -> Tuple[bool, bytes, Optional[str]]:
    """A MpqDecompress.cs:148-223 Mpq_DecompressSector()：按 mask 字节精确分派。

    A 用的是精确 switch，不支持的 mask 显式失败（返回 False 并给出原因），
    这里不再做任何“兜底再来一次”的猜测。
    """
    if size <= 0 or cap <= 0:
        return False, b'', None

    if size == cap:                            # A:156-162
        return True, bytes(src[off:off + size]), 'stored(src==dst)'

    mask = src[off]

    if mask == 0x08:                           # A:167-175 PKWare DCL implode
        err, out = blast(src, off + 1, size - 1, cap)
        if err == 0:
            return True, out, 'pkware'
        return False, b'', 'pkware-failed(err=%d)' % err

    if mask == 0x02:                           # A:177-185 纯 zlib 流（不剥 0x02）
        ok, out = _inflate_zlib(src, off + 1, size - 1, cap)
        if ok:
            return True, out, 'zlib(method-byte)'
        return False, b'', 'zlib-failed'

    if mask == 0x40 or mask == 0x80:           # A:187-198 ADPCM
        channels = 2 if mask == 0x80 else 1
        ok, out = adpcm_decode(src, off + 1, size - 1, cap, channels)
        if ok:
            return True, out, 'adpcm-stereo' if channels == 2 else 'adpcm-mono'
        return False, b'', 'adpcm-failed'

    if mask == 0x41 or mask == 0x81:           # A:200-217 Huffman + ADPCM
        channels = 2 if (mask & 0x80) else 1
        ok, tmp = huffman_decode(src, off + 1, size - 1, cap)
        if not ok:
            return False, b'', 'huffman-failed'
        ok, out = adpcm_decode(tmp, 0, len(tmp), cap, channels)
        if not ok:
            return False, b'', 'huffman+adpcm-failed'
        return True, out, 'huffman+adpcm-stereo' if channels == 2 else 'huffman+adpcm-mono'

    # 以下两个是 A 没有的扩展分支，保留本插件原有能力。
    if mask == 0x10:                           # bzip2（B 独有）
        try:
            out = bz2.decompress(src[off + 1:off + size])
        except Exception:
            return False, b'', 'bzip2-failed'
        return True, out, 'bzip2'

    if mask == 0x20:                           # sparse（B 独有）
        return True, decompress_sparse(src[off + 1:off + size], cap), 'sparse'

    return False, b'', 'unsupported sector compression mask 0x%02X' % mask


# --------------------------------------------------------------------------
# 归档
# --------------------------------------------------------------------------
_SIGNATURE_PROBE_SIZE = 1024        # A MpqArchive.cs:92
_SECTOR_SIZE_SHIFT_MAX = 15         # A MpqArchive.cs:88
_BLOCK_INDEX_MASK = 0x0FFFFFFF      # A MpqArchive.cs:80
_HASH_ENTRY_DELETED = 0xFFFFFFFE    # A MpqArchive.cs:78
_HASH_ENTRY_FREE = 0xFFFFFFFF       # A MpqArchive.cs:79
_INT_MAX = 0x7FFFFFFF


def _sector_table_looks_valid(offsets, sector_count: int, compressed_size: int) -> bool:
    """A MpqArchive.cs:752-764 SectorTableLooksValid()。"""
    if not offsets or sector_count == 0:
        return False
    if offsets[0] == 0 or offsets[0] > compressed_size:
        return False
    for i in range(sector_count):
        if offsets[i] > offsets[i + 1]:
            return False
        if offsets[i + 1] > compressed_size:
            return False
    return True


def _split_listfile(data: bytes) -> List[str]:
    """A MpqArchive.cs:482-504 SplitListfile()：CR/LF 分行、Latin1 解码、规范化路径。"""
    names: List[str] = []
    i = 0
    length = len(data)
    while i < length:
        while i < length and (data[i] == 0x0D or data[i] == 0x0A):
            i += 1
        if i >= length:
            break
        start = i
        while i < length and data[i] != 0x0D and data[i] != 0x0A:
            i += 1
        line = data[start:i].decode('latin-1')
        line = _normalize_mpq_path(line)
        line = _trim_edge_slashes(line)
        if not line:
            continue
        names.append(line)
    return names


class MPQArchive:
    """只读 MPQ 归档。"""

    HASH_ENTRY_FREE = _HASH_ENTRY_FREE
    HASH_ENTRY_DELETED = _HASH_ENTRY_DELETED
    BLOCK_INDEX_MASK = _BLOCK_INDEX_MASK

    def __init__(self, path: str):
        self.path = path
        self.f = open(path, 'rb')
        self._source_length = os.fstat(self.f.fileno()).st_size
        self._lookup_cache: Dict[str, int] = {}         # 规范名 -> 块下标
        self._hash_pair_index: Dict[Tuple[int, int], str] = {}
        self._listfile: Optional[List[str]] = None      # None = 尚未构建
        self._name_cache: Dict[str, Optional[str]] = {}
        try:
            self._read_header()
            self._read_tables()
        except Exception:
            try:
                self.f.close()
            except Exception:
                pass
            raise

    # ---- 原始读取 ----------------------------------------------------
    def _read_range(self, offset: int, count: int) -> bytes:
        """A MpqArchive.cs:798-817 ReadAt()，含边界检查。"""
        if count == 0:
            return b''
        if offset < 0 or offset + count > self._source_length:
            raise ValueError('读取 %d 字节 @%d 超出归档范围（%d 字节）'
                             % (count, offset, self._source_length))
        self.f.seek(offset)
        data = self.f.read(count)
        if len(data) != count:
            raise ValueError('归档在 %d 处意外结束（应有 %d 字节，实得 %d）'
                             % (offset, count, len(data)))
        return data

    def _try_read_range(self, offset: int, count: int):
        """A MpqArchive.cs:819-830 TryReadRange()：把失败当作返回值。"""
        try:
            return self._read_range(offset, count), None
        except (OSError, ValueError) as exc:
            return None, str(exc)

    # ---- 头与表 -----------------------------------------------------
    def _find_signature(self) -> int:
        """A MpqArchive.cs:768-784 FindArchiveSignature()：只在前 1024 字节里找签名。

        .w3x/.w3m 的 MPQ 前面还有 512 字节地图头，所以归档基址不一定是 0。
        """
        probe_length = min(_SIGNATURE_PROBE_SIZE, self._source_length)
        probe = self._read_range(0, probe_length) if probe_length > 0 else b''
        index = probe.find(b'MPQ\x1a')
        if index < 0:
            raise ValueError('%s: 前 %d 字节内没有 MPQ 签名' % (self.path, probe_length))
        return index

    def _read_header(self) -> None:
        """A MpqArchive.cs:126-159。"""
        self.base_offset = self._find_signature()
        header = self._read_range(self.base_offset, 32)

        (hdr_size, archive_size, fmt, block_shift,
         hash_pos, block_pos, hash_size, block_size) = struct.unpack_from('<IIHHIIII', header, 4)

        self.header_size = hdr_size
        self.archive_size = archive_size
        self.format_version = fmt
        self.block_shift = block_shift

        if block_shift > _SECTOR_SIZE_SHIFT_MAX:
            raise ValueError('%s: 不支持的 wSectorSizeShift %d（上限 %d）'
                             % (self.path, block_shift, _SECTOR_SIZE_SHIFT_MAX))
        self.sector_size = 1 << (block_shift + 9)

        self.hash_table_pos = hash_pos
        self.block_table_pos = block_pos
        self.hash_table_size = hash_size
        self.block_table_size = block_size

        if hash_size == 0:
            raise ValueError('%s: 空哈希表' % self.path)
        if block_size == 0:
            raise ValueError('%s: 空块表' % self.path)

        self._require_within_source(hash_pos, hash_size * 16, '哈希表')
        self._require_within_source(block_pos, block_size * 16, '块表')

    def _require_within_source(self, relative_offset: int, length: int, what: str) -> None:
        """A MpqArchive.cs:786-791 RequireWithinSource()。"""
        end = self.base_offset + relative_offset + length
        if end > self._source_length:
            raise ValueError('%s: %s 超出归档末尾（%d > %d）'
                             % (self.path, what, end, self._source_length))

    def _read_tables(self) -> None:
        """A MpqArchive.cs:161-169：两张表都用固定密钥解密，表位置相对归档基址。"""
        raw = self._read_range(self.base_offset + self.hash_table_pos, self.hash_table_size * 16)
        raw = decrypt(raw, KEY_HASH_TABLE)
        self.hash_entries = [struct.unpack_from('<IIHHI', raw, i * 16)
                             for i in range(self.hash_table_size)]

        raw = self._read_range(self.base_offset + self.block_table_pos, self.block_table_size * 16)
        raw = decrypt(raw, KEY_BLOCK_TABLE)
        self.block_entries = [struct.unpack_from('<IIII', raw, i * 16)
                              for i in range(self.block_table_size)]

    # ---- 查找 -------------------------------------------------------
    def _find_block_index(self, hash1: int, hash2: int, locale: Optional[int] = None):
        """A MpqArchive.cs:360-399 FindBlockIndex()：探测 + 全表扫描兜底。

        返回 (块下标, 哈希表槽位)，找不到时是 (None, None)。
        """
        if self.hash_table_size == 0:
            return None, None

        mask = self.hash_table_size - 1
        hash_pos = hash1 & mask
        entries = self.hash_entries

        for index in range(self.hash_table_size):
            slot = (hash_pos + index) & mask
            entry = entries[slot]
            entry_block = entry[4]

            if entry_block == _HASH_ENTRY_FREE:
                break
            if entry_block == _HASH_ENTRY_DELETED:
                continue
            if entry[0] == hash1 and entry[1] == hash2:
                if locale is not None and entry[2] != locale:
                    continue
                return entry_block & _BLOCK_INDEX_MASK, slot

        # 第二遍全表扫描（A:385-396）：探测被 free 槽位挡住时仍能命中。
        for index in range(self.hash_table_size):
            entry = entries[index]
            entry_block = entry[4]
            if entry_block == _HASH_ENTRY_DELETED or entry_block == _HASH_ENTRY_FREE:
                continue
            if entry[0] == hash1 and entry[1] == hash2:
                if locale is not None and entry[2] != locale:
                    continue
                return entry_block & _BLOCK_INDEX_MASK, index

        return None, None

    def _resolve(self, name: str, locale: Optional[int] = None):
        """A MpqArchive.cs:328-353 TryResolveEntry()：规范化 + listfile 缓存 + 哈希探测。"""
        canonical = _canonicalize_key(name)
        if not canonical:
            return None, canonical

        self._ensure_listfile_index()

        cached = self._lookup_cache.get(canonical)
        if cached is not None:
            return (cached, canonical) if cached < self.block_table_size else (None, canonical)

        hash1 = hash_string(canonical, HASH_NAME_A)
        hash2 = hash_string(canonical, HASH_NAME_B)
        block_index, _slot = self._find_block_index(hash1, hash2, locale)
        if block_index is None:
            return None, canonical
        self._lookup_cache[canonical] = block_index
        if block_index >= self.block_table_size:
            return None, canonical
        return block_index, canonical

    def _resolve_direct(self, name: str):
        """A MpqArchive.cs:463-473 TryResolveEntryDirect()：不查 listfile 缓存，避免递归。"""
        canonical = _canonicalize_key(name)
        if not canonical:
            return None, canonical
        hash1 = hash_string(canonical, HASH_NAME_A)
        hash2 = hash_string(canonical, HASH_NAME_B)
        block_index, _slot = self._find_block_index(hash1, hash2)
        if block_index is None or block_index >= self.block_table_size:
            return None, canonical
        return block_index, canonical

    def find(self, name: str, locale: Optional[int] = None) -> Optional[int]:
        """条目名对应的块表下标，找不到返回 None。"""
        block_index, _canonical = self._resolve(name, locale)
        return block_index

    def has_file(self, name: str) -> bool:
        try:
            return self.find(name) is not None
        except Exception:
            return False

    def block_info(self, blk: int) -> dict:
        off, asize, fsize, flags = self.block_entries[blk]
        return {'index': blk, 'offset': off, 'archived_size': asize,
                'file_size': fsize, 'flags': flags, 'flag_str': flag_str(flags)}

    def _file_key(self, canonical_name: str, blk: int) -> int:
        """A MpqArchive.cs:536-546：file key 用 basename，FIX_KEY 再混入偏移与大小。"""
        off, _asize, fsize, flags = self.block_entries[blk]
        key = hash_string(_base_name(canonical_name), HASH_FILE_KEY)
        if flags & MPQ_FILE_FIX_KEY:
            key = ((key + off) ^ fsize) & 0xFFFFFFFF
        return key

    # ---- 读取 -------------------------------------------------------
    def read_file(self, name: str, locale: Optional[int] = None) -> Optional[bytes]:
        """A MpqArchive.cs:256-267 ReadFile()：找不到返回 None，解码失败抛 ValueError。"""
        blk, canonical = self._resolve(name, locale)
        if blk is None:
            return None
        data, error = self._read_entry(blk, canonical)
        if error is not None:
            raise ValueError("无法读取 '%s'：%s" % (name, error))
        return data

    def read_block(self, blk: int, name: Optional[str] = None) -> Optional[bytes]:
        """按块表下标注取。加密块必须给出条目名才能推导 file key。"""
        if blk < 0 or blk >= self.block_table_size:
            raise ValueError('块索引 %d 超出块表范围（%d 项）' % (blk, self.block_table_size))
        flags = self.block_entries[blk][3]
        if flags & MPQ_FILE_DELETE_MARKER:
            return None

        canonical = _canonicalize_key(name) if name else ''
        if not canonical and (flags & MPQ_FILE_ENCRYPTED):
            raise ValueError('块 %d 已加密，必须提供条目名' % blk)

        data, error = self._read_entry(blk, canonical)
        if error is not None:
            raise ValueError('无法读取块 %d：%s' % (blk, error))
        return data

    def _read_entry(self, block_index: int, canonical_name: str):
        """A MpqArchive.cs:512-564 ReadEntry()：三段式——未压缩 / 单块 / 扇区。"""
        if block_index >= self.block_table_size:
            return None, '块索引 %d 超出块表范围（%d 项）' % (block_index, self.block_table_size)

        offset, block_size, file_size, flags = self.block_entries[block_index]

        if file_size > _INT_MAX or block_size > _INT_MAX:
            return None, ('文件过大（size=%d, compressed=%d）' % (file_size, block_size))

        if file_size == 0:
            return b'', None

        file_key = 0
        if flags & MPQ_FILE_ENCRYPTED:
            file_key = self._file_key(canonical_name, block_index)

        # A:548-558：只看 COMPRESS(0x200)。没有这一位就是原样存储的明文区间，
        # 不能再去嗅探内容或当成扇区表解析。
        if not (flags & MPQ_FILE_COMPRESS):
            plain, error = self._try_read_range(offset, file_size)
            if error is not None:
                return None, error
            if flags & MPQ_FILE_ENCRYPTED:
                plain = decrypt(plain, file_key)
            return plain, None

        if flags & MPQ_FILE_SINGLE_UNIT:
            return self._read_single_unit(offset, block_size, file_size, flags, file_key)

        return self._read_sectors(offset, block_size, file_size, flags, file_key)

    def _read_single_unit(self, offset: int, block_size: int, file_size: int,
                          flags: int, file_key: int):
        """A MpqArchive.cs:573-624 ReadSingleUnit()。"""
        if block_size == 0:
            return None, '单块条目的压缩大小为 0'

        compressed, error = self._try_read_range(offset, block_size)
        if error is not None:
            return None, error

        ok, produced = try_inflate_sector(compressed, 0, block_size, file_size)
        method = 'zlib'

        if not ok and (flags & MPQ_FILE_ENCRYPTED):
            # C 版会整块解密后重试一次。
            compressed = decrypt(compressed, file_key)
            ok, produced = try_inflate_sector(compressed, 0, block_size, file_size)
            if ok:
                method += '+decrypted'

        if not ok and block_size >= file_size:
            produced = compressed[:file_size]
            ok = True
            method = 'stored(block>=file)'

        if not ok:
            return None, ('单块解压失败（compressed=%d, size=%d, flags=0x%08X）'
                          % (block_size, file_size, flags))

        if len(produced) != file_size:
            return None, ('单块数据被截断：只解出 %d/%d 字节（%s）'
                          % (len(produced), file_size, method))
        return produced, None

    def _read_sectors(self, offset: int, block_size: int, file_size: int,
                      flags: int, file_key: int):
        """A MpqArchive.cs:627-749 ReadSectors()。"""
        sector_size = self.sector_size
        sector_count = (file_size + sector_size - 1) // sector_size
        offset_count = sector_count + 1

        if offset_count > _INT_MAX // 4:
            return None, '扇区表大得不合理（%d 个偏移）' % offset_count

        # A:634-643 SECTOR_CRC 不额外占表项，直接忽略该标志。
        offset_bytes, error = self._try_read_range(offset, offset_count * 4)
        if error is not None:
            return None, error

        offsets = list(struct.unpack_from('<%dI' % offset_count, offset_bytes, 0))
        valid = _sector_table_looks_valid(offsets, sector_count, block_size)

        if not valid and (flags & MPQ_FILE_ENCRYPTED):
            # 加密文件的扇区偏移表用 fileKey - 1 加密；先用原 key 试，再重解一次。
            offset_bytes = decrypt(offset_bytes, (file_key - 1) & 0xFFFFFFFF)
            offsets = list(struct.unpack_from('<%dI' % offset_count, offset_bytes, 0))
            valid = _sector_table_looks_valid(offsets, sector_count, block_size)

        if not valid:
            return None, ('非法的扇区偏移表（%d 个扇区, compressed=%d, flags=0x%08X）'
                          % (sector_count, block_size, flags))

        result = bytearray()
        written = 0

        for sector in range(sector_count):
            if written >= file_size:
                break

            start_offset = offsets[sector]
            end_offset = offsets[sector + 1]
            if end_offset < start_offset:
                return None, ('扇区 %d 的偏移表倒退了（%d > %d）'
                              % (sector, start_offset, end_offset))

            compressed_size = end_offset - start_offset
            uncompressed_size = sector_size
            if sector == sector_count - 1:
                tail = file_size % sector_size
                if tail != 0:
                    uncompressed_size = tail
            if uncompressed_size > sector_size:
                uncompressed_size = sector_size

            compressed, error = self._try_read_range(offset + start_offset, compressed_size)
            if error is not None:
                return None, error

            if flags & MPQ_FILE_ENCRYPTED:
                compressed = decrypt(compressed, (file_key + sector) & 0xFFFFFFFF)

            mask_error = None
            # A:695-713 的顺序：zlib 快路径 -> mask 分派 -> 原样存储。
            ok, produced = try_inflate_sector(compressed, 0, compressed_size, uncompressed_size)
            method = 'zlib'
            if not ok:
                ok, produced, mask_error = try_decompress_sector(
                    compressed, 0, compressed_size, uncompressed_size)
                method = 'mask'
            if not ok and compressed_size >= uncompressed_size:
                produced = compressed[:uncompressed_size]
                ok = True
                method = 'stored(sector>=uncompressed)'

            if not ok:
                first = compressed[0] if compressed_size else 0
                return None, ('扇区 %d/%d 解压失败：%s（compressed=%d, uncompressed=%d, '
                              '首字节 0x%02X, flags=0x%08X）'
                              % (sector, sector_count, mask_error or '解压失败',
                                 compressed_size, uncompressed_size, first, flags))

            available = len(produced)
            to_copy = min(available, file_size - written)
            if to_copy > 0:
                result += produced[:to_copy]
                written += to_copy

            if available < uncompressed_size and written < file_size:
                return None, ('扇区 %d 解码长度不足（%d/%d 字节，%s）'
                              % (sector, available, uncompressed_size, method))

        if written != file_size:
            return None, ('只解出 %d/%d 字节（%d 个扇区）' % (written, file_size, sector_count))
        return bytes(result), None

    # ---- listfile ---------------------------------------------------
    def _build_listfile_index(self) -> None:
        """A MpqArchive.cs:407-460 PreloadListfileCache()。"""
        entries: List[str] = []
        try:
            block_index, canonical = self._resolve_direct('(listfile)')
            if block_index is not None:
                data, error = self._read_entry(block_index, canonical)
                if error is None and data is not None:
                    entries = _split_listfile(data)
        except (OSError, ValueError):
            entries = []
        self._listfile = entries

        for entry in entries:
            canonical = _canonicalize_key(entry)
            if not canonical:
                continue
            pair = (hash_string(canonical, HASH_NAME_A), hash_string(canonical, HASH_NAME_B))
            self._hash_pair_index[pair] = canonical

        if self._hash_pair_index:
            for i in range(self.hash_table_size):
                entry = self.hash_entries[i]
                entry_block = entry[4]
                if entry_block == _HASH_ENTRY_FREE or entry_block == _HASH_ENTRY_DELETED:
                    continue
                name = self._hash_pair_index.get((entry[0], entry[1]))
                if name is not None:
                    self._lookup_cache[name] = entry_block & _BLOCK_INDEX_MASK

    def _ensure_listfile_index(self) -> List[str]:
        if self._listfile is None:
            self._listfile = []           # 先占位，_build_listfile_index 内部不再重入
            self._build_listfile_index()
        return self._listfile

    def listfile_names(self) -> Optional[List[str]]:
        """归档自带 (listfile) 里的名字；没有 (listfile) 时返回 None。

        MPQ 不强制带 (listfile)，查找也不依赖它，这里只是方便枚举。
        """
        names = self._ensure_listfile_index()
        return list(names) if names else None

    def close(self) -> None:
        try:
            self.f.close()
        except Exception:
            pass


# --------------------------------------------------------------------------
# 便捷封装：把若干归档当做一个整体查找
# --------------------------------------------------------------------------
class MPQSet:
    """按固定顺序搜索的一组归档。"""

    def __init__(self, archives):
        self.archives: List[Tuple[str, MPQArchive]] = []
        for path in archives:
            if not os.path.isfile(path):
                continue
            try:
                archive = MPQArchive(path)
            except (OSError, ValueError):
                continue
            self.archives.append((path, archive))

    def __len__(self) -> int:
        return len(self.archives)

    def read(self, name: str) -> Optional[bytes]:
        """文件内容；没有任何归档含有它时返回 None。

        空文件（0 字节）是成功结果，所以判据用 is not None 而不是真假值。
        """
        for _path, archive in self.archives:
            try:
                data = archive.read_file(name)
            except (OSError, ValueError):
                continue
            if data is not None:
                return data
        return None

    def close(self) -> None:
        for _path, archive in self.archives:
            archive.close()
