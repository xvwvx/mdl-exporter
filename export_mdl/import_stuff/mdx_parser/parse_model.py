from . import binary_reader


def parse_model(data: bytes):
    """MODL 块：返回 (模型名, 动画文件名)。

    A(MdxLoader.cs:510-520)：Name(80) + AnimationFile(260) + 包围盒 + BlendTime。
    旧实现读出了 animation_file_name 却丢弃，mdxdump 的 animFile 字段因此没有对应值。
    """
    r = binary_reader.Reader(data)
    name = r.gets(80)
    animation_file_name = r.gets(260)
    bounds_radius = r.getf('<f')[0]
    minimum_extent = r.getf('<3f')
    maximum_extent = r.getf('<3f')
    blend_time = r.getf('<I')[0]
    return name, animation_file_name
