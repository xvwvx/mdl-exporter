"""MDL (text) particle and ribbon emitter chunks.

Mirrors the writers in export_mdl: save_model_emitters / save_particle_emitters /
save_ribbon_emitters and the War3Emitter / War3ParticleSystem /
War3RibbonEmitter write_* methods.

Static values are matched line-anchored so that "static Speed 40" is not mistaken
for the "Speed 3 { ... }" track, and so that "Length" does not match
"TailLength".  Animated tracks are recognised by a chunkifier label followed by a
keyframe count.
"""

import re
from typing import List, Optional

from .mdl_reader import extract_bracket_content, extract_float_values, chunkifier
from .parse_geoset_transformation import parse_geoset_transformation
from .parse_node import parse_node
from ...classes.War3EmitterSettings import War3EmitterSettings
from ...classes.War3ParticleEmitter import War3ParticleEmitter
from ...classes.War3ParticleSystem import War3ParticleSystem
from ...classes.War3RibbonEmitter import War3RibbonEmitter

NUMBER = r'(-?[\d.]+(?:[eE][-+]?\d+)?)'

# Track label -> (War3 attribute, timeline value format)
PE2_TRACKS = {
    'Speed': ('speed_anim', '<f'),
    'Variation': ('variation_anim', '<f'),
    'Latitude': ('latitude_anim', '<f'),
    'Gravity': ('gravity_anim', '<f'),
    'EmissionRate': ('emission_rate_anim', '<f'),
    'Width': ('scale_anim', '<f'),
    'Length': ('scale_anim', '<f'),
    'Alpha': ('alpha_anim', '<f'),
    'Visibility': ('visibility', '<f'),
}

PE_TRACKS = {
    'EmissionRate': ('emission_rate_anim', '<f'),
    'Gravity': ('gravity_anim', '<f'),
    'Longitude': ('longitude_anim', '<f'),
    'Latitude': ('latitude_anim', '<f'),
    'InitVelocity': ('speed_anim', '<f'),
    'Visibility': ('visibility', '<f'),
}

RIBBON_TRACKS = {
    'HeightAbove': ('scale_anim', '<f'),
    'HeightBelow': (None, '<f'),
    'Alpha': ('alpha_anim', '<f'),
    'Color': ('ribbon_color_anim', '<3f'),
    'TextureSlot': (None, '<I'),
    'Visibility': ('visibility', '<f'),
}


def static_number(body: str, name: str) -> Optional[float]:
    match = re.search(r'static\s+%s\s+%s' % (name, NUMBER), body)
    return float(match.group(1)) if match else None


def static_int(body: str, name: str) -> Optional[int]:
    value = static_number(body, name)
    return int(round(value)) if value is not None else None


def plain_number(body: str, name: str) -> Optional[float]:
    """A "Name 12," line that is not preceded by the static keyword."""
    match = re.search(r'(?m)^[ \t]*%s[ \t]+%s' % (name, NUMBER), body)
    return float(match.group(1)) if match else None


def plain_int(body: str, name: str) -> Optional[int]:
    value = plain_number(body, name)
    return int(round(value)) if value is not None else None


def has_keyword(body: str, name: str) -> bool:
    return re.search(r'(?m)^[ \t]*%s[ \t]*,?[ \t]*$' % name, body) is not None


def bracketed_numbers(body: str, name: str) -> List[float]:
    match = re.search(r'%s\s*\{' % name, body)
    if not match:
        return []
    return extract_float_values(extract_bracket_content(body[match.start():]))


def parse_tracks(body: str, node, tracks) -> None:
    """Fill the node's animation curves from its track chunks."""
    for chunk in chunkifier(body):
        label = chunk.strip().split(' ')[0]
        entry = tracks.get(label)
        if entry is None:
            continue
        # Only "Label <count> {" opens a track; a static value never does.
        if not re.match(r'%s\s+\d' % label, chunk.strip()):
            continue
        attribute, _ = entry
        curve = parse_geoset_transformation(chunk)
        if curve is None:
            continue
        if attribute is None:
            continue
        if attribute == 'scale_anim' and getattr(node, attribute, None) is not None:
            # Width and Length collapse into one scale curve on export.
            continue
        curve.type = 'Color' if label == 'Color' else 'Float'
        setattr(node, attribute, curve)


def parse_particle_emitter2(data: str) -> War3ParticleSystem:
    node = War3ParticleSystem("")
    parse_node(data, node)

    body = extract_bracket_content(data)
    settings = War3EmitterSettings()
    settings.emitter_type = 'ParticleEmitter2'

    settings.sort_far_z = has_keyword(body, 'SortPrimsFarZ')
    settings.unshaded = has_keyword(body, 'Unshaded')
    settings.line_emitter = has_keyword(body, 'LineEmitter')
    settings.unfogged = has_keyword(body, 'Unfogged')
    settings.model_space = has_keyword(body, 'ModelSpace')
    settings.xy_quad = has_keyword(body, 'XYQuad')

    settings.head = has_keyword(body, 'Head')
    settings.tail = has_keyword(body, 'Tail')
    if has_keyword(body, 'Both'):
        settings.head = settings.tail = True

    for name, attribute in (('Speed', 'speed'), ('Variation', 'variation'),
                            ('Latitude', 'latitude'), ('Gravity', 'gravity'),
                            ('EmissionRate', 'emission_rate'),
                            ('Width', 'width'), ('Length', 'length')):
        value = static_number(body, name)
        if value is not None:
            setattr(settings, attribute, value)

    life_span = plain_number(body, 'LifeSpan')
    if life_span is not None:
        settings.life_span = life_span
    tail_length = plain_number(body, 'TailLength')
    if tail_length is not None:
        settings.tail_length = tail_length
    time = plain_number(body, 'Time')
    if time is not None:
        settings.time = time
    rows = plain_int(body, 'Rows')
    if rows is not None:
        settings.rows = rows
    columns = plain_int(body, 'Columns')
    if columns is not None:
        settings.cols = columns
    texture_id = plain_int(body, 'TextureID')
    if texture_id is not None:
        settings.texture_id = texture_id
    priority_plane = plain_int(body, 'PriorityPlane')
    if priority_plane is not None:
        settings.priority_plane = priority_plane

    # The filter mode is a bare keyword line.
    for mode in ('None', 'Blend', 'Transparent', 'Additive', 'AddAlpha',
                 'Modulate', 'Modulate2x'):
        if has_keyword(body, mode):
            settings.filter_mode = mode
            break

    # SegmentColor { Color {..}, Color {..}, Color {..} } - stored BGR.
    segment = re.search(r'SegmentColor\s*\{', body)
    if segment:
        colors = [list(reversed(values))
                  for values in (extract_float_values(match)
                                 for match in re.findall(r'Color\s*\{([^}]*)\}',
                                                         body[segment.start():]))]
        colors = [values for values in colors if len(values) >= 3]
        if len(colors) >= 3:
            settings.set_colors(colors[0][:3], colors[1][:3], colors[2][:3])

    alpha = bracketed_numbers(body, 'Alpha')
    if len(alpha) >= 3:
        settings.start_alpha, settings.mid_alpha, settings.end_alpha = (
            int(round(value)) for value in alpha[:3])
    scaling = bracketed_numbers(body, 'ParticleScaling')
    if len(scaling) >= 3:
        settings.start_scale, settings.mid_scale, settings.end_scale = scaling[:3]

    for name, prefix in (('LifeSpanUVAnim', 'head_life'),
                         ('DecayUVAnim', 'head_decay'),
                         ('TailUVAnim', 'tail_life'),
                         ('TailDecayUVAnim', 'tail_decay')):
        values = bracketed_numbers(body, name)
        if len(values) >= 3:
            setattr(settings, prefix + '_start', int(round(values[0])))
            setattr(settings, prefix + '_end', int(round(values[1])))
            setattr(settings, prefix + '_repeat', int(round(values[2])))

    node.emitter = settings
    parse_tracks(body, node, PE2_TRACKS)
    return node


def parse_particle_emitter(data: str) -> War3ParticleEmitter:
    node = War3ParticleEmitter("")
    parse_node(data, node)

    body = extract_bracket_content(data)
    settings = War3EmitterSettings()
    settings.emitter_type = 'ParticleEmitter'

    # 与二进制端成对：节点标志 0x8000/0x10000 在 MDL 里写成这两个关键字，
    # 写出端见 War3ParticleEmitter.write_particle。
    settings.unshaded = has_keyword(body, 'EmitterUsesMDL')
    settings.sort_far_z = has_keyword(body, 'EmitterUsesTGA')

    for name, attribute in (('EmissionRate', 'emission_rate'),
                            ('Gravity', 'gravity'),
                            ('Longitude', 'longitude'),
                            ('Latitude', 'latitude')):
        value = static_number(body, name)
        if value is not None:
            setattr(settings, attribute, value)

    # The particle definition is a nested "Particle { ... }" block.
    particle = re.search(r'Particle\s*\{', body)
    if particle:
        particle_body = extract_bracket_content(body[particle.start():])
        life_span = plain_number(particle_body, 'LifeSpan')
        if life_span is not None:
            settings.life_span = life_span
        velocity = static_number(particle_body, 'InitVelocity')
        if velocity is not None:
            settings.speed = velocity
        path = re.search(r'Path\s+"([^"]*)"', particle_body)
        if path:
            settings.model_path = path.group(1)
        # LifeSpan and InitVelocity may also be tracks inside the block.
        parse_tracks(particle_body, node, PE_TRACKS)

    node.emitter = settings
    parse_tracks(body, node, PE_TRACKS)
    return node


def parse_ribbon_emitter(data: str) -> War3RibbonEmitter:
    node = War3RibbonEmitter("")
    parse_node(data, node)

    body = extract_bracket_content(data)
    settings = War3EmitterSettings()
    settings.emitter_type = 'RibbonEmitter'

    for name, attribute in (('HeightAbove', 'height_above'),
                            ('HeightBelow', 'height_below')):
        value = static_number(body, name)
        if value is not None:
            setattr(settings, attribute, value)

    alpha = static_number(body, 'Alpha')
    if alpha is not None:
        settings.alpha = alpha

    color = bracketed_numbers(body, 'Color')
    if len(color) >= 3:
        # Stored BGR.
        settings.ribbon_color = list(reversed(color[:3]))

    texture_slot = static_int(body, 'TextureSlot')
    if texture_slot is not None:
        settings.texture_id = texture_slot

    for name, attribute in (('EmissionRate', 'emission_rate'),
                            ('LifeSpan', 'life_span'),
                            ('Gravity', 'gravity')):
        value = plain_number(body, name)
        if value is not None:
            setattr(settings, attribute, value)

    rows = plain_int(body, 'Rows')
    if rows is not None:
        settings.rows = rows
    columns = plain_int(body, 'Columns')
    if columns is not None:
        settings.cols = columns
    material_id = plain_int(body, 'MaterialID')
    if material_id is not None:
        settings.material_id = material_id

    node.emitter = settings
    parse_tracks(body, node, RIBBON_TRACKS)
    return node
