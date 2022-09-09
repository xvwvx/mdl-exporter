from typing import List, Dict

from ..MDXImportProperties import MDXImportProperties
from ..load_warcraft_3_model import load_warcraft_3_model
from ...classes.War3Model import War3Model
from ... import constants
from . import binary_reader
from .parse_attachments import parse_attachments
from .parse_bones import parse_bones
from .parse_collision_shapes import parse_collision_shapes
from .parse_events import parse_events
from .parse_geoset_animations import parse_geoset_animations
from .parse_geosets import parse_geosets
from .parse_helpers import parse_helpers
from .parse_materials import parse_materials
from .parse_model import parse_model
from .parse_pivot_points import parse_pivot_points
from .parse_sequences import parse_sequences
from .parse_textures import parse_textures
from .parse_version import parse_version
from .parse_lights import parse_lights
from ...classes.War3Node import War3Node


def parse_mdx(data: bytes, import_properties: MDXImportProperties):
    data_size = len(data)
    r = binary_reader.Reader(data)
    r.getid(constants.CHUNK_MDX_MODEL)

    model = War3Model("")
    model.file = import_properties.mdx_file_path
    id_to_node: Dict[str, War3Node] = {}
    pivot_points: List[List[float]] = []

    while r.offset < data_size:
        chunk_id = r.getid(constants.SUB_CHUNKS_MDX_MODEL, debug=True)
        chunk_size = r.getf('<I')[0]
        chunk_data: bytes = data[r.offset: r.offset + chunk_size]
        r.skip(chunk_size)

        if chunk_id == constants.CHUNK_VERSION:
            model.version = parse_version(chunk_data)
        elif chunk_id == constants.CHUNK_GEOSET:
            print("geosets !!!!!!!!!!!")
            model.geosets.extend(parse_geosets(chunk_data, model.version, model.name))
        elif chunk_id == constants.CHUNK_TEXTURE:
            model.textures.extend(parse_textures(chunk_data))
        elif chunk_id == constants.CHUNK_MATERIAL:
            model.materials.extend(parse_materials(chunk_data, model.version))
        elif chunk_id == constants.CHUNK_MODEL:
            print("model name!")
            model.name = parse_model(chunk_data)
        elif chunk_id == constants.CHUNK_BONE:
            model.bones.extend(parse_bones(chunk_data, id_to_node))
        elif chunk_id == constants.CHUNK_PIVOT_POINT:
            pivot_points.extend(parse_pivot_points(chunk_data))
        elif chunk_id == constants.CHUNK_HELPER:
            model.helpers.extend(parse_helpers(chunk_data, id_to_node))
        elif chunk_id == constants.CHUNK_LIGHT:
            model.lights.extend(parse_lights(chunk_data, id_to_node))
        elif chunk_id == constants.CHUNK_ATTACHMENT:
            model.attachments.extend(parse_attachments(chunk_data, id_to_node))
        elif chunk_id == constants.CHUNK_EVENT_OBJECT:
            model.event_objects.extend(parse_events(chunk_data, id_to_node))
        elif chunk_id == constants.CHUNK_COLLISION_SHAPE:
            model.collision_shapes.extend(parse_collision_shapes(chunk_data, id_to_node))
        elif chunk_id == constants.CHUNK_SEQUENCE:
            model.sequences.extend(parse_sequences(chunk_data))
        elif chunk_id == constants.CHUNK_GEOSET_ANIMATION:
            model.geoset_anims.extend(parse_geoset_animations(chunk_data))

    for i, node in enumerate(id_to_node.values()):
        node.pivot = pivot_points[i]
        # print("node #", i, ":", node)
        if node.parent:
            # print("parent: ", node.parent)
            node.parent = id_to_node[node.parent].name

    for node_id, node in id_to_node.items():
        model.object_indices[node.name] = int(node_id)

    for geoset in model.geosets:
        # geoset.mat_name = model.materials[int(geoset.mat_name)].name
        for mg in geoset.matrices:
            b_names = []
            for bone in mg:
                b_names.append(id_to_node[bone].name)
            mg.clear()
            mg.extend(b_names)
        for vert in geoset.vertices:
            b_names = []
            for bone in vert.bone_list:
                if bone in id_to_node:
                    b_names.append(id_to_node[bone].name)
            if b_names:
                vert.bone_list.clear()
                vert.bone_list.extend(b_names)

    # print("model.materials:", model.materials)
    for material in model.materials:
        for layer in material.layers:
            layer.texture = model.textures[int(layer.texture_path)]

    model.objects_all.extend(model.bones)
    model.objects_all.extend(model.helpers)

    load_warcraft_3_model(model, import_properties)