"""Materialise TextureAnims as UV Mapping node animation.

The exporter reads a layer's UV animation from a Mapping node inside the
material's node tree (see create_material_stuff.get_texture_anim), so each
animated layer gets such a node plus an action on the node tree holding its
Translation / Rotation / Scaling tracks.

The node is named ``TVertexAnim_<layer index>`` so the exporter can put the
animation back on the same layer.  Note that the node-derived layer list the
exporter falls back to is not guaranteed to have the same length as the source
material's layer list, so the index is clamped on the way back out.
"""

import re
from typing import Dict, List, Optional

import bpy
from mathutils import Euler

from ..classes.War3Model import War3Model
from ..compat import action_fcurves, bind_action
from ..utils import uv_anim_gseq_key, uv_anim_node_name

# War3TextureAnim attribute -> Mapping node socket holding that track.
TRACK_SOCKETS = (
    ('translation', 'Location'),
    ('rotation', 'Rotation'),
    ('scale', 'Scale'),
)
CHANNELS = 3


def create_texture_animations(model: War3Model,
                              bpy_materials: Optional[Dict[str, object]] = None,
                              frame_time: float = 1000 / 30
                              ) -> List[bpy.types.Object]:
    """Create one Mapping node per animated layer, with its curves.

    ``frame_time`` is milliseconds per frame, as in MDXImportProperties; a track's
    keyframe times are in milliseconds while Blender keyframes are frames.
    """
    if bpy_materials is None:
        return []

    print(" creating texture animations")
    created: List[bpy.types.Object] = []
    if not frame_time:
        frame_time = 1000 / 30

    for material_index, material in enumerate(model.materials):
        animated = [(index, layer.texture_anim)
                    for index, layer in enumerate(material.layers)
                    if layer.texture_anim is not None]
        if not animated:
            continue
        entry = bpy_materials.get(str(material_index))
        if entry is None:
            continue
        bpy_material = entry.bpy_material
        if not bpy_material.use_nodes or bpy_material.node_tree is None:
            continue

        node_tree = bpy_material.node_tree
        action = _get_uv_action(bpy_material, node_tree)
        for layer_index, texture_anim in animated:
            node = _create_mapping_node(node_tree, layer_index)
            _write_tracks(action, node, texture_anim, frame_time)
            _connect_to_textures(node_tree, node)
            created.append(node)

    return created


def _get_uv_action(bpy_material: bpy.types.Material,
                   node_tree: bpy.types.NodeTree) -> bpy.types.Action:
    anim_data = node_tree.animation_data
    if anim_data is not None and anim_data.action is not None:
        return anim_data.action
    action = bpy.data.actions.new(name=bpy_material.name + ' UVAnim')
    action.use_fake_user = True
    bind_action(node_tree, action)
    return action


def _create_mapping_node(node_tree: bpy.types.NodeTree,
                         layer_index: int) -> bpy.types.Node:
    name = uv_anim_node_name(layer_index)
    existing = node_tree.nodes.get(name)
    if existing is not None:
        node_tree.nodes.remove(existing)
    node = node_tree.nodes.new('ShaderNodeMapping')
    node.name = name
    node.label = name
    node.location = (-800.0, -260.0 * layer_index)
    return node


def _write_tracks(action: bpy.types.Action,
                  node: bpy.types.Node,
                  texture_anim,
                  frame_time: float) -> None:
    for attribute, socket_name in TRACK_SOCKETS:
        curve = getattr(texture_anim, attribute, None)
        if curve is None:
            continue
        # Blender cannot express a Warcraft global sequence, so keep the value
        # for the exporter to restore.
        action[uv_anim_gseq_key(node.name, attribute)] = int(
            curve.global_sequence or -1)
        channels = max((len(values) for values in curve.keyframes.values()),
                       default=0)
        data_path = 'nodes["%s"].inputs["%s"].default_value' % (node.name,
                                                               socket_name)
        fcurves = action_fcurves(action)
        for channel in range(min(channels, CHANNELS)):
            fcurve = fcurves.find(data_path, index=channel)
            if fcurve is None:
                fcurve = fcurves.new(data_path, index=channel,
                                     action_group=node.name)
            for frame, values in curve.keyframes.items():
                if channel >= len(values):
                    continue
                value = values[channel]
                if attribute == 'rotation' and len(values) == 4:
                    # MDL stores a quaternion; a Mapping node holds Euler XYZ.
                    value = Euler(_quat_wxyz_to_euler(values))[channel]
                # Track times are milliseconds, Blender keyframes are frames.
                point = fcurve.keyframe_points.insert(frame / frame_time, value)
                point.interpolation = 'LINEAR'


def _quat_wxyz_to_euler(values) -> List[float]:
    from mathutils import Quaternion
    w, x, y, z = values
    return list(Quaternion((w, x, y, z)).to_euler())


def _connect_to_textures(node_tree: bpy.types.NodeTree,
                         mapping_node: bpy.types.Node) -> None:
    """Feed any unconnected texture Vector input from the mapping node."""
    output = mapping_node.outputs.get("Vector")
    if output is None:
        return
    for node in node_tree.nodes:
        if not isinstance(node, bpy.types.ShaderNodeTexImage):
            continue
        vector_input = node.inputs.get("Vector")
        if vector_input is None or vector_input.is_linked:
            continue
        node_tree.links.new(output, vector_input)
