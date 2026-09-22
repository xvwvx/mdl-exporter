import bpy


class WAR3_OT_remove_seq_from_armature(bpy.types.Operator):
    bl_idname = 'war_3.remove_sequence_from_armature'
    bl_label = '从骨架移除序列'
    bl_description = '从序列列表里删除选中的序列，可选择连同 Blender 动作一起删除'
    bl_options = {'UNDO'}

    type: bpy.props.EnumProperty(
        name="方式",
        description="「只移除」保留 Blender 动作以便以后再用；「连同动作删除」会一并删掉动作",
        items=[('REMOVE', "只移除序列", "保留 Blender 动作"),
               ('DELETE', "连同动作删除", "同时删除 Blender 动作")],
        default='REMOVE'
    )

    def execute(self, context):
        if context.armature:
            war3_data = context.armature.war_3
            if self.type == 'DELETE':
                seq_prop = war3_data.sequencesList[war3_data.sequencesListIndex]
                animation_name = seq_prop.name
                bpy_action = bpy.data.actions.get(animation_name)
                bpy.data.actions.remove(bpy_action)

            war3_data.sequencesList.remove(war3_data.sequencesListIndex)
            if war3_data.sequencesListIndex < len(war3_data.sequencesList):
                war3_data.sequencesListIndex = war3_data.sequencesListIndex
            elif 0 < war3_data.sequencesListIndex:
                war3_data.sequencesListIndex = war3_data.sequencesListIndex-1

        return {'FINISHED'}
