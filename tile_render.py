# ============================================================
# Kingdom Stack - Batch Tile Renderer (Viewport-Fit Edition)
# Blender 3.6+ / 4.x
#
# Now includes Azure Blob upload support.
# ============================================================

import bpy
import os
import math
import json
import sys
import zipfile
from mathutils import Vector

# -----------------------------
# & "C:\Program Files\Blender Foundation\Blender 5.0\blender.exe" -b --python tile_render.py -- --config tile_render_config.json

# & "C:\Program Files\Blender Foundation\Blender 5.0\5.0\python\bin\python.exe" -m pip install azure-storage-blob azure-identity

# -----------------------------
# CONFIG
# -----------------------------
CONFIG = {
    "input_dir": r"C:\myapps\temp",
    "output_dir": r"C:\myapps\temp",

    "supported_exts": [".obj", ".fbx", ".glb", ".gltf", ".stl", ".ply", ".dae"],

    "engine": "CYCLES",
    "transparent_background": True,
    "resolution_x": 256,
    "resolution_y": 256,
    "resolution_percentage": 100,
    "cycles_samples": 64,
    "cycles_denoise": True,
    "views": ["right", "back", "left", "front"],

    "camera_ortho": True,
    "camera_ortho_zoom": 1.4,
    "camera_fit_safety": 1.05,
    "camera_margin_factor": 0,
    "camera_distance": 5.0,

    "lighting_mode": "EMISSIVE_AO",
    "emission_strength": 2.5,
    "fake_ao_strength": 0.35,

    "render_toon_variant": True,
    "render_toon_only": False,
    "toon_steps": 4,
    "toon_specular": 0.1,

    "crop_mode": "AUTO",
    "alpha_threshold": 0.01,
    "crop_top": 0,
    "crop_bottom": 0,
    "crop_left": 0,
    "crop_right": 0,

    "output_width": 128,
    "output_height": 128,
    "scale_to_fit": True,
    "scale_mode": "FILL",

    "output_prefix": "",
    "output_suffix": "",
    "temp_dir": None,

    "cleanup_between_files": True,
    "force_emissive_only": False,

    # -----------------------------
    # AZURE BLOB CONFIG
    # -----------------------------
    "upload_to_azure": True,
    "azure_upload_mode": "individual",
    "azure_storage_account_name": "ksstorage",
    "azure_container_name": "game-assets",
    # Optional virtual folder inside the container
    "azure_blob_prefix": "tiles",
    "azure_zip_filename": "tiles_bundle.zip",

    # -----------------------------
    # TILE MANIFEST CONFIG
    # -----------------------------
    "write_tiles_manifest": True,
    "tiles_manifest_filename": "tiles.json",
    "tiles_manifest_version": 1,
    "tiles_manifest_generated_by": "kingdom-stack-blender",
    "tile_defaults": {
        "kind": "tile",
        "uiColor": "bg-gray-400",
        "properties": {}
    },
    "tile_metadata": {}
}

# -----------------------------
# AZURE HELPERS
# -----------------------------


def get_blob_service_client():
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient

    account_name = CONFIG["azure_storage_account_name"]
    account_url = f"https://{account_name}.blob.core.windows.net"
    credential = DefaultAzureCredential()
    return BlobServiceClient(account_url=account_url, credential=credential)


def ensure_blob_container(blob_service_client):
    container_name = CONFIG["azure_container_name"]
    container_client = blob_service_client.get_container_client(container_name)

    try:
        container_client.create_container()
        print(f"Created Azure container: {container_name}")
    except Exception:
        # Usually means it already exists
        pass

    return container_client


def upload_file_to_azure(container_client, local_file_path, blob_name):
    from azure.storage.blob import ContentSettings

    content_settings = None

    if local_file_path.lower().endswith(".png"):
        content_settings = ContentSettings(content_type="image/png")
    elif local_file_path.lower().endswith(".json"):
        content_settings = ContentSettings(content_type="application/json")
    elif local_file_path.lower().endswith(".zip"):
        content_settings = ContentSettings(content_type="application/zip")

    blob_client = container_client.get_blob_client(blob_name)

    with open(local_file_path, "rb") as data:
        blob_client.upload_blob(
            data,
            overwrite=True,
            content_settings=content_settings
        )

    print(f"Uploaded to Azure Blob: {blob_name}")


def build_blob_name(filename):
    prefix = CONFIG.get("azure_blob_prefix", "").strip("/")

    if prefix:
        return f"{prefix}/{filename}"
    return filename

# -----------------------------
# UTILITIES
# -----------------------------


def get_or_create_camera_light(cam_obj):
    light_obj = bpy.data.objects.get("KS_CameraLight")

    if light_obj is None:
        light_data = bpy.data.lights.new(name="KS_CameraLight", type="SUN")
        light_data.energy = 3.5
        light_data.angle = math.radians(6)

        light_obj = bpy.data.objects.new("KS_CameraLight", light_data)
        bpy.context.collection.objects.link(light_obj)

    light_obj.parent = cam_obj
    light_obj.matrix_parent_inverse = cam_obj.matrix_world.inverted()
    light_obj.location = Vector((0, 0, 0))
    light_obj.rotation_euler = (0, 0, 0)

    return light_obj


def apply_emissive_only_fallback(meshes):
    original_materials = {}
    hidden_lights = []

    for obj in meshes:
        original_materials[obj] = list(obj.data.materials)
        new_mats = []

        for mat in obj.data.materials:
            if not mat or not mat.use_nodes:
                continue

            src_nodes = mat.node_tree.nodes
            principled = next(
                (n for n in src_nodes if n.type == "BSDF_PRINCIPLED"), None)

            em_mat = bpy.data.materials.new(mat.name + "__EMISSIVE")
            em_mat.use_nodes = True
            nodes = em_mat.node_tree.nodes
            links = em_mat.node_tree.links
            nodes.clear()

            out = nodes.new("ShaderNodeOutputMaterial")
            em = nodes.new("ShaderNodeEmission")
            em.inputs["Strength"].default_value = CONFIG["emission_strength"]

            if principled:
                base_color_input = principled.inputs["Base Color"]
                if base_color_input.is_linked:
                    links.new(
                        base_color_input.links[0].from_socket, em.inputs["Color"])
                else:
                    em.inputs["Color"].default_value = base_color_input.default_value
            else:
                em.inputs["Color"].default_value = (1, 1, 1, 1)

            links.new(em.outputs["Emission"], out.inputs["Surface"])
            new_mats.append(em_mat)

        obj.data.materials.clear()
        for m in new_mats:
            obj.data.materials.append(m)

    for obj in bpy.data.objects:
        if obj.type == "LIGHT" and not obj.hide_render:
            obj.hide_render = True
            hidden_lights.append(obj)

    return original_materials, hidden_lights


def restore_after_emissive_fallback(original_materials, hidden_lights):
    for obj, mats in original_materials.items():
        if not obj or obj.type != "MESH":
            continue
        obj.data.materials.clear()
        for m in mats:
            obj.data.materials.append(m)

    for l in hidden_lights:
        l.hide_render = False


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def parse_cli_args(argv):
    args = {"config": None}

    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--config":
            if i + 1 >= len(argv):
                raise ValueError("Expected a path after --config")
            args["config"] = argv[i + 1]
            i += 2
            continue
        raise ValueError(f"Unknown argument: {arg}")

    return args


def load_config_file(config_path):
    with open(config_path, "r", encoding="utf-8") as f:
        loaded = json.load(f)

    if not isinstance(loaded, dict):
        raise ValueError("Config file must contain a JSON object")

    unknown_keys = sorted(set(loaded) - set(CONFIG))
    if unknown_keys:
        print(
            f"Warning: ignoring unknown config keys: {', '.join(unknown_keys)}")

    CONFIG.update({k: v for k, v in loaded.items() if k in CONFIG})
    print(f"Loaded config: {config_path}")


def merge_dicts(base, extra):
    merged = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def validate_required_tile_properties(tile_id, properties):
    missing = [
        key for key in ("biome", "type")
        if properties.get(key) in (None, "")
    ]
    if missing:
        raise ValueError(
            f"Tile '{tile_id}' is missing required properties: "
            f"{', '.join(missing)}"
        )


def build_tile_manifest_entry(tile_id, source_filename, rendered_images):
    tile_defaults = CONFIG.get("tile_defaults", {})
    tile_cfg = CONFIG.get("tile_metadata", {}).get(tile_id, {})

    kind = tile_cfg.get("kind", tile_defaults.get("kind", "tile"))
    ui_color = tile_cfg.get(
        "uiColor", tile_defaults.get("uiColor", "bg-gray-400"))

    properties = {
        "ks_asset_id": tile_id,
        "ks_kind": "tile_mesh",
        "ks_source_file": tile_id,
    }
    properties.update(tile_defaults.get("properties", {}))
    properties.update(tile_cfg.get("properties", {}))
    validate_required_tile_properties(tile_id, properties)

    entry = {
        "id": tile_id,
        "kind": kind,
        "images": rendered_images,
        "variants": list(rendered_images.keys()),
        "uiColor": ui_color,
        "properties": properties,
        "metadata": merge_dicts(
            {"sourceModel": source_filename},
            tile_cfg.get("metadata", {})
        ),
    }

    if "phaserColor" in tile_cfg:
        entry["phaserColor"] = tile_cfg["phaserColor"]
    elif "phaserColor" in tile_defaults:
        entry["phaserColor"] = tile_defaults["phaserColor"]

    return entry


def write_tiles_manifest(output_dir, tile_entries):
    manifest = {
        "version": CONFIG["tiles_manifest_version"],
        "generatedBy": CONFIG["tiles_manifest_generated_by"],
        "tiles": tile_entries,
    }

    manifest_path = os.path.join(output_dir, CONFIG["tiles_manifest_filename"])
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")

    print("Saved manifest:", manifest_path)
    return manifest_path


def create_zip_bundle(bundle_path, files_to_include):
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for local_path, archive_name in files_to_include:
            zf.write(local_path, arcname=archive_name)

    print("Saved zip bundle:", bundle_path)
    return bundle_path


def clear_scene_objects():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def compute_bounds_world(objects):
    min_v = Vector((float("inf"), float("inf"), float("inf")))
    max_v = Vector((float("-inf"), float("-inf"), float("-inf")))
    any_bb = False

    for obj in objects:
        if obj.type != "MESH":
            continue
        any_bb = True
        for corner in obj.bound_box:
            w = obj.matrix_world @ Vector(corner)
            min_v.x = min(min_v.x, w.x)
            min_v.y = min(min_v.y, w.y)
            min_v.z = min(min_v.z, w.z)
            max_v.x = max(max_v.x, w.x)
            max_v.y = max(max_v.y, w.y)
            max_v.z = max(max_v.z, w.z)

    if not any_bb:
        min_v, max_v = Vector((-1, -1, -1)), Vector((1, 1, 1))

    return min_v, max_v


def center_objects_at_origin(objects):
    min_v, max_v = compute_bounds_world(objects)
    center = (min_v + max_v) * 0.5
    for obj in objects:
        obj.location -= center


def normalize_scale(objects):
    min_v, max_v = compute_bounds_world(objects)
    size = max_v - min_v
    max_dim = max(size.x, size.y, size.z)
    if max_dim <= 1e-6:
        return
    s = 2.0 / max_dim
    for obj in objects:
        obj.scale *= s


def import_model(filepath: str):
    ext = os.path.splitext(filepath)[1].lower()
    before = set(bpy.data.objects)

    if ext == ".obj":
        bpy.ops.wm.obj_import(filepath=filepath)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=filepath)
    elif ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=filepath)
    elif ext == ".stl":
        bpy.ops.import_mesh.stl(filepath=filepath)
    elif ext == ".ply":
        bpy.ops.import_mesh.ply(filepath=filepath)
    elif ext == ".dae":
        bpy.ops.wm.collada_import(filepath=filepath)
    else:
        raise ValueError(f"Unsupported extension: {ext}")

    after = set(bpy.data.objects)
    imported = [o for o in (after - before)
                if o.type in {"MESH", "EMPTY", "CURVE", "ARMATURE"}]
    meshes = [o for o in imported if o.type == "MESH"]
    return meshes if meshes else imported


def get_or_create_camera():
    cam = next((o for o in bpy.data.objects if o.type == "CAMERA"), None)
    if cam is None:
        cam_data = bpy.data.cameras.new("KS_Camera")
        cam = bpy.data.objects.new("KS_Camera", cam_data)
        bpy.context.collection.objects.link(cam)

    bpy.context.scene.camera = cam
    cam.data.type = "ORTHO" if CONFIG["camera_ortho"] else "PERSP"
    return cam


def set_render_settings():
    scene = bpy.context.scene
    scene.render.engine = CONFIG["engine"]
    scene.render.resolution_x = CONFIG["resolution_x"]
    scene.render.resolution_y = CONFIG["resolution_y"]
    scene.render.resolution_percentage = CONFIG["resolution_percentage"]
    scene.render.film_transparent = CONFIG["transparent_background"]
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 15

    if scene.render.engine == "CYCLES":
        scene.cycles.samples = CONFIG["cycles_samples"]
        try:
            scene.cycles.use_denoising = CONFIG["cycles_denoise"]
        except Exception:
            pass

# -----------------------------
# CAMERA + VIEW FIT
# -----------------------------


def project_bounds_to_camera(cam_obj, objects):
    cam_inv = cam_obj.matrix_world.inverted()
    min_x = min_y = min_z = float("inf")
    max_x = max_y = float("-inf")

    for obj in objects:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            world = obj.matrix_world @ Vector(corner)
            cam_local = cam_inv @ world
            min_x = min(min_x, cam_local.x)
            max_x = max(max_x, cam_local.x)
            min_y = min(min_y, cam_local.y)
            max_y = max(max_y, cam_local.y)
            min_z = min(min_z, cam_local.z)

    return min_x, max_x, min_y, max_y, min_z


def ensure_fully_in_view(cam_obj, objects, safety=None):
    cam = cam_obj.data
    cam.clip_start, cam.clip_end = 0.001, 1000.0
    min_x, max_x, min_y, max_y, min_z = project_bounds_to_camera(
        cam_obj, objects)

    if safety is None:
        safety = CONFIG.get("camera_fit_safety", 1.05)

    half_w = max(abs(min_x), abs(max_x))
    half_h = max(abs(min_y), abs(max_y))
    needed = max(half_w, half_h) * 2.0 * safety * \
        CONFIG.get("camera_ortho_zoom", 1.0)

    if cam.type == "ORTHO":
        cam.ortho_scale = needed
        if min_z > -cam.clip_start:
            cam_obj.location += cam_obj.matrix_world.to_quaternion() @ Vector((0, 0, -needed * 0.5))


def create_camera_target(objects):
    min_v, max_v = compute_bounds_world(objects)
    center = (min_v + max_v) * 0.5
    empty = bpy.data.objects.new("KS_Target", None)
    empty.empty_display_type = "SPHERE"
    empty.location = center
    bpy.context.collection.objects.link(empty)
    return empty


def set_camera_view(cam_obj, view_name, objects):
    target = bpy.data.objects.get("KS_Target")
    if not target:
        target = create_camera_target(objects)

    cam_obj.constraints.clear()
    tr = cam_obj.constraints.new(type="TRACK_TO")
    tr.target = target
    tr.track_axis = "TRACK_NEGATIVE_Z"
    tr.up_axis = "UP_Y"

    dist = CONFIG["camera_distance"]
    tz = target.location.z

    if view_name == "front":
        cam_obj.location = Vector((0, -dist, tz))
    elif view_name == "back":
        cam_obj.location = Vector((0, dist, tz))
    elif view_name == "left":
        cam_obj.location = Vector((-dist, 0, tz))
    elif view_name == "right":
        cam_obj.location = Vector((dist, 0, tz))
    elif view_name == "top":
        cam_obj.location = Vector((0, 0, tz + dist))
    elif view_name == "bottom":
        cam_obj.location = Vector((0, 0, tz - dist))
    elif view_name == "iso":
        cam_obj.location = Vector((dist, -dist, tz + dist))
    else:
        raise ValueError(f"Unknown view: {view_name}")

# -----------------------------
# RENDER + SAVE
# -----------------------------


def render_to_path(filepath: str):
    bpy.context.scene.render.filepath = filepath
    bpy.ops.render.render(write_still=True)


def save_pixels_to_png(path, w, h, pixels):
    img = bpy.data.images.new("KS_Out", width=w, height=h, alpha=True)
    img.pixels = pixels
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


def disable_world_light():
    if bpy.context.scene.world:
        bpy.context.scene.world.use_nodes = True
        bg = bpy.context.scene.world.node_tree.nodes.get("Background")
        if bg:
            bg.inputs["Strength"].default_value = 0.0

    for obj in bpy.data.objects:
        if obj.type == "LIGHT":
            obj.hide_render = True

# -----------------------------
# RUN BATCH
# -----------------------------


def run():
    args = parse_cli_args(sys.argv)
    if args["config"]:
        load_config_file(args["config"])

    input_dir = CONFIG["input_dir"]
    output_dir = CONFIG["output_dir"]
    ensure_dir(output_dir)

    temp_dir = CONFIG["temp_dir"] or os.path.join(output_dir, "_temp")
    ensure_dir(temp_dir)

    set_render_settings()
    disable_world_light()

    container_client = None
    upload_mode = CONFIG.get("azure_upload_mode", "individual").lower()
    if CONFIG.get("upload_to_azure"):
        blob_service_client = get_blob_service_client()
        container_client = ensure_blob_container(blob_service_client)

    files = [
        os.path.join(input_dir, f)
        for f in os.listdir(input_dir)
        if os.path.splitext(f)[1].lower() in CONFIG["supported_exts"]
    ]
    files.sort()

    if not files:
        print("No files found.")
        return

    tile_entries = []
    bundle_files = []

    for fp in files:
        base = os.path.splitext(os.path.basename(fp))[0]
        source_filename = os.path.basename(fp)
        print(f"\n=== Processing: {base} ===")

        clear_scene_objects()

        cam = get_or_create_camera()
        get_or_create_camera_light(cam)

        meshes = import_model(fp)
        center_objects_at_origin(meshes)
        normalize_scale(meshes)

        create_camera_target(meshes)

        if container_client is not None:
            if upload_mode == "individual":
                source_blob_name = build_blob_name(source_filename)
                upload_file_to_azure(container_client, fp, source_blob_name)
            elif upload_mode == "zip":
                bundle_files.append((fp, source_filename))

        rendered_images = {}
        for view in CONFIG["views"]:
            set_camera_view(cam, view, meshes)
            bpy.context.view_layer.update()
            ensure_fully_in_view(cam, meshes)

            temp_path = os.path.join(temp_dir, f"{base}__{view}__temp.png")
            final_filename = f"{base}__{view}.png"
            final_path = os.path.join(output_dir, final_filename)

            fallback_state = None
            if CONFIG.get("force_emissive_only"):
                fallback_state = apply_emissive_only_fallback(meshes)

            render_to_path(temp_path)

            if fallback_state:
                restore_after_emissive_fallback(*fallback_state)

            os.replace(temp_path, final_path)
            print("Saved locally:", final_path)
            rendered_images[view] = final_filename

            if container_client is not None:
                if upload_mode == "individual":
                    blob_name = build_blob_name(final_filename)
                    upload_file_to_azure(container_client, final_path, blob_name)
                elif upload_mode == "zip":
                    bundle_files.append((final_path, final_filename))

        tile_entries.append(build_tile_manifest_entry(
            base, source_filename, rendered_images))

    manifest_path = None
    if CONFIG.get("write_tiles_manifest"):
        manifest_path = write_tiles_manifest(output_dir, tile_entries)
        if container_client is not None:
            if upload_mode == "individual":
                manifest_blob_name = build_blob_name(
                    os.path.basename(manifest_path))
                upload_file_to_azure(
                    container_client, manifest_path, manifest_blob_name)
            elif upload_mode == "zip":
                bundle_files.append(
                    (manifest_path, os.path.basename(manifest_path)))

    if container_client is not None and upload_mode == "zip":
        zip_filename = CONFIG["azure_zip_filename"]
        zip_path = os.path.join(output_dir, zip_filename)
        create_zip_bundle(zip_path, bundle_files)
        zip_blob_name = build_blob_name(zip_filename)
        upload_file_to_azure(container_client, zip_path, zip_blob_name)


# ============================================================
if __name__ == "__main__":
    run()
