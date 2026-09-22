import bpy
from bpy.props import StringProperty, IntProperty, BoolProperty
from bpy.types import Operator


class WAR3_OT_generate_from_actions(Operator):
    """按现有动作生成序列：每个 Blender 动作生成一条同名序列，长度取动作的帧范围。"""
    bl_idname = "war_3.generate_from_actions"
    bl_label = "从动作生成序列"
    bl_description = '按现有的 Blender 动作（Action）批量生成动画序列'
    bl_options = {'UNDO'}

    def execute(self, context: bpy.types.Context):
        # scene = context.window.scene
        # sequences = scene.mdl_sequences
        #
        # s = sequences.add()
        # s.name = self.name
        # s.rarity = self.rarity
        # s.non_looping = self.non_looping
        #
        # scene.mdl_sequence_index = len(sequences) - 1
        if context.armature:
            war3_data = context.armature.war_3
            sequences_list = war3_data.sequencesList
            sequence_index = war3_data.sequencesListIndex
            sequences_names = set(seq.name for seq in sequences_list)

            for action in bpy.data.actions:
                if action.name not in sequences_names:
                    sequence = war3_data.sequencesList.add()
                    sequence.name = action.name
                    sequence.length = action.frame_range[1] - action.frame_range[0]
            war3_data.sequencesListIndex = sequence_index

        return {'FINISHED'}
