import re

from .parse_node import parse_node
from .mdl_reader import extract_bracket_content, extract_float_values, chunkifier
from .parse_geoset_transformation import parse_geoset_transformation
from ...classes.War3Light import War3Light

LIGHT_TYPES = ('Omnidirectional', 'Directional', 'Ambient')

# "static <Field> <number>" -> War3Light attribute
STATIC_SCALARS = {
    'AttenuationStart': 'atten_start',
    'AttenuationEnd': 'atten_end',
    'Intensity': 'intensity',
    'AmbIntensity': 'amb_intensity',
}

# Animated track label -> War3Light attribute.  Visibility is handled by
# parse_node along with Translation / Rotation / Scaling.
ANIMATED_TRACKS = {
    'AttenuationStart': ('atten_start_anim', 'Float'),
    'AttenuationEnd': ('atten_end_anim', 'Float'),
    'Intensity': ('intensity_anim', 'Float'),
    'AmbIntensity': ('amb_intensity_anim', 'Float'),
    'Color': ('color_anim', 'Color'),
    'AmbColor': ('amb_color_anim', 'Color'),
}

STATIC_SCALAR_RE = re.compile(r'static\s+(\w+)\s+(-?[\d.]+(?:[eE][-+]?\d+)?)')
STATIC_COLOR_RE = re.compile(r'static\s+(\w+)\s*\{([^}]*)\}')


def parse_light(data: str) -> War3Light:
    """Parse a Light chunk.

    Mirrors export_mdl.save_lights: the node part (ObjectId / Parent / tracks)
    plus the light specific static values and animated tracks.  Colours are
    stored BGR in the file because the exporter reverses them, so they are
    flipped back to RGB here.
    """
    light = War3Light("")
    parse_node(data, light)

    body = extract_bracket_content(data)

    # The light type is a bare keyword line, e.g. "Omnidirectional,".
    for light_type in LIGHT_TYPES:
        if re.search(r'(?:^|[\s,])%s\s*,' % light_type, body):
            light.light_type = light_type
            break

    for name, value in STATIC_SCALAR_RE.findall(body):
        attribute = STATIC_SCALARS.get(name)
        if attribute is not None:
            setattr(light, attribute, float(value))

    for name, content in STATIC_COLOR_RE.findall(body):
        values = extract_float_values(content)
        if len(values) < 3:
            continue
        values = list(reversed(values[:3]))
        if name == 'Color':
            light.color = values
        elif name == 'AmbColor':
            light.amb_color = values

    for chunk in chunkifier(body):
        label = chunk.strip().split(' ')[0]
        entry = ANIMATED_TRACKS.get(label)
        if entry is None:
            continue
        attribute, curve_type = entry
        curve = parse_geoset_transformation(chunk)
        if curve is None:
            continue
        curve.type = curve_type
        setattr(light, attribute, curve)

    return light
