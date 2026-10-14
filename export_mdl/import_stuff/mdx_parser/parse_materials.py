from typing import List

from ... import constants
from ...classes.War3Layer import War3Layer
from ...classes.War3Material import War3Material
from . import binary_reader
from .parse_layers import parse_layers
from .parse_records import find_next_record_start
from .parse_timeline import parse_timeline

# 材质记录的最小声明长度：size(4) + priorityPlane(4) + flags(4)
MINIMUM_MATERIAL_RECORD_SIZE = 12


def parse_materials(data: bytes, version: int) -> List[War3Material]:
    r = binary_reader.Reader(data)
    data_size = len(data)

    materials: List[War3Material] = []

    while r.offset < data_size:
        record_start = r.offset
        if record_start + 4 > data_size:
            print("  MTLS：末尾剩 %d 字节，不足一条记录" % (data_size - record_start))
            break

        material = War3Material("")
        inclusive_size = r.getf('<I')[0]
        record_end = record_start + inclusive_size

        if inclusive_size < MINIMUM_MATERIAL_RECORD_SIZE or record_end > data_size:
            resync = find_next_record_start(data, record_start, data_size,
                                            MINIMUM_MATERIAL_RECORD_SIZE)
            if resync < 0:
                print("  MTLS：偏移 %d 处的记录声明 %d 字节且无法重同步 - 剩余数据忽略"
                      % (record_start, inclusive_size))
                break
            print("  MTLS：偏移 %d 处的记录声明 %d 字节，重同步到偏移 %d"
                  % (record_start, inclusive_size, resync))
            r.offset = resync
            continue

        # A(MdxLoader.cs:674-676)：priorityPlane 是 ReadI32（有符号），0xFFFFFFFF 自然
        # 变成 -1；真实模型里还存在 -5/-4/-3 的负优先级（TornadoElemental、
        # ClearIceRock、DwarfCar、TopRightPanel 等），用 '<I' 读会得到 4294967291
        # 之流，下游拿它做渲染层级排序即错（S14 同族）。
        priority_plane = r.getf('<i')[0]
        flags = r.getf('<I')[0]
        material.priority_plane = priority_plane
        material.flags = flags

        if 800 < version < 1100:
            shader = r.gets(80)
            if shader == "Shader_HD_DefaultUnit":
                material.is_hd = True

        # A(MdxLoader.cs:595-636)：材质记录内部同样是 tag 驱动的循环。LAYS 之前或之后
        # 都可能出现材质级轨道 KMTE(自发光) / KMTA(alpha) / KMTF(翻页)，遇到未知 tag
        # 就跳到记录末尾（记录长度始终可信）。
        # 旧实现直接假定 LAYS 紧跟记录头，一旦记录带材质级轨道，层与后续材质的边界
        # 全部错位（S4）。
        while r.offset + 4 <= min(record_end, data_size):
            # 白名单里带上材质级轨道，否则 binary_reader.getid 会对每个已知的
            # KMTE/KMTA/KMTF 都打印一条 "unknown chunk_id" 噪音警告。
            chunk_id = r.getid((constants.CHUNK_LAYER,
                                constants.CHUNK_MATERIAL_EMISSIONS,
                                constants.CHUNK_MATERIAL_ALPHA,
                                constants.CHUNK_MATERIAL_TEXTURE_ID), debug=True)

            if chunk_id == constants.CHUNK_LAYER:
                layers_count = r.getf('<I')[0]
                for _ in range(layers_count):
                    layer = parse_layers(r, version)
                    if layer.multi_texture_ids:
                        material.is_hd = 1000 <= version
                        for texture_slot in layer.multi_texture_ids:
                            newLayer = War3Layer()
                            # multi_texture_ids 里存的是纹理槽的"值"本身，要用值查找。
                            # 旧实现写成 layer.multi_texture_ids[texture_id]，把值当成
                            # 列表下标（S15）。下游 import_stuff/process_warcraft_3_model.py:64
                            # 用 int(layer.texture_path) 去索引 model.textures，所以这里
                            # 同时把 texture_path 设成该值。
                            newLayer.texture_id = texture_slot
                            newLayer.texture_path = str(texture_slot)
                            newLayer.filter_mode = layer.filter_mode
                            newLayer.unshaded = layer.unshaded
                            newLayer.two_sided = layer.two_sided
                            newLayer.unfogged = layer.unfogged
                            newLayer.texture_anim = layer.texture_anim
                            newLayer.alpha_anim = layer.alpha_anim
                            newLayer.alpha_value = layer.alpha_value
                            newLayer.no_depth_test = layer.no_depth_test
                            newLayer.no_depth_set = layer.no_depth_set
                            material.layers.append(newLayer)
                    else:
                        material.layers.append(layer)
            elif chunk_id == constants.CHUNK_MATERIAL_EMISSIONS:
                # 材质级轨道：A 存进 material.Emission。War3Material 没有对应字段，
                # 且 classes/ 不在本次可改范围，故用动态属性保存（信息不再丢失）。
                material.emission_anim = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_MATERIAL_ALPHA:
                material.alpha_anim = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_MATERIAL_TEXTURE_ID:
                # A 的材质级 KMTF 是翻页(Flipbook)，键值是 Int1 纹理号。
                material.flipbook_anim = parse_timeline(r, '<I')
            else:
                print("  未知的材质子块 %r - 跳到记录末尾" % chunk_id)
                break

        # A 的 ReadRecordList 始终用声明长度定位下一条记录。
        r.offset = record_end if record_end <= data_size else data_size
        materials.append(material)
    return materials
