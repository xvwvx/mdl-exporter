"""MDX (binary) RIBB chunk - RibbonEmitter."""

from typing import List

from . import binary_reader
from .parse_node import parse_node
from .parse_timeline import parse_timeline
from .parse_particle_emitters import iter_records
from ... import constants
from ...classes.War3EmitterSettings import War3EmitterSettings
from ...classes.War3RibbonEmitter import War3RibbonEmitter


def parse_ribbon_emitters(data: bytes) -> List[War3RibbonEmitter]:
    emitters: List[War3RibbonEmitter] = []
    for record in iter_records(data):
        record_size = len(record)
        r = binary_reader.Reader(record)
        node = War3RibbonEmitter("")
        parse_node(r, node)

        settings = War3EmitterSettings()
        settings.emitter_type = 'RibbonEmitter'
        settings.height_above = r.get_float()
        settings.height_below = r.get_float()
        settings.alpha = r.get_float()
        settings.ribbon_color = list(r.get_floats(3))
        settings.life_span = r.get_float()
        settings.texture_id = r.get_int()
        settings.emission_rate = r.get_int()
        settings.rows = r.get_int()
        settings.cols = r.get_int()
        settings.material_id = r.get_int()
        settings.gravity = r.get_float()
        node.emitter = settings

        while r.offset < record_size:
            chunk_id = r.getid(constants.SUB_CHUNKS_RIBBON_EMITTER)
            if chunk_id == constants.CHUNK_RIBBON_HEIGHT_ABOVE:
                node.scale_anim = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_RIBBON_HEIGHT_BELOW:
                parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_RIBBON_ALPHA:
                node.alpha_anim = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_RIBBON_COLOR:
                node.ribbon_color_anim = parse_timeline(r, '<3f')
            elif chunk_id == constants.CHUNK_RIBBON_TEXTURE_SLOT:
                parse_timeline(r, '<I')
            elif chunk_id == constants.CHUNK_RIBBON_VISIBILITY:
                node.visibility = parse_timeline(r, '<f')
            else:
                print("  unknown RIBB track %r - skipping the rest of the record"
                      % chunk_id)
                break

        emitters.append(node)
    return emitters
