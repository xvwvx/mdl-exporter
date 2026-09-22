# -- Object types -- #
# Bone
# Light
# Helper
# Attachment
# Particle Emitter
# Particle Emitter 2
# Ribbon Emitter
# Event Object
# Collision shape
# ------------------ #
import datetime
import getpass
from typing import List

import bpy
from mathutils import Matrix

from .save_attachment_points import save_attachment_points
from .save_bones import save_bones
from .save_cameras import save_cameras
from .save_collision_shape import save_collision_shape
from .save_event_objects import save_event_objects
from .save_geoset_animations import save_geoset_animations
from .save_geosets import save_geosets
from .save_global_sequences import save_global_sequences
from .save_helpers import save_helpers
from .save_lights import save_lights
from .save_materials import save_materials
from .save_model_emitters import save_model_emitters
from .save_model_header import save_model_header
from .save_particle_emitters import save_particle_emitters
from .save_pivot_points import save_pivot_points
from .save_ribbon_emitters import save_ribbon_emitters
from .save_sequences import save_sequences
from .save_texture_animations import save_texture_animations
from .save_textures import save_textures
from ..classes.War3ExportSettings import War3ExportSettings
from ..classes.War3Model import War3Model
from ..classes.model_utils.from_scene import from_scene
from ..compat import bind_action
from ..utils import float2str


def save(operator, context: bpy.types.Context, settings: War3ExportSettings, filepath="", mdl_version=800):

    print("Save, context: ", context)
    scene = context.scene

    current_frame = scene.frame_current
    obj_to_anim = {}  # save objects' active action
    for obj in scene.objects:
        if obj.animation_data is not None:
            obj_to_anim[obj] = obj.animation_data.action
    scene.frame_set(0)

    frame2ms: float = 1000 / context.scene.render.fps  # Frame to millisecond conversion
    model: War3Model = from_scene(context, settings)

    for obj, anim in obj_to_anim.items():  # set objects' active actions
        bind_action(obj, anim)
    scene.frame_set(current_frame)

    write_model_file(filepath, mdl_version, model, frame2ms, settings)
    print('Done saving "%s"' % filepath)


def write_model_file(filepath: str, mdl_version: int, model: War3Model, frame2ms: float, settings: War3ExportSettings):
    prepare_geosets(model)
    with open(filepath, 'w') as output:
        fw = output.write

        date = datetime.datetime.now().strftime("%a %b %d %H:%M:%S %Y")
        fw("// Exported on %s by %s\n" % (date, getpass.getuser()))

        if settings.use_skinweights:
            fw("Version {\n\tFormatVersion %d,\n}\n" % 1000)
        else:
            fw("Version {\n\tFormatVersion %d,\n}\n" % mdl_version)
        # HEADER
        save_model_header(fw, model)

        # SEQUENCES
        save_sequences(fw, model.sequences, model.global_extents_min, model.global_extents_max, frame2ms)

        # GLOBAL SEQUENCES
        save_global_sequences(fw, model.global_seqs)

        # TEXTURES
        save_textures(fw, model.textures)

        # MATERIALS
        save_materials(fw, model.materials, model.textures, model.tvertex_anims, model.global_seqs)

        # TEXTURE ANIMATIONS
        save_texture_animations(fw, model.tvertex_anims, model.global_seqs)

        # GEOSETS
        save_geosets(fw, model, settings)

        # GEOSET ANIMS
        save_geoset_animations(fw, model.geoset_anims, model.geosets, model.global_seqs)

        # BONES
        save_bones(fw, model)

        # LIGHTS
        save_lights(fw, model)

        # HELPERS
        save_helpers(fw, model)

        # ATTACHMENT POINTS
        save_attachment_points(fw, model.attachments, model.global_seqs)

        # PIVOT POINTS
        save_pivot_points(fw, model.objects_all)

        # MODEL EMITTERS
        save_model_emitters(fw, model.particle_systems, model.global_seqs)

        # PARTICLE EMITTERS
        save_particle_emitters(fw, model)

        # RIBBON EMITTERS
        save_ribbon_emitters(fw, model)

        # CAMERAS
        save_cameras(fw, model, settings)

        # EVENT OBJECTS
        save_event_objects(fw, model.event_objects, model.global_seqs)

        # COLLISION SHAPES
        save_collision_shape(fw, model.collision_shapes)

        if settings.use_skinweights:
            fw("BindPose {\n")
            fw("\tMatrices %s {\n" % (len(model.objects_all) + len(model.cameras)))
            for obj in model.objects_all:
                obj_mat = mat_to_tuple(obj.bindpose)
                bp = tuple(obj_mat) + (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
                fw("\t\t{ %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s },\n" % tuple(map(float2str, bp[0:12])))
            for cam in model.cameras:
                cam_mat = mat_to_tuple(cam.bindpose)
                bp = tuple(cam_mat) + (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
                fw("\t\t{ %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s },\n" % tuple(map(float2str, bp[0:12])))
            fw("\t}\n")
            fw("}\n")


def mat_to_tuple(mat: Matrix):
    v_list: List[float] = []
    for row in mat:
        v_list.extend(list(row))
    return tuple(v_list)


def prepare_geosets(model: War3Model) -> None:
    """Drop vertex-less geosets and renumber the geoset animations to match.

    ``save_geosets`` skips geosets that have no vertices, but the header's
    ``NumGeosets`` and every ``GeosetAnim``'s ``GeosetId`` were still derived from
    the unfiltered list.  A skipped geoset therefore shifted all later indices and
    could leave a ``GeosetId`` pointing past the last geoset -- producing a file
    this addon's own importer then rejects.

    ``War3Geoset`` compares and hashes by value, so geoset identity has to be
    tracked with ``id()``.
    """
    total = len(model.geosets)
    if not total:
        return
    kept = [g for g in model.geosets if len(g.vertices)]
    if len(kept) == total:
        return

    kept_ids = {id(g) for g in kept}
    new_index = {id(g): i for i, g in enumerate(kept)}
    old_to_new = {}
    for old_index, geoset in enumerate(model.geosets):
        if id(geoset) in kept_ids:
            old_to_new[old_index] = len(old_to_new)

    dropped = total - len(kept)
    print("  skipping %d geoset(s) with no vertices" % dropped)

    model.geosets = kept
    surviving = []
    for anim in model.geoset_anims:
        if anim.geoset is not None:
            index = new_index.get(id(anim.geoset))
        else:
            index = old_to_new.get(anim.geoset_id)
        if index is None:
            print("  dropped geoset animation for a skipped geoset")
            continue
        anim.geoset_id = index
        surviving.append(anim)
    model.geoset_anims = surviving
