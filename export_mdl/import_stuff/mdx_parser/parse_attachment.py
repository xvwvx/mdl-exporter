from ... import constants
from ...classes.War3Attachment import War3Attachment
from . import binary_reader
from .parse_timeline import parse_timeline
from .parse_node import parse_node


def parse_attachment(attach_data: bytes) -> War3Attachment:
    r = binary_reader.Reader(attach_data)
    data_size = len(attach_data)
    node = War3Attachment("")
    parse_node(r, node)
    # A(MdxLoader.cs:1144-1176)：路径之后是 AttachmentId，然后才是可选的
    # KATV 可见性轨道。（A 用 AttachmentPathLength=256 再读一个保留的 uint32，
    # 合计正好 260 字节，与格式规范一致。）
    # 旧实现把 path / node_id / visibility 全读进局部变量后丢弃：附件路径、
    # 附件 id 和可见性动画全部丢失（S6）。
    node.path = r.gets(260)
    node.attachment_id = r.getf('<I')[0]

    while r.offset + 4 <= data_size:
        chunk_id = r.getid(constants.CHUNK_ATTACHMENT_VISIBILITY, debug=True)
        if chunk_id == constants.CHUNK_ATTACHMENT_VISIBILITY:
            node.visibility = parse_timeline(r, '<f')
        else:
            # A:1144-1176 对未知子块跳过 4 字节继续。
            # 注意：A 对未知 tag 只消费 tag 自身的 4 字节（getid 已经消费掉了），
            # 这里不能再额外 skip，否则之后的读取整体错位 4 字节。
            print("  unknown ATCH track %r - skipping 4 bytes" % chunk_id)
    return node
