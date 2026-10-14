from typing import List

from ...classes.War3Geoset import War3Geoset
from ...classes.War3Vertex import War3Vertex
from .binary_reader import Reader
from ... import constants


def read_element_count(r: Reader, record_end: int, chunk_id: str, element_bytes: int) -> int:
    """读子块的元素数并校验数据是否够用（对应 A(MdxLoader.cs:880-892)）。

    元素数如果是坏的（很大），按它去读会直接读出记录之外，所以先算一遍。
    """
    count = r.getf('<I')[0]
    needed = count * element_bytes
    available = record_end - r.offset
    if needed > available:
        raise Exception('%s：%d 个元素（每个 %d 字节）需要 %d 字节，但记录里只剩 %d 字节'
                        % (chunk_id, count, element_bytes, needed, available))
    return count


def parse_geometry(data: bytes, version: int) -> War3Geoset:
    r = Reader(data)
    geoset = War3Geoset()
    geoset.name = ''
    data_size = len(data)
    print("  parsing geoset")

    locations: List[List[float]] = []
    normals: List[List[float]] = []
    uvs_raw: List[List[float]] = []
    uv_channel_count = 0
    vert_matrix_groups: List[int] = []
    matrix_groups_sizes: List[int] = []
    matrix_node_ids: List[int] = []
    matrix_groups: List[List[int]] = []
    sw_bones: List[List[str]] = []
    sw_weights: List[List[int]] = []

    # A(MdxLoader.cs:774-865)：GEOS 记录内部是 tag 驱动的子块列表，不是固定顺序；
    # 未知子块跳 4 字节后继续。旧实现写死了顺序，遇到顺序不同或多余子块的文件就会
    # 把数据当成别的子块读（S9）。
    while r.offset + 4 <= data_size:
        chunk_id = r.getid(constants.SUB_CHUNKS_GEOSET, debug=True)

        if chunk_id == constants.CHUNK_VERTEX_POSITION:
            vertex_count = read_element_count(r, data_size, chunk_id, 12)
            print("   ", chunk_id, "parsing %d vertices" % vertex_count)
            for _ in range(vertex_count):
                locations.append(list(r.getf('<3f')))

        elif chunk_id == constants.CHUNK_VERTEX_NORMAL:
            normal_count = read_element_count(r, data_size, chunk_id, 12)
            for _ in range(normal_count):
                normals.append(list(r.getf('<3f')))

        elif chunk_id == constants.CHUNK_VERTEX_TEXTURE_POSITION:
            # UVBS：每个顶点可能带多套 UV 坐标，这里先原样读回来，循环结束后再拆。
            # A(MdxLoader.cs:838-842) 是 "geoset.Uvs = ReadFloats(count * 2)"，也就是
            # 再遇到一个 UVBS 时**整个覆盖**前一个，而不是累加。实测
            # FreezingBreathTargetArt.mdx 的 geoset 里就有两个 UVBS 子块（各 372 组），
            # 累加会让 B 端算出 2 套 UV，而参考实现只有 1 套（uvChannels=1、uv2=0）。
            del uvs_raw[:]
            uv_count = read_element_count(r, data_size, chunk_id, 8)
            for _ in range(uv_count):
                u, v = r.getf('<2f')
                uvs_raw.append([u, 1 - v])

        elif chunk_id == constants.CHUNK_FACE_TYPE_GROUP:
            count = read_element_count(r, data_size, chunk_id, 4)
            geoset.primitive_type_count = count
            r.skip(4 * count)

        elif chunk_id == constants.CHUNK_FACE_GROUP:
            count = read_element_count(r, data_size, chunk_id, 4)
            geoset.primitive_counts_count = count
            r.skip(4 * count)

        elif chunk_id == constants.CHUNK_FACE:
            indices_count = read_element_count(r, data_size, chunk_id, 2)
            if indices_count % 3 != 0:
                raise Exception('bad indices (indices_count % 3 != 0)')
            for _ in range(indices_count // 3):
                geoset.triangles.append(list(r.getf('<3H')))

        elif chunk_id == constants.CHUNK_VERTEX_GROUP:
            matrix_groups_count = read_element_count(r, data_size, chunk_id, 1)
            for _ in range(matrix_groups_count):
                vert_matrix_groups.append(r.getf('<B')[0])

        elif chunk_id == constants.CHUNK_MATRIX_GROUP:
            matrix_groups_sizes_count = read_element_count(r, data_size, chunk_id, 4)
            for _ in range(matrix_groups_sizes_count):
                matrix_groups_sizes.append(r.getf('<I')[0])

        elif chunk_id == constants.CHUNK_MATRIX_INDEX:
            # A(MdxLoader.cs:894-932)：MATS 子块自带矩阵数量，其尾部还跟着
            # materialId / group / selectable / 包围盒 / 序列包围盒列表。
            # 旧实现把这些字段放在子块循环之外读，等于假定它们紧跟矩阵索引。
            matrix_indices_count = read_element_count(r, data_size, chunk_id, 4)
            for _ in range(matrix_indices_count):
                matrix_node_ids.append(r.getf('<I')[0])

            # A(MdxLoader.cs:915-917)：materialId/group/selectable 都是 ReadI32（有符号），
            # 0xFFFFFFFF 归一为 -1（S14 同族）。
            geoset.mat_name = str(r.getf('<i')[0])
            selection_group = r.getf('<i')[0]
            selection_flags = r.getf('<i')[0]
            geoset.selection_group = selection_group
            geoset.selection_flags = selection_flags

            # 版本 >800 的 geoset 多出 LOD 字段（B 端是超集，保留，见 S19）。
            if version > 800:
                lod = r.getf('<I')[0]
                lod_name = r.gets(80)

            bounds_radius = r.getf('<f')[0]
            minimum_extent = r.getf('<3f')
            maximum_extent = r.getf('<3f')

            extents_count = r.getf('<I')[0]
            geoset.sequence_bounds_count = extents_count
            for _ in range(extents_count):
                r.getf('<f')
                r.getf('<3f')
                r.getf('<3f')

        elif chunk_id == constants.CHUNK_TEXTURE_VERTEX_GROUP:
            # UVAS：本 geoset 有几套 UV 坐标（A:940-965）。
            uv_channel_count = r.getf('<I')[0]

        elif chunk_id == constants.CHUNK_TANGENTS:
            # A 的 geoset 子块集合里没有 TANG，但旧版实现会读它（B 端是超集，保留）。
            tangent_size = r.getf('<I')[0]
            r.skip(16 * tangent_size)

        elif chunk_id == constants.CHUNK_SKIN:
            skin_size = r.getf('<I')[0]
            for _ in range(skin_size // 8):
                sw_weight = r.getf('<8B')
                sw_bones.append([str(sw_weight[0]), str(sw_weight[1]),
                                 str(sw_weight[2]), str(sw_weight[3])])
                sw_weights.append([sw_weight[4], sw_weight[5],
                                   sw_weight[6], sw_weight[7]])
            r.skip(skin_size % 8)

        else:
            # A(MdxLoader.cs:774-865) 的 default 分支：未知子块跳 4 字节。
            # 注意：A 对未知 tag 只消费 tag 自身的 4 字节（getid 已经消费掉了），
            # 这里不能再额外 skip，否则 geoset 记录内后续子块整体错位 4 字节。
            print("  unknown geoset sub-chunk %r - skipping 4 bytes" % chunk_id)

    # A(MdxLoader.cs:934-1009)：UVAS 声明的通道数要和 UVBS 里的实际数据量对齐。
    vertex_count = len(locations)
    pair_count = len(uvs_raw)
    channels = uv_channel_count if uv_channel_count >= 1 else 1
    if vertex_count > 0 and pair_count >= vertex_count:
        channels_in_data = pair_count // vertex_count
        if channels != channels_in_data and uv_channel_count > 1:
            print("  UVAS 声明了 %d 套 UV，但 UVBS 里每个顶点只有 %d 组 - 以数据为准"
                  % (uv_channel_count, channels_in_data))
        channels = max(1, min(channels, max(1, channels_in_data)))
    uv_channels = max(1, channels)

    uvs = uvs_raw
    uvs2 = None
    if vertex_count > 0 and uv_channels >= 2 and pair_count >= vertex_count * 2:
        # 第二套 UV：旧实现把 2N 组 UV 全部塞进 uvs、丢掉 group_count，第二套 UV
        # 因此完全消失（S10）。这里按顶点数拆成 uvs / uvs2 两段。
        uvs = uvs_raw[:vertex_count]
        uvs2 = uvs_raw[vertex_count:vertex_count * 2]

    # 矩阵组按 MTGC 给出的大小切分矩阵索引（A:894-932 的 MatrixGroups）。
    curr_index = 0
    for size in matrix_groups_sizes:
        if size < 0:
            size = 0
        end = min(curr_index + size, len(matrix_node_ids))
        matrix_groups.append(matrix_node_ids[curr_index:end])
        curr_index = end
    if not matrix_groups:
        matrix_groups = [[0]]

    if not len(sw_bones):
        for group in vert_matrix_groups:
            v_b: List[str] = []
            v_w: List[int] = []
            bones = matrix_groups[group] if 0 <= group < len(matrix_groups) else []
            for bone in bones:
                v_b.append(str(bone))
                v_w.append(255)
            sw_bones.append(v_b)
            sw_weights.append(v_w)

    # 顶点数以 VRTX 为准：旧实现用 zip(locations, normals, uvs, sw_bones, sw_weights)，
    # 任一列表短一点都会静默丢掉尾部的顶点（顶点数直接对不上参考实现）。
    for index, position in enumerate(locations):
        normal = normals[index] if index < len(normals) else [0.0, 0.0, 0.0]
        uv = uvs[index] if index < len(uvs) else [0.0, 0.0]
        v_b = sw_bones[index] if index < len(sw_bones) else []
        v_w = sw_weights[index] if index < len(sw_weights) else []
        geoset.vertices.append(War3Vertex(position, normal, uv, v_b, v_w))

    # 损坏模型的 GEOS 会让 FACES 引用不存在的顶点（例如 ScorchedRemains0.mdx：515 个
    # 顶点却出现索引 17395 的三角面；VRTX/FACES 的计数与数据本身对不上）。Blender 的
    # from_pydata 不校验面索引，越界的 loop 会让后面的 UV、法线、蒙皮全部抛
    # IndexError。参考实现把读不成形的几何降级处理而不是报错，这里照做：丢弃无效
    # 三角面，剩下的部分照常导入。
    valid_triangles = [t for t in geoset.triangles if max(t) < len(geoset.vertices)]
    if len(valid_triangles) != len(geoset.triangles):
        print("   geoset %r：%d/%d 个三角面引用了不存在的顶点（顶点数 %d），已丢弃"
              % (geoset.name, len(geoset.triangles) - len(valid_triangles),
                 len(geoset.triangles), len(geoset.vertices)))
        geoset.triangles = valid_triangles

    geoset.matrices = sw_bones
    # 动态属性：UVBS 的 UV 对数（mdxdump 的 geoset.uvBytes = 2 * pair_count）
    # 与矩阵组数（A 的 geoset.MatrixGroups.Length = MTGC 条目数，无 MTGC 时为 1）。
    geoset.uv_pair_count = pair_count
    geoset.matrix_group_count = len(matrix_groups)
    # 新增属性（不重命名、不删除既有属性）：第二套 UV 与 UV 通道数，供下游按需取用。
    geoset.uvs2 = uvs2
    geoset.uv_channel_count = uv_channels

    return geoset
