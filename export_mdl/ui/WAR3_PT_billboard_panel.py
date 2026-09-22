import bpy
from bpy.props import PointerProperty
from bpy.types import Panel

from ..properties import War3BillboardProperties
from ..properties.War3NodeProperties import (NODE_TYPE_ATTACHMENT,
                                             NODE_TYPE_COLLISION_SHAPE,
                                             NODE_TYPE_EVENT, NODE_TYPE_HELPER,
                                             get_object_node_type)


class WAR3_PT_billboard_panel(Panel):
    """让节点始终面向镜头（广告牌效果）。
导入的挂点、辅助体、事件、碰撞体，以及灯光，都会显示这个面板；
勾选后导出时会写出 Billboarded 标志和对应的轴向锁定。"""
    bl_idname = "WAR3_PT_billboard_panel"
    bl_label = "MDL 广告牌选项"
    bl_region_type = 'WINDOW'
    bl_space_type = 'PROPERTIES'
    bl_context = 'object'

    @classmethod
    def register(cls):
        bpy.types.Object.mdl_billboard = PointerProperty(type=War3BillboardProperties.War3BillboardProperties)

    @classmethod
    def unregister(cls):
        del bpy.types.Object.mdl_billboard

    @classmethod
    def poll(cls, context):
        obj = bpy.context.active_object

        if obj is None:
            return False

        # 导入的节点带着自己的魔兽争霸3节点类型；手工搭的场景回退到旧的名字约定。
        if get_object_node_type(obj) in (NODE_TYPE_ATTACHMENT, NODE_TYPE_HELPER,
                                         NODE_TYPE_EVENT,
                                         NODE_TYPE_COLLISION_SHAPE):
            return True

        if obj.type == 'EMPTY' and obj.name.lower().startswith("bone"):
            return True

        if obj.type in ('LAMP', 'LIGHT'):
            return True

        if obj.name.endswith(" Ref"):
            return True

        return False

    def draw(self, context):
        layout = self.layout
        data = bpy.context.active_object.mdl_billboard
        layout.prop(data, "billboarded")
        column = layout.column()
        column.enabled = data.billboarded
        column.prop(data, "billboard_lock_x")
        column.prop(data, "billboard_lock_y")
        column.prop(data, "billboard_lock_z")