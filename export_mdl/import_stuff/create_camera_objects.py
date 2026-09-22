"""Materialise parsed cameras as Blender camera objects.

The exporter picks cameras up by object type, and rebuilds the target from the
camera's orientation plus its depth-of-field focus distance:

    camera.target = matrix_world @ Vector([0, 0, -dof.focus_distance])

so the object is aimed down its local -Z at the target and the focus distance is
set to the camera-to-target distance.  That makes the position *and* the target
survive a round-trip.
"""

from typing import List

import bpy
from mathutils import Vector

from ..classes.War3Camera import War3Camera


def create_camera_objects(model) -> List[bpy.types.Object]:
    print(" creating cameras")
    cameras: List[bpy.types.Object] = []
    for camera in model.cameras:
        bpy_object = create_bpy_camera(camera)
        if bpy_object is not None:
            cameras.append(bpy_object)
    return cameras


def create_bpy_camera(camera: War3Camera):
    cam_data: bpy.types.Camera = bpy.data.cameras.new(camera.name)
    if camera.field_of_view and 0.0 < camera.field_of_view < 3.141592653589793:
        cam_data.angle = camera.field_of_view
    if camera.near_clip and camera.near_clip > 0.0:
        cam_data.clip_start = camera.near_clip
    if camera.far_clip and camera.far_clip > cam_data.clip_start:
        cam_data.clip_end = camera.far_clip

    bpy_object = bpy.data.objects.new(camera.name, cam_data)
    bpy.context.scene.collection.objects.link(bpy_object)
    if bpy_object.name != camera.name:
        camera.name = bpy_object.name

    pivot = Vector(camera.pivot)
    target = Vector(camera.target)
    bpy_object.location = pivot

    direction = target - pivot
    if direction.length > 0.0:
        bpy_object.rotation_mode = 'QUATERNION'
        bpy_object.rotation_quaternion = direction.to_track_quat('-Z', 'Y')
        cam_data.dof.focus_distance = direction.length

    return bpy_object
