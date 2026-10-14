import itertools
from typing import List, Dict, Set

import bpy
from mathutils import Vector, Matrix

from .create_material_stuff import get_new_material2
from .make_bones import parse_armatures
from ..War3AnimationAction import War3AnimationAction
from ..War3Bone import War3Bone
from ..War3Camera import War3Camera
from ..War3CollisionShape import War3CollisionShape
from ..War3Emitter import War3Emitter
from ..War3ExportSettings import War3ExportSettings
from ..War3Helper import War3Helper
from ..War3Material import War3Material
from ..War3Layer import War3Layer
from ..War3Model import War3Model
from .add_empties_animations import get_event, get_helper, get_bone, get_attachment, get_collision
from .add_lights import get_lights
from .add_particle_systems import get_particle_emitter, get_particle_emitter2, get_ribbon_emitter
from .get_actions import get_actions
from ..War3Node import War3Node
from .make_mesh import create_geoset, get_geoset_anim, create_geoset_bone, create_armature_bone
from ..War3Texture import War3Texture
from ..bpy_helpers.BpySceneObjects import BpySceneObjects
from ...properties.War3NodeProperties import (NODE_TYPE_BONE, NODE_TYPE_HELPER,
                                              get_node_type)
from ...utils import calc_extents


def from_scene(context: bpy.types.Context,
               settings: War3ExportSettings) -> War3Model:
    print("context: ", context)

    print("from_scene!")

    bpy_scene_objects = BpySceneObjects(context, settings)

    frame2ms: float = 1000 / context.scene.render.fps  # Frame to millisecond conversion
    model_name = bpy.path.basename(context.blend_data.filepath).replace(".blend", "")
    war3_model = War3Model(model_name)

    sequences, actions = get_actions(frame2ms, bpy_scene_objects.actions,
                                     settings.use_actions, bpy_scene_objects.sequences)
    war3_model.sequences.extend(sequences)

    parse_bpy_objects2(bpy_scene_objects, settings, war3_model, actions)
    node_types = get_scene_node_types(bpy_scene_objects)
    skinned_bones = collect_scene_bone_names(bpy_scene_objects)
    link_parents_and_drop_standin_bones(war3_model, node_types, skinned_bones)

    for bpy_geoset in bpy_scene_objects.geosets:
        print("creating geoset from: " + bpy_geoset.name)
        if bpy_geoset.self_as_parent:
            war3_model.bones.append(create_geoset_bone(bpy_geoset, actions,
                                                       war3_model.sequences, war3_model.global_seqs,
                                                       settings))
        elif bpy_geoset.no_vgs and bpy_geoset.parent_name not in [b.name for b in war3_model.bones]:
            war3_model.bones.append(create_armature_bone(bpy_geoset, actions,
                                                         war3_model.sequences, war3_model.global_seqs,
                                                         settings))
        war_geoset = create_geoset(bpy_geoset)
        war3_model.geosets.append(war_geoset)

        # A geoset with a vertex that has no vertex group needs some node to
        # fall back on.  Dropping the stand-in bones can leave the model with no
        # bones at all (a model may legitimately contain only emitters), so add a
        # synthetic root bone on demand, as parse_armatures() already does.
        if not len(war3_model.bones) and any(
                name == "" for row in war_geoset.matrices for name in row):
            war3_model.bones.append(War3Bone("No_Bones_Found"))

        for i in range(0, len(war_geoset.matrices)):
            for j in range(0, len(war_geoset.matrices[i])):
                if war_geoset.matrices[i][j] == "":
                    war_geoset.matrices[i][j] = war3_model.bones[0].name

        # Needs fixing. supposed to make sure that the 4 first weights adds up to 255.
        # if settings.use_skinweights:
        #     bone_zero: str = war3_model.bones[0].name
        #     for vertex in war_geoset.vertices:
        #         fix_skin_bones(vertex.bone_list, vertex.weight_list, bone_zero)
        if bpy_geoset.bpy_material and bpy_geoset.bpy_material.node_tree:
            geo_anim = get_geoset_anim(bpy_geoset, actions, war3_model.sequences, war3_model.global_seqs)
            war_geoset.geoset_anim = geo_anim
            if geo_anim:
                geo_anim.geoset = war_geoset
                geo_anim.geoset_id = len(war3_model.geosets)-1

    for bpy_material in bpy_scene_objects.materials:
        if bpy_material is None:
            # An empty material slot can reach here; it is not an error.
            continue
        use_const_color = any([g for g in war3_model.geosets
                               if g.mat_name == bpy_material.name
                               and g.geoset_anim is not None
                               and any((g.geoset_anim.color, g.geoset_anim.color_anim))])
        new_material = get_new_material2(bpy_material, settings.use_skinweights, use_const_color, actions,
                                         war3_model.sequences, war3_model.global_seqs)
        war3_model.materials.append(new_material)

    # Add default material if no other materials present
    if any((x for x in war3_model.geosets if x.mat_name == "default")):
        default_mat = War3Material("default")
        war_layer = War3Layer()
        war_layer.texture = War3Texture()
        default_mat.layers.append(war_layer)
        war3_model.materials.append(default_mat)

    war3_model.materials = sorted(war3_model.materials, key=lambda x: x.priority_plane)

    layers = list(itertools.chain.from_iterable([material.layers for material in war3_model.materials]))
    war3_model.textures.extend(set((layer.texture for layer in layers)))
    war3_model.textures_paths.extend(set((layer.texture_path for layer in layers)))
    war3_model.tvertex_anims.extend(set((layer.texture_anim for layer in layers if layer.texture_anim is not None)))
    # Convert to set and back to list for unique entries

    if settings.demote_to_helper:
        # Demote bones to helpers if they have no attached geosets
        demote_to_helpers(war3_model, node_types, skinned_bones)

    # We also need the textures used by emitters
    emitters: List[War3Emitter] = []
    emitters.extend(war3_model.particle_systems)
    emitters.extend(war3_model.particle_systems2)
    emitters.extend(war3_model.particle_ribbon)
    # for particle_sys in emitters:
    #     if particle_sys.emitter.texture_path not in war3_model.textures_paths:
    #         # war3_model.textures.append(War3Texture(particle_sys.emitter.texture_path))
    #         war3_model.textures.append(particle_sys.texture)
    #         war3_model.textures_paths.append(particle_sys.emitter.texture_path)
    for particle_sys in war3_model.particle_systems2:
        if particle_sys.emitter.texture_path not in war3_model.textures_paths:
            war3_model.textures.append(particle_sys.texture)
            war3_model.textures_paths.append(particle_sys.emitter.texture_path)

    # Ribbon emitters address their texture through a TextureSlot index, so the
    # texture has to exist in the model's list before the file is written.
    for ribbon in war3_model.particle_ribbon:
        texture_path = ribbon.emitter.texture_path
        if texture_path and texture_path not in war3_model.textures_paths:
            war3_model.textures.append(War3Texture(texture_path))
            war3_model.textures_paths.append(texture_path)

    collect_all_nodes(war3_model)

    vertices_all: List[List[float]] = []
    vertices_all.extend(collect_all_pos(war3_model.objects_all))

    for geoset in war3_model.geosets:
        for vertex in geoset.vertices:
            vertices_all.append(vertex.pos)

        geoset.min_extent, geoset.max_extent = calc_extents([vert.pos for vert in geoset.vertices])

        if geoset.geoset_anim is not None:
            for bone in itertools.chain.from_iterable(geoset.matrices):
                war3_model.geoset_anim_map[bone] = geoset.geoset_anim

    # # Account for particle systems when calculating bounds
    # for particle_sys in list(war3_model.particle_systems) + list(war3_model.particle_systems2) + list(war3_model.particle_ribbon):
    #     vertices_all.append([x + y/2 for x, y in zip(particle_sys.pivot, particle_sys.dimensions)])
    #     vertices_all.append([x - y/2 for x, y in zip(particle_sys.pivot, particle_sys.dimensions)])

    war3_model.geoset_anims = list(set(g.geoset_anim for g in war3_model.geosets if g.geoset_anim is not None))

    war3_model.global_extents_min, war3_model.global_extents_max \
        = calc_extents(vertices_all) if len(vertices_all) else ([0, 0, 0], [0, 0, 0])
    war3_model.global_seqs = sorted(war3_model.global_seqs)

    return war3_model


def node_groups(war3_model: War3Model):
    """Every list of War3 nodes that takes part in the node hierarchy."""
    return (war3_model.bones, war3_model.helpers, war3_model.lights,
            war3_model.attachments, war3_model.event_objects,
            war3_model.collision_shapes, war3_model.particle_systems,
            war3_model.particle_systems2, war3_model.particle_ribbon)


def collect_used_bone_names(war3_model: War3Model) -> Set[str]:
    """Bone names referenced by a geoset's matrix groups."""
    used_bones: Set[str] = set()
    for geoset in war3_model.geosets:
        for matrix in geoset.matrices:
            used_bones.update(matrix)
    return used_bones


def collect_scene_bone_names(bpy_scene_objects: BpySceneObjects) -> Set[str]:
    """Bone names any geoset skins to, read off the Blender side.

    The War3 geosets are only built later in from_scene(), but the skinning
    information is already known here, and a bone that a mesh skins to must never
    be converted or dropped.
    """
    names: Set[str] = set()
    for geoset in bpy_scene_objects.geosets:
        for bone_list in geoset.bone_list:
            names.update(name for name in bone_list if name)
    return names


def get_scene_node_types(bpy_scene_objects: BpySceneObjects) -> Dict[str, str]:
    """Node types recorded on the armature bones at import time."""
    node_types: Dict[str, str] = {}
    for pose_bones in bpy_scene_objects.bpy_nodes.values():
        for pose_bone in pose_bones:
            node_types[pose_bone.name] = get_node_type(pose_bone.bone)
    return node_types


def link_parents_and_drop_standin_bones(war3_model: War3Model,
                                        node_types: Dict[str, str],
                                        skinned_bones: Set[str]) -> None:
    """Restore node types, resolve parents and remove the stand-in bones.

    Importing represents every War3 node as an armature bone *and* as a separate
    object, and on export only bones ever get ``parent_node`` set -- every other
    node type carries just its parent's *name*.  Three problems follow from that:

    * lights, attachments, events, collision shapes and emitters were written
      without a ``Parent`` line at all, so the node hierarchy was flattened,
    * the stand-in bone was written as an extra ``Bone`` chunk next to the node's
      real chunk, duplicating the node and shifting every later ``ObjectId``, and
    * helper nodes came back as bones, because the Bone / Helper distinction was
      not recorded anywhere.

    The first two are fixed here directly; the third uses the node type recorded
    on the armature bone by :func:`create_armature_object.record_node_types`.
    """
    groups = node_groups(war3_model)

    by_name: Dict[str, War3Node] = {}
    for group in groups:
        for node in group:
            by_name.setdefault(node.name, node)

    for group in groups:
        for node in group:
            if node.parent_node is None and node.parent:
                node.parent_node = by_name.get(node.parent)

    used_bones = skinned_bones | collect_used_bone_names(war3_model)
    dropped = 0

    # 1. Bones that came from a Helper chunk become helpers again.
    bone_to_helper: Dict[War3Node, War3Node] = {}
    for bone in war3_model.bones:
        if node_types.get(bone.name) != NODE_TYPE_HELPER:
            continue
        helper = War3Helper(bone.name, bone.obj_id, bone.pivot, bone.parent_id,
                            bone.parent, bone.anim_loc, bone.anim_rot,
                            bone.anim_scale, bone.bindpose)
        helper.parent_node = bone.parent_node
        helper.billboarded = bone.billboarded
        helper.billboard_lock = bone.billboard_lock
        helper.dont_inherit = getattr(bone, "dont_inherit", (False, False, False))
        helper.camera_anchored = getattr(bone, "camera_anchored", False)
        helper.visibility = getattr(bone, "visibility", None)
        war3_model.helpers.append(helper)
        bone_to_helper[bone] = helper
    if bone_to_helper:
        for group in groups:
            for node in group:
                if node.parent_node in bone_to_helper:
                    node.parent_node = bone_to_helper[node.parent_node]
        for bone in bone_to_helper:
            war3_model.bones.remove(bone)
        dropped += len(bone_to_helper)
        print("  restored %d helper node(s)" % len(bone_to_helper))

    # 2. Bones that only stand in for a node with its own chunk writer go away.
    # A geoset matrix refers to a node by *name*, and the node keeps its name
    # with its real chunk, so dropping the stand-in never breaks skinning.
    non_bone: Dict[str, War3Node] = {}
    for group in (war3_model.lights, war3_model.attachments,
                  war3_model.event_objects, war3_model.collision_shapes,
                  war3_model.particle_systems, war3_model.particle_systems2,
                  war3_model.particle_ribbon, war3_model.helpers):
        for node in group:
            non_bone.setdefault(node.name, node)

    bone_to_node: Dict[War3Node, War3Node] = {}
    for bone in war3_model.bones:
        node = non_bone.get(bone.name)
        if node is not None and node is not bone:
            bone_to_node[bone] = node

    if bone_to_node:
        for group in groups:
            for node in group:
                if node.parent_node in bone_to_node:
                    node.parent_node = bone_to_node[node.parent_node]
        for bone in bone_to_node:
            war3_model.bones.remove(bone)
        dropped += len(bone_to_node)
        print("  dropped %d stand-in bone(s)" % len(bone_to_node))


def demote_to_helpers(war3_model: War3Model, node_types: Dict[str, str],
                      skinned_bones: Set[str]):
    """Demote unused bones to helpers, unless they are explicitly typed bones.

    A bone that was read from a Bone chunk keeps its type, so a round-trip does
    not silently rewrite it; only bones with no recorded type (a hand-built
    armature) are demoted on the strength of "no geoset uses it".
    """
    used_bones = skinned_bones | collect_used_bone_names(war3_model)
    bone_to_helper: Dict[War3Node, War3Node] = {}
    for bone in war3_model.bones:
        if node_types.get(bone.name) == NODE_TYPE_BONE:
            continue
        if bone.name not in used_bones:
            # print("demoting", bone.name, "to helper")
            helper = War3Helper(bone.name, bone.obj_id, bone.pivot,
                                bone.parent_id, bone.parent,
                                bone.anim_loc, bone.anim_rot, bone.anim_scale,
                                bone.bindpose)
            helper.parent_node = bone.parent_node
            helper.billboard_lock = bone.billboard_lock
            helper.billboarded = bone.billboarded
            helper.dont_inherit = getattr(bone, "dont_inherit", (False, False, False))
            helper.camera_anchored = getattr(bone, "camera_anchored", False)
            helper.bindpose = bone.bindpose
            war3_model.helpers.append(helper)
            bone_to_helper[bone] = helper

    for node in (n for n in war3_model.bones if n.parent_node in bone_to_helper):
        node.parent_node = bone_to_helper[node.parent_node]
    for node in (n for n in war3_model.lights if n.parent_node in bone_to_helper):
        node.parent_node = bone_to_helper[node.parent_node]
    for node in (n for n in war3_model.helpers if n.parent_node in bone_to_helper):
        node.parent_node = bone_to_helper[node.parent_node]
    for node in (n for n in war3_model.attachments if n.parent_node in bone_to_helper):
        node.parent_node = bone_to_helper[node.parent_node]
    for node in (n for n in war3_model.particle_systems if n.parent_node in bone_to_helper):
        node.parent_node = bone_to_helper[node.parent_node]
    for node in (n for n in war3_model.particle_systems2 if n.parent_node in bone_to_helper):
        node.parent_node = bone_to_helper[node.parent_node]
    for node in (n for n in war3_model.particle_ribbon if n.parent_node in bone_to_helper):
        node.parent_node = bone_to_helper[node.parent_node]
    for node in (n for n in war3_model.event_objects if n.parent_node in bone_to_helper):
        node.parent_node = bone_to_helper[node.parent_node]
    for node in (n for n in war3_model.collision_shapes if n.parent_node in bone_to_helper):
        node.parent_node = bone_to_helper[node.parent_node]

    for bone in bone_to_helper.keys():
        war3_model.bones.remove(bone)


def collect_all_nodes(war3_model: War3Model):
    model_objects_all = war3_model.objects_all
    model_objects_all.extend(war3_model.bones)
    model_objects_all.extend(war3_model.lights)
    model_objects_all.extend(war3_model.helpers)
    model_objects_all.extend(war3_model.attachments)
    model_objects_all.extend(war3_model.particle_systems)
    model_objects_all.extend(war3_model.particle_systems2)
    model_objects_all.extend(war3_model.particle_ribbon)
    model_objects_all.extend(war3_model.event_objects)
    model_objects_all.extend(war3_model.collision_shapes)

    for i, war3_node in enumerate(model_objects_all):
        # print("Setting nodeID: ", i, war3_node.name)
        war3_node.obj_id = i

    for war3_node in model_objects_all:
        if war3_node.parent_node is not None:
            # print("setting parent id to", war3_node.parent_node.obj_id,
            #       "for", war3_node.name, "\t(", war3_node.parent_node.name, ")")
            war3_node.parent_id = war3_node.parent_node.obj_id


def collect_all_pos(model_objects_all: List[War3Node]) -> List[List[float]]:
    pos_all: List[List[float]] = []
    for war3_node in model_objects_all:
        pos_all.append(war3_node.pivot)
        if isinstance(war3_node, War3CollisionShape):
            for vert in war3_node.verts:
                pos_all.append(vert)
    return pos_all


def parse_bpy_objects2(bpy_scene_objects: BpySceneObjects,
                       settings: War3ExportSettings,
                       war3_model: War3Model,
                       actions: List[bpy.types.Action]):
    global_matrix: Matrix = settings.global_matrix
    global_scale: float = settings.scale
    optimize_animation: bool = settings.optimize_animation
    optimize_tolerance: float = settings.optimize_tolerance if optimize_animation else -1
    sequences: List[War3AnimationAction] = war3_model.sequences
    global_seqs: Set[int] = war3_model.global_seqs

    print("parse_bpy_objects2!")
    war3_model.bones.extend(parse_armatures(bpy_scene_objects, global_matrix,
                                            optimize_tolerance, actions,
                                            sequences, global_seqs))

    for bpy_empty_node in bpy_scene_objects.collisions:
        war3_model.collision_shapes.append(get_collision(bpy_empty_node, global_matrix))

    for bpy_emitter in bpy_scene_objects.particle1s:
        particle_emitter = get_particle_emitter(sequences, global_seqs, actions, bpy_emitter,
                                                optimize_tolerance,
                                                global_matrix)
        war3_model.particle_systems.append(particle_emitter)

    for bpy_emitter in bpy_scene_objects.particle2s:
        emitter_ = get_particle_emitter2(sequences, global_seqs, actions, bpy_emitter,
                                         optimize_tolerance,
                                         global_matrix, global_scale)
        war3_model.particle_systems2.append(emitter_)

    for bpy_emitter in bpy_scene_objects.ribbons:
        ribbon_emitter = get_ribbon_emitter(sequences, global_seqs, actions, bpy_emitter,
                                            optimize_tolerance,
                                            global_matrix)
        ribbon_material = ribbon_emitter.emitter.ribbon_material
        if ribbon_material is not None:
            validMaterials = [m for m in war3_model.materials if (m.name == ribbon_material.name)]
        else:
            validMaterials = []
        if 0 < len(validMaterials):
            ribbon_emitter.material = validMaterials[0]
        elif 0 < len(war3_model.materials):
            ribbon_emitter.material = war3_model.materials[0]
        war3_model.particle_ribbon.append(ribbon_emitter)

    for bpy_light in bpy_scene_objects.lights:
        light = get_lights(sequences, global_seqs, actions, bpy_light, global_matrix)
        war3_model.lights.append(light)

    for bpy_empty_node in bpy_scene_objects.events:
        event = get_event(sequences, global_seqs, actions, bpy_empty_node,
                          optimize_tolerance, global_matrix)
        war3_model.event_objects.append(event)

    for bpy_empty_node in bpy_scene_objects.helpers:
        if bpy_empty_node.should_be_bone:
            bone = get_bone(sequences, global_seqs, actions, bpy_empty_node,
                            optimize_tolerance, global_matrix)
            war3_model.bones.append(bone)
        else:
            helper = get_helper(sequences, global_seqs, actions, bpy_empty_node,
                                optimize_tolerance, global_matrix)
            war3_model.helpers.append(helper)

    for bpy_empty_node in bpy_scene_objects.attachments:
        attachment = get_attachment(sequences, global_seqs, actions, bpy_empty_node,
                                    optimize_tolerance, global_matrix)
        war3_model.attachments.append(attachment)

    for bpy_obj in bpy_scene_objects.cameras:
        camera = get_camera(bpy_obj, global_matrix, global_scale)
        war3_model.cameras.append(camera)


def get_camera(bpy_obj: bpy.types.Object, global_matrix: Matrix, global_scale: float):
    camera = War3Camera(bpy_obj.name)

    camera.pivot = global_matrix @ Vector(bpy_obj.location)
    camera.field_of_view = bpy_obj.data.angle
    camera.far_clip = bpy_obj.data.clip_end * global_scale
    camera.near_clip = bpy_obj.data.clip_start * global_scale

    if bpy_obj.data.dof.focus_object is None:
        targetDist = bpy_obj.data.dof.focus_distance
        camera.target = global_matrix @ bpy_obj.matrix_world @ Vector([0, 0, -targetDist])
    else:
        camera.target = global_matrix @ bpy_obj.data.dof.focus_object.location
    camera.bindpose = bpy_obj.matrix_basis

    return camera


def fix_skin_bones(bone_list: List[str], weight_list: List[int], bone_zero: str):
    # Warcraft 800+ do support vertex (skin) weights;
    # 4 bone bindings per vertex whose weight sum up to 255
    # This will ensure that the weight of the (up to) 4 first bones sums up to 255
    numBones = len(weight_list)

    # Ugly fix to make sure total weight is 255

    tot_weight = sum(weight_list[:min(4, numBones)])
    w_conv = 255.0 / tot_weight
    weight_adjust = 255
    for i in range(numBones):
        weight_list[i] = round(i * w_conv)
        weight_adjust -= weight_list[i]

    if len(weight_list) == 1 or weight_list[1] - weight_adjust < 0 and 0 < (weight_list[1] - weight_adjust):
        print("ugg")

    if weight_adjust < 0 and 1 < len(weight_list) and 0 < (weight_list[1] - weight_adjust):
        print("ugg2")


def fix_skin_bones1(bone_list: List[str], weight_list: List[int], bone_zero: str):
    # Warcraft 800+ do support vertex (skin) weights;
    # 4 bone bindings per vertex whose weight sum up to 255
    # This will ensure that the weight of the (up to) 4 first bones sums up to 255
    numBones = len(weight_list)
    weight_list_temp = weight_list[:min(4, numBones)]

    tot_weight = sum(weight_list_temp)
    w_conv = 255.0 / tot_weight
    weight_list_temp = [round(i * w_conv) for i in weight_list_temp]
    # Ugly fix to make sure total weight is 255

    weight_adjust = 255 - sum(weight_list_temp)
    weight_list[0] = int(weight_list[0] + weight_adjust)

    # bone_list = bone_list[:min(4, numBones)]
    # if numBones < 4:
    #     print("not enough bones:", numBones)
    #     for i in range(4-numBones):
    #         print("adding bone!")
    #         bone_list.append(bone_zero)
    #         weight_list.append(0)
