"""MDX (binary) CAMS chunk - Camera.

A camera record is not a node: it has a name but no ObjectId / ParentId / flags.
The record is still length prefixed, so unknown tracks can be abandoned safely.

Layout (offsets relative to the record body, i.e. after the inclusive size):

    0   char  name[80]
    80  float position[3]
    92  float fieldOfView
    96  float farClip
    100 float nearClip
    104 float targetPosition[3]
    116 tracks: KCTR (translation), KCRL (roll), KTTR (target translation)
"""

from typing import List

from . import binary_reader
from .parse_particle_emitters import iter_records
from .parse_timeline import parse_timeline
from ... import constants
from ...classes.War3Camera import War3Camera

TRACK_IDS = tuple(tag.encode('ascii') for tag in constants.SUB_CHUNKS_CAMERA)


def parse_cameras(data: bytes) -> List[War3Camera]:
    cameras: List[War3Camera] = []
    for record in iter_records(data):
        record_size = len(record)
        r = binary_reader.Reader(record)

        camera = War3Camera("")
        camera.name = r.gets(80)
        camera.pivot = list(r.get_floats(3))
        camera.field_of_view = r.get_float()
        camera.far_clip = r.get_float()
        camera.near_clip = r.get_float()

        # The static target follows the clip planes.  Guard on a track tag so a
        # file that goes straight to the tracks is not misread.
        if record_size - r.offset >= 12 \
                and record[r.offset:r.offset + 4] not in TRACK_IDS:
            camera.target = list(r.get_floats(3))

        while r.offset < record_size:
            chunk_id = r.getid(constants.SUB_CHUNKS_CAMERA)
            if chunk_id == constants.CHUNK_CAMERA_TRANSLATION:
                camera.anim_loc = parse_timeline(r, '<3f')
            elif chunk_id == constants.CHUNK_CAMERA_ROLL:
                camera.anim_roll = parse_timeline(r, '<f')
            elif chunk_id == constants.CHUNK_CAMERA_TARGET:
                camera.anim_target = parse_timeline(r, '<3f')
            else:
                print("  unknown camera track %r - skipping the rest of the record"
                      % chunk_id)
                break

        cameras.append(camera)
    return cameras
