"""Compatibility helpers for running this addon on modern Blender.

The addon was written against Blender 3.4.  Between 3.4 and 5.2 the following
APIs it relied on were removed or reshaped:

* ``Action.fcurves`` / ``Action.groups`` -- actions became layered+slotted
  (Blender 4.4) and the flat accessors were dropped (Blender 5.0).  F-curves now
  live in an ``ActionChannelbag`` belonging to a (strip, slot) pair, and the
  ``FCurveCollection.new`` keyword is ``group_name``, not ``action_group``.
* ``Material.shadow_method`` -- removed in 4.2; shadow casting moved to
  ``Object.visible_shadow``.  ``blend_method`` survives but its enum shrank to
  OPAQUE/CLIP/HASHED/BLEND in 4.2.
* ``Mesh.calc_normals_split`` / ``free_normals_split`` / ``use_auto_smooth`` /
  ``auto_smooth_angle`` -- removed in 4.1.  Corner normals are now derived
  automatically from the sharp-edge / sharp-face attributes.
* ``Pose.bone_groups`` / ``PoseBone.bone_group`` / ``BoneCollection.color_set``
  -- bone groups became bone collections in 4.0, and bone *collections* lost
  their colour in 5.0 (per-bone ``Bone.color.palette`` remains).
* Safer Principled BSDF socket names -- ``Specular`` became
  ``Specular IOR Level``, ``Emission`` became ``Emission Color``, and so on.

Detection is done with instance-level ``hasattr``: ``bpy.types`` classes do not
expose RNA collection properties to ``hasattr`` on any Blender version, so
class-level probing silently reports "missing" everywhere.
"""

from typing import Any, List, Optional

import bpy

# Version thresholds for the changes above, for the few places where no
# instance is at hand.
VER_SLOTTED_ACTIONS = (4, 4, 0)
VER_BONE_COLLECTIONS = (4, 0, 0)
VER_NO_AUTOSMOOTH = (4, 1, 0)
VER_NO_SHADOW_METHOD = (4, 2, 0)

CURRENT_VERSION: tuple = tuple(bpy.app.version)


def _at_least(version: tuple) -> bool:
    return CURRENT_VERSION >= version


# --------------------------------------------------------------------------
# actions / f-curves
# --------------------------------------------------------------------------
def has_slotted_actions(action=None) -> bool:
    """True when ``action`` uses the layered/slotted API (Blender 4.4+)."""
    if action is not None:
        return hasattr(action, "layers")
    return _at_least(VER_SLOTTED_ACTIONS)


def _pick_slot(action: "bpy.types.Action", id_type: str):
    for slot in action.slots:
        if getattr(slot, "target_id_type", id_type) == id_type:
            return slot
    return action.slots[0] if len(action.slots) else None


def ensure_action_slot(action: "bpy.types.Action", id_type: str = "OBJECT"):
    """Return ``action``'s slot for ``id_type``, creating one when missing."""
    if action is None or not has_slotted_actions(action):
        return None
    slot = _pick_slot(action, id_type)
    if slot is None:
        slot = action.slots.new(id_type=id_type, name=action.name)
    return slot


def _slot_of(action: "bpy.types.Action", id_type: str):
    """Existing slot only -- never creates one."""
    slot = _pick_slot(action, id_type)
    return slot


def ensure_channelbag(action: "bpy.types.Action", id_type: str = "OBJECT"):
    """Return the ``ActionChannelbag`` holding ``action``'s f-curves."""
    if action is None or not has_slotted_actions(action):
        return None
    slot = ensure_action_slot(action, id_type)
    for layer in action.layers:
        for strip in layer.strips:
            bag = strip.channelbag(slot)
            if bag is not None:
                return bag
    layer = action.layers[0] if len(action.layers) else action.layers.new("Layer")
    strip = (layer.strips[0] if len(layer.strips)
             else layer.strips.new(type="KEYFRAME"))
    return strip.channelbag(slot, ensure=True)


def _existing_channelbag(action: "bpy.types.Action", id_type: str):
    """Return the existing channelbag, or ``None`` (no side effects)."""
    if action is None:
        return None
    if not has_slotted_actions(action):
        return action.fcurves
    slot = _slot_of(action, id_type)
    if slot is None:
        return None
    for layer in action.layers:
        for strip in layer.strips:
            bag = strip.channelbag(slot)
            if bag is not None:
                return bag.fcurves
    return None


class ActionFCurves:
    """Legacy ``action.fcurves`` facade over Blender's slotted actions.

    Covers the slice of the ``bpy_prop_collection`` interface this addon uses:
    ``find``, ``new``, ``remove``, ``get``, indexing, ``len``, iteration and
    ``values``/``keys``/``items``.
    """

    def __init__(self, action: "bpy.types.Action", id_type: str = "OBJECT"):
        self._action = action
        self._id_type = id_type

    def __len__(self) -> int:
        coll = _existing_channelbag(self._action, self._id_type)
        return len(coll) if coll is not None else 0

    def __iter__(self):
        coll = _existing_channelbag(self._action, self._id_type)
        return iter(list(coll)) if coll is not None else iter(())

    def __getitem__(self, item):
        if not has_slotted_actions(self._action):
            return self._action.fcurves[item]
        return ensure_channelbag(self._action, self._id_type).fcurves[item]

    def find(self, data_path: str, index: int = 0):
        coll = _existing_channelbag(self._action, self._id_type)
        return coll.find(data_path, index=index) if coll is not None else None

    def new(self, data_path: str, index: int = 0, action_group: str = "",
            group_name: str = ""):
        group = group_name or action_group
        if not has_slotted_actions(self._action):
            return self._action.fcurves.new(data_path, index=index,
                                            action_group=group)
        coll = ensure_channelbag(self._action, self._id_type).fcurves
        return coll.new(data_path, index=index, group_name=group)

    def remove(self, fcurve) -> None:
        coll = _existing_channelbag(self._action, self._id_type)
        if coll is not None:
            coll.remove(fcurve)

    def get(self, key, default=None):
        coll = _existing_channelbag(self._action, self._id_type)
        return coll.get(key, default) if coll is not None else default

    def values(self) -> List[Any]:
        return list(self)

    def keys(self) -> List[str]:
        return [fc.data_path for fc in self]

    def items(self):
        return [(fc.data_path, fc) for fc in self]


def action_fcurves(action: "bpy.types.Action",
                   id_type: str = "OBJECT") -> Optional[ActionFCurves]:
    """Legacy-style f-curve collection for ``action`` (``None`` if no action)."""
    if action is None:
        return None
    return ActionFCurves(action, id_type)


def bind_action(id_data, action):
    """Assign ``action`` to ``id_data`` and bind a matching slot.

    On 4.4+ assigning a *fresh* action does not auto-select a slot, so without
    this the f-curves would animate nothing.
    """
    if id_data is None:
        return None
    anim_data = id_data.animation_data
    if anim_data is None:
        anim_data = id_data.animation_data_create()
    anim_data.action = action
    if action is not None and has_slotted_actions(action):
        id_type = getattr(id_data, "id_type", None) or "OBJECT"
        slot = _pick_slot(action, id_type) or ensure_action_slot(action, id_type)
        try:
            anim_data.action_slot = slot
        except (TypeError, RuntimeError):
            pass
    return anim_data


def action_of(id_data) -> Optional["bpy.types.Action"]:
    """The action currently assigned to ``id_data`` (``None`` when unset)."""
    anim_data = getattr(id_data, "animation_data", None)
    return anim_data.action if anim_data is not None else None


# --------------------------------------------------------------------------
# materials
# --------------------------------------------------------------------------
def set_material_blend(material: "bpy.types.Material",
                       blend_method: str = "HASHED") -> None:
    """Set the material's transparency, on both the old and new properties.

    ``blend_method`` is the pre-4.2 control (still present in 5.2 with a reduced
    enum).  ``surface_render_method`` is what EEVEE Next actually uses, so both
    are set or a transparent material would still render as a solid slab.
    """
    if hasattr(material, "blend_method"):
        try:
            material.blend_method = blend_method
        except TypeError:
            material.blend_method = "BLEND"
    if hasattr(material, "surface_render_method"):
        try:
            material.surface_render_method = (
                "BLENDED" if blend_method in ("BLEND", "HASHED", "CLIP")
                else "DITHERED")
        except TypeError:
            pass


def set_material_shadow_method(material: "bpy.types.Material",
                               shadow_method: str = "HASHED") -> None:
    """No-op on 4.2+, where per-material shadow casting was removed.

    Shadow visibility became an object level setting (``Object.visible_shadow``),
    so there is nothing meaningful to forward this to.  Note that setting
    ``surface_render_method`` here would *overwrite* ``blend_method`` (DITHERED
    forces HASHED), so this deliberately leaves it alone.
    """
    if hasattr(material, "shadow_method"):
        material.shadow_method = shadow_method


# War3 layer filter mode -> Blender material blend method.
#
# War3 renders 'Additive' and 'AddAlpha' layers with additive blending, which is
# what makes the black parts of an effect texture disappear.  Blender has no
# additive material blend mode, so those are approximated by 'BLEND': what
# matters is that the texture's alpha is honoured instead of the layer being
# drawn as an opaque black slab, which is what 'HASHED'/opaque did.
FILTER_MODE_TO_BLEND = {
    'None': 'OPAQUE',
    # 'Transparent' is the game's AlphaKey mode: a 1-bit alpha test that does not
    # blend, which is what Blender's 'CLIP' does.  Mapping it to 'BLEND' turned
    # leaves, flags, hair and other cut-out geometry into a blended sheet.
    'Transparent': 'CLIP',
    'Blend': 'BLEND',
    'Additive': 'BLEND',
    'AddAlpha': 'BLEND',
    'Modulate': 'BLEND',
    'Modulate2x': 'BLEND',
}

# Layers the game draws additively; used to make the material emit light so the
# effect reads as a glow rather than as dark geometry.
ADDITIVE_FILTER_MODES = frozenset(['Additive', 'AddAlpha'])


def blend_for_filter_mode(filter_mode: str) -> str:
    """Blender blend method for a War3 layer filter mode."""
    return FILTER_MODE_TO_BLEND.get(filter_mode, 'OPAQUE')


def is_additive_filter_mode(filter_mode: str) -> bool:
    return filter_mode in ADDITIVE_FILTER_MODES


def blend_to_filter_mode(blend_method: str) -> str:
    """The War3 filter mode an imported material's blend method came from.

    Used when a material has no mdl_layers (an imported one), so that exporting
    it again writes back the filter mode the model originally had instead of
    flattening everything to 'None'.
    """
    if blend_method == 'CLIP':
        return 'Transparent'
    if blend_method in ('BLEND', 'HASHED'):
        return 'Blend'
    return 'None'


def principled_input(shader_node, *names: str):
    """First existing Principled BSDF socket among ``names``."""
    if shader_node is None:
        return None
    for name in names:
        socket = shader_node.inputs.get(name)
        if socket is not None:
            return socket
    return None


def set_principled_default(shader_node, value, *names: str) -> bool:
    socket = principled_input(shader_node, *names)
    if socket is None:
        return False
    socket.default_value = value
    return True


# --------------------------------------------------------------------------
# meshes
# --------------------------------------------------------------------------
def mesh_calc_normals(mesh: "bpy.types.Mesh") -> None:
    """Recompute split/corner normals where the API still requires it.

    From 4.1 on corner normals are derived lazily from the sharp-edge and
    sharp-face attributes, so there is nothing to call.
    """
    calc = getattr(mesh, "calc_normals_split", None)
    if calc is not None:
        calc()


def mesh_calc_tangents(mesh: "bpy.types.Mesh") -> bool:
    """Compute tangents; returns whether a UV layer made that possible."""
    if not len(mesh.uv_layers):
        return False
    try:
        mesh.calc_tangents()
    except RuntimeError:
        return False
    return True


# --------------------------------------------------------------------------
# armatures: bone groups (<= 3.x) vs bone collections (4.0+)
# --------------------------------------------------------------------------
def has_bone_collections(armature) -> bool:
    if armature is not None:
        return hasattr(armature, "collections")
    return _at_least(VER_BONE_COLLECTIONS)


def get_bone_collection(armature, name: str) -> Optional[Any]:
    """Find a bone collection by name, or ``None``."""
    if not has_bone_collections(armature):
        return None
    return armature.collections.get(name)


def new_bone_collection(armature, name: str):
    """Create a bone collection / pose bone group called ``name``."""
    if has_bone_collections(armature):
        return armature.collections.new(name=name)
    return None


def bone_collection_for(armature_object: "bpy.types.Object", name: str):
    """Find or create the bone collection called ``name`` on ``armature_object``."""
    armature = armature_object.data
    collection = get_bone_collection(armature, name)
    if collection is None:
        collection = new_bone_collection(armature, name)
    return collection


def assign_bone_to_collection(bone: "bpy.types.Bone", collection) -> None:
    """Replace ``bone``'s bone-collection membership with ``collection``."""
    if collection is None or bone is None:
        return
    if not hasattr(bone, "collections"):
        return  # legacy pose bone groups are assigned via PoseBone.bone_group
    bone.collections.clear()
    collection.assign(bone)


def set_bone_palette(holder, color: Optional[str]) -> None:
    """Give a bone / pose bone one of the ``THEME0x`` palettes, when supported."""
    if not color:
        return
    bone_color = getattr(holder, "color", None)
    if bone_color is not None and hasattr(bone_color, "palette"):
        try:
            bone_color.palette = color
        except TypeError:
            pass


def set_node_type_collection(armature_object: "bpy.types.Object",
                             bone_name: str,
                             collection_name: Optional[str],
                             color: Optional[str] = None) -> None:
    """Put a bone in exactly one bone collection (or clear it when ``None``).

    Abstracts over bone collections (4.0+, where colour lives on the bone) and
    the legacy pose bone groups (where colour lives on the group).
    """
    armature = armature_object.data
    bone = armature.bones.get(bone_name)
    if bone is None:
        return

    if has_bone_collections(armature):
        if collection_name is None:
            bone.collections.clear()
            return
        collection = (get_bone_collection(armature, collection_name)
                      or new_bone_collection(armature, collection_name))
        bone.collections.clear()
        collection.assign(bone)
        pose_bone = armature_object.pose.bones.get(bone_name)
        set_bone_palette(bone, color)
        if pose_bone is not None:
            set_bone_palette(pose_bone, color)
        return

    pose_bone = armature_object.pose.bones.get(bone_name)
    if pose_bone is None:
        return
    if collection_name is None:
        pose_bone.bone_group = None
        return
    pose = armature_object.pose
    group = pose.bone_groups.get(collection_name)
    if group is None:
        group = pose.bone_groups.new(name=collection_name)
        if color:
            try:
                group.color_set = color
            except (AttributeError, TypeError):
                pass
    pose_bone.bone_group = group
