"""Plain-Python holder for particle / ribbon emitter settings.

Mirrors :class:`export_mdl.properties.War3ParticleSystemProperties` field for
field, but without needing Blender data.  The parsers run before any Blender
object exists, so they fill one of these; ``import_stuff.create_particle_emitters``
copies it into the real ``mdl_particle_sys`` property group when the emitter is
materialised in the scene.

``apply_to()`` copies by name, so adding a field to the property group does not
require touching this file as long as the holder is given the same name.
"""

from typing import List


class War3EmitterSettings:
    def __init__(self):
        # Shared
        self.emitter_type: str = 'ParticleEmitter2'
        self.texture_path: str = ''
        self.model_path: str = ''
        self.emission_rate: float = 100.0
        self.life_span: float = 1.0
        self.speed: float = 100.0
        self.gravity: float = 0.0
        self.latitude: float = 0.0
        self.longitude: float = 0.0
        self.variation: float = 0.0
        self.alpha: float = 1.0
        self.rows: int = 1
        self.cols: int = 1
        self.head: bool = True
        self.tail: bool = False
        self.tail_length: float = 0.0
        self.time: float = 0.5
        self.priority_plane: int = 0

        # ParticleEmitter2 only
        self.filter_mode: str = 'Blend'
        self.unshaded: bool = False
        self.unfogged: bool = False
        self.line_emitter: bool = False
        self.sort_far_z: bool = False
        self.model_space: bool = False
        self.xy_quad: bool = False
        self.start_color: List[float] = [1.0, 1.0, 1.0]
        self.mid_color: List[float] = [1.0, 1.0, 1.0]
        self.end_color: List[float] = [1.0, 1.0, 1.0]
        self.start_alpha: int = 255
        self.mid_alpha: int = 255
        self.end_alpha: int = 255
        self.start_scale: float = 1.0
        self.mid_scale: float = 1.0
        self.end_scale: float = 1.0
        self.head_life_start: int = 0
        self.head_life_end: int = 0
        self.head_life_repeat: int = 1
        self.head_decay_start: int = 0
        self.head_decay_end: int = 0
        self.head_decay_repeat: int = 1
        self.tail_life_start: int = 0
        self.tail_life_end: int = 0
        self.tail_life_repeat: int = 1
        self.tail_decay_start: int = 0
        self.tail_decay_end: int = 0
        self.tail_decay_repeat: int = 1

        # RibbonEmitter only.  The Blender-side field is a Material pointer, so
        # the material is resolved by name in create_particle_emitters.
        self.ribbon_material_name: str = ''
        self.ribbon_color: List[float] = [1.0, 1.0, 1.0]
        self.ribbon_above: bool = False
        self.ribbon_emitter_visibility: bool = True

        # Not part of the property group: parsed indices that
        # create_particle_emitters resolves against the model, plus the emitter
        # plane size used to reproduce Width / Length on export.
        self.texture_id: int = 0
        self.replaceable_id: int = 0
        self.material_id: int = -1
        self.width: float = 1.0
        self.length: float = 1.0
        self.height_above: float = 0.0
        self.height_below: float = 0.0

    def set_colors(self, start, mid, end):
        self.start_color = list(start)
        self.mid_color = list(mid)
        self.end_color = list(end)

    def apply_to(self, target) -> List[str]:
        """Copy every matching field onto a ``War3ParticleSystemProperties``.

        Returns a list describing fields that could not be assigned, so a
        mismatch is reported instead of silently dropped.
        """
        failures: List[str] = []
        for prop in target.bl_rna.properties:
            name = prop.identifier
            if name == 'rna_type' or not hasattr(self, name):
                continue
            value = getattr(self, name)
            try:
                setattr(target, name, value)
            except (TypeError, ValueError) as exc:
                failures.append("%s=%r (%s)" % (name, value, exc))
        return failures
