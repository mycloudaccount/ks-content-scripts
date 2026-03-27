import bpy
import os
import sys

# ============================================================
# CONFIG (override via CLI args if you want)
# ============================================================

INPUT_DIR = None
OUTPUT_GLB = None
FPS = 30

# ============================================================
# CLI ARGUMENTS
# ============================================================

argv = sys.argv
argv = argv[argv.index("--") + 1:] if "--" in argv else []

if len(argv) >= 2:
    INPUT_DIR = argv[0]
    OUTPUT_GLB = argv[1]
else:
    raise SystemExit(
        "Usage:\n"
        "  blender -b -P merge_glbs.py -- <input_dir> <output.glb>"
    )

INPUT_DIR = os.path.abspath(INPUT_DIR)
OUTPUT_GLB = os.path.abspath(OUTPUT_GLB)

if not os.path.isdir(INPUT_DIR):
    raise SystemExit(f"Input directory not found: {INPUT_DIR}")

os.makedirs(os.path.dirname(OUTPUT_GLB), exist_ok=True)

# ============================================================
# RESET SCENE (HEADLESS SAFE)
# ============================================================

bpy.ops.wm.read_factory_settings(use_empty=True)

scene = bpy.context.scene
scene.render.fps = FPS

# ============================================================
# HELPERS
# ============================================================


def import_glb(path):
    bpy.ops.import_scene.gltf(filepath=path)


def get_armatures():
    return [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]


def bone_signature(armature):
    return [b.name for b in armature.data.bones]


def action_name_from_file(path):
    return os.path.splitext(os.path.basename(path))[0].lower()


def cleanup_except(keep_armature):
    keep = {keep_armature}

    # keep any meshes parented to the armature
    for obj in bpy.context.scene.objects:
        if obj.parent == keep_armature:
            keep.add(obj)

    for obj in list(bpy.context.scene.objects):
        if obj not in keep:
            bpy.data.objects.remove(obj, do_unlink=True)


# ============================================================
# IMPORT + COLLECT ACTIONS
# ============================================================


armature = None
reference_bones = None
actions = []

for file in sorted(os.listdir(INPUT_DIR)):
    if not file.lower().endswith(".glb"):
        continue

    path = os.path.join(INPUT_DIR, file)
    print(f"📥 Importing {file}")

    import_glb(path)

    armatures = get_armatures()
    if not armatures:
        raise RuntimeError(f"No armature found in {file}")

    current = armatures[-1]

    if armature is None:
        armature = current
        reference_bones = bone_signature(armature)
    else:
        if bone_signature(current) != reference_bones:
            raise RuntimeError(f"Bone mismatch in {file}")

    # **Read action BEFORE cleanup**
    if not current.animation_data or not current.animation_data.action:
        raise RuntimeError(f"No animation in {file}")

    action = current.animation_data.action
    action.name = action_name_from_file(path)
    actions.append(action)

    # **Now cleanup**
    cleanup_except(armature)

# ============================================================
# EXPORT MERGED GLB
# ============================================================

bpy.ops.export_scene.gltf(
    filepath=OUTPUT_GLB,
    export_format="GLB",
    export_animations=True,
    export_animation_mode="ACTIONS",
    export_force_sampling=True,
    export_skins=True,
    export_apply=True,
)

print(f"✅ Export complete: {OUTPUT_GLB}")
