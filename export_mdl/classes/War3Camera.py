from typing import TextIO, Set, List, Optional

from mathutils import Matrix

from export_mdl.export_mdl.write_animation_chunk import write_animation_chunk
from export_mdl.utils import float2str


class War3Camera:
    def __init__(self, name,
                 obj_id: int = 0,
                 pivot: List[float] = [200, 0, 100],
                 field_of_view: float = 50,
                 far_clip: float = 500, near_clip: float = 10,
                 target: List[float] = [0, 0, 80],
                 bindpose: Optional[Matrix] = None):
        self.name: str = name
        self.obj_id: int = obj_id
        self.pivot: List[float] = pivot  # TODO
        self.field_of_view: float = field_of_view
        self.far_clip: float = far_clip
        self.near_clip: float = near_clip
        self.target: List[float] = target
        # Populated by the importers; the exporter does not build these.
        self.anim_loc = None
        self.anim_target = None
        self.anim_roll = None
        self.bindpose: Optional[Matrix] = bindpose  # TODO

    def write_camera(self, fw: TextIO.write,
                     global_seqs: Set[int]):
        fw("Camera \"%s\" {\n" % self.name)

        if self.anim_loc is not None:
            write_animation_chunk(fw, self.anim_loc, "Translation", global_seqs, "\t")
        else:
            fw("\tPosition { %s, %s, %s },\n" % tuple(map(float2str, self.pivot)))
        fw("\tFieldOfView %f,\n" % self.field_of_view)
        fw("\tFarClip %f,\n" % self.far_clip)
        fw("\tNearClip %f,\n" % self.near_clip)

        fw("\tTarget {\n")
        if self.anim_target is not None:
            write_animation_chunk(fw, self.anim_target, "Translation", global_seqs,
                                  "\t\t")
        else:
            fw("\t\tPosition { %s, %s, %s },\n"
               % tuple(map(float2str, self.target)))
        fw("\t}\n")
        fw("}\n")
