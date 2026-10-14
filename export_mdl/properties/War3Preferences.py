import bpy


def _drop_mpq_cache(self, context):
    """Release the cached archives so a changed 魔兽3 目录 takes effect at once."""
    try:
        from ..import_stuff import create_material
        create_material.clear_mpq_cache()
    except Exception:
        pass


class War3Preferences(bpy.types.AddonPreferences):
    bl_idname = 'export_mdl'
    resourceFolder: bpy.props.StringProperty(
        name='贴图资源目录',
        description='导入 .mdl/.mdx 时，按模型里记录的贴图路径（例如 Textures\\Foo.blp）'
                    '到这个目录下查找图片文件。一般填魔兽争霸的安装目录，或你解包出来的'
                    '贴图根目录。找不到时该贴图会变成空白图，但模型本身仍能正常导入',
        default='',
        subtype='DIR_PATH'
        )
    alternativeResourceFolder: bpy.props.StringProperty(
        name='备用贴图目录',
        description='上面的目录里没找到时，再到这个目录找一遍。适合放你自己整理或转换过的'
                    '贴图（例如从 .blp 转出来的 .png）',
        default='',
        subtype='DIR_PATH'
        )
    textureExtension: bpy.props.StringProperty(
        name='贴图扩展名',
        description='查找贴图前，把模型里的 .blp 后缀替换成这里填的后缀。\n'
                    '默认 blp：直接加载原始 .blp 文件（插件自己解码，无需事先转换）；\n'
                    '填 png 等其它后缀：改为查找同名的转换后图片，找不到就留空白。',
        default='blp'
        )
    war3Folder: bpy.props.StringProperty(
        name='魔兽3 目录',
        description='魔兽争霸3 的安装目录（含 war3.mpq、War3x.mpq 等）。\n'
                    '勾选下面的「允许从 MPQ 中直接加载」后，前两个目录都没找到的贴图'
                    '会到这里面的游戏归档里再找一次。\n'
                    '这是优先级最低的一级：它是游戏原版内容，覆盖不了你自己的贴图。',
        default='',
        subtype='DIR_PATH',
        update=_drop_mpq_cache
        )
    useMpq: bpy.props.BoolProperty(
        name='允许从 MPQ 中直接加载',
        description='开启后，磁盘上找不到的贴图会直接从「魔兽3 目录」里的 .mpq 归档中读取，'
                    '无需事先解包。\n'
                    '优先级最低：只有在贴图资源目录、备用贴图目录里都找不到时才会用到。\n'
                    '注意：这是游戏原版贴图，地图自带的自定义贴图不在其中。',
        default=True,
        update=_drop_mpq_cache
        )
    defaultEncoding: bpy.props.EnumProperty(
        name='文本默认编码',
        description='.mdl 是文本格式，里面的模型名、骨骼名和贴图路径按这个编码读取。'
                    '中文模型常用 GBK 或 GB18030，韩文用 euc_kr，日文用 euc_jp。'
                    '导入后如果名字是乱码，换一个再试（latin-1 永远不会报错，'
                    '但中文会显示成乱码）',
        items=[
            ('LATIN_1', 'latin-1',      "永不报错的兜底编码，非西欧文字会乱码"),
            ('UTF_8',   'utf-8',        "现代通用编码"),
            ('UTF_16',  'utf-16',       ""),
            ('UTF_32',  'utf-32',       ""),
            ('ASCII',   'ascii',        ""),
            ('GBK',     'gbk (简体中文)',   "简体中文模型常用"),
            ('GB18030', 'gb18030 (简体中文)', "GBK 的超集，生僻字更全"),
            ('BIG5',    'big5 (繁体中文)',  "繁体中文模型常用"),
            ('EUC_KR',  'euc_kr (韩文)',   ""),
            ('EUC_JP',  'euc_jp (日文)',   ""),
        ],
        default='LATIN_1'
        )

    def draw(self, context):
        layout = self.layout

        box = layout.box()
        box.label(text="贴图查找", icon='IMAGE_DATA')
        box.prop(self, 'resourceFolder')
        box.prop(self, 'alternativeResourceFolder')
        box.prop(self, 'textureExtension')
        box.separator()
        box.prop(self, 'war3Folder')
        box.prop(self, 'useMpq')
        box.label(text="按上面的顺序依次查找，魔兽3 目录的 MPQ 优先级最低", icon='INFO')

        box = layout.box()
        box.label(text="文本编码", icon='FILE_TEXT')
        box.prop(self, 'defaultEncoding')
