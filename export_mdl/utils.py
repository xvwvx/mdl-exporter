import math
import re
from operator import itemgetter
from typing import Optional, SupportsRound, List, Tuple

from .compat import action_fcurves

decimal_places = 5

# Naming convention linking a material's UV animation to a material layer: the
# importer creates a Mapping node called "TVertexAnim_<layer index>" and the
# exporter looks the animation up by that name.
UV_ANIM_NODE_PREFIX = 'TVertexAnim_'
UV_ANIM_NODE_RE = re.compile(r'^%s(\d+)$' % UV_ANIM_NODE_PREFIX)


def uv_anim_node_name(layer_index: int) -> str:
    return '%s%d' % (UV_ANIM_NODE_PREFIX, layer_index)


def uv_anim_layer_index(node_name: str) -> Optional[int]:
    match = UV_ANIM_NODE_RE.match(node_name or '')
    return int(match.group(1)) if match else None


# Blender has no equivalent of a Warcraft global sequence id, so the value is
# parked on the UV animation's action as "<prefix><node>_<track>" and restored on
# export.
UV_ANIM_GSEQ_PREFIX = 'mdl_uv_global_seq_'


def uv_anim_gseq_key(node_name: str, track: str) -> str:
    return '%s%s_%s' % (UV_ANIM_GSEQ_PREFIX, node_name, track)


def rnd(val: float) -> float:
    return round(val, decimal_places)


def rnd(val: int) -> int:
    return round(val, decimal_places)


# def rnd(val: SupportsRound[_Protocol[T_co]]):
#     return round(val, decimal_places)


def float2str(value: float) -> str:
    return ('%.6f' % value).rstrip('0').rstrip('.')


def calc_bounds_radius(min_ext: List[float], max_ext: List[float]):
    x = (max_ext[0] - min_ext[0])/2
    y = (max_ext[1] - min_ext[1])/2
    z = (max_ext[2] - min_ext[2])/2
    return math.sqrt(math.pow(x, 2) + math.pow(y, 2) + math.pow(z, 2))


def calc_extents(vertices: List[List[float]]) -> Tuple[List[float], List[float]]:
    # max_extents = [max(vertices, key=itemgetter(i))[i] for i in range(3)]
    # min_extents = [min(vertices, key=itemgetter(i))[i] for i in range(3)]

    min_extents: List[float] = [0.0, 0.0, 0.0]
    max_extents: List[float] = [0.0, 0.0, 0.0]

    for vertex in vertices:
        for i, v in enumerate(vertex):
            min_extents[i] = min(min_extents[i], v)
            max_extents[i] = max(max_extents[i], v)

    return min_extents, max_extents


def get_curve(obj, data_paths):
    if obj.animation_data and obj.animation_data.action:
        fcurves = action_fcurves(obj.animation_data.action)
        for path in data_paths:
            curve = fcurves.find(path)
            if curve is not None:
                return curve
    return None


def get_curves(obj, data_path, indices):
    curves = {}
    if obj.animation_data and obj.animation_data.action:
        fcurves = action_fcurves(obj.animation_data.action)
        for index in indices:
            curve = fcurves.find(data_path, index=index)
            if curve is not None:
                curves[(data_path.split('.')[-1], index)] = curve # For now, i'm just interested in the type, not the whole data path. Hence, the split returns the name after the last dot. 
    if len(curves):
        return curves
    return None
