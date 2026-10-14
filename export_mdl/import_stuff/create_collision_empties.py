from typing import List, Set

import bpy
from mathutils import Vector

from export_mdl.classes.War3CollisionShape import War3CollisionShape
from export_mdl.classes.War3Node import War3Node
from export_mdl.import_stuff.apply_node_flags import apply_node_flags
from export_mdl.properties.War3NodeProperties import (NODE_TYPE_COLLISION_SHAPE,
                                                      set_object_node_type)


def create_collision_empties(nodes: List[War3CollisionShape],
                             bpy_armature_object: bpy.types.Object):
    node_names: Set[str] = set()
    collisions: List[bpy.types.Object] = []
    for indexNode, node in enumerate(nodes):
        print("\tCol - adding ", node, " type: ", node.type)
        bpy_object = create_bpy_collision(node, node_names)
        if node.parent:
            apply_parent_bone(bpy_armature_object, bpy_object, node)
        collisions.append(bpy_object)
    return collisions


def apply_parent_bone(bpy_armature_object: bpy.types.Object, bpy_object: bpy.types.Object, node: War3Node):
    bpy_object.parent = bpy_armature_object
    bpy_object.parent_type = 'BONE'
    bpy_object.parent_bone = node.parent
    armature: bpy.types.Armature = bpy_armature_object.data
    parent_bone: bpy.types.Bone = armature.bones.get(node.parent)
    if parent_bone:
        bpy_object.location = bpy_object.location - parent_bone.tail


def create_bpy_collision(node: War3CollisionShape, node_names: Set[str]):
    # The "Collision " prefix the exporter used to look for is replaced by the
    # mdl_node_type property, so the node keeps its own name.
    node_name = node.name
    if node_name in node_names:
        node_name = node_name + ".001"
        if node_name in node_names:
            node_name = node_name + ".002"
        node.name = node_name
    node_names.add(node_name)
    bpy_object = bpy.data.objects.new(node_name, None)
    bpy.context.scene.collection.objects.link(bpy_object)
    set_object_node_type(bpy_object, NODE_TYPE_COLLISION_SHAPE)
    bpy_object.location = node.pivot

    # A collision chunk may omit BoundsRadius, and a Box is described by its
    # corner vertices instead, so neither field can be assumed to be present.
    radius = node.radius
    if radius is None and node.verts:
        radius = Vector(node.verts[0]).length
    if radius is None:
        print("\tCol - \"%s\" has neither BoundsRadius nor vertices" % node.name)
        radius = 0.0

    # bpy_object.empty_display_type =
    if node.type == 'Sphere':
        bpy_object.empty_display_size = radius
        bpy_object.empty_display_type = 'SPHERE'
    else:
        # Box and Cylinder are both drawn as a cube.
        bpy_object.empty_display_size = radius
        bpy_object.empty_display_type = 'CUBE'
    apply_node_flags(bpy_object, node)
    return bpy_object
