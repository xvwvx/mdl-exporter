# export_mdl —— Blender 3.4 → 5.2 移植说明

目标环境：**Blender 5.2.2 LTS**（Python 3.13.13，构建 2026-09-15）。
原代码基线：`tw1lac/mdl-exporter` 的 `3.4` 分支。

---

## 1. Blender 3.4 → 5.2 的破坏性变更及处理

### 1.1 分层 / 槽位动作（4.4 引入，5.0 移除旧接口）

**症状**：`AttributeError: 'Action' object has no attribute 'fcurves'`（`Action.groups` 同样被移除）。

4.4 起动作改为「层 → 条 → 通道包（channelbag）」结构，F-Curve 归属于
(条, 槽位) 组合；`ActionChannelbagFCurves.new()` 的关键字也从 `action_group`
改名为 `group_name`。此外给一个**空**动作赋值 `animation_data.action` 不再
自动选中槽位，不绑定槽位则曲线不驱动任何东西。

**处理**：新增 `compat.py`，提供 `action_fcurves()` 门面（模拟旧
`action.fcurves` 的 `find/new/remove/get/[]/len/iter/values` 接口）与
`bind_action()`（赋值并绑定匹配槽位）。调用点全部改为走兼容层。

### 1.2 `Material.shadow_method` 移除（4.2）

阴影投射改为物体级 `Object.visible_shadow`。`compat.set_material_shadow_method()`
在新版本上退化为设置 `surface_render_method`；同时把 Principled BSDF 的插槽
访问从**下标**改为**按名**（`Specular` → `Specular IOR Level`，
`Emission` → `Emission Color` 等）。

### 1.3 网格法线 API 移除（4.1）

`Mesh.calc_normals_split` / `free_normals_split` / `use_auto_smooth` /
`auto_smooth_angle` 全部移除。`compat.mesh_calc_normals()` /
`mesh_calc_tangents()` 做版本自适应。

### 1.4 骨骼组 → 骨骼集合（4.0）

`Pose.bone_groups` / `PoseBone.bone_group` 被骨骼集合取代，且骨骼**集合**在
5.0 失去颜色属性。`compat.set_node_type_collection()` 统一两种模型。

### 1.5 其他

* **`bpy.types` 类级 `hasattr` 在任何版本上都探测不到 RNA 集合属性**，
  因此兼容层一律用**实例级** `hasattr` 或版本号判定。
* `unregister()` 漏了 `TOPBAR_MT_file_import.remove(menu_import_mdx)`，
  重复启用会叠加导入菜单项 —— 已补上。
* `bpy_extras.anim_utils.bake_action_objects` 在 4.0 改为
  `(object_action_pairs, *, frames, bake_options)`。其唯一调用点
  （`BpySceneObjects.get_bpy_armature`）已被注释掉，属死代码，仅加说明注释。

---

## 2. 修复的既有缺陷（与 Blender 版本无关）

### 2.1 导入路径

| 位置 | 问题 |
|---|---|
| `mdx_parser/parse_mdx.py` | chunk 循环假设链延伸到文件末尾；文件尾部打包器签名（`_SMINAD` 的 5 字节水印）会越界崩溃。 |
| `mdl_parser/mdl_reader.py` | 首行 `//` 注释使第一个 chunk 的标签变成 `//`，`Version` 从未被解析。现在剥离整行注释。 |
| `mdl_parser/parse_node.py` | 只把 Translation/Rotation/Scaling 当作轨道块起点，仅含 `Visibility` 轨道的节点会丢失该轨道。 |
| `mdl_parser/parse_light.py` | **只解析节点部分**，不读 `static Intensity` / `Color` / `Ambience` / `Attenuation*`，而导出器会写这些字段。已补全（含动画轨道；颜色在文件中是 BGR，读回时反序）。 |
| `create_object_actions.py` | geoset alpha 曲线按下标 `color_curves[3]` 取用，颜色关键帧全在序列区间外时列表为空 → `IndexError`。 |
| `process_warcraft_3_model.py` | 不校验 `GeosetId` 越界。 |
| `create_light_objects.py` | 灯光 chunk 允许只有动画轨道而无静态值，此时各字段为 `None` → 赋值崩溃。 |
| `create_collision_empties.py` | 不校验 `radius` / `verts` 是否存在。 |
| **全局序列** | `parse_mdx.py` 打印 "Global sequence! (unimplemented)"，`parse_mdl.py` 也没有 `GlobalSequences` 分支；而且两者都把轨道里的**索引**当成毫秒时长存进 `global_sequence`。现在两侧都解析 `GLBS` / `GlobalSequences` 并把索引解析为时长（见 §3.3）。 |
| **相机** | 见 §3.2。 |
| **粒子 / Ribbon 发射器** | 见 §3.1。 |
| **贴图动画** | 见 §3.4。 |

### 2.2 导出路径

| 位置 | 问题 |
|---|---|
| `export_mdl.py` | `save_geosets` 跳过无顶点的 geoset，但 `NumGeosets` 与各 `GeosetAnim` 的 `GeosetId` 仍用未过滤下标 → **自产文件自己读不回**。新增 `prepare_geosets()` 统一重编号。 |
| `export_mdl.py` | `save_geoset_animations` 的调试打印调用 `geosets.index()`（`War3Geoset` 按值哈希，语义不可靠）。 |
| **`from_scene.py`** | **非骨骼节点完全没有 `Parent` 行** —— 导出路径上只有骨骼会建立 `parent_node`，其他节点只带父节点**名字**，导致灯/挂点/发射器/事件/碰撞体的层级被压平。 |
| **`from_scene.py`** | **非骨骼节点被导出两次**：导入时每个 War3 节点既建了一根骨骼又建了一个物体，导出时两者都写（多出一个同名 `Bone` 块），并位移其后所有 `ObjectId`。 |
| **`from_scene.py` / `create_armature_object.py`** | **Helper 节点回来变成 Bone**：Bone/Helper 区别原本没有任何地方记录，只能靠「是否被 geoset 使用」猜测。 |
| `save_helpers.py` | 导出时把 Helper 名字改写成 `Bone_<name>`（并把 `.` 换成 `_`），靠名字前缀让导入器识别 —— 现在类型已正确记录，改名只会破坏保真度。 |
| `create_attachment_empties.py` | 给附件名追加 ` Ref` 后缀，同样是为了让导出器靠名字识别。 |
| `create_collision_empties.py` | 给碰撞体名加 `Collision ` 前缀，同上。 |
| `save_collision_shape.py` | `Cylinder` 类型写成 `Sphere` 却不写 `BoundsRadius` → 导入时 `int(None)` 崩溃。 |
| `War3RibbonEmitter.py` | `textures.index(emitter.texture_path)` 拿字符串在 `War3Texture` 列表里查找；`MaterialID` 未处理材质缺失。 |
| `War3ParticleSystem.py` | `textures.index(self.texture)` 依赖对象身份，而 `War3Texture` 无 `__eq__`；当贴图路径与材质层重复时发射器不在列表中 → `ValueError`。 |
| `War3ParticleEmitter.py` | `static Longitude` 实际写出的是 `latitude`。 |
| `BpySceneObjects.py` | `particle_settings.emtitter_type` 拼写错误（应为 `emitter_type`）→ Ribbon 发射器必崩。 |
| `BpySceneObjects.py` | 把 `ribbon_material`（可能为 `None`）直接放进 materials 集合 → 导出时 `'NoneType' object has no attribute 'name'`。 |
| `from_scene.py` | Ribbon 的贴图未登记进 `model.textures`，`TextureSlot` 无有效索引。 |
| `classes/War3Layer.py` + 两侧 `parse_layers` / `parse_materials` | **字段语义冲突**：`layer.texture_anim` 被用来存 KMTF（贴图 ID 动画）曲线，而导出侧同一字段期望的是 `War3TextureAnim`（TextureAnims 引用）。一旦模型含 KMTF，`save_texture_animations` 会去迭代动画曲线并崩溃。KMTF 曲线改用 `texture_id_anim`。 |
| `classes/War3AnimationCurve.py` | `__hash__` 直接 hash 含 list 的元组 → `TypeError: unhashable type: 'list'`。导出侧用 `set()` 去重 `tvertex_anims` 时会触发（此前该路径不可达）。 |

---

## 3. 原本完全无法导入的两类对象

### 3.1 粒子 / Ribbon 发射器

`parse_mdl.py` 与 `parse_mdx.py` 原本对 `PREM` / `PRE2` / `RIBB` 一律打印
"not implemented"，`import_stuff/` 中也没有任何代码把它们实例化为 Blender
物体，而导出侧只在 `bpy_obj.particle_systems[0].settings.mdl_particle_sys`
上寻找发射器 —— 因此发射器必然丢失。

现已补全：

* **MDX 二进制解析**：`mdx_parser/parse_particle_emitters.py`（PREM / PRE2）、
  `parse_ribbon_emitters.py`（RIBB）。每条记录以 inclusiveSize 前缀，因此遇到
  未知轨道时可以安全放弃该记录而不打乱外层 chunk 遍历。二进制布局已用 10 个
  真实文件逐字段核对（filter/rows/cols/alpha/scale 均落在合法范围，且无未知轨道）。
* **MDL 文本解析**：`mdl_parser/parse_particle_emitters.py`。静态值按**行首锚定**
  匹配，避免把 `static Speed 40` 误当成 `Speed 3 { ... }` 轨道，也避免 `Length`
  命中 `TailLength`。
* **物化**：`import_stuff/create_particle_emitters.py` 为每个发射器建一个平面
  网格物体 + Blender 粒子系统，并把设置写入 `mdl_particle_sys`。平面尺寸有意义：
  PRE2 的 `Width`/`Length` 取自 `Object.dimensions`，Ribbon 的
  `HeightAbove`/`HeightBelow` 取自 `dimensions[0] / 2`。
* `classes/War3EmitterSettings.py` 是纯 Python 的设置载体，字段与
  `War3ParticleSystemProperties` 一一对应，`apply_to()` 按名拷贝。

### 3.2 相机

MDL 侧 `parse_mdl.py` 打印 "Camera not implemented yet"，MDX 侧
`parse_mdx.py` 根本没有 `CAMS` 分支。现已补全：

* `mdx_parser/parse_cameras.py`：相机记录**不是**节点（有名字，没有
  ObjectId / ParentId / flags），静态布局为
  `name[80] → position[3] → fieldOfView → farClip → nearClip → targetPosition[3]`
  （共 116 字节），之后才是 `KCTR` / `KCRL` / `KTTR` 轨道。
* `mdl_parser/parse_cameras.py`：对应 `War3Camera.write_camera` 的文本格式，
  含 `Target { ... }` 嵌套块与其中的 `Translation` 轨道。
* `import_stuff/create_camera_objects.py`：建 Blender 相机并**对准目标**——
  导出侧是从相机朝向与景深焦距反推目标的
  （`target = matrix_world @ Vector([0, 0, -dof.focus_distance])`），所以物体沿
  自身 -Z 指向目标、焦距设为相机到目标的距离，位置与目标才能一起往返。
* `War3Camera.write_camera` 补上了 `Translation` 轨道写出（原先只写静态
  `Position`），使相机动画也能往返。

实测相机字段往返完全一致（pivot / target / fov / near / far）。

### 3.3 全局序列

两种格式都把轨道里的全局序列写成**索引**（MDL 是 `GlobalSeqId N`，MDX 是轨道头的一个 uint32），而插件其余部分用的是**毫秒时长**（`write_animation_chunk` 用时长在模型列表里反查索引）。原来 MDX 侧完全不解析 `GLBS` 且把索引当时长存下，MDL 侧连 `GlobalSequences` 块都不解析。

现在：

* `import_stuff/global_sequences.py` 作为两种解析器共享的上下文，保存当前文件的序列时长列表；`parse_mdx` / `parse_mdl` 在开始时 `reset()`。
* `mdx_parser/parse_global_sequences.py` 解析 `GLBS`（并对被 `_SMINAD` 打包器写坏的 count 做截断保护）；`mdl_parser/parse_global_sequences.py` 解析 `Duration N,`。
* `parse_timeline` / `parse_geoset_transformation` 把索引解析为时长；索引越界时告警并置 -1（列表为空时静默，因为那是这些重打包模型的常态）。

### 3.4 贴图动画（TextureAnims / TXAN）

`parse_mdx.py` 没有 `TXAN` 分支，`parse_mdl.py` 打印 "TextureAnims not implemented yet"，而导出侧只在 `layer.texture_anim` 上取动画 —— 且 `layer.texture_anim` 还被 KMTF 曲线占用（见 §2.2）。现已补全：

* `mdx_parser/parse_texture_animations.py`：每条记录含 `KTAT`（平移）/`KTAR`（旋转，四元数）/`KTAS`（缩放）。
* `mdl_parser/parse_texture_animations.py`：对应 `TVertexAnim { Translation/Rotation/Scaling N { ... } }`。
* `process_warcraft_3_model` 用图层的 `textureAnimationId` / `TVertexAnimId` 把图层与动画关联起来（TextureAnims 块在 Materials 之后，所以在解析结束后统一解析引用）。
* `import_stuff/create_texture_animations.py`：为每个有动画的图层在材质节点树里建一个 `ShaderNodeMapping` 节点（名为 `TVertexAnim_<图层序号>`）并把三条轨道写进节点树自己的动作 —— 这正是 `create_material_stuff.get_texture_anim` 读取的形式。
* 导出侧 `get_new_material2` 的节点回退分支新增 `attach_texture_animations()`，按节点名把动画放回对应图层；`get_texture_anim` 现在**优先读节点树自己的动作**（曲线本来就属于它），再回退到调用方传入的动作列表。
* 两个 Blender 无法表达的细节做了兜底：**全局序列 id** 存在动作的自定义属性上（`mdl_uv_global_seq_<节点>_<轨道>`）供导出还原；**四元数旋转**在物化时转成 Mapping 节点的欧拉角，导出时再转回四元数（`quaternion_rotation()`），否则 MDL 里会写出 3 个分量的非法旋转。
* 关键帧时间做了 **毫秒 → 帧** 换算（`frame / frame_time`），与 `create_transformation_curves` 的约定一致；否则每经过一次 MDL 往返时间都会乘以 f2ms 膨胀。

---

## 4. 验证结果（Blender 5.2.2）

测试脚本位于 `C:\Users\x\mdl_upgrade\tools\`（不属于插件本体）。

| 测试 | 结果 |
|---|---|
| 插件注册 / 注销 / 重复启停 3 轮 | 通过，注销后无残留 RNA 类型 |
| 真实模型导入（`zq` 43 个 + 其它 13 个） | **56/56** |
| 导入 → 导出 `.mdl` → 再导入 | **56/56** |
| **导出节点构成与源文件逐类型逐名字一致** | **43/43 与 13/13（零处名字差异）** |
| **被图层引用的贴图动画往返** | **43/43** |
| 合成场景导出 + 再导入 | 通过 |
| 全部模块字节码编译 | 无错误、无警告 |

「节点构成一致」由 `tools/node_fidelity.py` 度量：源文件一侧用**插件自己的**
MDX 解析器统计各 chunk 的节点数，导出侧用正则统计 `.mdl` 的节点块，两者逐类型、
逐数量、逐名字比对（Bone / Helper / Attachment / Light / ParticleEmitter /
ParticleEmitter2 / RibbonEmitter / EventObject / CollisionShape / Camera）。

「贴图动画往返」由 `tools/txan_fidelity.py` 度量：统计源文件中**被图层引用**的
去重动画数（无引用的 TextureAnims 条目是死数据，重新写出等于凭空制造引用，
因此不计入）与导出侧的 `TVertexAnim` 块数。

合成场景覆盖的导出分支：`ParticleEmitter`、`ParticleEmitter2`、
`RibbonEmitter`、`Camera`、`Light`、`EventObject`、`Attachment`、
`CollisionShape`、`Helper`、`Billboarded`、骨骼 / 蒙皮 / Geoset / Material /
Sequence。

另经逐字段核对：发射器设置与相机字段（pivot / target / fov / near / far）
在往返后完全一致。

### 关于往返后的曲线数量

往返后 `fcurves` 数量仍会上升（例如某模型 1006 → 2310 条），这是导出器**既有**
的语义，不是移植引入的重复曲线：导出会把静态轨道物化为显式关键帧，且每个节点在
`#UNANIMATED` / `all sequences` 动作中固定写入 10 条曲线
（location 3 + rotation_quaternion 4 + scale 3），实测与节点数精确吻合。

### 关于往返后的几何计数

物体数、网格数、UV 层数完全一致；顶点/面数只有千分之几的差异
（例如某模型 verts 2350 → 2341、polys 2987 → 2993）。这是导入器按
「位置 + 法线 + UV」去重顶点的粒度差异，不是数据丢失。材质数会减少，因为导出
会把共用同一贴图的多个 layer 合并进一个 Material。

---

## 5. 直接加载 .blp 贴图（新增）

Blender 完全不认识 `.blp`，所以插件自己解码。偏好设置里的「贴图扩展名」默认值由
`png` 改为 **`blp`**：直接加载原始 `.blp`，不需要事先转换。

* `import_stuff/blp.py` 是纯 Python 解码器（不依赖 bpy）：
  * **BLP1** 压缩 0（内嵌 JPEG）与压缩 1（调色板）
  * **BLP2** 压缩 1（调色板）、2（DXT1/DXT3/DXT5，含单独的 8 位 alpha 平面）、
    3（原始 BGRA）
* 内嵌 JPEG 交给 Blender 自己的解码器（经临时文件），因此**渐进式、CMYK
  （4 分量）**这类 JPEG 也能正确解出——实测颜色正常，没有反相或通道丢失。
* BLP1-JPEG 的 mipmap 表**不可信**：被 `_SMINAD` 之类工具重打包过的文件里，
  这张表整体错位一格（`mipmapOffsets[0]` 指向的是 mip1），因此改为按 JPEG 自身
  的 `FFD8FF` / `FFD9` 标记定位满尺寸图，它固定位于 160 字节头部之后。
* 解码结果写进一个新建的 Blender 图像并 `pack()`，同时把**模型文件里的原始
  War3 路径**记在图像的 `mdl_texture_path` 自定义属性上；导出侧
  （`collect_tex_nodes`）优先用它，这样导出的模型引用的是
  `Textures\Foo.blp` 这类游戏能找到的路径，而不是本地磁盘路径。
  （此前贴图常常解析不到，导出写的是空路径或 `D:\...` 绝对路径。）
* 顺带修掉两个非 Blender 版本的坑：
  * 对**未打包**的图像设置 `filepath` 会让 Blender 去读那个路径（`.blp` 读不了），
    把刚写进去的像素冲成黑色 —— 所以 `pack()` 必须**先于**路径设置，并且要用
    `filepath_raw`（用 `filepath` 还会让 Blender 刷一行
    `ERROR: Image "" not available`）。
  * `image.has_data` 对打包图像是懒加载的：必须先访问一次 `image.size`，
    否则会误判成"没有像素数据"。
* 导入结束时会打印一行汇总，便于一眼判断贴图为什么是空白：
  `贴图：共 N 个 —— 解码 a，直接读取 b，解码失败 c，未找到 d`，并列出未找到的路径。
* 新增的模块已补进各 `reload_*.py` 清单（`blp`、`global_sequences`、相机/粒子/飘带/
  贴图动画的解析与创建模块），否则「重载脚本」会漏掉它们。

实测：语料里 43 个模型共引用 141 个贴图路径（196 次引用），其中 87 个
（140 次）文件在磁盘上不存在；**凡是磁盘上存在的（56 次）全部成功加载**。

### 5.1 同时修掉的 PRE2 解析缺陷

`PRE2`（ParticleEmitter2）记录里，`PriorityPlane` 之后、轨道列表之前还有**一个
uint32**（规范里的 geometry emitter type）。原来的代码只在 `version >= 900` 时才读它，
但实际文件里**版本 800 也有**，于是轨道起点整体偏移 4 字节，解析器读到全零标签后
放弃整条记录——表现是刷屏 `unknown PRE2 track '\x00\x00\x00\x00'`，
**并且该发射器的所有动画轨道丢失**。

改为不写死长度：从静态字段末尾起，按 4 字节对齐寻找第一个合法的轨道头
（标签已知 + 关键帧数量合理 + 时间戳能放进记录）。256 条记录里 246 条偏移是 4 字节，
另有 10 条（如 `zuoqi_VIP19_SMINAD`）多出 56 字节，探测法一并覆盖。

修复后整个语料的 `unknown PRE2 track` 警告从 256 条降到 **0 条**，
发射器参数（速率/寿命/速度/行列）全部读到合理值。

### 5.2 从 MPQ 归档直接加载（新增）

偏好设置新增两项：

* **魔兽3 目录** —— 魔兽争霸3 安装目录（含 `war3.mpq`、`War3x.mpq` 等）。
* **允许从 MPQ 中直接加载** —— 默认开启。

查找顺序（**MPQ 优先级最低**，确保玩家自己的贴图总是优先）：

1. 贴图资源目录
2. 备用贴图目录
3. 魔兽3 目录里的 MPQ 归档

`import_stuff/mpq.py` 是一个纯 Python 的 MPQ 读取器（无需外部 DLL），支持
hash/block 表解密、按名查找、以及 stored / zlib / bzip2 / PKWare implode /
huffman / sparse / 分扇区 / 单块 / 加密 / FIX_KEY 各种存储方式。归档在首次使用时
打开并缓存，改动偏好设置会立刻作废缓存。

实现过程中修掉三个读取缺陷（都会让贴图读成空）：

* **单块文件没有分扇区表**：`archived_size == file_size` 且不超过一个扇区的块
  是整块存放的，把有效载荷当作扇区表来解析是读空的原因。
* **重打包归档把整文件存放**却不设 `COMPRESS` 标志（只留 `MPQ_FILE_EXISTS`），
  这类块同样没有分扇区表。改为按**文件签名**（`BLP1`/`BLP2`/`MDLX` 等）判断，
  而不是只看标志位。
* 每个扇区自带压缩类型字节，因此即使块标志没写 `COMPRESS`，也要逐扇区尝试解压。

实测效果（用户的地图解包目录 + `D:\Game\Warcraft3`）：

| 项目 | 数量 |
|---|---|
| 模型引用的贴图路径 | 12184 个（15642 次引用） |
| 磁盘上缺失的 | 495 个（1423 次引用） |
| 能从 MPQ 取出的 | 197 个 |
| **能解出可用像素的** | **12 个（52 次引用）** |
| 归档内已损坏、取不出的 | 185 个 |

也就是说 MPQ 这一级确实有用，但收成有限：大部分缺失的是**地图自带的自定义贴图**
（`jn\`、`zq\` 等），游戏原版归档里没有；而该机 `war3.mpq` 是被裁剪过的残缺副本，
许多贴图（例如 `Textures\Flare.blp`：磁盘版 4794 字节、SOF=(32,32)，归档版只有
2436 字节、25.9% 零字节、无有效 SOF）在归档里就已经损坏。这类贴图现在会打印
`from MPQ but unusable (damaged in the archive)`，并按「未找到」统计，不会伪装成
加载成功。

同时也修正了 BLP1 内嵌 JPEG 的**结尾定位**：不再搜索第一个 `FFD9`（COM/APP 段里
可能碰巧出现这两个字节，会截断图像并让 Blender 报 `Empty JPEG image`），而是按
JPEG 段结构扫描到真正的 EOI。

### 5.3 修掉 `TXAN` 块被丢弃（影响 27 个模型）

`SUB_CHUNKS_MDX_MODEL`（MDX 块白名单）里漏了 `CHUNK_TEXTURE_ANIMATIONS`（`TXAN`）。
`parse_mdx` 的分支里其实**已经有**处理 `TXAN` 的代码，但白名单先一步把它判为未知块，
于是走进 `else` 分支、整块内容被丢掉。

症状很像模型损坏：`zuoqi_VIP23_SMINAD.mdx` 导入后日志报

```
unknown chunk_id: "{TXAN}" expected "{('VERS', 'GEOS', 'TEXS', ...)}"
```

并且该模型的**贴图动画全部缺失**。文件本身是好的。

影响范围（扫了整个解包目录的 2213 个 `.mdx`）：**27 个模型**带 `TXAN`，全部受影响，
包括 `wq\wuqi_ck_2_SMINAD.mdx`、`jn\jn_ds_15lbhf_1_SMINAD.mdx`、`gw\guai_hongshe.mdx` 等。

修复后 `zuoqi_VIP23_SMINAD.mdx` 解析结果：6 张贴图、**2 条贴图动画**（修复前为 0）、
8 个 geoset、50 根骨骼、3 个辅助体、6 个挂点、14 个粒子发射器、1 条飘带、1 个相机。

同时把 `else` 分支的提示改成醒目中文（`警告：跳过了未知的块 ...`），因为走到这里
意味着该块内容会**静默地**不进模型，很容易被误判成模型损坏。

### 5.4 修掉蒙皮权重未归一化（模型“炸开”/碎片化）

`create_mesh_objects.py` 把顶点权重写成 `weight_list[i] / 255.0`，但**没有在多个
骨骼影响之间归一化**。魔兽3 的权重是**相对值**：一个顶点刚性绑定到两根骨骼时，
两个权重都是 255，除以 255 后各得 1.0，**和为 2.0**。

Blender 的骨架修改器期望一个顶点的权重**和为 1**。权重和是 2/3/4 的顶点会被
放大 2～4 倍地跟随骨骼位移，于是模型看起来像**炸开的碎片**、大片黑色多边形交错，
但几何体本身、UV、材质、骨骼其实全都是正确的——很容易被误判成模型损坏。

实测 `zuoqi_VIP23_SMINAD.mdx` 第一个 geoset 的权重和分布：

```
修复前：{1.0: 104, 2.0: 16, 3.0: 5, 4.0: 3}
修复后：{1.0: 128}
```

修复方式：先把一个顶点的所有非零影响收集起来求总和，再按 `weight / total` 写入。
导出侧的 `fix_skin_bones` 本来就会把权重重新缩放到 255，所以往返精度不受影响
（43+13 个模型仍是 56/56 完全往返）。

### 5.5 关于 `zuoqi_VIP23_SMINAD.mdx` 的排查结论（不是缺陷）

该模型被报告“导入后显示有问题”。逐项核对后确认**导入是正确的**，列表如下：

| 检查项 | 结果 |
|---|---|
| 顶点权重和 | 全部为 1.0（偏差 0.0000） |
| 骨骼静止姿态下的顶点位移 | 8 个 geoset 全部为 0.000（骨架没有推移任何顶点） |
| 骨骼 | 75 根，无零长度骨骼，无未归位的 pose |
| 解析出的顶点坐标 vs 导入坐标 | 完全一致 |
| UV / 材质 / 贴图 | 8 个 geoset 全部正常，贴图全部解码 |

**看起来“碎片化/炸开”的真正原因**：这个模型里有两组**特效面片 geoset**
（`jn_zuoqi_VIP23_SMINAD`，128×128，黑底 + 蓝色发光）。魔兽争霸3 用**加法混合**
渲染它们，所以在 Blender 的普通渲染下它们是一块块**不透明的黑色平面**，
把本体遮住，看起来就像模型散了架。

**使用建议**：

* 在大纲视图里隐藏 `jn_*` 那几个网格，只看本体（`zuoqi_VIP23_SMINAD`）即可确认形态正常。
* 或者在这些材质的材质属性里把混合模式改成 `Alpha Blend`，并把图层的混合模式设为「叠加」。

这一点也写进了 BLP 解析的教训：`check_effect_tex.py` 一度把 BLP1 头部字段读错位
（报出 `4x1` 这种不可能的尺寸），实际头部是
`compression=0, alphaBits=8, width=256, height=256`，与内嵌 JPEG 的尺寸一致。
解码器本身没有问题，是那个临时诊断脚本的字段标签写错了。

---

## 6. 按 open-realm `mdx_preview` 的参考实现逐字节对照后的修正

参照物：`D:\Dev\C++\open-realm\Godot\addons\mdx_preview`（open-realm 引擎
`games/warcraft-3/renderer/mdx/r_mdx_*.c` 的纯 C# 逐字节验证移植）以及据此
写出的命令行探针 `refprobe`（`blp` / `mpqextract` / `mpqlist` / `mdxdump`）。
原则：**以参考实现 + 真实语料的逐字节一致为准**，不以"能打开文件"为准。

### 6.1 `import_stuff/mpq.py` 重写

| 项 | 修正前 | 修正后 |
|---|---|---|
| ADPCM | 完全不识别 0x40/0x80/0x41/0x81，落到 explode 兜底解出噪声且不报错 | 移植 Blizzard ADPCM（步长表、`(channel+1)%channels` 轮转、0x80 降步长 / 0x81 升步长特例） |
| Huffman (0x01) | 用"前 256 字节当码长表"的静态表 + MSB 位流 | FGK 自适应树（profile 必须为 7、LSB-first 位流、256=EOS、逃逸码插新符号后重平衡） |
| Implode (0x08) | ZIP-implode 风格，完全不消费 DCL 两字节头 | PKWare blast（lit ≤1、dict 4..6、EOS len==519、LSB-first 位序） |
| 是否压缩 | 靠"大小 + 文件头魔数嗅探"猜 | 只按 `flags & COMPRESS`，三段式：未压缩 → 单块 → 扇区表 |
| 块索引 | 未掩码，越界抛 `IndexError` | `blk &= 0x0FFFFFFF` + 越界显式失败 |
| 归档基址 | 只认文件 0 偏移 | 前 1024 字节搜索 `MPQ\x1a`（`.w3m`/`.w3x` 的 HM3W 前缀因此可读） |
| 哈希查找 | 单遍探针 | 补第二遍全表扫描（重建/重打包过的归档） |
| 文件名规范化 | `str.upper()`（Unicode 感知）+ 不裁剪斜杠 | `CanonicalizeKey`（`/`→`\`、仅 ASCII 折小写、截断 1023）+ `TrimEdgeSlashes` |
| 基名 | `os.path.basename`（Linux/macOS 不认 `\`，导致所有加密条目解出乱码） | 手写按 `\` 与 `/` 切分 |
| 扇区表 | 不校验、失败静默返回半截数据 | 单调性与上界校验，非法时先用明文再按 `fileKey-1` 重解，仍非法即报错 |
| SECTOR_CRC | 按标志多读一个表项 | 与参考一致地忽略该标志 |
| listfile | UTF-8 优先 + 只 strip | Latin-1 + 路径规范化 + `(listfile)` 预载索引 |
| raw-deflate 兜底 | 存在（`War3Patch.mpq` 里 `Maps\Campaign\*.w3m` 的 0xD5 扇区会被误接受） | 删除，扇区解压失败即报错 |
| 32 位回绕 | `step >> shift` 按 Python 语义（不回绕） | `diff = step >> (shift & 31)`（对齐 C#/C 的 mod 32 语义） |

**验证**：558 个抽样条目（war3/War3Patch/War3x/War3xLocal 四个归档，含
ENCRYPTED\|COMPRESS 的 `.blp`、0x41/0x81 的 `.wav`、0x08 的 `.html`、
未压缩跨多扇区的 `.w3m`/`.tga`）与 `refprobe mpqextract` 逐字节比较：
**一致 557、不一致 0、双方一致失败 1**（`Units\Undead\Ghoul\GhoulWarcry1.wav`，
组合掩码 0x71，参考同样报扇区读取失败）。

### 6.2 `import_stuff/blp.py` 重写 + 新增 `import_stuff/wc3_jpeg.py`

| 项 | 修正前 | 修正后 |
|---|---|---|
| BLP1 表偏移 | offsets 读 0x20、lengths 读 0x60（错位一个字段） | offsets 0x1C、lengths 0x5C、data 0x9C、JPEG 头区 0xA0 |
| BLP2 表偏移 | 宽高读 0x10/0x14，表位置靠"一致性"猜 | offsets 0x14、lengths 0x54、palette 0x94、头长 0x494 |
| WC3 四分量 JPEG | 直接交给 Blender（libjpeg 按 CMYK/YCCK 判定，报 `ERR_PARSE_ERROR`） | 自带解码器 `wc3_jpeg.py`：SOF Nf=4、分量按 B,G,R,A、不做 YCbCr 变换，baseline 与 progressive 两条路径、整数 IDCT |
| JPEG 定位 | 扫描 `FFD8FF` 找（重打包过的 `.blp` 会取错切片） | 用头部 `jpegHeaderSize` + `offsets[0]/lengths[0]` |
| 调色板 alpha | 只支持 8 位，且 alphaBits=0 时错用调色板条目 alpha | 0/1/4/8 四种（0 = 全 255，1 = LSB 位图，4 = 低半字节复制，8 = 每像素一字节） |
| 565 → 888 | 复制位法（数值与参考不同） | `r*255/31`、`g*255/63`、`b*255/31` 整数除法 |
| DXT | 靠 alphaDepth/alphaEncoding 猜解码器、DXT1 恒按 `c0>c1` | 按参考的 `ResolveDxtFormat` 判定，DXT1/3/5 逐字节移植 |
| Mip | 只解第 0 级 | 逐级解码 |

**验证**：真实语料 220 个 `.blp`（含 512×512）+ 合成 BLP2 40 个（调色板
0/1/4/8 位 × 多尺寸、DXT1/3/5 各组合、原始 BGRA、非法组合）+ 100 个 BLP1
四分量 JPEG 样本，与参考逐字节比较**全部一致**；非法形态双方一致拒绝。

### 6.3 `import_stuff/mdx_parser/` 解析修正

- **PRE2**：`KP2V`→Visibility、`KP2R`→Variation（原来两 tag 对调且 `KP2R` 不在
  白名单，导致其后所有轨道被丢）；静态段补齐第 4 个 uint（Squirt）；滤镜表用
  PRE2 专用的 5 值表（0 混合 / 1 相加 / 2 调制 / 3 2 倍调制 / 4 AlphaKey）。
- **PREM**：`FileNameLength` 为 260 字节且其后没有 flags 字段（原来少读 180 字节
  又多读 4 字节，后续 7 条轨道全部静默失效）；轨道标签改用
  `KPEE/KPEG/KPLN/KPLT/KPEL/KPES/KPEV`。
- **MTLS**：消费材质级的 `KMTE/KMTA/KMTF` 子块（原来读完 priority/flags 就假定
  紧跟 `LAYS`，层数据与后续材质整体错位）；priority 按有符号读取（真实模型里有
  −5/−4/−3）。
- **KEVT**：事件键改用原始列表保存（同一时间戳的多条键不再被 dict 折叠）。
- **ATCH**：`Path` 256 字节 + 保留 uint + `attachmentId` + `KATV` 可见性。
- **GEOS**：按 tag 驱动而非固定顺序；未知子块跳 4 字节；用"元素数 × 元素大小"
  校验剩余；`inclusive_size < 4` 时不再回退读取位置（原来会死循环），改为逐字节
  重同步；双 UV（`UVAS` 通道数 + `UVBS` 拆成 uv/uv2）。
- **通用**：未知插值类型不再多读；`0xFFFFFFFF` 统一归一为 −1；`SEQS` 用有符号
  并按 `flags & 1` 判 NonLooping；`TEXS` 保存 wrapFlags；`CLID` 未知 type 归
  Box（原来当 Sphere 少读 12 字节）；`RIBB` 六条轨道独立；顶层逐块 try/except
  与尾部残留字节提示。

**验证**：3381 个 `.mdx` 全部逐字段与 `refprobe mdxdump` 对比通过
（materials / sequences / textures / cameras / attachments / counts 全 0 差异）。

### 6.4 运行期语义（导入 → 导出往返）

- **材质层标志**：`ShadingFlags` 现在展开成 Unshaded / TwoSided / Unfogged /
  NoDepthTest / NoDepthSet（原来只存进一个从未被引用的字段，重新导出时永久丢失）。
- **节点标志位**：新增 `export_mdl/node_flags.py` 统一位映射，
  `Billboarded` / 三个锁轴 / `DontInheritTranslation|Rotation|Scaling` /
  `CameraAnchored` 现在会写入 Blender 宿主（`Object.mdl_billboard` 与骨骼的
  `warcraft_3.nodeFlags`）、并被导出端读回。此前 `Billboarded` 一类标志在
  `.mdx` 主路径上永远是 False（文本 `.mdl` 路径才有），往返一次即丢失。
- **发射器标志**：PRE2 的 `Unshaded` / `SortPrimsFarZ` / `LineEmitter` /
  `Unfogged` / `ModelSpace` / `XYQuad` 与 PREM 的 `EmitterUsesMDL` /
  `EmitterUsesTGA` 现在按位还原（PREM 原来无条件写 `EmitterUsesMDL`）。
- **滤镜模式 1/2**：`1` 是 AlphaKey（1 位 alpha 测试）、`2` 才是 Blend，
  原来写反；相应地 `Transparent` 映射到 Blender 的 `CLIP` 而不是 `BLEND`。

实测语料中的分布：PRE2 里 Unshaded 2908 个、SortPrimsFarZ 1207 个、LineEmitter
277 个、XYQuad 295 个、ModelSpace 226 个、Unfogged 622 个（共 3947）；层标志中
`0x10` TwoSided、`0x20` Unfogged、`0x40/0x80` 深度相关各数百层；滤镜模式 1
（AlphaKey）约 2200 层。

### 6.5 验证方式（本机没有 Blender 本体）

本机没有 `blender.exe`，因此**没有做 Blender 内的端到端导入冒烟**。替代做法：

1. 用打了桩（`bpy`/`mathutils` 替身）的探针直接调用
   `import_stuff/mdx_parser/parse_mdx`，把解析结果与参考实现逐字段对比。
2. BLP / MPQ 直接用 `refprobe` 的输出做逐字节比较。
3. 全插件 `python -m compileall` 通过，确认无语法/缩进错误。

语料规模：`.mdx` 3381 个、`.blp` 247 个（另加合成 40 个）、MPQ 抽样 558 条。

---

## 7. 已知的剩余缺口

1. **贴图动画与图层的对应关系在多层材质上不保证精确。** 导入的材质没有
   `mdl_layers` 条目，导出侧走 `layers_from_mat_nodes` 从节点图重建图层，其图层数
   与源材质不一定相同（例如源材质 6 层、重建后 5 层）。动画本身会完整写出，
   `TVertexAnimId` 指向的图层序号则按名字里的序号尽量对齐、越界时退回第 0 层并
   打印提示。实测 43 个模型里被引用的动画 100% 往返，但 `layer refs` 计数在部分
   模型上会减少。
2. **`BpySceneObjects.get_bpy_armature` 是死代码**，仍针对 4.0 之前的
   `bake_action_objects` 签名；重新启用前需要移植。
3. 若要以 Blender 4.2+ 的**扩展（extension）**形式分发，需要补
   `blender_manifest.toml` 并改为安装到扩展目录。当前以传统
   `scripts/addons/` 形式工作正常（已验证出现在插件列表中、可正常启停）。
4. **导出端只写 `.mdl` 文本**：`export_mdl/write_mdx.py` 仍是空壳
   （`def write_mdx(): pass`），无法导出 `.mdx` 二进制。
5. **没有在 Blender 本体里做过端到端冒烟**（本机无 `blender.exe`）：
   第 6 节所有导入侧改动（节点标志写回宿主、层标志展开等）只做了静态核对与
   纯 Python 逐字段对比，物化到 Blender 对象后的表现需要在装有 Blender 的机器上复验。
6. **同一时间戳的多条关键帧仍会被折叠**：插件用 `{时间: 值}` 字典保存轨道，
   而 MDX 允许同一时间戳有多条键（Blender 的 F-Curve 也是每帧一键，无法承载）。
   实测 3381 个模型里只有 6 个受影响（4 个蜘蛛的事件轨道、Arthas 的事件轨道、
   Infernal 的 geoset 颜色轨道）。彻底还原需要把 `War3AnimationCurve.keyframes`
   改成 `(时间, 值)` 序列并同步所有消费方，属跨模块改动。
7. **`GLBS` 首字段的语义差**：MDX 规范里第一个 uint 是时长个数，参考实现与游戏
   引擎却把它当 `durations[0]`。插件按规范读，因此当模型的 `GlobalSeqId` 恰好
   等于时长个数时插件算出 −1（3381 个模型里 481 个会出现这种情况，其中真正引用
   该序列的极少）。保持规范行为，差异记录在此。
