import struct
from typing import Tuple, List

import bpy

from export_mdl import War3Preferences, constants


class Reader:
    def __init__(self, data: bytes):
        self.__data: bytes = data
        self.offset = 0
        preferences: War3Preferences = bpy.context.preferences.addons.get('export_mdl').preferences
        self.default_enc = constants.ENCODINGS[preferences.defaultEncoding]

    def getf(self, value_format: str) -> Tuple:
        size = struct.calcsize(value_format)
        self.offset += size
        return struct.unpack_from(value_format, self.__data, self.offset - size)

    def gets(self, size: int) -> str:
        self.offset += size
        # return struct.unpack_from('<{}s'.format(size), self.__data, self.offset - size)[0].split(b'\x00')[0].decode(encoding='mbcs')
        string_struct: bytes = struct.unpack_from('<{}s'.format(size), self.__data, self.offset - size)[0].split(b'\x00')[0]
        try:
            return string_struct.decode(encoding=self.default_enc)
        except UnicodeDecodeError:
            for enc in constants.ENCODINGS.values():
                string = self.try_get_decoded_string(string_struct, enc)
                if string is not None:
                    return string
            return str(string_struct)

    def try_get_decoded_string(self, string_struct: bytes, encoding: str):
        try:
            return string_struct.decode(encoding=encoding)
        except UnicodeError:
            return None

    def getid(self, required_chunks_id: Tuple[str, ...], debug=True):
        self.offset += 4
        # A(MdxLoader.cs) 把 tag 当 uint32 比较，从不解码成文本；旧实现用 utf-8
        # 严格解码，一旦未知 tag 的 4 字节里含非法 utf-8 序列就会抛
        # UnicodeDecodeError，导致整条记录（甚至整块）被丢弃。这里在严格 utf-8
        # 失败时退化为 latin-1（任何字节都可解码），从而保证"未知 tag 只消费
        # 自己的 4 字节后继续"的语义（S9/S24）。
        raw_chunk_id = struct.unpack_from('<4s', self.__data, self.offset - 4)[0]
        try:
            chunk_id = raw_chunk_id.decode(encoding='utf-8')
        except UnicodeDecodeError:
            chunk_id = raw_chunk_id.decode(encoding='latin-1')

        if type(required_chunks_id) == str:
            required_chunks_id = [required_chunks_id, ]

        if chunk_id not in required_chunks_id:
            if not debug:
                # raise Exception('chunk id "{0}" not in "{1}"'.format(chunk_id, required_chunks_id))
                raise Exception('chunk id "{%s}" not in "{%s}"' % (chunk_id, required_chunks_id))
            else:
                print('unknown chunk_id: "{%s}" expected "{%s}"' % (chunk_id, required_chunks_id))
                return chunk_id
        else:
            return chunk_id

    def skip(self, count: int):
        self.offset += count

    def get_float(self) -> float:
        return self.get_floats(1)[0]

    def get_floats(self, num: int) -> Tuple[float]:
        value_format = '<f' if num == 1 else '<%sf' % num
        return self.getf(value_format)

    def get_int(self) -> int:
        return self.get_ints(1)[0]

    def get_ints(self, num: int) -> Tuple[int]:
        value_format = '<%sI' % num
        return self.getf(value_format)

    def get_ushort(self) -> int:
        return self.get_ushorts(1)[0]

    def get_ushorts(self, num: int) -> Tuple[int]:
        value_format = '<%sH' % num
        return self.getf(value_format)

    def get_byte(self) -> bytes:
        return self.get_bytes(1)[0]

    def get_bytes(self, num: int) -> Tuple[bytes]:
        value_format = '<%sB' % num
        return self.getf(value_format)

    def get_floats1(self, num: int) -> List[float]:
        value_format = '<%sf' % num
        return list(self.getf(value_format))

    def get_ints1(self, num: int) -> List[int]:
        value_format = '<%sI' % num
        return list(self.getf(value_format))

    def get_ushort1(self, num: int) -> List[int]:
        value_format = '<%sH' % num
        return list(self.getf(value_format))

    def get_bytes1(self, num: int) -> List[float]:
        value_format = '<%sB' % num
        return list(self.getf(value_format))
    #
    # def get_floats(self, num: int) -> List[float]:
    #     value_format = '<f' if num == 1 else '<%sf' % num
    #     return list(self.getf(value_format))
    #
    # def get_ints(self, num: int) -> List[int]:
    #     value_format = '<I' if num == 1 else '<%sI' % num
    #     return list(self.getf(value_format))
    #
    # def get_ushort(self, num: int) -> List[int]:
    #     value_format = '<H' if num == 1 else '<%sH' % num
    #     return list(self.getf(value_format))
    #
    # def get_bytes(self, num: int) -> List[float]:
    #     value_format = '<B' if num == 1 else '<%sB' % num
    #     return list(self.getf(value_format))
