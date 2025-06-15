bl_info = {
    "name": "OBJ MC Blender",
    "author": "IllegalTempo",
    "version": (1, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > OBJMC",
    "description": "Export to Minecraft easier through OBJMC (Thanks to Godlander)",
    "category": "Import-Export"
}

import bpy
import bmesh
import tempfile
import os
import json
from bpy.props import StringProperty, EnumProperty
import threading
import sys
import subprocess
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty, EnumProperty
from bpy.types import Operator, Panel, AddonPreferences

class OBJMCPreferences(AddonPreferences):
    bl_idname = __name__

    objmc_path: StringProperty(
        name="OBJMC Path",
        subtype='FILE_PATH',
        description="Path to objmc.py script",
        default="C:\\objmc\\objmc.py"
    )
    resourcepack_path: StringProperty(
        name="Resource Pack Path",
        subtype='DIR_PATH',
        description="Path to Minecraft resource pack folder",
        default="C:\\Users\\%USERNAME%\\AppData\\Roaming\\.minecraft\\resourcepacks"
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "objmc_path")
        layout.prop(self, "resourcepack_path")

class OBJMC_PT_main_panel(Panel):
    bl_label = "OBJ MC Tools"
    bl_idname = "OBJMC_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'OBJMC'

    def draw(self, context):
        layout = self.layout
        
        # Show current OBJMC path
        preferences = bpy.context.preferences.addons[__name__].preferences
        if preferences:
            box = layout.box()
            box.label(text="OBJMC Settings")
            box.prop(preferences, "objmc_path")
            box.prop(preferences, "resourcepack_path")        # Model type selector
        box = layout.box()
        box.label(text="Model Type")
        row = box.row()
        row.prop(context.scene, "model_type", text="")        # Animation settings
        box = layout.box()
        box.label(text="Animation Settings")
        row = box.row()
        row.prop(context.scene, "autoplay")
        row = box.row()
        row.prop(context.scene, "colorbehavior1", text="Color Behavior 1")
        row.prop(context.scene, "colorbehavior2", text="Color Behavior 2")
        row.prop(context.scene, "colorbehavior3", text="Color Behavior 3")

        # Export button
        box = layout.box()
        box.label(text="Export")
        row = box.row()
        row.operator("objmc.export_mc", text="Export to MC", icon='EXPORT')

class OBJMC_OT_export_mc(Operator):
    bl_idname = "objmc.export_mc"
    bl_label = "Export to MC"
    bl_description = "Export model in Minecraft format"
    
    def execute(self, context):
        if not context.active_object:
            self.report({'ERROR'}, "No object selected")
            return {'CANCELLED'}
        
        # Get preferences first for objmc path
        preferences = bpy.context.preferences.addons[__name__].preferences
        if not preferences:
            self.report({'ERROR'}, "Addon preferences not found")
            return {'CANCELLED'}
          # Save temp OBJ files for each frame
        objmc_folder = os.path.dirname(preferences.objmc_path)
        obj_files = []
        
        # Store current frame
        current_frame = context.scene.frame_current
          # Get keyframes from animation data
        keyframes = set()
        obj = context.active_object
        
        # Check object's animation data
        if obj.animation_data and obj.animation_data.action:
            for fcurve in obj.animation_data.action.fcurves:
                for keyframe in fcurve.keyframe_points:
                    keyframes.add(int(keyframe.co[0]))
        
        if not keyframes:
            self.report({'WARNING'}, "No keyframes found, using first and last frame")
            keyframes = {context.scene.frame_start, context.scene.frame_end}
        
        # Sort keyframes
        keyframes = sorted(list(keyframes))
        
        # Export OBJ for every nth frame in the animation (step)
        frame_start = context.scene.frame_start
        frame_end = context.scene.frame_end
        step = context.scene.frame_step  # Default to 1 if not set
        obj_files = []

        for frame in range(frame_start-1, frame_end , step):
            context.scene.frame_set(frame)
            temp_obj = os.path.join(objmc_folder, f"temp_frame_{frame:04d}.obj")
            obj_files.append(temp_obj)
            bpy.ops.wm.obj_export(
                filepath=temp_obj,
                export_selected_objects=True,
                export_materials=True,
                export_uv=True,
                export_normals=True
            )
            self.report({'INFO'}, f"Exported frame {frame}")

        # Restore original frame
        context.scene.frame_set(current_frame)

        # Use the first obj file as reference for checks
        temp_obj = obj_files[0] if obj_files else None
        if not temp_obj:
            self.report({'ERROR'}, "No frames were exported")
            return {'CANCELLED'}
        
        # Collect all texture paths from materials and ensure they are absolute paths
        texs = []
        obj = context.active_object
        if obj.material_slots:
            for slot in obj.material_slots:
                if slot.material and slot.material.node_tree:
                    for node in slot.material.node_tree.nodes:
                        if node.type == 'TEX_IMAGE' and node.image:
                            # Get absolute path
                            if node.image.filepath_raw.startswith("//"):
                                # Convert relative path to absolute
                                abs_path = os.path.abspath(bpy.path.abspath(node.image.filepath_raw))
                            else:
                                abs_path = os.path.abspath(node.image.filepath_raw)
                            
                            # Ensure Windows path format with forward slashes
                            abs_path = abs_path.replace("\\", "/")
                            
                            if abs_path not in texs:
                                texs.append(abs_path)
        
        if not texs:
            self.report({'ERROR'}, "No textures found in materials. Please add textures to your material.")
            return {'CANCELLED'}
        
        objmc_path = preferences.objmc_path
        resourcepack_path = preferences.resourcepack_path
        
        # Get output name from the blend file or object name
        out_name = context.active_object.name
        
        # Construct output paths
        model_path = os.path.join(resourcepack_path, "assets", "minecraft", "models", "item", out_name + ".json")
        texture_path = os.path.join(resourcepack_path, "assets", "minecraft", "textures", "block", out_name + ".png")
        
        # Create directories if they don't exist
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        os.makedirs(os.path.dirname(texture_path), exist_ok=True)
        
        # Debug info
        self.report({'INFO'}, f"OBJ path: {temp_obj}")

        self.report({'INFO'}, f"Texture path: {texs[0]}")
        
        # Check if OBJ file exists and has content
        if os.path.exists(temp_obj):
            with open(temp_obj, 'r') as f:
                obj_content = f.read()
                self.report({'INFO'}, f"OBJ file size: {len(obj_content)} bytes")
        else:
            self.report({'ERROR'}, f"Temp OBJ file not found: {temp_obj}")            
            return {'CANCELLED'}        # Run objmc with full paths
        temp_json = os.path.join(objmc_folder, out_name + ".json")
        temp_texture = os.path.join(objmc_folder, out_name + ".png")        # Calculate animation duration from Blender timeline
        fps = context.scene.render.fps
        duration_seconds = (frame_end - frame_start+1) / fps  # Duration in seconds
        duration_ticks = int(duration_seconds * 20)  # Convert to Minecraft ticks (20 ticks = 1 second)
          # Build command arguments list        
        cmd_args = [
            '--objs'] + obj_files + [
            '--texs', texs[0],
            '--compression', "false",
            '--duration', str(duration_ticks),
            '--colorbehavior',
            context.scene.colorbehavior1,
            context.scene.colorbehavior2,
            context.scene.colorbehavior3,
            '--out', out_name + ".json", "block/" + out_name + ".png",
        ]
        
        # Add autoplay argument only if enabled
        if context.scene.autoplay:
            cmd_args += ['--autoplay']
            
        cmd = ['python', objmc_path] + cmd_args
        self.report({'INFO'}, f"Running command: {' '.join(cmd)}")
          # Run the process in a visible console window and keep it open
              # Start thread and wait for completion
        process = None
        def run_objmc_and_store():
            nonlocal process
            process = subprocess.Popen(
                cmd,
                cwd=objmc_folder,
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            
        thread = threading.Thread(target=run_objmc_and_store)
        thread.start()
        thread.join()  # Wait for thread to complete
        
        if process:
            process.wait()  # Wait for the process to complete
            
        # Check if output files exist
        if not os.path.exists(temp_json) or not os.path.exists(temp_texture):
            self.report({'ERROR'}, "Output files not generated. Check the console for errors.")
            return {'CANCELLED'}
            
        import shutil
        # Move files to their destinations        
        shutil.move(temp_json, model_path)
        shutil.move(temp_texture, texture_path)

        # Read the JSON file
        with open(model_path, 'r') as f:
            data = json.load(f)
            
            # Add the parent property for generated item
        data['parent'] = 'item/' + context.scene.model_type
            
        # Write the modified JSON back
        with open(model_path, 'w') as f:
            json.dump(data, f,indent=1)
            self.report({'INFO'}, "Added item parent and display settings to JSON")
        
        # Clean up temporary OBJ and MTL files
        for obj_file in obj_files:
            try:
                os.remove(obj_file)
                mtl_file = obj_file.replace('.obj', '.mtl')
                if os.path.exists(mtl_file):
                    os.remove(mtl_file)
            except Exception as e:
                self.report({'WARNING'}, f"Could not remove temporary file {obj_file} or its .mtl: {str(e)}")
        
        return {'FINISHED'}


classes = (
    OBJMC_PT_main_panel,
    OBJMC_OT_export_mc,
    OBJMCPreferences
)

def register():
    # Register model type property
    bpy.types.Scene.model_type = EnumProperty(
        name="Model Type",
        description="Type of model to export",
        items=[
            ('generated', "Generated", "Generated item model"),
            ('weapon', "Weapon", "Weapon model"),
        ],
        default='weapon'
    )    # Register autoplay property
    bpy.types.Scene.autoplay = bpy.props.BoolProperty(
        name="Autoplay",
        description="Auto play animation in Minecraft",
        default=True
    )
    
    allowed_behaviors = [
        ('time', 'Time', ''),
        ('pitch', 'Pitch', ''),
        ('yaw', 'Yaw', ''),
        ('roll', 'Roll', ''),
        ('scale', 'Scale', ''),
        ('overlay', 'Overlay', ''),
        ('hurt', 'Hurt', ''),
    ]
    bpy.types.Scene.colorbehavior1 = bpy.props.EnumProperty(
        name="Color Behavior 1",
        description="First color behavior argument",
        items=allowed_behaviors,
        default='time'
    )
    bpy.types.Scene.colorbehavior2 = bpy.props.EnumProperty(
        name="Color Behavior 2",
        description="Second color behavior argument",
        items=allowed_behaviors,
        default='time'
    )
    bpy.types.Scene.colorbehavior3 = bpy.props.EnumProperty(
        name="Color Behavior 3",
        description="Third color behavior argument",
        items=allowed_behaviors,
        default='time'
    )
    
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    # Unregister model type property
    del bpy.types.Scene.model_type
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()