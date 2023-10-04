from typing import Optional, List

from mathutils import Matrix

from .War3AnimationCurve import War3AnimationCurve
from .War3Node import War3Node


class War3Bone(War3Node):
    def __init__(self, name: str,
                 pivot: List[float] = [0, 0, 0],
                 parent: Optional[str] = None,
                 anim_loc: Optional[War3AnimationCurve] = None,
                 anim_rot: Optional[War3AnimationCurve] = None,
                 anim_scale: Optional[War3AnimationCurve] = None,
                 bindpose: Optional[Matrix] = None):
        super().__init__(name, pivot, parent, anim_loc, anim_rot, anim_scale, bindpose)

    @classmethod
    def create_from(cls, node: 'War3Node'):
        return War3Bone(node.name, node.pivot, node.parent,
                        node.anim_loc, node.anim_rot, node.anim_scale,
                        node.bindpose)
    # def __unit__(self, obj, model):
    #     War3Node.__init__(self, obj.name)
    #     model.objects['bone'].add(self)
