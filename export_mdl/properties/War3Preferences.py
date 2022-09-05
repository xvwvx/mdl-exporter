import bpy


class War3Preferences(bpy.types.AddonPreferences):
    bl_idname = 'export_mdl'
    resourceFolder: bpy.props.StringProperty(
        name='Resource',
        default='',
        subtype='DIR_PATH'
        )
    alternativeResourceFolder: bpy.props.StringProperty(
        name='Alternative Resource',
        default='',
        subtype='DIR_PATH'
        )
    textureExtension: bpy.props.StringProperty(
        name='Image Extension',
        default='png'
        )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, 'resourceFolder')
        layout.prop(self, 'alternativeResourceFolder')
        layout.prop(self, 'textureExtension')
