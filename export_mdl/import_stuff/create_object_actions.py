from typing import List

import bpy

from export_mdl import constants
from export_mdl.classes.War3Model import War3Model
from export_mdl.compat import action_fcurves


def create_object_actions1(model: War3Model,
                           bpy_objects: List[bpy.types.Object],
                           frame_time: float):
    print("creating object animations")
    geoset_animations = model.geoset_anims
    sequences = model.sequences
    data_path_color = 'color'

    for geosetAnimation in geoset_animations:
        # geoset_id = geosetAnimation.geoset_id
        # action = bpy.data.actions.new(name='#UNANIMATED' + ' ' + bpy_objects[geoset_id].name)
        action = bpy.data.actions.new(name='#UNANIMATED' + ' ' + geosetAnimation.geoset_name)
        color_r = action_fcurves(action).new(data_path_color, index=0)
        color_g = action_fcurves(action).new(data_path_color, index=1)
        color_b = action_fcurves(action).new(data_path_color, index=2)
        color_a = action_fcurves(action).new(data_path_color, index=3)
        color_r.keyframe_points.insert(0.0, 1.0)
        color_g.keyframe_points.insert(0.0, 1.0)
        color_b.keyframe_points.insert(0.0, 1.0)
        color_a.keyframe_points.insert(0.0, 1.0)

    for sequence in sequences:
        interval_start = sequence.start
        interval_end = sequence.end
        for geosetAnimation in geoset_animations:
            # geoset_id = geosetAnimation.geoset_id
            color_anim = geosetAnimation.color_anim
            alpha_anim = geosetAnimation.alpha_anim
            # action = bpy.data.actions.new(name=sequence.name + ' ' + bpy_objects[geoset_id].name)
            action = bpy.data.actions.new(name=sequence.name + ' ' + geosetAnimation.geoset_name)
            color_r = None
            color_g = None
            color_b = None
            color_a = None
            interpolation_type = constants.INTERPOLATION_NAME_BLEND_NAME[color_anim.interpolation]

            for time, color in color_anim.keyframes.items():
                # time = color_anim.times[index]
                # color = color_anim.values[index]
                if interval_start <= time <= interval_end or time == 0:
                    if not color_r:
                        color_r = action_fcurves(action).new(data_path_color, index=0)
                    if not color_g:
                        color_g = action_fcurves(action).new(data_path_color, index=1)
                    if not color_b:
                        color_b = action_fcurves(action).new(data_path_color, index=2)
                    if time == 0:
                        real_time = 0.0
                    else:
                        real_time = round((time - interval_start) / frame_time, 0)
                    color_r_keyframe = color_r.keyframe_points.insert(real_time, color[0])
                    color_g_keyframe = color_g.keyframe_points.insert(real_time, color[1])
                    color_b_keyframe = color_b.keyframe_points.insert(real_time, color[2])
                    color_r_keyframe.interpolation = interpolation_type
                    color_g_keyframe.interpolation = interpolation_type
                    color_b_keyframe.interpolation = interpolation_type
            if not color_r:
                color_r = action_fcurves(action).new(data_path_color, index=0)
                color_r.keyframe_points.insert(0, 1.0)
            if not color_g:
                color_g = action_fcurves(action).new(data_path_color, index=1)
                color_g.keyframe_points.insert(0, 1.0)
            if not color_b:
                color_b = action_fcurves(action).new(data_path_color, index=2)
                color_b.keyframe_points.insert(0, 1.0)
            interpolation_type = constants.INTERPOLATION_NAME_BLEND_NAME[alpha_anim.interpolation]

            for time, alpha in color_anim.keyframes.items():
                # time = alpha_anim.times[index]
                # alpha = alpha_anim.values[index]
                if interval_start <= time <= interval_end or time == 0:
                    if not color_a:
                        color_a = action_fcurves(action).new(data_path_color, index=3)
                    if time == 0:
                        real_time = 0.0
                    else:
                        real_time = round((time - interval_start) / frame_time, 0)
                    color_a_keyframe = color_a.keyframe_points.insert(real_time, alpha)
                    color_a_keyframe.interpolation = interpolation_type
            if not color_a:
                color_a = action_fcurves(action).new(data_path_color, index=3)
                color_a.keyframe_points.insert(0, 1.0)


def create_geoset_actions(model: War3Model,
                          bpy_objects: List[bpy.types.Object],
                          frame_time: float):
    print(" creating geoset animations")
    geoset_animations = model.geoset_anims
    sequences = model.sequences
    data_path_color = 'color'

    color_curves = []
    color1 = [1.0, 0, 0, 0.5]
    for geosetAnimation in geoset_animations:
        action: bpy.types.Action = bpy.data.actions.get('#UNANIMATED')
        if not action:
            action = bpy.data.actions.new(name='#UNANIMATED')
        for i in range(4):
            data_path = '["' + geosetAnimation.geoset_name + '"].' + data_path_color
            if action_fcurves(action).find(data_path, index=i) is None:
                # color_curve.keyframe_points.insert(0.0, 1.0)
                color_curve = action_fcurves(action).new(data_path, index=i, action_group=geosetAnimation.geoset_name)
                color_curve.keyframe_points.insert(0.0, color1[i])
                color_curves.append(color_curve)

    for sequence in sequences:
        interval_start = sequence.start
        interval_end = sequence.end
        for geosetAnimation in geoset_animations:
            action: bpy.types.Action = bpy.data.actions.get(sequence.name)
            if not action:
                action = bpy.data.actions.new(name=sequence.name)

            color_curves = []
            color_anim = geosetAnimation.color_anim
            g_name = geosetAnimation.geoset_name
            data_path = '["' + geosetAnimation.geoset_name + '"].' + data_path_color

            def get_or_add_curve(index: int):
                existing = action_fcurves(action).find(data_path, index=index)
                if existing is not None:
                    return existing
                return action_fcurves(action).new(data_path, index=index, action_group=g_name)

            # The RGB curves are fetched once per geoset, not once per keyframe:
            # the keyframe loop below used to re-append them every iteration and
            # then index the list positionally, which broke whenever the colour
            # track had no keyframe inside this sequence.
            rgb_curves = [get_or_add_curve(i) for i in range(3)]
            color_curves.extend(rgb_curves)

            if color_anim:
                interpolation_type = constants.INTERPOLATION_NAME_BLEND_NAME[color_anim.interpolation]

                for time, color in color_anim.keyframes.items():
                    if interval_start <= time <= interval_end or time == 0:
                        real_time = round((time - interval_start) / frame_time, 0)

                        for i in range(3):
                            kf_point = rgb_curves[i].keyframe_points.insert(real_time, color[i])
                            kf_point.interpolation = interpolation_type
            else:
                interpolation_type = constants.INTERPOLATION_NAME_BLEND_NAME['Linear']
                color = geosetAnimation.color
                real_time = 0
                for i in range(3):
                    kf_point = rgb_curves[i].keyframe_points.insert(real_time, color[i])
                    kf_point.interpolation = interpolation_type

            alpha_curve = get_or_add_curve(3)
            color_curves.append(alpha_curve)
            alpha_anim = geosetAnimation.alpha_anim
            if alpha_anim:
                interpolation_type = constants.INTERPOLATION_NAME_BLEND_NAME[alpha_anim.interpolation]

                for time, alpha in alpha_anim.keyframes.items():
                    if interval_start <= time <= interval_end or time == 0:
                        real_time = round((time - interval_start) / frame_time, 0)

                        kf_point = alpha_curve.keyframe_points.insert(real_time, alpha[0])
                        kf_point.interpolation = interpolation_type
            else:
                interpolation_type = constants.INTERPOLATION_NAME_BLEND_NAME['Linear']
                alpha = geosetAnimation.alpha
                real_time = 0
                kf_point = alpha_curve.keyframe_points.insert(real_time, alpha[0])
                kf_point.interpolation = interpolation_type

