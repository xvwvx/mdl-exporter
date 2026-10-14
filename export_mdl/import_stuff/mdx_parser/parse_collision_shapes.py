from typing import List

from ...classes.War3CollisionShape import War3CollisionShape
from . import binary_reader
from .parse_node import parse_node


def parse_collision_shapes(data: bytes) -> List[War3CollisionShape]:
    data_size = len(data)
    r = binary_reader.Reader(data)

    nodes: List[War3CollisionShape] = []
    while r.offset < data_size:

        node = War3CollisionShape("")
        parse_node(r, node)
        collision_type = r.getf('<I')[0]

        # A(MdxLoader.cs:1075-1096)：只有 0..3 是已知类型，未知类型一律按 Box 处理
        # （并记诊断）。旧实现把未知类型当 Sphere：Sphere 只读 1 个顶点、多读一个
        # 半径，于是后续记录整整错位 12 字节。
        if collision_type > 3:
            print('  未知的碰撞体类型 %d - 按 Box 处理' % collision_type)
            collision_type = 0

        if collision_type == 0:
            vertices_count = 2
            node.type = 'Box'
        elif collision_type == 1:
            vertices_count = 2
            node.type = 'Plane'
        elif collision_type == 2:
            vertices_count = 1
            node.type = 'Sphere'
        elif collision_type == 3:
            vertices_count = 2
            node.type = 'Cylinder'

        for _ in range(vertices_count):
            position = r.getf('<3f')
            node.verts.append(list(position))

        if collision_type == 2 or collision_type == 3:
            bounds_radius = r.getf('<f')[0]
            node.radius = bounds_radius

        nodes.append(node)
    return nodes
