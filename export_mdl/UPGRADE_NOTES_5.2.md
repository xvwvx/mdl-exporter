# export_mdl —— Blender 3.4 → 5.2 移植说明

目标环境：**Blender 5.2.2 LTS**（Python 3.13.13，构建 2026-09-15）。
原代码基线：`tw1lac/mdl-exporter` 的 `3.4` 分支。

---

## 1. Blender 3.4 → 5.2 的破坏性变更及处理

### 1.1 分层 / 槽位动作（Blender 4.4 引入，5.0 移除旧接口）

**症状**：`AttributeError: 'Action' object has no attribute 'fcurves'`（`Action.groups` 同样被移除）。

4.4 起动作改为「层 → 条 → 通道包（channelbag）」结构，F-Curve 归属于
(条, 槽位) 组合；`ActionChannelbagFCurves.new()` 的关键字也从 `action_group`
改名为 `group_name`。此外给一个**空**动作赋值 `animation_data.action` 不再
自动选中槽位，不绑定槽位则曲线不驱动任何东西。

**处理**：新增 `compat.py`，提供 `action_fcurves()` 门面（模拟旧
`action.fcurves` 的 `find/new/remove/get/[]/len/iter/values` 接口）与
`bind_action()`（赋值并绑定匹配槽位）。调用点全部改为走兼容层。

涉及：`utils.py`、`classes/animation_curve_utils/get_wc3_animation_curve.py`、
`import_stuff/create_armature_actions.py`、`import_stuff/create_object_actions.py`、
`import_stuff/create_other_objects.py`、`classes/bpy_helpers/BpySceneObjects.py`、
`properties/War3ArmatureProperties.py`、`properties/War3ArmatureSequenceListItem.py`、
`operators/WAR3_OT_add_seq_to_armature.py`、`export_mdl/export_mdl.py`。

### 1.2 `Material.shadow_method` 移除（4.2）

`shadow_method` 已删除（阴影投射改为物体级 `Object.visible_shadow`）。
`compat.set_material_shadow_method()` 在新版本上退化为设置
`surface_render_method`，并保留 `blend_method`（4.2 起枚举仅剩
OPAQUE/CLIP/HASHED/BLEND）。

同时把 Principled BSDF 的插槽访问从**下标**改为**按名**：`Specular` →
`Specular IOR Level`，`Emission` → `Emission Color` 等。

涉及：`import_stuff/War3BpyMaterial.py`、`import_stuff/create_material.py`。

### 1.3 网格法线 API 移除（4.1）

`Mesh.calc_normals_split` / `free_normals_split` / `use_auto_smooth` /
`auto_smooth_angle` 全部移除；角法线现由 sharp-edge / sharp-face 属性惰性推导。
`compat.mesh_calc_normals()` / `mesh_calc_tangents()` 做版本自适应（并在无 UV
层时安全跳过切线计算）。

涉及：`classes/model_utils/get_bpy_mesh.py`。

### 1.4 骨骼组 → 骨骼集合（4.0）

`Pose.bone_groups` / `PoseBone.bone_group` 被骨骼集合取代；且骨骼**集合**在
5.0 失去了颜色属性，颜色改挂在骨骼自身（`Bone.color.palette`）。
`compat.set_node_type_collection()` 统一两种模型。

涉及：`properties/War3NodeProperties.py`、`operators/WAR3_OT_update_bone_settings.py`。

> 注：`import_stuff/create_bone_groups.py`（旧路径）与
> `create_bone_collections.py`（4.0+ 路径）的分支逻辑原本就存在，未改动。

### 1.5 其他

* `bpy.types` 类级 `hasattr` 在**任何**版本上都探测不到 RNA 集合属性，
  因此兼容层一律用**实例级** `hasattr` 或版本号判定。
* `unregister()` 漏了 `TOPBAR_MT_file_import.remove(menu_import_mdx)`，
  重复启用会叠加导入菜单项 —— 已补上。
* `bpy_extras.anim_utils.bake_action_objects` 在 4.0 改为
  `(object_action_pairs, *, frames, bake_options)`。其唯一调用点
  （`BpySceneObjects.get_bpy_armature`）在本分支中已被注释掉，属死代码，
  仅加了说明注释，未改写。

---

## 2. 验证过程中暴露并修复的既有缺陷（与 Blender 版本无关）

这些缺陷在 3.4 上同样存在，但会阻塞端到端验证，故一并修复：

| 位置 | 问题 |
|---|---|
| `import_stuff/mdx_parser/parse_mdx.py` | chunk 循环假设链一直延伸到文件末尾；文件尾部的打包器签名（如 `_SMINAD` 的 5 字节水印）会越界崩溃。改为边界检查 + 忽略尾随字节。 |
| `import_stuff/create_object_actions.py` | geoset alpha 曲线按下标 `color_curves[3]` 取用；当颜色关键帧全在序列区间外时列表为空 → `IndexError`。改为持有曲线引用。 |
| `import_stuff/process_warcraft_3_model.py` | 不校验 `GeosetId` 是否越界。改为越界即告警丢弃。 |
| `export_mdl/export_mdl.py` | `save_geosets` 会跳过无顶点的 geoset，但 `NumGeosets` 与各 `GeosetAnim` 的 `GeosetId` 仍用未过滤下标 → 自产文件自己读不回。新增 `prepare_geosets()` 统一重编号。 |
| `export_mdl/save_geoset_animations.py` | 调试打印里调用 `geosets.index()`（`War3Geoset` 按值哈希，语义不可靠）。已移除。 |
| `export_mdl/save_collision_shape.py` | `Cylinder` 类型写成 `Sphere` 却不写 `BoundsRadius` → 导入时 `int(None)` 崩溃。形状关键字与半径现在一并决定。 |
| `import_stuff/create_collision_empties.py` | 不校验 `radius` / `verts` 是否存在。已加防护。 |
| `classes/bpy_helpers/BpySceneObjects.py` | `particle_settings.emtitter_type` 拼写错误（应为 `emitter_type`）→ Ribbon 发射器必崩。 |
| `classes/War3RibbonEmitter.py` | `textures.index(emitter.texture_path)` 拿字符串在 `War3Texture` 列表里查找；`MaterialID` 未处理材质缺失。改为按路径查找并安全回退。 |
| `classes/model_utils/from_scene.py` | Ribbon 的贴图未登记进 `model.textures`，导致 `TextureSlot` 无有效索引。已补。 |
| `import_stuff/create_light_objects.py` | 灯光 chunk 允许只有动画轨道而无静态值，此时各字段为 `None` → 赋值崩溃。已加防护。 |
| `operators/WAR3_OT_emitter_set_from_bpy.py` | `p_sys.child_type is 'NONE'`（`is` 比较字符串字面量，SyntaxWarning）。 |

---

## 3. 验证结果（Blender 5.2.2）

测试脚本位于 `C:\Users\x\mdl_upgrade\tools\`（不属于插件本体）。

| 测试 | 结果 |
|---|---|
| 插件注册 / 注销 / 重复启停 3 轮 | 通过，注销后无残留 RNA 类型 |
| 真实模型导入（`D:\rpg\output\files\zq` 43 个 + 其它 13 个） | **56/56** |
| 导入 → 导出 `.mdl` → 再导入（43 个角色模型） | **43/43** |
| 同上（13 个道具/发射器模型） | **13/13** |
| 合成场景导出（覆盖真实语料未触及的路径） | 通过 |
| 合成场景 `.mdl` 再导入 | 通过 |
| 全部 222 个模块字节码编译 | 无错误、无警告 |

合成场景覆盖的导出分支：`ParticleEmitter`、`ParticleEmitter2`、
`RibbonEmitter`、`Camera`、`Light`、`EventObject`、`Attachment`、
`CollisionShape`、`Helper`、`Billboarded`、骨骼 / 蒙皮 / Geoset / Material /
Sequence。

### 关于往返后的计数差异

往返后 `bones` 与 `fcurves` 数量会上升（例如某模型 1006 → 2310 条曲线），
这是导出器**既有**的语义，不是移植引入的重复曲线：

* 导出会把静态轨道物化为显式关键帧；
* `should_be_bone` 的 helper 节点会写成 `Bone` chunk；
* 每个节点的 `#UNANIMATED` / `all sequences` 动作固定写入 10 条曲线
  （location 3 + rotation_quaternion 4 + scale 3），实测与节点数精确吻合。

几何量（`verts` / `polys`）往返基本一致。

---

## 4. 已知的既有功能缺口（本次未实现，与版本无关）

1. **粒子发射器无法往返。**
   * MDX 解析器（`mdx_parser/parse_mdx.py`）根本不识别 `PRE1`/`PRE2`/`RIBB` 块，
     仅打印 "unknown or unimplemented chunkId"。
   * 即便走 MDL 文本路径解析出了发射器，`import_stuff/` 中**没有任何代码**把
     `model.particle_systems` / `particle_systems2` / `particle_ribbon`
     实例化为 Blender 物体（没有创建 Blender 粒子系统）。
   * 而导出侧只在 `bpy_obj.particle_systems[0].settings.mdl_particle_sys`
     上寻找发射器，因此导入再导出必然丢失发射器。
   * 导出侧本身是完整的（合成场景已验证可写出 `ParticleEmitter` /
     `ParticleEmitter2` / `RibbonEmitter`），可用 UI 手工建发射器后导出。

2. **骨骼节点类型（`bone.warcraft_3`）功能未接线。**
   `properties/War3NodeProperties.py` 定义了 `War3NodeProperties`，但
   `__init__.py` 的 `prop_classes` 未注册它，因此 `bone.warcraft_3` 不存在；
   `WAR3_OT_update_bone_settings` 也未列入 `op_classes`。二者目前都是死代码。
   （已顺手把它们的 4.0+ 骨骼集合兼容写好，注册后即可用。）

3. **MDL 文本解析器的灯光不完整。**
   `mdl_parser/parse_light.py` 只解析节点部分，不读 `static Intensity` /
   `Color` / `Ambience` / `Attenuation*`，而导出器会写这些字段。
   MDX 二进制路径不受影响。

4. 若要让本插件以 Blender 4.2+ 的**扩展（extension）**形式分发，需要补
   `blender_manifest.toml` 并改为安装到扩展目录。当前以传统
   `scripts/addons/` 形式工作正常（已验证出现在插件列表中、可正常启停）。
