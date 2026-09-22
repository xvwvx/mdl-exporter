import bpy.types
from bpy.props import EnumProperty
import os
from bpy.types import Operator


def load_texture_list():
    directory = os.path.dirname(__file__)

    path = os.path.join(directory, "../textures.txt")
    texture_list = []
    with open(path, 'r') as f:
        texture_list = [(line[:-1], os.path.basename(line[:-1]), os.path.basename(line[:-1])) for line in f.readlines()]

    return texture_list


texture_paths = load_texture_list()


class WAR3_OT_search_texture(Operator):
    """从魔兽争霸3 内建贴图列表里查找并填入贴图路径。"""
    bl_idname = "object.search_texture"
    bl_label = "查找贴图"
    bl_options = {'REGISTER', 'INTERNAL'}
    bl_property = "path"

    target: EnumProperty(
                name="目标类型",
                description="把选中的贴图填给谁：发射器的贴图，还是材质的图层",
                items=[('Emitter', '发射器', ''),
                       ('Material', '材质图层', '')]
            )

    path: EnumProperty(
                name="贴图路径",
                items=texture_paths
            )

    def invoke(self, context, event):
        wm = context.window_manager
        wm.invoke_search_popup(self)
        return {'FINISHED'}

    def execute(self, context: bpy.types.Context):
        try:
            if self.target == 'Material':
                mat = context.active_object.active_material
                i = mat.mdl_layer_index
                item = mat.mdl_layers[i]
                item.path = self.path
            else:
                psys = context.active_object.particle_systems.active.settings.mdl_particle_sys
                psys.texture_path = self.path

        except IndexError:
            pass

        return {'FINISHED'}
