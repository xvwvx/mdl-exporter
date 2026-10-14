from .binary_reader import Reader
from ...classes.War3Node import War3Node
from ... import constants, node_flags
from .parse_timeline import parse_timeline


def parse_node(r: Reader, node: War3Node):
    inclusive_size = r.offset + r.getf('<I')[0]
    node.name = r.gets(80)
    node_id = r.getf('<I')[0]
    node.obj_id = int(node_id)
    parent = r.getf('<I')[0]

    if parent != 0xffffffff:
        node.parent_id = parent
        node.parent = str(parent)

    # A(MdxLoader.cs:1477)：节点标志是 MdxNodeFlags（MdxModel.cs:63-87）。
    # 旧实现把它读进一个局部变量就丢掉，于是 Billboarded/锁轴/DontInherit* 以及
    # 发射器的 Unshaded/SortPrimsFarZ/LineEmitter/Unfogged/ModelSpace/XYQuad
    # 全部按 False 处理，再导出时这些关键字被直接删掉（P0-2）。
    flags = r.getf('<I')[0]
    node_flags.set_node_flags(node, flags)

    while r.offset + 4 <= inclusive_size:
        chunk_id = r.getid(constants.SUB_CHUNKS_NODE)

        if chunk_id == constants.CHUNK_GEOSET_TRANSLATION:
            node.anim_loc = parse_timeline(r, '<3f')
        elif chunk_id == constants.CHUNK_GEOSET_ROTATION:
            node.anim_rot = parse_timeline(r, '<4f')
        elif chunk_id == constants.CHUNK_GEOSET_SCALING:
            node.anim_scale = parse_timeline(r, '<3f')
        else:
            # A(MdxLoader.cs:1460-1501)：未知的节点子块跳过 4 字节后继续。旧实现
            # 不消费 payload，会把轨道数据当成下一个 tag 读，节点动画全部错乱。
            # 注意：A 对未知 tag 只消费 tag 自身的 4 字节（getid 已经消费掉了），
            # 这里不能再额外 skip，否则节点后面所有轨道读取整体错位 4 字节。
            print("  unknown node sub-chunk %r - skipping 4 bytes" % chunk_id)

    return node
