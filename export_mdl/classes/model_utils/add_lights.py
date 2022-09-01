from typing import Tuple, List, Set

import bpy
from mathutils import Vector, Matrix

from ..War3AnimationAction import War3AnimationAction
from ..War3ExportSettings import War3ExportSettings
from ..War3Light import War3Light
from ..War3Model import War3Model
from ..War3Node import War3Node
from ..War3AnimationCurve import War3AnimationCurve
from ..animation_curve_utils.get_wc3_animation_curve import get_wc3_animation_curve
from .get_visibility import get_visibility
from .register_global_sequence import register_global_sequence
from ..bpy_helpers.BpyLight import BpyLight
from ...properties import War3LightSettings


def add_lights(war3_model: War3Model, billboard_lock: Tuple[bool, bool, bool], billboarded: bool,
               bpy_obj: bpy.types.Object,
               settings: War3ExportSettings):
    visibility = get_visibility(war3_model.sequences, bpy_obj)
    pivot = settings.global_matrix @ Vector(bpy_obj.location)
    light = War3Light(bpy_obj.name, pivot)
    # light.bpy_obj = bpy_obj
    light.pivot = settings.global_matrix @ Vector(bpy_obj.location)
    light.billboarded = billboarded
    light.billboard_lock = billboard_lock

    # obj: bpy.types.Light = bpy_obj
    bpy_light: bpy.types.Light = bpy_obj.data
    if isinstance(bpy_light, bpy.types.Light):
        print("data is Light")
    if isinstance(bpy_light, bpy.types.PointLight):
        print("data is PointLight")
    # data: bpy.types.PointLight = bpy_obj.data
    # data.animation_data
    print("light data: ", bpy_light)

    if hasattr(bpy_light, "mdl_light"):
        light_data: War3LightSettings = bpy_light.mdl_light
        light.type = light_data.light_type

        light.intensity = light_data.intensity
        light.intensity_anim = get_wc3_animation_curve(bpy_light.animation_data, 'mdl_light.intensity', 1, war3_model.sequences)
        # get_curve(obj.data, ['mdl_light.intensity'])

        register_global_sequence(war3_model.global_seqs, light.intensity_anim)

        light.atten_start = light_data.atten_start
        light.atten_start_anim = get_wc3_animation_curve(bpy_light.animation_data, 'mdl_light.atten_start', 1, war3_model.sequences)
        # get_curve(obj.data, ['mdl_light.atten_start'])

        register_global_sequence(war3_model.global_seqs, light.atten_start_anim)

        light.atten_end = light_data.atten_end
        light.atten_end_anim = get_wc3_animation_curve(bpy_light.animation_data, 'mdl_light.atten_end', 1, war3_model.sequences)
        # get_curve(obj.data, ['mdl_light.atten_end'])

        register_global_sequence(war3_model.global_seqs, light.atten_end_anim)

        light.color = light_data.color
        light.color_anim = get_wc3_animation_curve(bpy_light.animation_data, 'mdl_light.color', 3, war3_model.sequences)
        # get_curve(obj.data, ['mdl_light.color'])

        register_global_sequence(war3_model.global_seqs, light.color_anim)

        light.amb_color = light_data.amb_color
        light.amb_color_anim = get_wc3_animation_curve(bpy_light.animation_data, 'mdl_light.amb_color', 3, war3_model.sequences)
        # get_curve(obj.data, ['mdl_light.amb_color'])

        register_global_sequence(war3_model.global_seqs, light.amb_color_anim)

        light.amb_intensity = light_data.amb_intensity
        light.amb_intensity_anim = get_wc3_animation_curve(bpy_light.animation_data, 'mdl_light.amb_intensity', 1, war3_model.sequences)
        # get_curve(obj.data, ['obj.mdl_light.amb_intensity'])

        register_global_sequence(war3_model.global_seqs, light.amb_intensity_anim)

    light.visibility = visibility
    register_global_sequence(war3_model.global_seqs, visibility)
    war3_model.objects['light'].add(light)


def get_lights(sequences: List[War3AnimationAction], global_seqs: Set[int],
               bpy_light: BpyLight, global_matrix: Matrix):
    visibility = get_visibility(sequences, bpy_light.bpy_obj)
    pivot = global_matrix @ Vector(bpy_light.location)
    light = War3Light(bpy_light.name, pivot, bpy_light.bpy_obj.matrix_basis)

    light.billboarded = bpy_light.billboarded
    light.billboard_lock = bpy_light.billboard_lock

    # obj: bpy.types.Light = bpy_obj
    # bpy_light: bpy.types.Light = bpy_obj.data
    if isinstance(bpy_light.bpy_light, bpy.types.Light):
        print("data is Light")
    if isinstance(bpy_light.bpy_light, bpy.types.PointLight):
        print("data is PointLight")
    print("light data: ", bpy_light.bpy_light)

    animation_data = bpy_light.bpy_light.animation_data
    if hasattr(bpy_light.bpy_light, "mdl_light"):
        light_data: War3LightSettings = bpy_light.bpy_light.mdl_light
        light.type = light_data.light_type

        light.intensity = light_data.intensity
        light.intensity_anim = get_wc3_animation_curve(animation_data, 'mdl_light.intensity', 1, sequences)

        register_global_sequence(global_seqs, light.intensity_anim)

        light.atten_start = light_data.atten_start
        light.atten_start_anim = get_wc3_animation_curve(animation_data, 'mdl_light.atten_start', 1, sequences)

        register_global_sequence(global_seqs, light.atten_start_anim)

        light.atten_end = light_data.atten_end
        light.atten_end_anim = get_wc3_animation_curve(animation_data, 'mdl_light.atten_end', 1, sequences)

        register_global_sequence(global_seqs, light.atten_end_anim)

        light.color = light_data.color
        light.color_anim = get_wc3_animation_curve(animation_data, 'mdl_light.color', 3, sequences)

        register_global_sequence(global_seqs, light.color_anim)

        light.amb_color = light_data.amb_color
        light.amb_color_anim = get_wc3_animation_curve(animation_data, 'mdl_light.amb_color', 3, sequences)

        register_global_sequence(global_seqs, light.amb_color_anim)

        light.amb_intensity = light_data.amb_intensity
        light.amb_intensity_anim = get_wc3_animation_curve(animation_data, 'mdl_light.amb_intensity', 1, sequences)

        register_global_sequence(global_seqs, light.amb_intensity_anim)

    light.visibility = visibility
    register_global_sequence(global_seqs, visibility)
    return light
