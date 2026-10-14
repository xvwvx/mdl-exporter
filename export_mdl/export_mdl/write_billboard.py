from typing import Optional, Sequence, TextIO


def write_billboard(fw: TextIO.write, billboarded, billboard_lock,
                    dont_inherit: Optional[Sequence[bool]] = None,
                    camera_anchored: bool = False):
    """Write the node flags that MdxNodeFlags (A MdxModel.cs:63-87) stores as bits.

    ``dont_inherit`` is (Translation, Rotation, Scaling).
    """
    if dont_inherit is not None:
        for flag, keyword in zip(dont_inherit, ('DontInheritTranslation',
                                                'DontInheritRotation',
                                                'DontInheritScaling')):
            if flag:
                fw("\t%s,\n" % keyword)
    for flag, axis in zip(billboard_lock, ('Z', 'Y', 'X')):
        if flag:
            fw("\tBillboardedLock%s,\n" % axis)
    if billboarded:
        fw("\tBillboarded,\n")
    if camera_anchored:
        fw("\tCameraAnchored,\n")
