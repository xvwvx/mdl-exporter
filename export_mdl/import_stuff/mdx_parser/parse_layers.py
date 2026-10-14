import struct

from ...classes.War3Layer import War3Layer
from ... import constants
from .binary_reader import Reader
from .parse_timeline import parse_timeline


# 注意：这里原本还有另一个同名函数 parse_layers(data: bytes, version)，但它被下面
# 这个 parse_layers(r: Reader, version) 覆盖，从未被调用（死代码），因此删除。

def parse_layers(r: Reader, version: int) -> War3Layer:
    data_size = r.offset
    inclusive_size = r.getf('<I')[0]
    data_size = data_size + inclusive_size
    # print("inclusive_size: ", inclusive_size, "max offset: ", data_size)

    layer = War3Layer()
    # inclusive_size = r.offset + r.getf('<I')[0]
    layer.filter_mode = constants.FILTER_MODES.get(r.getf('<I')[0], 'None')
    # A(MdxLoader.cs:668-677)：这一项是 MdxGeoFlags，位定义见 MdxModel.cs:147-160。
    # 旧实现只把它存进 shadingFlags 就再没人引用，于是 Unshaded/TwoSided/Unfogged/
    # NoDepthTest/NoDepthSet 整类语义在导入时就是 False，再导出时因为
    # save_materials.py 只在布尔为真时写关键字而被永久删除。
    layer.shadingFlags = r.getf('<I')[0]
    layer.unshaded = (layer.shadingFlags & constants.LAYER_FLAG_UNSHADED) != 0
    layer.two_sided = (layer.shadingFlags & constants.LAYER_FLAG_TWO_SIDED) != 0
    layer.unfogged = (layer.shadingFlags & constants.LAYER_FLAG_UNFOGGED) != 0
    layer.no_depth_test = (layer.shadingFlags & constants.LAYER_FLAG_NO_DEPTH_TEST) != 0
    layer.no_depth_set = (layer.shadingFlags & constants.LAYER_FLAG_NO_DEPTH_SET) != 0
    # A(MdxLoader.cs:674-676)：这三个字段在参考实现里都是 ReadI32（有符号），
    # 0xFFFFFFFF 自然变成 -1，且真实模型里还存在 0xFFFFFFFD/FC/FB（-3/-4/-5，
    # 例如 TornadoElemental、ClearIceRock、DwarfCar）—— 用 '<I' 读会把它们变成
    # 4294967293 之类的巨大正数，下游拿去做列表下标即越界（S14）。
    layer.texture_id = r.getf('<i')[0]
    layer.texture_path = str(layer.texture_id)
    layer.textureAnimationId = r.getf('<i')[0]
    # A(MdxLoader.cs:676)：coordId 是 ReadI32（有符号），0xFFFFFFFF 必须自然是 -1（S14）。
    layer.coordId = r.getf('<i')[0]
    layer.alpha_value = r.getf('<f')[0]

    if 800 < version:
        layer.emissive_gain = r.getf('<f')[0]

    if 900 < version:
        layer.fresnel_color = list(r.getf('<3f'))
        layer.fresnel_opacity = r.getf('<f')[0]
        layer.fresnel_team_color = r.getf('<f')[0]

    if 1000 < version:
        hdFlag = r.getf('<I')[0]
        numTextures: int = r.getf('<I')[0]

        # print("numTextures:", numTextures)

        layer.multi_texture_ids = []
        i = 0
        while i < numTextures:
            value = r.getf('<I')[0]
            # print("Texture:", i, ", animOrTextureId:", animOrTextureId)
            if 1024 < value:
                # value 其实是下一个层子块（例如 KMTF）的 tag，回退 4 字节后按 tag 处理。
                i -= 1
                r.offset -= struct.calcsize('<I')
                anim_id = r.getid(constants.SUB_CHUNKS_LAYER)
                # print("Texture:", i, ", anim_id: ", anim_id)
                layer.texture_id_anim = parse_timeline(r, '<I')
            else:
                # 旧实现（继承自上游 mdl-exporter）在这个分支里又读了一次 uint32，
                # 于是每个纹理槽消耗 8 字节而不是 4 字节，version > 1000 的整层都会
                # 错位：合成样本 synth_hd1100.mdx 会因此读到层尾之外并抛
                # struct.error。纹理槽就是上面刚读到的那个 uint32，不重复消费。
                # 槽位在参考实现里是 ReadI32：真实模型里存在 -3/-4/-5 的纹理槽，
                # 用 '<I' 读会得到 4294967293 之类的大正数（S14 同族）。
                texture_slot = value if value < 0x80000000 else value - 0x100000000
                layer.multi_texture_ids.append(texture_slot)
                # print("Texture:", i, "textureSlot", textureSlot, ", textureID: ", animOrTextureId)
            i += 1

    # print("r.offset:", r.offset, "of", data_size)

    while r.offset + 4 <= data_size:
        chunk_id = r.getid(constants.SUB_CHUNKS_LAYER)
        # print("layer chunk: " + chunk_id)
        if chunk_id == constants.CHUNK_MATERIAL_TEXTURE_ID:
            layer.texture_id_anim = parse_timeline(r, '<I')
        elif chunk_id == constants.CHUNK_MATERIAL_ALPHA:
            layer.alpha_anim = parse_timeline(r, '<f')
        elif chunk_id == constants.CHUNK_MATERIAL_FRESNEL_COLOR:
            layer.fresnel_color = parse_timeline(r, '<3f')
        elif chunk_id == constants.CHUNK_MATERIAL_EMISSIONS:
            layer.emissions = parse_timeline(r, '<f')
        elif chunk_id == constants.CHUNK_MATERIAL_FRESNEL_ALPHA:
            layer.fresnel_alpha = parse_timeline(r, '<f')
        elif chunk_id == constants.CHUNK_MATERIAL_FRESNEL_TEAMCOLOR:
            layer.fresnel_team_color = parse_timeline(r, '<f')
        else:
            # A(MdxLoader.cs:638-712)：未知的层子块跳 4 字节后继续（旧实现不消费
            # payload，会把轨道数据当成下一个 tag 读）。
            # 注意：A(MdxLoader.cs:689-707) 对未知 tag 只消费 tag 自身的 4 字节
            # （getid 已经消费掉了），这里不能再额外 skip，否则层内后续读取整体
            # 错位 4 字节，下一个层（乃至下一个材质）的边界全错。
            print("  unknown layer sub-chunk %r - skipping 4 bytes" % chunk_id)
        # print("r.offset:", r.offset, "of", data_size)

    return layer

