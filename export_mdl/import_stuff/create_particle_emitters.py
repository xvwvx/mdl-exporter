"""Materialise parsed particle / ribbon emitters as Blender objects.

The exporter locates emitters through
``bpy_obj.particle_systems[0].settings.mdl_particle_sys``, so an imported emitter
only survives a re-export if it is represented by a mesh object carrying a
particle system with that property group filled in.

The emitter plane's size matters: ParticleEmitter2 exports its plane extents as
``static Width`` / ``static Length`` (taken from ``Object.dimensions``), and
RibbonEmitter exports ``HeightAbove`` / ``HeightBelow`` as ``dimensions[0] / 2``.
"""

from typing import Dict, List, Optional, Tuple

import bpy
from mathutils import Vector

from ..classes.War3EmitterSettings import War3EmitterSettings
from ..classes.War3Model import War3Model
from ..classes.War3Node import War3Node
from ..properties.War3NodeProperties import NODE_TYPE_NONE, set_object_node_type
from .create_material import get_repl_img
from .create_other_objects import animate_objects

# Keep the emitter plane thin; only X and Y are read back on export.
FLAT_THICKNESS = 0.01
DEFAULT_SIZE = 20.0


def create_particle_emitters(model: War3Model,
                             bpy_armature_object: bpy.types.Object,
                             bpy_materials: Optional[Dict[str, object]] = None,
                             team_color: str = 'RED',
                             fps_ratio: float = 1000 / 30):
    """Create one object per emitter and return ``[(war3_node, bpy_object)]``."""
    print(" creating particle emitters")
    created: List[Tuple[War3Node, bpy.types.Object]] = []

    for node in (list(model.particle_systems)
                 + list(model.particle_systems2)
                 + list(model.particle_ribbon)):
        settings: Optional[War3EmitterSettings] = getattr(node, "emitter", None)
        if settings is None:
            print("  emitter \"%s\" has no settings - skipped" % node.name)
            continue
        bpy_object = create_bpy_emitter(node, settings, model, bpy_materials,
                                        team_color)
        if bpy_object is None:
            continue
        if node.parent:
            apply_parent_bone(bpy_armature_object, bpy_object, node)
        created.append((node, bpy_object))

    if created:
        # Give the emitters the same node animation treatment as lights,
        # attachments and events so their Translation / Rotation / Scaling
        # tracks land in the sequence actions.
        animate_objects(fps_ratio, model.sequences,
                        [node for node, _ in created],
                        [bpy_object for _, bpy_object in created])

    return created


def get_emitter_size(settings: War3EmitterSettings) -> Tuple[float, float]:
    if settings.emitter_type == 'RibbonEmitter':
        height = settings.height_above + settings.height_below
        return (height if height > 0 else DEFAULT_SIZE, DEFAULT_SIZE)
    if settings.emitter_type == 'ParticleEmitter2':
        length = settings.length if settings.length else DEFAULT_SIZE
        width = settings.width if settings.width else DEFAULT_SIZE
        return (length, width)
    return (DEFAULT_SIZE, DEFAULT_SIZE)


def create_plane_mesh(name: str, size_x: float, size_y: float) -> bpy.types.Mesh:
    mesh = bpy.data.meshes.new(name)
    x = size_x / 2
    y = size_y / 2
    mesh.from_pydata([(-x, -y, 0.0), (x, -y, 0.0), (x, y, 0.0), (-x, y, 0.0)],
                     [], [(0, 1, 2, 3)])
    mesh.update()
    return mesh


def resolve_texture_path(settings: War3EmitterSettings,
                         model: War3Model,
                         team_color: str) -> str:
    if settings.replaceable_id > 0:
        return get_repl_img(settings.replaceable_id, team_color)
    index = settings.texture_id
    if 0 <= index < len(model.textures):
        texture = model.textures[index]
        if texture.texture_path:
            return texture.texture_path
    return settings.texture_path


def resolve_ribbon_material(settings: War3EmitterSettings,
                            model: War3Model,
                            bpy_materials: Optional[Dict[str, object]]):
    if bpy_materials is None:
        return None
    index = settings.material_id
    if 0 <= index < len(model.materials):
        settings.ribbon_material_name = model.materials[index].name
    if settings.ribbon_material_name:
        entry = bpy_materials.get(settings.ribbon_material_name)
        if entry is not None:
            return entry.bpy_material
    return None


def create_bpy_emitter(node: War3Node,
                       settings: War3EmitterSettings,
                       model: War3Model,
                       bpy_materials: Optional[Dict[str, object]],
                       team_color: str) -> Optional[bpy.types.Object]:
    size_x, size_y = get_emitter_size(settings)
    mesh = create_plane_mesh(node.name, size_x, size_y)
    bpy_object = bpy.data.objects.new(node.name, mesh)
    bpy.context.scene.collection.objects.link(bpy_object)
    # Emitters are found through their particle system, but recording the type
    # keeps the classification consistent for every node object.
    set_object_node_type(bpy_object, NODE_TYPE_NONE)

    # Blender may have renamed the object to keep names unique; the animation
    # data paths are built from node.name, so keep them in sync.
    if bpy_object.name != node.name:
        node.name = bpy_object.name

    bpy_object.modifiers.new(name="ParticleSystem", type='PARTICLE_SYSTEM')
    if not len(bpy_object.particle_systems):
        print("  could not add a particle system to \"%s\"" % node.name)
        return None

    settings.texture_path = resolve_texture_path(settings, model, team_color)
    if settings.emitter_type == 'RibbonEmitter':
        material = resolve_ribbon_material(settings, model, bpy_materials)
        if material is not None:
            mesh.materials.append(material)

    particle_settings = bpy_object.particle_systems[0].settings
    target = particle_settings.mdl_particle_sys
    failures = settings.apply_to(target)
    if failures:
        print("  emitter \"%s\": could not set %s" % (node.name, failures))
    if settings.emitter_type == 'RibbonEmitter' and settings.ribbon_material_name:
        entry = (bpy_materials or {}).get(settings.ribbon_material_name)
        if entry is not None:
            target.ribbon_material = entry.bpy_material

    bpy_object.location = node.pivot
    return bpy_object


def apply_parent_bone(bpy_armature_object: bpy.types.Object,
                      bpy_object: bpy.types.Object,
                      node: War3Node) -> None:
    bpy_object.parent = bpy_armature_object
    bpy_object.parent_type = 'BONE'
    bpy_object.parent_bone = node.parent
    armature: bpy.types.Armature = bpy_armature_object.data
    parent_bone: bpy.types.Bone = armature.bones.get(node.parent)
    if parent_bone:
        bpy_object.location = bpy_object.location - parent_bone.tail
