import bpy


def set_sequence_name(self, value):
    for marker in bpy.context.scene.timeline_markers:
        if marker.name == self.seq_name:
            marker.name = value
    self.seq_name = value
    self.name = value


def set_current_sequence(self):
    bpy.context.scene.frame_start = self.start
    bpy.context.scene.frame_end = self.end


def get_sequence_name(self):
    return self.seq_name


def get_sequence_start(self):
    scene = bpy.context.scene
    if not len(scene.war3_mdl_sequences.mdl_sequences):
        return 0
    # active_sequence = scene.mdl_sequences[scene.mdl_sequence_index]
    return min(tuple(m.frame for m in scene.timeline_markers if m.name == self.seq_name))


def get_sequence_end(self):
    scene = bpy.context.scene
    if not len(scene.war3_mdl_sequences.mdl_sequences):
        return 0
    # active_sequence = scene.mdl_sequences[scene.mdl_sequence_index]
    return max(tuple(m.frame for m in scene.timeline_markers if m.name == self.seq_name))


class War3SequenceProperties(bpy.types.PropertyGroup):

    # Backing field

    name_display: bpy.props.StringProperty(
        name="序列名",
        description="序列的名字，导出后就是动画名（Stand、Attack 等）。"
                    "改名会同步改时间轴上同名的标记。",
        default="Stand",
        get=get_sequence_name,
        set=set_sequence_name
        )

    seq_name: bpy.props.StringProperty(
        name="",
        default="Sequence"
        )

    start: bpy.props.IntProperty(
        name="",
        get=get_sequence_start
        )

    end: bpy.props.IntProperty(
        name="",
        get=get_sequence_end
        )

    rarity: bpy.props.IntProperty(
        name="稀有度",
        description="随机播放权重：0 表示必定播放，数字越大越少播放。"
                    "用于同一用途的多个随机动画。",
        default=0,
        min=0
        )

    non_looping: bpy.props.BoolProperty(
        name="不循环",
        description="开启后该动画只播放一次不重复。攻击、死亡、消失这类动作要开。",
        default=False
        )

    move_speed: bpy.props.IntProperty(
        name="移动速度",
        description="该动画按 100% 速度播放时对应的单位移动速度。Walk 类动画必须填，"
                    "游戏据此调整播放快慢，让脚不打滑。",
        default=270,
        min=0
        )

