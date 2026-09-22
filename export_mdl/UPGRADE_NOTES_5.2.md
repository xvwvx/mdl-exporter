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

## 5. 已知的剩余缺口

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
