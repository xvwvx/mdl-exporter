import bpy
from bpy.props import EnumProperty
from bpy.types import Operator


class WAR3_OT_create_collision_shape(Operator):
    """新建一个碰撞体：游戏里点击单位时用的判定形状。
导出时球体写成 Sphere，方块写成 Box；圆柱形没有对应的格式，会按球体近似导出。"""
    bl_idname = "object.create_collision_shape"
    bl_label = "添加碰撞体"

    shape: EnumProperty(
        name="形状",
        description="碰撞体的形状。球体用于大多数单位；方块适合建筑等方正的模型",
        items=[('SPHERE', "球体碰撞", ""),
               ('CUBE', "方块碰撞", "")],
        default='SPHERE'
        )

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)

    def execute(self, context):
        bpy.ops.object.empty_add(type=self.shape, radius=1.0, align='WORLD', location=context.scene.cursor.location)

        obj = context.active_object
        counter = 0

        while True:
            if not any((bpy.data.objects.get("Collision%s%d" % (name, counter)) for name in ('Box', 'Sphere'))):
                obj.name = "Collision%s%d" % ('Sphere' if self.shape == 'SPHERE' else 'Box', counter)
                break
            counter += 1

        return {'FINISHED'}
