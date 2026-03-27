import bpy
import sys
import os
import math
import mathutils
import shutil
import json
from PIL import Image
import zipfile

DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__),
    "render_2d_via_camera_config.json"
)


def parse_cli_args(argv):
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    args = {
        "glb_path": None,
        "config": DEFAULT_CONFIG_PATH if os.path.isfile(DEFAULT_CONFIG_PATH) else None,
    }

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--config":
            if i + 1 >= len(argv):
                raise ValueError("Expected a path after --config")
            args["config"] = argv[i + 1]
            i += 2
            continue
        if args["glb_path"] is None:
            args["glb_path"] = arg.strip().strip('"').strip("'")
            i += 1
            continue
        raise ValueError(f"Unknown argument: {arg}")

    return args


def merge_dicts(base, extra):
    merged = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


DEFAULT_CONFIG = {
    "GLB_PATH": None,
    "RENDER_SIZE": 256,
    "CAMERA_FOV_DEG": 35.0,
    "CAMERA_HEIGHT_OFFSET": 1.0,
    "FIT_PADDING": 1.0,
    "BACKGROUND_TRANSPARENT": True,
    "MAX_FRAMES_PER_ANIM": 24,
    "MIN_FRAME_STEP": 2,
    "TARGET_CHARACTER_HEIGHT": 10.0,
    "PERSPECTIVE_DISTANCE_MULTIPLIER": 1.25,
    "ROTATE_CHARACTER_X": 0.0,
    "ROTATE_CHARACTER_Y": 0.0,
    "ROTATE_CHARACTER_Z": 0.0,
    "CLEAN_VIEW_DIR": True,
    "CHAR_SETTINGS": {
        "JUMP_STRENGTH": 12.0,
        "SPRITE_SCALE_FACTOR": 0.24,
        "DEFAULT_ANIMATION_NAME": "idle",
    },
    "ENABLE_HEADSHOTS": True,
    "HEADSHOT_HEIGHT_RATIO": 0.35,
    "HEADSHOT_FRAME": 0,
    "HEADSHOT_FILENAME": "headshot.png",
    "SHADOWS": {
        "ENABLED": False,
        "KEY_SOFT_SIZE": 3.2,
        "FILL_SOFT_SIZE": 2.0,
        "KEY_ENERGY": 1.0,
        "FILL_ENERGY": 0.8,
        "SUN_ANGLE_DEG": 4.0,
    },
    "LIGHTING": {
        "EXPOSURE": 1.0,
        "INDIRECT_INTENSITY": 2.02,
        "INDIRECT_COLOR": [1.0, 1.0, 1.0],
        "TONE_MAPPING": "Filmic",
        "AO_ENABLED": True,
        "AO_INTENSITY": 5.89,
        "AO_DISTANCE": 5.0,
    },
    "FEATURES": {
        "SCALE_NORMALIZATION": True,
        "GROUNDING": True,
        "CAMERA_FIT": True,
        "LIGHTING": True,
        "WORLD_LIGHTING": True,
        "EMISSION": False,
        "BLOOM": True,
        "ORTHO_CAMERA": True,
    },
    "EMISSION": {
        "COLOR": [1.0, 1.0, 1.0, 1.0],
        "STRENGTH": 0.5,
        "MODE": "ADD",
    },
    "VIEWS": {
        "left": [-1, 0, -90],
    },
    "UPLOAD_TO_AZURE": True,
    "AZURE_STORAGE_ACCOUNT_NAME": "ksstorage",
    "AZURE_CONTAINER_NAME": "game-assets",
    "AZURE_BLOB_PREFIX": "characters",
}


def load_config(config_path):
    config = merge_dicts({}, DEFAULT_CONFIG)

    if config_path:
        with open(config_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)

        if not isinstance(loaded, dict):
            raise ValueError("Config file must contain a JSON object")

        config = merge_dicts(config, loaded)
        print(f"Loaded config: {config_path}")

    config["LIGHTING"]["INDIRECT_COLOR"] = tuple(
        config["LIGHTING"]["INDIRECT_COLOR"])
    config["EMISSION"]["COLOR"] = tuple(config["EMISSION"]["COLOR"])
    config["VIEWS"] = {
        key: tuple(value)
        for key, value in config["VIEWS"].items()
    }

    config["SHADOWS"] = dict(config["SHADOWS"])
    sun_angle_deg = config["SHADOWS"].pop("SUN_ANGLE_DEG", 4.0)
    config["SHADOWS"]["SUN_ANGLE"] = math.radians(sun_angle_deg)

    return config

# ============================================================
# COMMAND LINE ARGUMENTS
# ============================================================

CLI_ARGS = parse_cli_args(sys.argv)
CONFIG = load_config(CLI_ARGS["config"])
GLB_PATH = CLI_ARGS["glb_path"] or CONFIG.get("GLB_PATH")

if not GLB_PATH:
    raise RuntimeError(
        "No GLB path provided.\n"
        "Set GLB_PATH in the config file or pass it on the command line.\n"
        "Usage: blender -b --python render_2d_via_camera.py -- path/to/file.glb [--config path/to/config.json]"
    )

GLB_PATH = os.path.abspath(GLB_PATH)

if not os.path.isfile(GLB_PATH):
    raise FileNotFoundError(f"GLB not found: {GLB_PATH}")

GLB_DIR = os.path.dirname(GLB_PATH)
CHAR_NAME = os.path.splitext(os.path.basename(GLB_PATH))[0]

# Filled dynamically while rendering
ANIM_METADATA = {}
GENERATED_FILES = []

# ============================================================
# CONFIG
# ============================================================

RENDER_SIZE = CONFIG["RENDER_SIZE"]
CAMERA_FOV_DEG = CONFIG["CAMERA_FOV_DEG"]
CAMERA_HEIGHT_OFFSET = CONFIG["CAMERA_HEIGHT_OFFSET"]
FIT_PADDING = CONFIG["FIT_PADDING"]
BACKGROUND_TRANSPARENT = CONFIG["BACKGROUND_TRANSPARENT"]
MAX_FRAMES_PER_ANIM = CONFIG["MAX_FRAMES_PER_ANIM"]
MIN_FRAME_STEP = CONFIG["MIN_FRAME_STEP"]

# 🔧 SCALE NORMALIZATION
TARGET_CHARACTER_HEIGHT = CONFIG["TARGET_CHARACTER_HEIGHT"]  # Blender units (meters)

# 🔭 PERSPECTIVE CAMERA DISTANCE TUNING
PERSPECTIVE_DISTANCE_MULTIPLIER = CONFIG["PERSPECTIVE_DISTANCE_MULTIPLIER"]

# 🔄 CHARACTER ROTATION (DEGREES)
ROTATE_CHARACTER_X = CONFIG["ROTATE_CHARACTER_X"]
ROTATE_CHARACTER_Y = CONFIG["ROTATE_CHARACTER_Y"]
ROTATE_CHARACTER_Z = CONFIG["ROTATE_CHARACTER_Z"]

# Default behavior (False):
#   - Only deletes per-animation folders before rendering them
# When True:
#   - Deletes the entire view directory (e.g. 2d_left) before rendering anything
CLEAN_VIEW_DIR = CONFIG["CLEAN_VIEW_DIR"]

# ============================================================
# CHARACTER METADATA (JSON OUTPUT)
# ============================================================

CHAR_SETTINGS = dict(CONFIG["CHAR_SETTINGS"])
CHAR_SETTINGS["CHAR_NAME"] = CHAR_NAME
CHAR_SETTINGS["RENDER_SIZE"] = RENDER_SIZE

# ============================================================
# HEADSHOT SETTINGS
# ============================================================

ENABLE_HEADSHOTS = CONFIG["ENABLE_HEADSHOTS"]

# Percentage of character height to treat as "head"
# 0.30–0.40 tends to work well
HEADSHOT_HEIGHT_RATIO = CONFIG["HEADSHOT_HEIGHT_RATIO"]

# Which frame to sample for the headshot
# 0 is usually fine; can later switch to idle midpoint
HEADSHOT_FRAME = CONFIG["HEADSHOT_FRAME"]

HEADSHOT_FILENAME = CONFIG["HEADSHOT_FILENAME"]

HEADSHOT_METADATA = {}

# ============================================================
# SHADOW SETTINGS (EEVEE)
# ============================================================

SHADOWS = {
    "ENABLED": False,

    # Shadow softness
    "KEY_SOFT_SIZE": 3.2,
    "FILL_SOFT_SIZE": 2.0,

    # Shadow strength control
    "KEY_ENERGY": 1.0,
    "FILL_ENERGY": 0.8,

    # Sun softness (degrees → radians)
    "SUN_ANGLE": math.radians(4.0),
}
SHADOWS = CONFIG["SHADOWS"]

# ============================================================
# LIGHTING SETTINGS (EEVEE)
# ============================================================

LIGHTING = {
    "EXPOSURE": 1.0,
    "INDIRECT_INTENSITY": 2.02,
    "INDIRECT_COLOR": (1.0, 1.0, 1.0),
    "TONE_MAPPING": "Filmic",  # LINEAR or Filmic
    "AO_ENABLED": True,
    "AO_INTENSITY": 5.89,
    "AO_DISTANCE": 5.0,
}
LIGHTING = CONFIG["LIGHTING"]

# ============================================================
# FEATURE TOGGLES
# ============================================================

FEATURES = {
    "SCALE_NORMALIZATION": True,
    "GROUNDING": True,
    "CAMERA_FIT": True,
    "LIGHTING": True,
    "WORLD_LIGHTING": True,
    "EMISSION": False,
    "BLOOM": True,
    "ORTHO_CAMERA": True,
}
FEATURES = CONFIG["FEATURES"]

# ============================================================
# EMISSION SETTINGS
# ============================================================

EMISSION = {
    "COLOR": (1.0, 1.0, 1.0, 1.0),
    "STRENGTH": 0.5,
    "MODE": "ADD",
}
EMISSION = CONFIG["EMISSION"]

# ============================================================
# SIDE VIEWS
# ============================================================

# Each entry is (vx, vy, rot_z_deg)
# vx/vy determine camera direction on X/Y plane.
VIEWS = {
    "left": (-1, 0, -90),  # -X
}
VIEWS = CONFIG["VIEWS"]

# ============================================================
# LOGGING
# ============================================================


def log(msg):
    print(msg)


def recreate_dir(path):
    if os.path.exists(path):
        shutil.rmtree(path)
    os.makedirs(path)


def get_blob_service_client():
    try:
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient
    except ImportError as exc:
        raise RuntimeError(
            "Azure upload is enabled, but azure.identity / azure.storage.blob are not installed."
        ) from exc

    account_name = CONFIG["AZURE_STORAGE_ACCOUNT_NAME"]
    account_url = f"https://{account_name}.blob.core.windows.net"
    credential = DefaultAzureCredential()
    return BlobServiceClient(account_url=account_url, credential=credential)


def ensure_blob_container(blob_service_client):
    container_name = CONFIG["AZURE_CONTAINER_NAME"]
    container_client = blob_service_client.get_container_client(container_name)

    try:
        container_client.create_container()
        log(f"Created Azure container: {container_name}")
    except Exception:
        pass

    return container_client


def upload_file_to_azure(container_client, local_file_path, blob_name):
    from azure.storage.blob import ContentSettings

    content_settings = None
    lower_path = local_file_path.lower()

    if lower_path.endswith(".png"):
        content_settings = ContentSettings(content_type="image/png")
    elif lower_path.endswith(".json"):
        content_settings = ContentSettings(content_type="application/json")
    elif lower_path.endswith(".zip"):
        content_settings = ContentSettings(content_type="application/zip")

    blob_client = container_client.get_blob_client(blob_name)

    with open(local_file_path, "rb") as data:
        blob_client.upload_blob(
            data,
            overwrite=True,
            content_settings=content_settings
        )

    log(f"Uploaded to Azure Blob: {blob_name}")


def build_blob_name(filename):
    prefix = CONFIG.get("AZURE_BLOB_PREFIX", "").strip("/")

    if prefix:
        return f"{prefix}/{filename}"
    return filename


def create_zip_bundle(bundle_path, files_to_include):
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for local_path, archive_name in files_to_include:
            zf.write(local_path, arcname=archive_name)

    log(f"Saved zip bundle: {bundle_path}")
    return bundle_path


def collect_source_3d_files(directory):
    supported_exts = {
        ".glb",
        ".gltf",
        ".fbx",
        ".obj",
        ".stl",
        ".ply",
        ".dae",
        ".blend",
        ".abc",
        ".usd",
        ".usda",
        ".usdc",
        ".usdz",
        ".vox",
    }

    files = []
    for entry in os.scandir(directory):
        if not entry.is_file():
            continue

        ext = os.path.splitext(entry.name)[1].lower()
        if ext not in supported_exts:
            continue

        files.append((entry.path, os.path.join("3d", entry.name)))

    files.sort(key=lambda item: item[1].lower())
    return files


def crop_image_to_content(path, margin=8):
    """
    Crops transparent edges and adds a margin (in pixels).
    """
    img = Image.open(path)
    img_rgba = img.convert("RGBA")
    bbox = img_rgba.getbbox()

    if bbox is None:
        return  # image is fully transparent

    left, upper, right, lower = bbox

    # apply margin
    left = max(left - margin, 0)
    upper = max(upper - margin, 0)
    right = min(right + margin, img.width)
    lower = min(lower + margin, img.height)

    cropped = img_rgba.crop((left, upper, right, lower))
    cropped.save(path)


def compute_head_bounds_at_frame(mesh, frame, head_ratio):
    scene = bpy.context.scene
    scene.frame_set(frame)
    bpy.context.view_layer.update()

    depsgraph = bpy.context.evaluated_depsgraph_get()
    obj_eval = mesh.evaluated_get(depsgraph)

    bbox = [obj_eval.matrix_world @ mathutils.Vector(c)
            for c in obj_eval.bound_box]

    min_x = min(v.x for v in bbox)
    max_x = max(v.x for v in bbox)
    min_y = min(v.y for v in bbox)
    max_y = max(v.y for v in bbox)
    min_z = min(v.z for v in bbox)
    max_z = max(v.z for v in bbox)

    height = max_z - min_z
    head_min_z = max_z - (height * head_ratio)

    return (
        min_x, max_x,
        min_y, max_y,
        head_min_z, max_z
    )


def set_bloom(scene, enabled):
    eevee = scene.eevee
    if hasattr(eevee, "use_bloom"):
        eevee.use_bloom = enabled
    if hasattr(eevee, "bloom_intensity"):
        eevee.bloom_intensity = 0.0 if not enabled else 0.1
    if hasattr(eevee, "bloom_threshold"):
        eevee.bloom_threshold = 0.8
    if hasattr(eevee, "bloom_radius"):
        eevee.bloom_radius = 6.5


def set_lighting(scene):
    # Exposure
    if hasattr(scene.view_settings, "exposure"):
        scene.view_settings.exposure = LIGHTING["EXPOSURE"]

    # Tone mapping
    if hasattr(scene.view_settings, "view_transform"):
        scene.view_settings.view_transform = LIGHTING["TONE_MAPPING"]

    # Indirect / Ambient intensity
    if hasattr(scene.eevee, "indirect_light_intensity"):
        scene.eevee.indirect_light_intensity = LIGHTING["INDIRECT_INTENSITY"]
    if hasattr(scene.eevee, "indirect_light_color"):
        scene.eevee.indirect_light_color = LIGHTING["INDIRECT_COLOR"]

    # AO
    if hasattr(scene.eevee, "use_gtao"):
        scene.eevee.use_gtao = LIGHTING["AO_ENABLED"]
    if hasattr(scene.eevee, "gtao_distance"):
        scene.eevee.gtao_distance = LIGHTING["AO_DISTANCE"]
    if hasattr(scene.eevee, "gtao_factor"):
        scene.eevee.gtao_factor = LIGHTING["AO_INTENSITY"]


def enable_emission(obj, color, strength, mode="ADD"):
    for mat_slot in obj.material_slots:
        mat = mat_slot.material
        if not mat:
            continue

        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links

        principled = next(
            (n for n in nodes if n.type == "BSDF_PRINCIPLED"),
            None
        )
        if not principled:
            continue

        emission_color_input = (
            principled.inputs.get("Emission") or
            principled.inputs.get("Emission Color")
        )
        emission_strength_input = principled.inputs.get("Emission Strength")

        if not emission_color_input:
            continue

        base = principled.inputs.get("Base Color")

        if base and base.is_linked:
            src = base.links[0].from_socket
            links.new(src, emission_color_input)
        else:
            emission_color_input.default_value = color

        if emission_strength_input:
            emission_strength_input.default_value = strength


# ============================================================
# DEBUG HELPERS
# ============================================================


def debug_scene_overview(scene):
    log("🔍 Scene Overview")
    for o in scene.objects:
        log(
            f"  {o.name:25} "
            f"type={o.type:9} "
            f"loc={tuple(round(v, 4) for v in o.location)} "
            f"scale={tuple(round(v, 4) for v in o.scale)}"
        )


def debug_armature_motion(arm, frame):
    loc = arm.matrix_world.translation
    log(
        f"🦴 Frame {frame:4d} | Armature world loc = "
        f"({loc.x:.6f}, {loc.y:.6f}, {loc.z:.6f})"
    )


def debug_mesh_bounds(mesh, frame):
    dg = bpy.context.evaluated_depsgraph_get()
    eval_obj = mesh.evaluated_get(dg)

    bbox = [eval_obj.matrix_world @
            mathutils.Vector(c) for c in eval_obj.bound_box]

    min_v = mathutils.Vector((
        min(v.x for v in bbox),
        min(v.y for v in bbox),
        min(v.z for v in bbox),
    ))
    max_v = mathutils.Vector((
        max(v.x for v in bbox),
        max(v.y for v in bbox),
        max(v.z for v in bbox),
    ))

    log(
        f"📦 Frame {frame:4d} | "
        f"Bounds Z = ({min_v.z:.4f} → {max_v.z:.4f}) "
        f"Height = {(max_v.z - min_v.z):.4f}"
    )


def debug_camera_static(cam):
    log("📷 Camera Debug")
    log(f"  Location : {tuple(round(v, 4) for v in cam.location)}")
    log(
        f"  Rotation : "
        f"{tuple(round(math.degrees(v), 2) for v in cam.rotation_euler)}"
    )
    log(f"  FOV deg  : {math.degrees(cam.data.angle):.2f}")
    log(f"  Clip     : {cam.data.clip_start} → {cam.data.clip_end}")


def debug_camera_to_armature(cam, arm, frame):
    delta = arm.matrix_world.translation - cam.location
    log(f"📏 Frame {frame:4d} | Cam→Arm dist = {delta.length:.4f}")


def bounds_fingerprint(obj, precision=4):
    """
    Returns a stable, quantized fingerprint of the evaluated mesh bounds.
    Used to detect identical poses across frames.
    """
    depsgraph = bpy.context.evaluated_depsgraph_get()
    obj_eval = obj.evaluated_get(depsgraph)

    bbox = [obj_eval.matrix_world @ mathutils.Vector(c)
            for c in obj_eval.bound_box]

    return tuple(round(v, precision) for v in (
        min(v.x for v in bbox),
        max(v.x for v in bbox),
        min(v.y for v in bbox),
        max(v.y for v in bbox),
        min(v.z for v in bbox),
        max(v.z for v in bbox),
    ))


def drop_duplicate_loop_frame(frames, mesh):
    """
    Removes the final frame if it is visually identical to the first frame.
    Safe for sprite rendering from looping animations.
    """
    if len(frames) < 2:
        return frames

    scene = bpy.context.scene

    # First frame fingerprint
    scene.frame_set(frames[0])
    bpy.context.view_layer.update()
    fp_start = bounds_fingerprint(mesh)

    # Last frame fingerprint
    scene.frame_set(frames[-1])
    bpy.context.view_layer.update()
    fp_end = bounds_fingerprint(mesh)

    if fp_start == fp_end:
        log("🔁 Loop frame detected (first == last) → dropping final frame")
        return frames[:-1]

    return frames

# ============================================================
# FRAME SAMPLING
# ============================================================


def compute_sampled_frames(start, end, max_frames):
    total = end - start + 1
    if total <= max_frames:
        return list(range(start, end + 1))

    step = max(MIN_FRAME_STEP, total // max_frames)
    frames = list(range(start, end + 1, step))

    if frames[-1] != end:
        frames.append(end)

    return frames


parent_folder = os.path.basename(GLB_DIR)
if parent_folder.startswith("2d_"):
    GLB_DIR = os.path.dirname(GLB_DIR)

# OUT_DIR will be created per view later

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

set_bloom(scene, FEATURES["BLOOM"])
set_lighting(scene)

log(f"✨ Bloom = {FEATURES['BLOOM']}")
log(f"🎨 Render engine = {scene.render.engine}")
log(f"🎭 Film transparent = {scene.render.film_transparent}")

scene.frame_set(0)

# ============================================================
# IMPORT GLB
# ============================================================

log(f"▶ Importing GLB: {GLB_PATH}")
bpy.ops.import_scene.gltf(filepath=GLB_PATH)

debug_scene_overview(scene)

armature = next(o for o in scene.objects if o.type == 'ARMATURE')
mesh = next(
    o for o in scene.objects
    if o.type == 'MESH' and o.find_armature()
)

# ============================================================
# EMISSION (OPTIONAL)
# ============================================================

if FEATURES["EMISSION"]:
    enable_emission(mesh, EMISSION["COLOR"],
                    EMISSION["STRENGTH"], EMISSION["MODE"])

# ============================================================
# SCALE NORMALIZATION — ARMATURE ROOT ONLY (OPTIONAL)
# ============================================================

if FEATURES["SCALE_NORMALIZATION"]:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    mesh_eval = mesh.evaluated_get(depsgraph)

    bbox = [mesh_eval.matrix_world @
            mathutils.Vector(c) for c in mesh_eval.bound_box]

    min_z = min(v.z for v in bbox)
    max_z = max(v.z for v in bbox)
    current_height = max_z - min_z

    if current_height <= 0.0001:
        raise RuntimeError("❌ Invalid mesh bounds for scale normalization")

    scale_factor = TARGET_CHARACTER_HEIGHT / current_height
    log(f"📐 Normalizing scale (armature only) by factor: {scale_factor:.4f}")

    armature.scale *= scale_factor
    mesh.scale = (1.0, 1.0, 1.0)
    bpy.context.view_layer.update()

    debug_scene_overview(scene)

# ============================================================
# GROUND CHARACTER (OPTIONAL)
# ============================================================

if FEATURES["GROUNDING"]:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    mesh_eval = mesh.evaluated_get(depsgraph)

    bbox = [mesh_eval.matrix_world @
            mathutils.Vector(c) for c in mesh_eval.bound_box]

    min_z = min(v.z for v in bbox)
    offset = mathutils.Vector((0.0, 0.0, min_z))

    armature.location -= offset
    mesh.location -= offset
    bpy.context.view_layer.update()

    log(f"⬇ Ground offset applied: {offset.z:.6f}")


# ============================================================
# CHARACTER ROTATION (OPTIONAL) — VIA PARENT EMPTY
# ============================================================

if any((ROTATE_CHARACTER_X, ROTATE_CHARACTER_Y, ROTATE_CHARACTER_Z)):
    log(
        f"🔄 Rotating character via parent empty "
        f"(X={ROTATE_CHARACTER_X}°, "
        f"Y={ROTATE_CHARACTER_Y}°, "
        f"Z={ROTATE_CHARACTER_Z}°)"
    )

    # Create empty
    rot_empty = bpy.data.objects.new("CharacterRotation", None)
    rot_empty.empty_display_type = 'PLAIN_AXES'
    scene.collection.objects.link(rot_empty)

    # Match armature origin
    rot_empty.location = armature.location
    rot_empty.rotation_mode = 'XYZ'

    # Parent armature + mesh
    armature.parent = rot_empty
    mesh.parent = rot_empty

    # Apply rotation
    rot_empty.rotation_euler = (
        math.radians(ROTATE_CHARACTER_X),
        math.radians(ROTATE_CHARACTER_Y),
        math.radians(ROTATE_CHARACTER_Z),
    )

    bpy.context.view_layer.update()


# ============================================================
# CAMERA
# ============================================================

cam_data = bpy.data.cameras.new("PerspCam")
cam_data.type = 'ORTHO' if FEATURES["ORTHO_CAMERA"] else 'PERSP'

if not FEATURES["ORTHO_CAMERA"]:
    cam_data.lens_unit = 'FOV'
    cam_data.angle = math.radians(CAMERA_FOV_DEG)
else:
    cam_data.ortho_scale = 8.0

cam_data.clip_start = 0.01
cam_data.clip_end = 1000.0

cam = bpy.data.objects.new("PerspCam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam

# ============================================================
# NLA VALIDATION
# ============================================================

if not armature.animation_data or not armature.animation_data.nla_tracks:
    raise RuntimeError("❌ No NLA animations found")

armature.animation_data.action = None

# ============================================================
# CAMERA FIT HELPERS (per animation)
# ============================================================


def compute_mesh_bounds_at_frame(obj, frame):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    obj_eval = obj.evaluated_get(depsgraph)

    bbox = [obj_eval.matrix_world @
            mathutils.Vector(c) for c in obj_eval.bound_box]

    min_x = min(v.x for v in bbox)
    max_x = max(v.x for v in bbox)
    min_y = min(v.y for v in bbox)
    max_y = max(v.y for v in bbox)
    min_z = min(v.z for v in bbox)
    max_z = max(v.z for v in bbox)

    return min_x, max_x, min_y, max_y, min_z, max_z


def fit_camera_for_bounds(min_x, max_x, min_y, max_y, min_z, max_z, view=(1, 0, 90)):
    height = (max_z - min_z) * FIT_PADDING
    width = (max_y - min_y) * FIT_PADDING

    VERTICAL_BIAS = 0.42
    target_z = min_z + height * VERTICAL_BIAS

    vx, vy, rot_z = view

    if FEATURES["ORTHO_CAMERA"]:
        cam.location = (
            (max_x + 10) * vx if vx != 0 else (min_x + max_x) / 2,
            (min_y + max_y) / 2 if vy == 0 else (max_y + 10) * vy,
            target_z + CAMERA_HEIGHT_OFFSET
        )
        cam.rotation_euler = (
            math.radians(90),
            0.0,
            math.radians(rot_z)
        )
        cam.data.ortho_scale = max(height, width) * 1.1

    else:
        half_height = height * 0.5
        distance = (
            half_height / math.tan(cam_data.angle * 0.5)
        ) * PERSPECTIVE_DISTANCE_MULTIPLIER

        cam.location = (
            distance * vx,
            distance * vy,
            target_z + CAMERA_HEIGHT_OFFSET
        )
        cam.rotation_euler = (
            math.radians(90),
            0.0,
            math.radians(rot_z)
        )

# ============================================================
# LIGHTING (OPTIONAL)
# ============================================================


if FEATURES["WORLD_LIGHTING"]:
    scene.world = bpy.data.worlds.new("World")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 4.0
else:
    if scene.world:
        scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 4.0

if FEATURES["LIGHTING"]:
    # Key light (main shadow caster)
    light_key = bpy.data.lights.new("KeyLight", type='SUN')
    light_key.energy = SHADOWS["KEY_ENERGY"]
    light_key.angle = SHADOWS["SUN_ANGLE"]
    light_key.shadow_soft_size = SHADOWS["KEY_SOFT_SIZE"]

    if hasattr(light_key, "use_shadow"):
        light_key.use_shadow = SHADOWS["ENABLED"]

    light_key_obj = bpy.data.objects.new("KeyLight", light_key)
    scene.collection.objects.link(light_key_obj)

    light_key_obj.rotation_euler = (
        math.radians(45),
        0.0,
        math.radians(45)
    )

    # Fill light (softens shadows)
    light_fill = bpy.data.lights.new("FillLight", type='SUN')
    light_fill.energy = SHADOWS["FILL_ENERGY"]
    light_fill.angle = SHADOWS["SUN_ANGLE"]
    light_fill.shadow_soft_size = SHADOWS["FILL_SOFT_SIZE"]

    if hasattr(light_fill, "use_shadow"):
        light_fill.use_shadow = SHADOWS["ENABLED"]

    light_fill_obj = bpy.data.objects.new("FillLight", light_fill)
    scene.collection.objects.link(light_fill_obj)

    light_fill_obj.rotation_euler = (
        math.radians(60),
        0.0,
        math.radians(-45)
    )

# ============================================================
# RENDER ANIMATIONS
# ============================================================

for view_name, view_data in VIEWS.items():

    OUT_DIR = os.path.join(GLB_DIR, f"2d_{view_name}")

    if CLEAN_VIEW_DIR:
        log(f"🔥 Cleaning entire view dir: {OUT_DIR}")
        recreate_dir(OUT_DIR)
    else:
        os.makedirs(OUT_DIR, exist_ok=True)

    # ============================================================
    # RENDER HEADSHOT (ONCE PER VIEW)
    # ============================================================

    if ENABLE_HEADSHOTS:
        log(f"🧑 Rendering headshot [{view_name}]")

        min_x, max_x, min_y, max_y, min_z, max_z = compute_head_bounds_at_frame(
            mesh,
            HEADSHOT_FRAME,
            HEADSHOT_HEIGHT_RATIO
        )

        fit_camera_for_bounds(
            min_x, max_x,
            min_y, max_y,
            min_z, max_z,
            view_data
        )

        headshot_path = os.path.join(OUT_DIR, HEADSHOT_FILENAME)
        scene.render.filepath = headshot_path
        bpy.ops.render.render(write_still=True)
        crop_image_to_content(scene.render.filepath, margin=8)
        GENERATED_FILES.append(headshot_path)

        # Store metadata path (relative, engine-friendly)
        HEADSHOT_METADATA[view_name] = os.path.join(
            f"2d_{view_name}",
            HEADSHOT_FILENAME
        )

    for track in armature.animation_data.nla_tracks:

        for t in armature.animation_data.nla_tracks:
            t.mute = True
        track.mute = False

        strip = track.strips[0]
        name = track.name
        start = int(strip.frame_start)
        end = int(strip.frame_end)

        frames = compute_sampled_frames(start, end, MAX_FRAMES_PER_ANIM)
        frames = drop_duplicate_loop_frame(frames, mesh)

        # Store animation metadata (once per animation name)
        if name not in ANIM_METADATA:
            ANIM_METADATA[name] = {
                "FRAME_COUNT": len(frames),
                "FPS": scene.render.fps,
                "START_FRAME": start,
                "END_FRAME": end,
                "SAMPLED": len(frames) < (end - start + 1),
            }

        log(f"\n📦 Rendering '{name}' ({len(frames)} frames) [{view_name}]")

        if FEATURES["CAMERA_FIT"]:
            worst_min_x = float("inf")
            worst_max_x = float("-inf")
            worst_min_y = float("inf")
            worst_max_y = float("-inf")
            worst_min_z = float("inf")
            worst_max_z = float("-inf")

            for frame in frames:
                scene.frame_set(frame)
                bpy.context.view_layer.update()

                min_x, max_x, min_y, max_y, min_z, max_z = compute_mesh_bounds_at_frame(
                    mesh, frame)

                worst_min_x = min(worst_min_x, min_x)
                worst_max_x = max(worst_max_x, max_x)
                worst_min_y = min(worst_min_y, min_y)
                worst_max_y = max(worst_max_y, max_y)
                worst_min_z = min(worst_min_z, min_z)
                worst_max_z = max(worst_max_z, max_z)

            fit_camera_for_bounds(
                worst_min_x, worst_max_x,
                worst_min_y, worst_max_y,
                worst_min_z, worst_max_z,
                view_data
            )

            debug_camera_static(cam)

            anim_dir = os.path.join(OUT_DIR, name)
            recreate_dir(anim_dir)

        for i, frame in enumerate(frames, start=1):
            scene.frame_set(frame)
            bpy.context.view_layer.update()

            debug_armature_motion(armature, frame)
            debug_mesh_bounds(mesh, frame)
            debug_camera_to_armature(cam, armature, frame)

            scene.render.filepath = os.path.join(
                anim_dir,
                f"{name}_{str(i).zfill(3)}.png"
            )

            log(f"🎬 Rendering frame {frame} → {scene.render.filepath}")
            bpy.ops.render.render(write_still=True)
            GENERATED_FILES.append(scene.render.filepath)

# ============================================================
# WRITE CHARACTER JSON METADATA
# ============================================================

char_json = {
    **CHAR_SETTINGS,
    "HEADSHOTS": HEADSHOT_METADATA,
    "ANIMATIONS": {
        anim_name: {
            "FRAME_COUNT": data["FRAME_COUNT"],
            "FPS": data["FPS"],
            "START_FRAME": data["START_FRAME"],
            "END_FRAME": data["END_FRAME"],
            "SAMPLED": data["SAMPLED"],
        }
        for anim_name, data in ANIM_METADATA.items()
    }
}

json_path = os.path.join(GLB_DIR, f"{CHAR_NAME}.json")

with open(json_path, "w", encoding="utf-8") as f:
    json.dump(char_json, f, indent=2)

log(f"🧾 Wrote character metadata → {json_path}")
GENERATED_FILES.append(json_path)

zip_path = os.path.join(GLB_DIR, f"{CHAR_NAME}.zip")
bundle_files = [
    (path, os.path.relpath(path, GLB_DIR))
    for path in GENERATED_FILES
]
bundle_files.extend(collect_source_3d_files(GLB_DIR))
create_zip_bundle(zip_path, bundle_files)

if CONFIG.get("UPLOAD_TO_AZURE"):
    container_client = ensure_blob_container(get_blob_service_client())
    upload_file_to_azure(
        container_client,
        zip_path,
        build_blob_name(os.path.basename(zip_path))
    )


log(f"\n✅ Debug-render complete → {OUT_DIR}")
