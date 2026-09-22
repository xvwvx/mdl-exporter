"""MDL (text) TextureAnims chunk.

Mirrors export_mdl.save_texture_animations:

    TextureAnims 2 {
        TVertexAnim {
            Translation 1 {
                DontInterp,
                0: 0, 0, 0,
            }
        }
        TVertexAnim {
            ...
        }
    }

Material layers reference an entry by index through their TVertexAnimId.
"""

import re
from typing import List

from .mdl_reader import extract_bracket_content, chunkifier
from .parse_geoset_transformation import parse_geoset_transformation
from ...classes.War3TextureAnim import War3TextureAnim

TRACKS = (('Translation', 'translation', 'Translation'),
          ('Rotation', 'rotation', 'Rotation'),
          ('Scaling', 'scale', 'Scale'))


def parse_texture_animations(data: str) -> List[War3TextureAnim]:
    animations: List[War3TextureAnim] = []
    body = extract_bracket_content(data)

    for chunk in chunkifier(body):
        if chunk.strip().split(' ')[0] != 'TVertexAnim':
            continue
        texture_anim = War3TextureAnim()
        inner = extract_bracket_content(chunk)
        for label, attribute, curve_type in TRACKS:
            match = re.search(r'(?m)^[ \t]*%s\s+\d' % label, inner)
            if not match:
                continue
            curve = parse_geoset_transformation(inner[match.start():])
            if curve is None:
                continue
            curve.type = curve_type
            setattr(texture_anim, attribute, curve)
        animations.append(texture_anim)

    return animations
