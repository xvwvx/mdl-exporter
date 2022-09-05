import itertools
from typing import List, Union, Dict, Set, Optional, Tuple

import bpy
from mathutils import Matrix

from .BpyEmitter import BpyEmitter
from .BpyEmptyNode import BpyEmptyNode
from .BpyGeoset import BpyGeoset
from .BpyLight import BpyLight
from ..War3ExportSettings import War3ExportSettings
from ..model_utils.get_bpy_mesh import get_bpy_mesh
from ...properties import War3SequenceProperties, War3ParticleSystemProperties


class BpySceneObjects:
    def __init__(self, context: bpy.types.Context, settings: War3ExportSettings):
        self.actions: List[bpy.types.Action] = []
        self.sequences: List[War3SequenceProperties] = []
        self.materials: Set[bpy.types.Material] = set()

        self.meshes: List[bpy.types.Object] = []
        self.cameras: List[bpy.types.Object] = []

        self.particle1s: List[BpyEmitter] = []
        self.particle2s: List[BpyEmitter] = []
        self.ribbons: List[BpyEmitter] = []

        self.attachments: List[BpyEmptyNode] = []
        self.events: List[BpyEmptyNode] = []
        self.helpers: List[BpyEmptyNode] = []
        self.collisions: List[BpyEmptyNode] = []
        self.lights: List[BpyLight] = []

        self.geosets: List[BpyGeoset] = []
        self.bone_names: List[str] = []

        # self.bpy_nodes: Dict[bpy.types.Object, List[bpy.types.PoseBone]] = {}
        # self.bpy_meshes: Dict[bpy.types.Object, bpy.types.Mesh] = {}
        self.armatures: List[bpy.types.Object] = []
        self.bpy_nodes: Dict[str, List[bpy.types.PoseBone]] = {}
        self.bpy_meshes: Dict[str, Tuple[bpy.types.Object, bpy.types.Mesh]] = {}
        self.from_scene(context, settings)

    def from_scene(self, context: bpy.types.Context,
                   settings: War3ExportSettings):
        print("context: ", context)

        scene: bpy.types.Scene = context.scene

        frame2ms: float = 1000 / context.scene.render.fps  # Frame to millisecond conversion
        self.actions.extend(bpy.data.actions)
        self.sequences.extend(scene.mdl_sequences)

        objects: List[bpy.types.Object]

        if settings.use_selection:
            objects = list(obj for obj in scene.objects if obj.select_get() and obj.visible_get())
        else:
            objects = list(obj for obj in scene.objects if obj.visible_get())

        for bpy_obj in objects:
            self.parse_bpy_objects(bpy_obj, settings.global_matrix)

        for armature_id, arm_pose_bones in self.bpy_nodes.items():
            for pose_bone in arm_pose_bones:
                self.bone_names.append(pose_bone.name)

        for bpy_emitter in self.ribbons:
            particle_settings: War3ParticleSystemProperties = bpy_emitter.particle_settings
            mat: bpy.types.Material = particle_settings.ribbon_material
            self.materials.add(mat)

        for bpy_obj in self.meshes:
            bpy_mesh = get_bpy_mesh(bpy_obj, context, settings.global_matrix @ bpy_obj.matrix_world)
            # self.bpy_meshes[bpy_obj] = bpy_mesh
            self.bpy_meshes[bpy_obj.name] = (bpy_obj, bpy_mesh)
            self.collect_material(bpy_mesh, bpy_obj)
            self.make_bpy_geosets(bpy_mesh, bpy_obj)

    def parse_bpy_objects(self, bpy_obj: bpy.types.Object, global_matrix: Matrix):
        obj_name = bpy_obj.name

        # Particle Systems
        if len(bpy_obj.particle_systems):
            data = bpy_obj.particle_systems[0].settings
            if getattr(data, "mdl_particle_sys"):
                particle_settings: War3ParticleSystemProperties = data.mdl_particle_sys
                if particle_settings.emiter_type == 'ParticleEmitter':
                    self.particle1s.append(BpyEmitter(bpy_obj, global_matrix, particle_settings))
                elif particle_settings.emiter_type == 'ParticleEmitter2':
                    self.particle2s.append(BpyEmitter(bpy_obj, global_matrix, particle_settings))
                elif particle_settings.emiter_type == 'RibbonEmitter':
                    self.ribbons.append(BpyEmitter(bpy_obj, global_matrix, particle_settings))

        elif bpy_obj.type == 'MESH' or bpy_obj.type == 'CURVE':
            self.meshes.append(bpy_obj)

        elif bpy_obj.type == 'EMPTY':
            print("empty, mat:", bpy_obj.matrix_world)
            print("mat is mat:", isinstance(bpy_obj.matrix_world, Matrix))
            print("mat is list:", isinstance(bpy_obj.matrix_world, List))
            if obj_name.startswith("SND") \
                    or obj_name.startswith("UBR") \
                    or obj_name.startswith("FTP") \
                    or obj_name.startswith("SPL"):
                self.events.append(BpyEmptyNode(bpy_obj, global_matrix))
            elif bpy_obj.type == 'EMPTY' and obj_name.startswith('Collision'):
                self.collisions.append(BpyEmptyNode(bpy_obj, global_matrix))
            elif obj_name.endswith(" Ref"):
                self.attachments.append(BpyEmptyNode(bpy_obj, global_matrix))
            elif obj_name.startswith("Bone_"):
                self.helpers.append(BpyEmptyNode(bpy_obj, global_matrix))

        elif bpy_obj.type == 'ARMATURE':
            self.armatures.append(bpy_obj)
            self.bpy_nodes[bpy_obj.name] = bpy_obj.pose.bones

        elif bpy_obj.type in ('LAMP', 'LIGHT'):
            if isinstance(bpy_obj, bpy.types.Light):
                print("is Light")
            if isinstance(bpy_obj, bpy.types.PointLight):
                print("is PointLight")
            if isinstance(bpy_obj, bpy.types.SunLight):
                print("is SunLight")
            self.lights.append(BpyLight(bpy_obj, global_matrix))

        elif bpy_obj.type == 'CAMERA':
            self.cameras.append(bpy_obj)

    def make_bpy_geosets(self, bpy_mesh: bpy.types.Mesh, bpy_obj: bpy.types.Object):
        for i, m in enumerate(bpy_mesh.materials):
            self.geosets.append(BpyGeoset(bpy_mesh, bpy_obj, i))

    def collect_material(self, bpy_mesh: bpy.types.Mesh, bpy_obj: bpy.types.Object):
        anim_tuple: Tuple[Optional[Tuple[float]], Tuple[str, bpy.types.AnimData]] \
            = self.get_anim_tuple(bpy_obj)
        for bpy_material in bpy_mesh.materials:
            if bpy_material is not None:
                self.materials.add(bpy_material)



    def get_anim_tuple(self, obj: bpy.types.Object)\
            -> Tuple[Optional[Tuple[float]], Tuple[str, bpy.types.AnimData]]:
        vertex_color_anim = ('color', obj.animation_data)
        vertex_color: Optional[Tuple[float]] = None
        if any(i < 0.999 for i in obj.color[:3]):
            vertex_color = tuple(obj.color[:3])
        if not any((vertex_color, vertex_color_anim)):
            mat = obj.active_material
            if mat is not None and hasattr(mat, "node_tree") and mat.node_tree is not None:
                node = mat.node_tree.nodes.get("VertexColor")
                if node is not None:
                    attr = "outputs" if node.bl_idname == 'ShaderNodeRGB' else "inputs"
                    vertex_color = tuple(getattr(node, attr)[0].default_value[:3])
                    if hasattr(mat.node_tree, "animation_data"):
                        vertex_color_anim = ('nodes["VertexColor"].%s[0].default_value', mat.node_tree.animation_data)

        return vertex_color, vertex_color_anim
