from typing import Optional, List

from mathutils import Matrix

from .War3AnimationCurve import War3AnimationCurve


class War3Node:  # Stores information about an MDL object (not a blender object!)
    def __init__(self, name: str,
                 obj_id: int = -1,
                 pivot: List[float] = [0, 0, 0],
                 parent_id: Optional[int] = None,
                 parent: Optional[str] = None,
                 anim_loc: Optional[War3AnimationCurve] = None,
                 anim_rot: Optional[War3AnimationCurve] = None,
                 anim_scale: Optional[War3AnimationCurve] = None,
                 bindpose: Optional[Matrix] = None):
        self.name: str = name
        self.obj_id: int = obj_id
        self.parent_id: Optional[int] = parent_id
        self.parent: Optional[str] = parent
        self.parent_node: Optional[War3Node] = None
        self.pivot: List[float] = pivot  # TODO
        self.anim_loc: Optional[War3AnimationCurve] = anim_loc
        self.anim_rot: Optional[War3AnimationCurve] = anim_rot
        self.anim_scale: Optional[War3AnimationCurve] = anim_scale
        # 原始 MdxNodeFlags（A MdxModel.cs:63-87）。二进制的 parse_node 会填它；
        # billboarded / billboard_lock 是由它派生出来的宿主侧表示。
        self.flags: int = 0
        self.billboarded = False
        self.billboard_lock = (False, False, False)
        # DontInheritTranslation/Rotation/Scaling 与 CameraAnchored 同样来自 flags
        # （0x1/0x2/0x4/0x80），由 parse_node 解析、导入端回写到宿主。
        self.dont_inherit = (False, False, False)  # (Translation, Rotation, Scaling)
        self.camera_anchored = False
        self.bindpose: Optional[Matrix] = bindpose  # TODO

    @classmethod
    def create_from(cls, node: 'War3Node'):
        created = War3Node(node.name, node.obj_id, node.pivot,
                           node.parent_id, node.parent,
                           node.anim_loc, node.anim_rot, node.anim_scale,
                           node.bindpose)
        created.flags = node.flags
        created.billboarded = node.billboarded
        created.billboard_lock = node.billboard_lock
        created.dont_inherit = node.dont_inherit
        created.camera_anchored = node.camera_anchored
        return created

    # def set_billboard(self, billboard):
    #     bb = obj.mdl_billboard
    #     self.billboarded = bb.billboarded
    #     self.billboard_lock = (bb.billboard_lock_z, bb.billboard_lock_y, bb.billboard_lock_x)

    def __eq__(self, other):
        if isinstance(self, other.__class__):
            return self.name == other.name
        return NotImplemented

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        # return hash(tuple(sorted(self.__dict__.items())))
        return hash(self.name)
