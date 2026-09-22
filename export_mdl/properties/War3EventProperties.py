from bpy.props import EnumProperty
from bpy.types import PropertyGroup

from .War3EventTypesContainer import War3EventTypesContainer

war3_event_types = War3EventTypesContainer()


# def update_event_type(prop_group, context):
#     obj = context.active_object
#
#     counter = 0
#
#     prop_group.event_id = war3_event_types.enums[prop_group.event_type][0][0]
#
#     while True:
#         if not any(
#                 [ob for ob in context.scene.objects if ob.name.startswith("%s%d" % (prop_group.event_type, counter))]):
#             obj.name = "%s%d%s" % (prop_group.event_type, counter, prop_group.event_id)
#             break
#         counter += 1
#
#     obj['event_type'] = prop_group.event_type
#     obj['event_id'] = prop_group.event_id


def get_event_items(prop_group, context):
    return war3_event_types.enums[prop_group.event_type]


def update_event_id(self, context):
    obj = context.active_object

    counter = 0
    obj.name = "EVENT"

    while True:
        if not any([ob for ob in context.scene.objects if ob.name.startswith("%s%d" % (self.event_type, counter))]):
            obj.name = "%s%d%s" % (self.event_type, counter, self.event_id)
            break
        counter += 1

    obj['event_id'] = str(self.event_id)


class War3EventProperties(PropertyGroup):

    # @staticmethod
    def update_event_type(self, context):
        obj = context.active_object

        counter = 0

        self.event_id = war3_event_types.enums[self.event_type][0][0]

        while True:
            if not any([ob for ob in context.scene.objects if ob.name.startswith("%s%d" % (self.event_type, counter))]):
                obj.name = "%s%d%s" % (self.event_type, counter, self.event_id)
                break
            counter += 1

        obj['event_type'] = self.event_type
        obj['event_id'] = self.event_id

    event_type: EnumProperty(
        name="事件类型",
        description="事件在游戏里触发的效果种类。选定后物体名会自动改成"
                    "「类型+序号+事件ID」的形式，导出时靠这个名字识别",
        items=[('SND', "音效", "播放声音"),
               ('FTP', "脚印", "生成脚印贴花"),
               ('SPN', "生成单位", "生成其他单位或物体"),
               ('SPL', "地面贴花", "生成地面贴花"),
               ('UBR', "大范围贴花", "生成大范围地面贴花")],
        default='SND',
        update=update_event_type
    )

    event_id:   EnumProperty(
        name="事件ID",
        description="事件的具体编号，取值取决于上面选的事件类型"
                    "（例如音效类型下就是音效编号）",
        items=get_event_items,
        update=update_event_id
    )
