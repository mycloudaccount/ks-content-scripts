import bpy
import sys
import os

# ============================================================
# CONFIG
# ============================================================

HIPS_BONE = "mixamorig:Hips"

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

    removed = 0
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for fc in list(bag.fcurves):
                    if hips_bone in fc.data_path and fc.data_path.endswith("location"):
                        bag.fcurves.remove(fc)
                        removed += 1

    if removed:
        log(f"✔ Stripped {removed} root-motion curves from '{action.name}'")

    action.update_tag()


def push_action_to_nla(armature, action):
    armature.animation_data_create()
    ad = armature.animation_data

    track = ad.nla_tracks.new()
    track.name = action.name
    track.mute = False
    track.is_solo = False

    start, end = action.frame_range

    strip = track.strips.new(
        name=action.name,
        start=0,
        action=action
    )

    strip.action_frame_start = start
    strip.action_frame_end = end
    strip.blend_type = 'REPLACE'
    strip.extrapolation = 'HOLD_FORWARD'
    strip.influence = 1.0
    strip.mute = False

    # CRITICAL: ensure NLA evaluates
    armature.animation_data.action = None

    log(f"✔ NLA track '{action.name}' created and enabled")


def get_armatures():
    return [o for o in bpy.context.scene.objects if o.type == 'ARMATURE']


def get_bone_signature(armature):
    return [b.name for b in armature.data.bones]


def import_fbx(path):
    log(f"▶ Importing FBX: {path}")
    bpy.ops.import_scene.fbx(filepath=path)
    log("✔ FBX import completed")

# ============================================================
# ARGUMENTS
# ============================================================


argv = sys.argv
argv = argv[argv.index("--") + 1:] if "--" in argv else []

if len(argv) < 1:
    raise RuntimeError("❌ Provide export root directory")

EXPORT_ROOT = os.path.abspath(argv[0])
FILTER_CHAR = argv[1].lower() if len(argv) > 1 else None

if not os.path.isdir(EXPORT_ROOT):
    raise RuntimeError(f"❌ Invalid export root: {EXPORT_ROOT}")

# ============================================================
# CHARACTER DISCOVERY
# ============================================================

char_dirs = [
    d for d in os.listdir(EXPORT_ROOT)
    if os.path.isdir(os.path.join(EXPORT_ROOT, d))
]

if FILTER_CHAR:
    if FILTER_CHAR not in [c.lower() for c in char_dirs]:
        raise RuntimeError(f"❌ Character '{FILTER_CHAR}' not found")
    char_dirs = [d for d in char_dirs if d.lower() == FILTER_CHAR]

log(f"▶ Characters to process: {char_dirs}")

# ============================================================
# MAIN LOOP
# ============================================================

for char_name in char_dirs:
    log(f"\n==============================")
    log(f"▶ Processing character: {char_name}")
    log(f"==============================")

    char_dir = os.path.join(EXPORT_ROOT, char_name)
    fbx_files = sorted(
        f for f in os.listdir(char_dir)
        if f.lower().endswith(".fbx")
    )

    if not fbx_files:
        log("⚠ No FBX files found, skipping")
        continue

    output_glb = os.path.join(char_dir, f"{char_name}.glb")

    # Reset Blender
    bpy.ops.wm.read_factory_settings(use_empty=True)

    # --------------------------------------------------------
    # Import first FBX (authoritative armature)
    # --------------------------------------------------------

    import_fbx(os.path.join(char_dir, fbx_files[0]))

    armature_main = get_armatures()[0]
    bones_main = get_bone_signature(armature_main)

    action_main = armature_main.animation_data.action
    action_main.name = os.path.splitext(fbx_files[0])[0].lower()

    normalize_action_frames(action_main)
    strip_mixamo_root_motion(action_main)
    push_action_to_nla(armature_main, action_main)

    # --------------------------------------------------------
    # Import remaining FBXs
    # --------------------------------------------------------

    for fbx in fbx_files[1:]:
        import_fbx(os.path.join(char_dir, fbx))

        armatures = get_armatures()
        armature_secondary = [a for a in armatures if a != armature_main][0]

        if get_bone_signature(armature_secondary) != bones_main:
            raise RuntimeError(f"❌ Bone mismatch in {fbx}")

        action = armature_secondary.animation_data.action
        action.name = os.path.splitext(fbx)[0].lower()

        normalize_action_frames(action)
        strip_mixamo_root_motion(action)

        armature_main.animation_data.action = action

        # Remove secondary meshes
        for obj in list(bpy.context.scene.objects):
            if obj.type == 'MESH' and obj.parent == armature_secondary:
                bpy.data.objects.remove(obj, do_unlink=True)

        bpy.data.objects.remove(armature_secondary, do_unlink=True)

        push_action_to_nla(armature_main, action)

    # FINAL SAFETY: ensure no active action overrides NLA
    armature_main.animation_data.action = None

    # --------------------------------------------------------
    # Export GLB
    # --------------------------------------------------------

    log(f"\n▶ Exporting {output_glb}")

    bpy.ops.export_scene.gltf(
        filepath=output_glb,
        export_format='GLB',
        export_yup=True,
        export_apply=True,
        export_animations=True,
        export_animation_mode='NLA_TRACKS',
        export_force_sampling=True,
        export_skins=True,
        export_morph=False,
        export_cameras=False,
        export_lights=False
    )

    log(f"✅ Finished {char_name}")

log("\n🎉 All done!")
