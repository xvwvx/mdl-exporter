import bpy
from typing import Optional


def get_parent_name(bpy_obj: bpy.types.Object) -> Optional[str]:
    parent: bpy.types.Object = bpy_obj.parent

    print("parent: ", parent)
    print("parent_type: ", bpy_obj.parent_type)
    if parent is None:
        return None

    if bpy_obj.parent_type == 'BONE':
        return bpy_obj.parent_bone if bpy_obj.parent_bone != "" else None

    # if parent.type == 'EMPTY' and parent.name.startswith("Bone_"):
    if parent.type == 'EMPTY':
        return parent.name
        # return parent

    # anim_loc = get_curves(parent, 'location', (1, 2, 3))
    # anim_rot = get_curves(parent, 'rotation_quaternion', (1, 2, 3, 4))
    # anim_scale = get_curves(parent, 'scale', (1, 2, 3))
    # animations = (anim_loc, anim_rot, anim_scale)
    #
    # if bpy_obj.parent_type == 'ARMATURE':
    #     print('ARMATURE')
    #
    # if not any(animations):
    #     root_parent = get_parent(parent)
    #     if root_parent is not None:
    #         return root_parent.name

    return get_parent_name(parent)
