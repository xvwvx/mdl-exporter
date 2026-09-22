"""MDL (text) Camera chunk.

Mirrors War3Camera.write_camera:

    Camera "name" {
        Position { x, y, z },          (or a Translation track)
        FieldOfView 0.9,
        FarClip 5000,
        NearClip 1,
        Target {
            Position { x, y, z },      (or a Translation track)
        }
    }

Note that this addon writes FieldOfView in radians (it copies Camera.angle
straight through), so the value is read back verbatim.
"""

import re

from .mdl_reader import extract_bracket_content, extract_float_values
from .parse_geoset_transformation import parse_geoset_transformation
from ...classes.War3Camera import War3Camera


def _first_position(body: str):
    match = re.search(r'Position\s*\{', body)
    if not match:
        return None
    values = extract_float_values(extract_bracket_content(body[match.start():]))
    return values[:3] if len(values) >= 3 else None


def parse_camera(data: str) -> War3Camera:
    camera = War3Camera("")
    camera.name = data.split('"')[1] if '"' in data else ""

    body = extract_bracket_content(data)

    # The target block is nested, so parse it out before looking for the
    # camera's own position.
    target_match = re.search(r'Target\s*\{', body)
    target_body = ""
    if target_match:
        target_body = extract_bracket_content(body[target_match.start():])
        target_position = _first_position(target_body)
        if target_position:
            camera.target = target_position
        target_track = re.search(r'(?m)^[ \t]*Translation\s+\d', target_body)
        if target_track:
            camera.anim_target = parse_geoset_transformation(
                target_body[target_track.start():])
            camera.anim_target.type = 'Translation'

    outer_body = body[:target_match.start()] if target_match else body
    position = _first_position(outer_body)
    if position:
        camera.pivot = position
    position_track = re.search(r'(?m)^[ \t]*Translation\s+\d', outer_body)
    if position_track:
        camera.anim_loc = parse_geoset_transformation(
            outer_body[position_track.start():])
        camera.anim_loc.type = 'Translation'

    for name, attribute in (('FieldOfView', 'field_of_view'),
                            ('FarClip', 'far_clip'),
                            ('NearClip', 'near_clip')):
        match = re.search(r'(?m)^[ \t]*%s[ \t]+(-?[\d.]+(?:[eE][-+]?\d+)?)'
                          % name, outer_body)
        if match:
            setattr(camera, attribute, float(match.group(1)))

    return camera
