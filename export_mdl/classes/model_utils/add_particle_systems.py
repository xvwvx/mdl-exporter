from typing import Optional, Set, List

import bpy
from mathutils import Vector, Matrix

from ..War3AnimationAction import War3AnimationAction
from ..War3Emitter import War3Emitter
from ..War3ExportSettings import War3ExportSettings
from ..War3Model import War3Model
from ..War3ParticleEmitter import War3ParticleEmitter
from ..War3ParticleSystem import War3ParticleSystem
from .is_animated_ugg import is_animated_ugg
from .get_visibility import get_visibility
from .register_global_sequence import register_global_sequence
from ..War3RibbonEmitter import War3RibbonEmitter
from ..bpy_helpers.BpyEmitter import BpyEmitter
from ..utils.transform_rot import transform_rot
from ..utils.transform_vec import transform_vec, transform_vec1
from ...properties import War3ParticleSystemProperties


def add_particle_systems(war3_model: War3Model,
                         billboard_lock,
                         billboarded,
                         mats: Set[bpy.types.Material],
                         bpy_obj: bpy.types.Object,
                         parent_name: Optional[str],
                         settings: War3ExportSettings):
    sequences = war3_model.sequences
    global_seqs = war3_model.global_seqs
    visibility = get_visibility(sequences, bpy_obj)
    animation_data: bpy.types.AnimData = bpy_obj.animation_data
    anim_loc, anim_rot, anim_scale = is_animated_ugg(sequences, animation_data, settings)
    data = bpy_obj.particle_systems[0].settings
    global_matrix = settings.global_matrix

    if anim_loc is not None:
        transform_vec1(anim_loc, global_matrix)

    if anim_rot is not None:
        transform_rot(anim_rot.keyframes, global_matrix)

    if getattr(data, "mdl_particle_sys"):
        # particle_sys = War3ParticleSystem(bpy_obj.name, bpy_obj, war3_model)
        pivot = global_matrix @ Vector(bpy_obj.location)
        particle_settings: War3ParticleSystemProperties = data.mdl_particle_sys

        if particle_settings.emiter_type == 'ParticleEmitter':
            particle_sys: War3ParticleEmitter = War3ParticleEmitter(bpy_obj.name, anim_loc, anim_rot, anim_scale, parent_name, pivot)
            particle_sys.set_from(bpy_obj, sequences, global_seqs)
            particle_sys.visibility = visibility

            register_global_sequence(global_seqs, visibility)
            register_global_sequence(global_seqs, anim_loc)
            register_global_sequence(global_seqs, anim_rot)
            register_global_sequence(global_seqs, anim_scale)

            particle_sys.billboarded = billboarded
            particle_sys.billboard_lock = billboard_lock

            war3_model.particle_systems.append(particle_sys)

        elif particle_settings.emiter_type == 'ParticleEmitter2':
            particle_sys: War3ParticleSystem = War3ParticleSystem(bpy_obj.name, anim_loc, anim_rot, anim_scale, parent_name, pivot)
            particle_sys.set_from(bpy_obj, sequences, global_seqs)
            particle_sys.dimensions = Vector(map(abs, global_matrix @ bpy_obj.dimensions))
            particle_sys.visibility = visibility

            particle_sys.billboarded = billboarded
            particle_sys.billboard_lock = billboard_lock
            war3_model.particle_systems2.append(particle_sys)

        elif particle_settings.emiter_type == 'RibbonEmitter':
            particle_sys: War3RibbonEmitter = War3RibbonEmitter(bpy_obj.name, anim_loc, anim_rot, anim_scale, parent_name, pivot)
            particle_sys.set_from(bpy_obj, sequences, global_seqs)
            particle_sys.dimensions = Vector(map(abs, global_matrix @ bpy_obj.dimensions))
            particle_sys.visibility = visibility

            particle_sys.billboarded = billboarded
            particle_sys.billboard_lock = billboard_lock

            mat: bpy.types.Material = particle_sys.emitter.ribbon_material
            mats.add(mat)

            war3_model.particle_ribbon.append(particle_sys)

        else:
            particle_sys: War3Emitter = War3Emitter(bpy_obj.name, anim_loc, anim_rot, anim_scale, parent_name, pivot)
            # particle_sys.set_from(bpy_obj, sequences, global_seqs)
            particle_sys.dimensions = Vector(map(abs, global_matrix @ bpy_obj.dimensions))
            particle_sys.visibility = visibility

            particle_sys.billboarded = billboarded
            particle_sys.billboard_lock = billboard_lock

        if particle_sys is not None:
            register_global_sequence(global_seqs, visibility)
            register_global_sequence(global_seqs, anim_loc)
            register_global_sequence(global_seqs, anim_rot)
            register_global_sequence(global_seqs, anim_scale)


def get_particle_emitter(sequences: List[War3AnimationAction],
                         global_seqs: Set[int],
                         billboard_lock,
                         billboarded,
                         bpy_obj: bpy.types.Object,
                         parent_name: Optional[str],
                         settings: War3ExportSettings):
    visibility = get_visibility(sequences, bpy_obj)
    animation_data: bpy.types.AnimData = bpy_obj.animation_data

    anim_loc, anim_rot, anim_scale = is_animated_ugg(sequences, animation_data, settings)

    register_global_sequence(global_seqs, visibility)
    register_global_sequence(global_seqs, anim_loc)
    register_global_sequence(global_seqs, anim_rot)
    register_global_sequence(global_seqs, anim_scale)

    data = bpy_obj.particle_systems[0].settings

    global_matrix = settings.global_matrix
    if anim_loc is not None:
        transform_vec1(anim_loc, global_matrix)

    if anim_rot is not None:
        transform_rot(anim_rot.keyframes, global_matrix)

    pivot = global_matrix @ Vector(bpy_obj.location)
    particle_settings: War3ParticleSystemProperties = data.mdl_particle_sys

    particle_sys: War3ParticleEmitter = War3ParticleEmitter(bpy_obj.name, anim_loc, anim_rot, anim_scale, parent_name, pivot)
    particle_sys.set_from(bpy_obj, sequences, global_seqs)
    particle_sys.visibility = visibility

    particle_sys.billboarded = billboarded
    particle_sys.billboard_lock = billboard_lock

    return particle_sys


def get_particle_emitter2(sequences: List[War3AnimationAction],
                          global_seqs: Set[int],
                          billboard_lock,
                          billboarded,
                          bpy_obj: bpy.types.Object,
                          parent_name: Optional[str],
                          settings: War3ExportSettings):
    visibility = get_visibility(sequences, bpy_obj)
    animation_data: bpy.types.AnimData = bpy_obj.animation_data

    anim_loc, anim_rot, anim_scale = is_animated_ugg(sequences, animation_data, settings)

    register_global_sequence(global_seqs, visibility)
    register_global_sequence(global_seqs, anim_loc)
    register_global_sequence(global_seqs, anim_rot)
    register_global_sequence(global_seqs, anim_scale)

    data = bpy_obj.particle_systems[0].settings

    global_matrix = settings.global_matrix
    if anim_loc is not None:
        transform_vec1(anim_loc, global_matrix)

    if anim_rot is not None:
        transform_rot(anim_rot.keyframes, global_matrix)

    pivot = global_matrix @ Vector(bpy_obj.location)
    particle_settings: War3ParticleSystemProperties = data.mdl_particle_sys

    particle_sys: War3ParticleSystem = War3ParticleSystem(bpy_obj.name, anim_loc, anim_rot, anim_scale, parent_name, pivot)
    particle_sys.set_from(bpy_obj, sequences, global_seqs)
    particle_sys.dimensions = Vector(map(abs, global_matrix @ bpy_obj.dimensions))
    particle_sys.visibility = visibility

    particle_sys.billboarded = billboarded
    particle_sys.billboard_lock = billboard_lock

    return particle_sys


def get_ribbon_emitter(sequences: List[War3AnimationAction],
                       global_seqs: Set[int],
                       billboard_lock,
                       billboarded,
                       bpy_obj: bpy.types.Object,
                       parent_name: Optional[str],
                       settings: War3ExportSettings):
    visibility = get_visibility(sequences, bpy_obj)
    animation_data: bpy.types.AnimData = bpy_obj.animation_data

    anim_loc, anim_rot, anim_scale = is_animated_ugg(sequences, animation_data, settings)

    register_global_sequence(global_seqs, visibility)
    register_global_sequence(global_seqs, anim_loc)
    register_global_sequence(global_seqs, anim_rot)
    register_global_sequence(global_seqs, anim_scale)

    data = bpy_obj.particle_systems[0].settings

    global_matrix = settings.global_matrix
    if anim_loc is not None:
        transform_vec1(anim_loc, global_matrix)

    if anim_rot is not None:
        transform_rot(anim_rot.keyframes, global_matrix)

    pivot = global_matrix @ Vector(bpy_obj.location)
    particle_settings: War3ParticleSystemProperties = data.mdl_particle_sys

    particle_sys: War3RibbonEmitter = War3RibbonEmitter(bpy_obj.name, anim_loc, anim_rot, anim_scale, parent_name, pivot)
    particle_sys.set_from(bpy_obj, sequences, global_seqs)
    particle_sys.dimensions = Vector(map(abs, global_matrix @ bpy_obj.dimensions))
    particle_sys.visibility = visibility

    particle_sys.billboarded = billboarded
    particle_sys.billboard_lock = billboard_lock

    return particle_sys

######


def get_particle_emitter(sequences: List[War3AnimationAction],
                         global_seqs: Set[int],
                         bpy_emitter: BpyEmitter,
                         optimize_animation: bool,
                         optimize_tolerance: bool,
                         global_matrix: Matrix):
    visibility = get_visibility(sequences, bpy_emitter.bpy_obj)
    animation_data: bpy.types.AnimData = bpy_emitter.bpy_obj.animation_data

    anim_loc, anim_rot, anim_scale = is_animated_ugg(sequences, animation_data, optimize_animation, optimize_tolerance)

    register_global_sequence(global_seqs, visibility)
    register_global_sequence(global_seqs, anim_loc)
    register_global_sequence(global_seqs, anim_rot)
    register_global_sequence(global_seqs, anim_scale)

    if anim_loc is not None:
        transform_vec1(anim_loc, global_matrix)

    if anim_rot is not None:
        transform_rot(anim_rot.keyframes, global_matrix)

    pivot = global_matrix @ Vector(bpy_emitter.bpy_obj.location)

    particle_sys: War3ParticleEmitter = War3ParticleEmitter(bpy_emitter.bpy_obj.name, anim_loc, anim_rot, anim_scale,
                                                            bpy_emitter.parent_name, pivot,
                                                            bpy_emitter.bpy_obj.matrix_basis)
    particle_sys.set_from(bpy_emitter.bpy_obj, sequences, global_seqs)
    particle_sys.visibility = visibility

    particle_sys.billboarded = bpy_emitter.billboarded
    particle_sys.billboard_lock = bpy_emitter.billboard_lock

    return particle_sys


def get_particle_emitter2(sequences: List[War3AnimationAction],
                          global_seqs: Set[int],
                          bpy_emitter: BpyEmitter,
                          optimize_animation: bool,
                          optimize_tolerance: bool,
                          global_matrix: Matrix):
    visibility = get_visibility(sequences, bpy_emitter.bpy_obj)
    animation_data: bpy.types.AnimData = bpy_emitter.bpy_obj.animation_data

    anim_loc, anim_rot, anim_scale = is_animated_ugg(sequences, animation_data, optimize_animation, optimize_tolerance)

    register_global_sequence(global_seqs, visibility)
    register_global_sequence(global_seqs, anim_loc)
    register_global_sequence(global_seqs, anim_rot)
    register_global_sequence(global_seqs, anim_scale)

    if anim_loc is not None:
        transform_vec1(anim_loc, global_matrix)

    if anim_rot is not None:
        transform_rot(anim_rot.keyframes, global_matrix)

    pivot = global_matrix @ Vector(bpy_emitter.bpy_obj.location)


    particle_sys: War3ParticleSystem = War3ParticleSystem(bpy_emitter.bpy_obj.name, anim_loc, anim_rot, anim_scale, bpy_emitter.parent_name, pivot, bpy_emitter.bpy_obj.matrix_basis)
    particle_sys.set_from(bpy_emitter.bpy_obj, sequences, global_seqs)
    particle_sys.dimensions = Vector(map(abs, global_matrix @ bpy_emitter.bpy_obj.dimensions))
    particle_sys.visibility = visibility

    particle_sys.billboarded = bpy_emitter.billboarded
    particle_sys.billboard_lock = bpy_emitter.billboard_lock

    return particle_sys


def get_ribbon_emitter(sequences: List[War3AnimationAction],
                       global_seqs: Set[int], bpy_emitter: BpyEmitter,
                       optimize_animation: bool,
                       optimize_tolerance: bool,
                       global_matrix: Matrix):
    visibility = get_visibility(sequences, bpy_emitter.bpy_obj)
    animation_data: bpy.types.AnimData = bpy_emitter.bpy_obj.animation_data

    anim_loc, anim_rot, anim_scale = is_animated_ugg(sequences, animation_data, optimize_animation, optimize_tolerance)

    register_global_sequence(global_seqs, visibility)
    register_global_sequence(global_seqs, anim_loc)
    register_global_sequence(global_seqs, anim_rot)
    register_global_sequence(global_seqs, anim_scale)

    if anim_loc is not None:
        transform_vec1(anim_loc, global_matrix)

    if anim_rot is not None:
        transform_rot(anim_rot.keyframes, global_matrix)

    pivot = global_matrix @ Vector(bpy_emitter.location)

    particle_sys: War3RibbonEmitter = War3RibbonEmitter(bpy_emitter.name, anim_loc, anim_rot, anim_scale,
                                                        bpy_emitter.parent_name, pivot,
                                                        bpy_emitter.bpy_obj.matrix_basis)
    particle_sys.set_from(bpy_emitter.bpy_obj, sequences, global_seqs)
    particle_sys.dimensions = Vector(map(abs, global_matrix @ bpy_emitter.bpy_obj.dimensions))
    particle_sys.visibility = visibility

    particle_sys.billboarded = bpy_emitter.billboarded
    particle_sys.billboard_lock = bpy_emitter.billboard_lock

    return particle_sys
