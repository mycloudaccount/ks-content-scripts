import bpy
import sys
import os
import math
import mathutils

# ============================================================
# CONFIG
# ============================================================

RENDER_SIZE = 512
CAMERA_DISTANCE = 20.0
CAMERA_HEIGHT = 0.0
BACKGROUND_TRANSPARENT = True
FRAME_PADDING = 0
FIT_PADDING = 1.05  # safe sprite padding

MAX_FRAMES_PER_ANIM = 24   # ⬅ limits PNGs per animation
MIN_FRAME_STEP = 4         # safety clamp

# ============================================================
# LOGGING
# ============================================================


def log(msg):
    print(msg)

# ============================================================
# FRAME SAMPLING
# ============================================================


def compute_sampled_frames(start, end, max_frames):
    total = end - start + 1
    if total <= max_frames:
        return list(range(start, end + 1))

    step = max(MIN_FRAME_STEP, total // max_frames)
    frames = list(range(start, end + 1, step))

    # Ensure final frame is included
    if frames[-1] != end:
        frames.append(end)

    return frames

# ============================================================
# ARGUMENTS
# ============================================================


argv = sys.argv
argv = argv[argv.index("--") + 1:] if "--" in argv else []

if len(argv) != 1:
    raise RuntimeError("❌ Provide exactly one GLB file")

GLB_PATH = os.path.abspath(argv[0])
GLB_DIR = os.path.dirname(GLB_PATH)
OUT_DIR = os.path.join(GLB_DIR, "2d_right")

# ============================================================
# RESET SCENE
# ============================================================

bpy.ops.wm.read_factory_settings(use_empty=True)

scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = RENDER_SIZE
scene.render.resolution_y = RENDER_SIZE
scene.render.film_transparent = BACKGROUND_TRANSPARENT
scene.render.image_settings.file_format = 'PNG'

scene.frame_set(0)

# ============================================================
# IMPORT GLB
# ============================================================

log(f"▶ Importing GLB: {GLB_PATH}")
bpy.ops.import_scene.gltf(filepath=GLB_PATH)

armature = next(o for o in scene.objects if o.type == 'ARMATURE')
mesh = next(o for o in scene.objects if o.type == 'MESH')

# ============================================================
# INITIAL GROUND + CENTER (STATIC)
# ============================================================

depsgraph = bpy.context.evaluated_depsgraph_get()
mesh_eval = mesh.evaluated_get(depsgraph)

bbox = [
    mesh_eval.matrix_world @ mathutils.Vector(c)
    for c in mesh_eval.bound_box
]

min_x = min(v.x for v in bbox)
max_x = max(v.x for v in bbox)
min_y = min(v.y for v in bbox)
max_y = max(v.y for v in bbox)
min_z = min(v.z for v in bbox)

center = mathutils.Vector((
    (min_x + max_x) / 2,
    (min_y + max_y) / 2,
    min_z  # feet on ground
))

armature.location -= center
mesh.location -= center
scene.view_layers.update()

# ============================================================
# CAMERA (ORTHO — FIXED ROTATION)
# ============================================================

cam_data = bpy.data.cameras.new("OrthoCam")
cam_data.type = 'ORTHO'
cam_data.clip_start = 0.01
cam_data.clip_end = 1000.0

cam = bpy.data.objects.new("OrthoCam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam

cam.rotation_euler = (
    math.radians(90),
    0,
    math.radians(90)
)

# ============================================================
# LIGHTING
# ============================================================

light = bpy.data.lights.new("KeyLight", type='SUN')
light.energy = 3.0
light_obj = bpy.data.objects.new("KeyLight", light)
scene.collection.objects.link(light_obj)
light_obj.rotation_euler = (
    math.radians(45),
    0,
    math.radians(45)
)

# ============================================================
# NLA VALIDATION
# ============================================================

if not armature.animation_data or not armature.animation_data.nla_tracks:
    raise RuntimeError("❌ No NLA animations found")

armature.animation_data.action = None

# ============================================================
# PER-ANIMATION FIT + RENDER (SAMPLED)
# ============================================================

os.makedirs(OUT_DIR, exist_ok=True)

for track in armature.animation_data.nla_tracks:

    # SOLO THIS TRACK
    for t in armature.animation_data.nla_tracks:
        t.mute = True
    track.mute = False

    strip = track.strips[0]
    name = track.name
    start = int(strip.frame_start)
    end = int(strip.frame_end)

    sampled_frames = compute_sampled_frames(
        start, end, MAX_FRAMES_PER_ANIM
    )

    log(f"📦 Fitting '{name}' ({len(sampled_frames)} frames)")

    # --------------------------------------------------------
    # PASS 1: UNION BOUNDING BOX (SAMPLED FRAMES)
    # --------------------------------------------------------

    min_y = min_z = 1e9
    max_y = max_z = -1e9

    for frame in sampled_frames:
        scene.frame_set(frame)
        bpy.context.view_layer.update()

        depsgraph = bpy.context.evaluated_depsgraph_get()
        mesh_eval = mesh.evaluated_get(depsgraph)

        bbox = [
            mesh_eval.matrix_world @ mathutils.Vector(c)
            for c in mesh_eval.bound_box
        ]

        min_y = min(min_y, *(v.y for v in bbox))
        max_y = max(max_y, *(v.y for v in bbox))
        min_z = min(min_z, *(v.z for v in bbox))
        max_z = max(max_z, *(v.z for v in bbox))

    height = (max_z - min_z) * FIT_PADDING

    # --------------------------------------------------------
    # LOCK CAMERA FOR THIS ANIMATION
    # --------------------------------------------------------

    cam_data.ortho_scale = height
    cam.location = (
        CAMERA_DISTANCE,
        0.0,
        (max_z + min_z) * 0.5 + CAMERA_HEIGHT
    )

    # --------------------------------------------------------
    # PIXEL CROP (VERTICAL ONLY)
    # --------------------------------------------------------

    border_min_y = ((min_z - cam.location.z) / cam_data.ortho_scale) + 0.5
    border_max_y = ((max_z - cam.location.z) / cam_data.ortho_scale) + 0.5

    border_min_y = max(0.0, min(1.0, border_min_y))
    border_max_y = max(0.0, min(1.0, border_max_y))

    scene.render.use_border = True
    scene.render.use_crop_to_border = True
    scene.render.border_min_x = 0.0
    scene.render.border_max_x = 1.0
    scene.render.border_min_y = border_min_y
    scene.render.border_max_y = border_max_y

    # --------------------------------------------------------
    # PASS 2: RENDER (SAMPLED FRAMES)
    # --------------------------------------------------------

    anim_dir = os.path.join(OUT_DIR, name)
    os.makedirs(anim_dir, exist_ok=True)

    frame_index = 1

    for frame in sampled_frames:
        scene.frame_set(frame)
        bpy.context.view_layer.update()

        scene.render.filepath = os.path.join(
            anim_dir,
            f"{name}_{str(frame_index).zfill(FRAME_PADDING)}.png"
        )

        bpy.ops.render.render(write_still=True)
        frame_index += 1

    scene.render.use_border = False
    scene.render.use_crop_to_border = False

# ============================================================
# DONE
# ============================================================

log(
    f"\n✅ All animations rendered with sampled, grounded, 2D-ready framing → {OUT_DIR}"
)
