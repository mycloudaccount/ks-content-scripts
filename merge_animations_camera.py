import bpy
import sys
import os
import mathutils

# ============================================================
# CONFIG
# ============================================================

HIPS_BONE = "mixamorig:Hips"
RENDER_RES = (64, 64)
RENDER_FORMAT = "PNG"

# ============================================================
# UTILITIES
# ============================================================


def log(msg):
    print(msg)


def normalize_action_frames(action):
    if not action.layers:
        return

    frames = []
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for fc in bag.fcurves:
                    for kp in fc.keyframe_points:
                        frames.append(kp.co.x)

    if not frames:
        return

    offset = -min(frames)

    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for fc in bag.fcurves:
                    for kp in fc.keyframe_points:
                        kp.co.x += offset
                        kp.handle_left.x += offset
                        kp.handle_right.x += offset

    action.update_tag()


def strip_mixamo_root_motion(action, hips_bone=HIPS_BONE):
    if not action.layers:
        return

    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for fc in list(bag.fcurves):
                    if hips_bone in fc.data_path and fc.data_path.endswith("location"):
                        bag.fcurves.remove(fc)

    action.update_tag()


def push_action_to_nla(armature, action):
    armature.animation_data_create()
    ad = armature.animation_data

    track = ad.nla_tracks.new()
    track.name = action.name
    track.mute = False

    start, end = action.frame_range

    strip = track.strips.new(action.name, start=0, action=action)
    strip.action_frame_start = start
    strip.action_frame_end = end
    strip.blend_type = 'REPLACE'
    strip.extrapolation = 'HOLD_FORWARD'
    strip.influence = 1.0
    strip.mute = False

    armature.animation_data.action = None


def get_armatures():
    return [o for o in bpy.context.scene.objects if o.type == 'ARMATURE']


def get_bone_signature(armature):
    return [b.name for b in armature.data.bones]


def import_fbx(path):
    log(f"▶ Importing FBX: {path}")
    bpy.ops.import_scene.fbx(filepath=path)


# ============================================================
# CAMERA + RENDER
# ============================================================

def create_perspective_camera(target_obj):
    cam_data = bpy.data.cameras.new("PreviewCamera")
    cam_data.type = 'PERSP'
    cam_data.lens = 50

    cam = bpy.data.objects.new("PreviewCamera", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam

    # Compute bounding box center
    bbox = [target_obj.matrix_world @ mathutils.Vector(corner)
            for corner in target_obj.bound_box]
    center = sum(bbox, mathutils.Vector()) / 8

    size = max((v - center).length for v in bbox)

    cam.location = center + mathutils.Vector((0, -size * 2.5, size * 1.2))
    cam.rotation_euler = (mathutils.Vector(
        (center - cam.location))).to_track_quat('-Z', 'Y').to_euler()

    return cam


def render_preview(path):
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.render.resolution_x, scene.render.resolution_y = RENDER_RES
    scene.render.image_settings.file_format = RENDER_FORMAT
    scene.render.filepath = path

    bpy.ops.render.render(write_still=True)


# ============================================================
# ARGUMENTS
# ============================================================

argv = sys.argv
argv = argv[argv.index("--") + 1:] if "--" in argv else []

EXPORT_ROOT = os.path.abspath(argv[0])

# ============================================================
# MAIN LOOP
# ============================================================

for char_name in os.listdir(EXPORT_ROOT):
    char_dir = os.path.join(EXPORT_ROOT, char_name)
    if not os.path.isdir(char_dir):
        continue

    fbx_files = sorted(f for f in os.listdir(char_dir)
                       if f.lower().endswith(".fbx"))
    if not fbx_files:
        continue

    bpy.ops.wm.read_factory_settings(use_empty=True)

    import_fbx(os.path.join(char_dir, fbx_files[0]))
    armature_main = get_armatures()[0]

    create_perspective_camera(armature_main)

    bones_main = get_bone_signature(armature_main)

    action_main = armature_main.animation_data.action
    action_main.name = os.path.splitext(fbx_files[0])[0].lower()

    normalize_action_frames(action_main)
    strip_mixamo_root_motion(action_main)
    push_action_to_nla(armature_main, action_main)

    render_preview(os.path.join(
        char_dir, f"{char_name}_{action_main.name}.png"))

    for fbx in fbx_files[1:]:
        import_fbx(os.path.join(char_dir, fbx))
        arm2 = [a for a in get_armatures() if a != armature_main][0]

        action = arm2.animation_data.action
        action.name = os.path.splitext(fbx)[0].lower()

        normalize_action_frames(action)
        strip_mixamo_root_motion(action)

        armature_main.animation_data.action = action
        bpy.data.objects.remove(arm2, do_unlink=True)

        push_action_to_nla(armature_main, action)

        render_preview(os.path.join(
            char_dir, f"{char_name}_{action.name}.png"))

    bpy.ops.export_scene.gltf(
        filepath=os.path.join(char_dir, f"{char_name}.glb"),
        export_format='GLB',
        export_animation_mode='NLA_TRACKS'
    )

log("🎉 Done")
