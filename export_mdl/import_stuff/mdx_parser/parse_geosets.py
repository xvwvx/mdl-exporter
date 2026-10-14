from typing import List

from . import binary_reader
from .parse_geometry import parse_geometry
from .parse_records import find_next_record_start
from ... import constants
from ...classes.War3Geoset import War3Geoset

# GEOS 记录的最小声明长度：size(4) + 至少一个子块的 tag(4) 与计数(4)
MINIMUM_GEOSET_RECORD_SIZE = 12


def is_geoset_record(data: bytes, offset: int) -> bool:
    """offset 处是否像一条 geoset 记录（对应 A:774 传入的 plausibleRecord）。"""
    tag = data[offset + 4:offset + 8].decode('ascii', 'ignore')
    return tag in constants.SUB_CHUNKS_GEOSET


def parse_geosets(data: bytes, version: int, model_name: str) -> List[War3Geoset]:
    data_size = len(data)
    r = binary_reader.Reader(data)

    geosets: List[War3Geoset] = []
    while r.offset < data_size:
        record_start = r.offset
        if record_start + 4 > data_size:
            print("  GEOS：末尾剩 %d 字节，不足一条记录" % (data_size - record_start))
            break

        inclusive_size = r.getf('<I')[0]
        record_end = record_start + inclusive_size

        if inclusive_size < MINIMUM_GEOSET_RECORD_SIZE or record_end > data_size:
            # A(MdxLoader.cs:1622-1689)：记录声明的大小装不下时，向后重同步到下一条
            # 记录的开始（英雄模型里确实存在这种多余的字节）。
            # 旧实现用 r.skip(inclusive_size - 4)：当 inclusive_size < 4 时这个值是
            # 负数，读取位置反而回退，于是永远停在同一条记录上（死循环，S7）。
            resync = find_next_record_start(data, record_start, data_size,
                                            MINIMUM_GEOSET_RECORD_SIZE,
                                            is_geoset_record)
            if resync < 0:
                print("  GEOS：偏移 %d 处的记录声明 %d 字节且无法重同步 - 剩余数据忽略"
                      % (record_start, inclusive_size))
                break
            print("  GEOS：偏移 %d 处的记录声明 %d 字节，重同步到偏移 %d"
                  % (record_start, inclusive_size, resync))
            r.offset = resync
            continue

        geo_data = data[r.offset: record_end]
        # 无论如何都按声明长度前进：某条记录解析失败时不会连带毁掉后面的记录。
        r.offset = record_end

        try:
            mesh = parse_geometry(geo_data, version)
        except Exception as error:
            # A:450-467 对每条记录单独 try/catch，坏记录只丢它自己（S24）。
            print("  GEOS：偏移 %d 处的 geoset 解析失败（%s）- 跳过该记录"
                  % (record_start, error))
            continue

        geosets.append(mesh)

    for i, geoset in enumerate(geosets):
        if geoset.name == "":
            geoset.name = str(i)
    return geosets
