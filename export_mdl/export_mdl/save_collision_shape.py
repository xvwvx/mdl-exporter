from typing import TextIO, List

from mathutils import Vector

from ..classes.War3CollisionShape import War3CollisionShape
from ..utils import float2str, rnd


def save_collision_shape(fw: TextIO.write, collision_shapes: List[War3CollisionShape]):
    for collider in collision_shapes:
        fw("CollisionShape \"%s\" {\n" % collider.name)
        fw("\tObjectId %d,\n" % collider.obj_id)
        if collider.parent_id is not None:
            fw("\tParent %d,\n" % collider.parent_id)

        # MDL only knows Box and Sphere, so a Cylinder collider is written as a
        # sphere.  The shape keyword and the presence of BoundsRadius therefore
        # have to be decided together -- writing "Sphere" without a radius
        # produces a file the importer cannot read back.
        is_box = collider.type == 'Box'
        fw("\tBox,\n" if is_box else "\tSphere,\n")

        fw("\tVertices %d {\n" % len(collider.verts))
        for vert in collider.verts:
            fw("\t\t{ %s, %s, %s },\n" % tuple(float2str(rnd(x)) for x in list(vert)))
        fw("\t}\n")

        if not is_box:
            radius = collider.radius
            if radius is None:
                radius = max((Vector(v).length for v in collider.verts), default=0.0)
            fw("\tBoundsRadius %s,\n" % float2str(rnd(radius)))
        fw("}\n")
