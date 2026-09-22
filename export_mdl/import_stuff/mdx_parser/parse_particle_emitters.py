"""MDX (binary) particle emitter chunks: PREM (ParticleEmitter) and
PRE2 (ParticleEmitter2).

Each record is length prefixed with an inclusive size, so a record that contains
a track id this parser does not know about can be abandoned without desyncing
the outer chunk walk.
"""

from typing import Iterator, List

from . import binary_reader
from .parse_node import parse_node
from .parse_timeline import parse_timeline
from ... import constants
from ...classes.War3EmitterSettings import War3EmitterSettings
from ...classes.War3ParticleEmitter import War3ParticleEmitter
from ...classes.War3ParticleSystem import War3ParticleSystem


def iter_records(data: bytes) -> Iterator[bytes]:
    """Yield the body of every length-prefixed emitter record."""
    reader = binary_reader.Reader(data)
    data_size = len(data)
    while reader.offset < data_size:
        inclusive_size = reader.getf('<I')[0]
        if inclusive_size < 4:
            print("  emitter record with bad size %d - stopping" % inclusive_size)
            return
        record_size = inclusive_size - 4
        if reader.offset + record_size > data_size:
            print("  emitter record overruns the chunk - stopping")
            return
        record = data[reader.offset: reader.offset + record_size]
        reader.skip(record_size)
        yield record


def parse_particle_emitters(data: bytes) -> List[War3ParticleEmitter]:
    """PREM - the legacy particle emitter."""
    emitters: List[War3ParticleEmitter] = []
    for record in iter_records(data):
        record_size = len(record)
        r = binary_reader.Reader(record)
        node = War3ParticleEmitter("")
        parse_node(r, node)

        settings = War3EmitterSettings()
        settings.emitter_type = 'ParticleEmitter'
        settings.emission_rate = r.get_float()
        settings.gravity = r.get_float()
        settings.longitude = r.get_float()
        settings.latitude = r.get_float()
        settings.model_path = r.gets(80)
        settings.life_span = r.get_float()
        settings.speed = r.get_float()
        r.getf('<I')  # flags: EmitterUsesMDL / EmitterUsesTGA, implied on export
        node.emitter = settings

        while r.offset < record_size:
            chunk_id = r.getid(constants.SUB_CHUNKS_PARTICLE_EMITTER)
            if chunk_id == constants.CHUNK_PE_EMISSION_RATE:
                node.emission_rate_anim = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_PE_GRAVITY:
                node.gravity_anim = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_PE_LONGITUDE:
                node.longitude_anim = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_PE_LATITUDE:
                node.latitude_anim = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_PE_LIFE_SPAN:
                node.life_span_anim = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_PE_INIT_VELOCITY:
                node.speed_anim = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_PE_VISIBILITY:
                node.visibility = parse_timeline(r, '<f')
            else:
                print("  unknown PREM track %r - skipping the rest of the record"
                      % chunk_id)
                break

        emitters.append(node)
    return emitters


def parse_particle_emitters2(data: bytes, version: int = 800) -> List[War3ParticleSystem]:
    """PRE2 - the sprite sheet particle emitter."""
    emitters: List[War3ParticleSystem] = []
    for record in iter_records(data):
        record_size = len(record)
        r = binary_reader.Reader(record)
        node = War3ParticleSystem("")
        parse_node(r, node)

        settings = War3EmitterSettings()
        settings.emitter_type = 'ParticleEmitter2'
        settings.speed = r.get_float()
        settings.variation = r.get_float()
        settings.latitude = r.get_float()
        settings.gravity = r.get_float()
        settings.life_span = r.get_float()
        settings.emission_rate = r.get_float()
        settings.length = r.get_float()
        settings.width = r.get_float()
        settings.filter_mode = constants.FILTER_MODES.get(r.get_int(), 'Blend')
        settings.rows = r.get_int()
        settings.cols = r.get_int()

        head_or_tail = r.get_int()
        settings.head = head_or_tail in (constants.HEAD_OR_TAIL_HEAD,
                                         constants.HEAD_OR_TAIL_BOTH)
        settings.tail = head_or_tail in (constants.HEAD_OR_TAIL_TAIL,
                                         constants.HEAD_OR_TAIL_BOTH)
        settings.tail_length = r.get_float()
        settings.time = r.get_float()

        settings.set_colors(r.get_floats(3), r.get_floats(3), r.get_floats(3))
        # Segment alphas are bytes, not floats.
        settings.start_alpha, settings.mid_alpha, settings.end_alpha = r.get_bytes(3)
        settings.start_scale, settings.mid_scale, settings.end_scale = r.get_floats(3)

        (settings.head_life_start, settings.head_life_end,
         settings.head_life_repeat) = r.get_ints(3)
        (settings.head_decay_start, settings.head_decay_end,
         settings.head_decay_repeat) = r.get_ints(3)
        (settings.tail_life_start, settings.tail_life_end,
         settings.tail_life_repeat) = r.get_ints(3)
        (settings.tail_decay_start, settings.tail_decay_end,
         settings.tail_decay_repeat) = r.get_ints(3)

        settings.texture_id = r.get_int()
        settings.replaceable_id = r.get_int()
        settings.priority_plane = r.get_int()

        if version >= 900:
            # 900+ appends a geometry emitter type before the track list.
            r.getf('<I')

        node.emitter = settings

        while r.offset < record_size:
            chunk_id = r.getid(constants.SUB_CHUNKS_PARTICLE_EMITTER2)
            if chunk_id == constants.CHUNK_PE2_SPEED:
                node.speed_anim = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_PE2_VARIATION:
                node.variation_anim = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_PE2_LATITUDE:
                node.latitude_anim = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_PE2_GRAVITY:
                node.gravity_anim = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_PE2_EMISSION_RATE:
                node.emission_rate_anim = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_PE2_WIDTH:
                node.scale_anim = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_PE2_LENGTH:
                # Width and Length share one scale curve on export, so only the
                # first one seen is kept.
                if node.scale_anim is None:
                    node.scale_anim = parse_timeline(r, '<f')
                else:
                    parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_PE2_ALPHA:
                node.alpha_anim = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_PE2_COLOR:
                node.ribbon_color_anim = parse_timeline(r, '<3f')
            else:
                print("  unknown PRE2 track %r - skipping the rest of the record"
                      % chunk_id)
                break

        emitters.append(node)
    return emitters
