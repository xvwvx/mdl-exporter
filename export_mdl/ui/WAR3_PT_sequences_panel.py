from bpy.types import Panel


class WAR3_PT_sequences_panel(Panel):
    """场景级的动画序列列表。每个序列对应导出文件里的一段 Sequence；
起始/结束帧取自时间轴上与序列同名的标记，所以改完序列名要同步改标记。"""
    bl_idname = "WAR3_PT_sequences_panel"
    bl_label = "魔兽争霸3 序列"
    bl_region_type = 'WINDOW'
    bl_space_type = 'PROPERTIES'
    bl_context = 'scene'

    @classmethod
    def poll(cls, context):
        war3_mdl_sequences = context.scene.war3_mdl_sequences
        return war3_mdl_sequences.mdl_sequences is not None

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        war3_mdl_sequences = getattr(scene, "war3_mdl_sequences", None)
        # print("war3_mdl_sequences: ", war3_mdl_sequences, isinstance(war3_mdl_sequences, War3SequencesProperties),
        #       ", type:", type(war3_mdl_sequences), ", index:", war3_mdl_sequences.mdl_sequence_index)
        # if isinstance(war3_mdl_sequences, War3SequencesProperties):

        index = war3_mdl_sequences.mdl_sequence_index
        sequences = war3_mdl_sequences.mdl_sequences

        layout.operator("war_3.add_anim_sequence", text="新建序列")

        if sequences is not None:
            row = layout.row()
            row.template_list(
                listtype_name='WAR3_UL_sequence_list',
                list_id='name',
                dataptr=war3_mdl_sequences,
                propname='mdl_sequences',
                active_dataptr=war3_mdl_sequences,
                active_propname='mdl_sequence_index',
                rows=2
            )
        if sequences is not None and 0 <= index < len(sequences):
            active_sequence = sequences[index]

            col = layout.column(align=True)
            col.prop(active_sequence, "name_display")
            col.separator()

            row = layout.row()
            col = row.column()
            col.label(text="起始帧")
            col = row.column()
            col.label(text="结束帧")

            row = layout.row()
            col = row.column()
            col.enabled = False
            col.prop(active_sequence, "start")
            col = row.column()
            col.enabled = False
            col.prop(active_sequence, "end")

            col.separator()

            col = layout.column()
            col.prop(active_sequence, "rarity")
            col.separator()
            if 'walk' in active_sequence.name.lower():
                col.prop(active_sequence, "move_speed")
                col.separator()
            col.prop(active_sequence, "non_looping")
