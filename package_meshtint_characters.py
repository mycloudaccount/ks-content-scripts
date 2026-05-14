import json
import io
import os
import re
import shutil
import subprocess
import sys
import zipfile
from PIL import Image


CONFIG = {
    "input_zip": r"C:\Users\pilgr\Downloads\Modular Fantasy Characters Mega Toon Series.zip",
    "output_dir": r"C:\myapps\temp\meshtint-characters",
    "archive_root": "Modular Fantasy Characters Mega Toon Series",
    "asset_root": "meshtint-characters",
    "source_name": "Modular Fantasy Characters Mega Toon Series",
    "write_manifest": True,
    "manifest_filename": "manifest.json",
    "catalog_zip_filename": "meshtint-characters-catalog.zip",
    "archive_zip_filename": "meshtint-characters-source.zip",
    "input_zip_blob_name": None,
    "prefer_input_zip_from_azure": True,
    "downloaded_input_zip_filename": "meshtint-characters-source.zip",
    "upload_to_azure": True,
    "azure_storage_account_name": "ksstorage",
    "azure_container_name": "game-assets",
    "catalog_blob_prefix": "character-source-packs/meshtint-characters",
    "asset_blob_prefix": "character-source-packs/meshtint-characters",
    "include_uv_reference_images": False,
    "include_psd_sources": False,
    "include_psd_preview_sources": True,
    "include_unity_package": False,
    "include_tutorials": False,
    "upload_individual_files": True,
    "upload_manifest": True,
    "upload_catalog_zip": True,
    "upload_archive_zip": True,
    "render_previews": True,
    "upload_previews": True,
    "export_runtime_glb": True,
    "upload_runtime_glb": True,
    "runtime_export_categories": ["body", "face", "crown", "hat", "headdress", "helmet", "hood", "shoulder"],
    "runtime_merge_animation_categories": ["body"],
    "runtime_default_face_by_body": {
        "Character 01": "Face Female 04",
        "Character 02": "Face Female 04",
        "Character 03": "Face Female 04",
    },
    "preferred_runtime_motion_mode": "in-place",
    "preview_resolution": 256,
    "preview_render_engine": "BLENDER_EEVEE",
    "preview_samples": 32,
    "preview_default_texture": "assets/textures/costumes/f-cos-01-purple.png",
    "preview_category_materials": {
        "armor": "#b8bccf",
        "beard": "#5f463a",
        "belt": "#6b4f3e",
        "bracer": "#7b6b5a",
        "cape": "#7d3f4f",
        "earrings": "#d6c27a",
        "hair": "#5d463b",
        "crown": "#c8b5d8",
        "hat": "#9aa0c9",
        "headdress": "#b7a6d8",
        "helmet": "#8f96bc",
        "hood": "#7f88b0",
        "mask": "#8f8fb3",
        "quiver": "#6f5645",
        "shoulder": "#aaaec8",
        "vest": "#8c6b55",
        "weapon": "#b9bdc9",
    },
    "blender_executable": r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe",
    "skip_existing_previews": True,
    "dry_run": False,
    "focus_categories": None,
}


CONTENT_TYPES = {
    ".fbx": "application/octet-stream",
    ".glb": "model/gltf-binary",
    ".json": "application/json",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".zip": "application/zip",
}


FBX_CATEGORY_PATTERNS = [
    ("face", re.compile(r"^Face (Female|Male) (\d+)$", re.IGNORECASE)),
    ("hair", re.compile(r"^Hair (Female|Male)(?: For Hat)? (\d+)$", re.IGNORECASE)),
    ("body", re.compile(r"^Character (\d+)$", re.IGNORECASE)),
    ("armor", re.compile(r"^Armor (\d+)$", re.IGNORECASE)),
    ("cape", re.compile(r"^Cape (\d+)$", re.IGNORECASE)),
    ("quiver", re.compile(r"^Quiver (\d+)$", re.IGNORECASE)),
    ("vest", re.compile(r"^Vest (\d+)$", re.IGNORECASE)),
    ("beard", re.compile(r"^Beard (\d+)$", re.IGNORECASE)),
    ("earrings", re.compile(r"^Earrings (\d+)$", re.IGNORECASE)),
    ("crown", re.compile(r"^Crown (\d+)$", re.IGNORECASE)),
    ("hat", re.compile(r"^Hat (\d+)$", re.IGNORECASE)),
    ("headdress", re.compile(r"^Headdress (\d+)$", re.IGNORECASE)),
    ("helmet", re.compile(r"^Helmet (\d+)$", re.IGNORECASE)),
    ("hood", re.compile(r"^Hood (\d+)$", re.IGNORECASE)),
    ("mask", re.compile(r"^(Mask|Ninja Mask) (\d+)$", re.IGNORECASE)),
    ("belt", re.compile(r"^Belt (\d+)$", re.IGNORECASE)),
    ("bracer", re.compile(r"^Bracer (\d+)$", re.IGNORECASE)),
    ("shoulder", re.compile(r"^Shoulder (\d+)$", re.IGNORECASE)),
    ("weapon", re.compile(r"^(Arrow|Axe|Bow|Scythe|Shield|Shuriken|Sling|Spellbook|Sword|Wand) (\d+)$", re.IGNORECASE)),
]


CATEGORY_FOLDERS = {
    "animation": "animations",
    "armor": "armor",
    "beard": "beards",
    "belt": "belts",
    "body": "bodies",
    "bracer": "bracers",
    "cape": "capes",
    "costume": "costumes",
    "earrings": "earrings",
    "face": "faces",
    "hair": "hairs",
    "crown": "headwear",
    "hat": "headwear",
    "headdress": "headwear",
    "helmet": "headwear",
    "hood": "headwear",
    "mask": "masks",
    "prop": "props",
    "quiver": "quivers",
    "reference": "references",
    "shoulder": "shoulders",
    "vest": "vests",
    "weapon": "weapons",
}

HEADGEAR_CATEGORIES = {"crown", "hat", "headdress", "helmet", "hood"}
SHOULDER_ATTACHMENT_CATEGORIES = {"shoulder"}
BODY_DEPENDENCY_CATEGORIES = (
    {"animation", "costume", "face", "hair"}
    | HEADGEAR_CATEGORIES
    | SHOULDER_ATTACHMENT_CATEGORIES
)
CATEGORY_FILTER_ALIASES = {
    "headwear": sorted(HEADGEAR_CATEGORIES),
    "shoulders": ["shoulder"],
    "textures": ["costume"],
    "animations": ["animation"],
}


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def build_blender_temp_dir(base_dir):
    return os.path.join(base_dir, "_blender-temp")


def build_blender_process_env(base_dir):
    temp_dir = build_blender_temp_dir(base_dir)
    ensure_dir(temp_dir)
    env = os.environ.copy()
    env["TMP"] = temp_dir
    env["TEMP"] = temp_dir
    return env


def configure_process_temp_environment(base_dir):
    temp_dir = build_blender_temp_dir(base_dir)
    ensure_dir(temp_dir)
    os.environ["TMP"] = temp_dir
    os.environ["TEMP"] = temp_dir
    try:
        import tempfile

        tempfile.tempdir = temp_dir
    except Exception:
        pass
    return temp_dir


def parse_cli_args(argv):
    args = {"config": None, "render_job": None, "runtime_job": None, "categories": None}

    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = argv[1:]

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--config":
            if i + 1 >= len(argv):
                raise ValueError("Expected a path after --config")
            args["config"] = argv[i + 1]
            i += 2
            continue
        if arg == "--render-preview-job":
            if i + 1 >= len(argv):
                raise ValueError("Expected a path after --render-preview-job")
            args["render_job"] = argv[i + 1]
            i += 2
            continue
        if arg == "--export-runtime-job":
            if i + 1 >= len(argv):
                raise ValueError("Expected a path after --export-runtime-job")
            args["runtime_job"] = argv[i + 1]
            i += 2
            continue
        if arg == "--dry-run":
            CONFIG["dry_run"] = True
            i += 1
            continue
        if arg == "--no-upload":
            CONFIG["upload_to_azure"] = False
            i += 1
            continue
        if arg == "--no-previews":
            CONFIG["render_previews"] = False
            i += 1
            continue
        if arg == "--input-zip":
            if i + 1 >= len(argv):
                raise ValueError("Expected a path after --input-zip")
            CONFIG["input_zip"] = argv[i + 1]
            i += 2
            continue
        if arg == "--input-zip-blob":
            if i + 1 >= len(argv):
                raise ValueError("Expected a blob path after --input-zip-blob")
            CONFIG["input_zip_blob_name"] = argv[i + 1]
            i += 2
            continue
        if arg == "--prefer-input-zip-from-azure":
            CONFIG["prefer_input_zip_from_azure"] = True
            i += 1
            continue
        if arg == "--prefer-input-zip-local":
            CONFIG["prefer_input_zip_from_azure"] = False
            i += 1
            continue
        if arg == "--categories":
            if i + 1 >= len(argv):
                raise ValueError("Expected a comma-separated list after --categories")
            args["categories"] = argv[i + 1]
            i += 2
            continue
        raise ValueError(f"Unknown argument: {arg}")

    return args


def load_config_file(config_path):
    with open(config_path, "r", encoding="utf-8") as handle:
        loaded = json.load(handle)

    if not isinstance(loaded, dict):
        raise ValueError("Config file must contain a JSON object")

    unknown_keys = sorted(set(loaded) - set(CONFIG))
    if unknown_keys:
        print(f"Warning: ignoring unknown config keys: {', '.join(unknown_keys)}")

    CONFIG.update({key: value for key, value in loaded.items() if key in CONFIG})
    print(f"Loaded config: {config_path}")


def parse_focus_categories(raw_value):
    if raw_value is None:
        return None

    tokens = []
    for piece in str(raw_value).split(","):
        token = piece.strip().lower()
        if not token or token == "all":
            continue
        expanded = CATEGORY_FILTER_ALIASES.get(token)
        if expanded:
            tokens.extend(expanded)
        else:
            tokens.append(token)

    normalized = []
    seen = set()
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized or None


def entry_matches_focus_categories(descriptor, focus_categories):
    if not focus_categories:
        return True
    descriptor_category = (descriptor.get("category") or "").strip().lower()
    return descriptor_category in set(focus_categories)


def expand_focus_categories(focus_categories):
    if not focus_categories:
        return None

    expanded = set(focus_categories)
    requested = set(focus_categories)

    # A body runtime export is dependency-rich in this pipeline: the full publish
    # merges in animations, default faces, matching hairs, and optional runtime
    # attachments. Category mode needs to keep those inputs so the Azure result
    # matches a full run for the selected body slice.
    if "body" in requested:
        expanded.update(BODY_DEPENDENCY_CATEGORIES)

    return sorted(expanded)


def filter_entries_by_focus_categories(entries, focus_categories):
    if not focus_categories:
        return entries

    expanded_focus_categories = expand_focus_categories(focus_categories)
    if expanded_focus_categories != focus_categories:
        print(
            "Expanded category filter for dependencies: "
            + ", ".join(focus_categories)
            + " -> "
            + ", ".join(expanded_focus_categories)
        )

    filtered_entries = [
        (zip_entry, descriptor)
        for zip_entry, descriptor in entries
        if entry_matches_focus_categories(descriptor, expanded_focus_categories)
    ]
    print(
        "Filtering categories: "
        + ", ".join(expanded_focus_categories)
        + f" ({len(filtered_entries)} of {len(entries)} entries kept)"
    )
    return filtered_entries

def normalize_rel_path(path):
    return path.replace("\\", "/").strip("/")


def slugify_token(value):
    token = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return token or "asset"


def slugify_file_stem(value):
    token = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return token or "asset"


def build_safe_filename(stem, ext):
    normalized_ext = ext.lower()
    if normalized_ext == ".fbx":
        normalized_ext = ".fbx"
    return f"{slugify_file_stem(stem)}{normalized_ext}"


def infer_face_family_token(name):
    normalized_name = (name or "").strip().lower()
    if "face female" in normalized_name:
        return "female"
    if "face male" in normalized_name:
        return "male"
    return None


def infer_hair_family_token(name):
    normalized_name = (name or "").strip().lower()
    if "hair female" in normalized_name:
        return "female"
    if "hair male" in normalized_name:
        return "male"
    return None


def strip_archive_root(path):
    path = normalize_rel_path(path)
    archive_root = CONFIG["archive_root"].strip("/")
    prefix = f"{archive_root}/"
    if path.startswith(prefix):
        return path[len(prefix):]
    return path


def build_asset_blob_name(relative_path):
    prefix = CONFIG.get("asset_blob_prefix", "").strip("/")
    relative_path = normalize_rel_path(relative_path)
    return f"{prefix}/{relative_path}" if prefix else relative_path


def build_catalog_blob_name(relative_path):
    prefix = CONFIG.get("catalog_blob_prefix", "").strip("/")
    relative_path = normalize_rel_path(relative_path)
    return f"{prefix}/{relative_path}" if prefix else relative_path


def build_character_asset_api_path(relative_path):
    blob_name = build_asset_blob_name(relative_path)
    source_pack_prefix = "character-source-packs/"
    if blob_name.startswith(source_pack_prefix):
        return f"/api/assets/character-source-packs/{blob_name[len(source_pack_prefix):]}"
    return f"/api/assets/character-source-packs/{blob_name}"


def build_source_archive_blob_name():
    return build_asset_blob_name(f"archives/{CONFIG['archive_zip_filename']}")


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
        pass

    return container_client


def upload_bytes_to_azure(container_client, data, blob_name, source_name):
    from azure.storage.blob import ContentSettings

    ext = os.path.splitext(blob_name)[1].lower()
    content_type = CONTENT_TYPES.get(ext)
    content_settings = ContentSettings(content_type=content_type) if content_type else None

    blob_client = container_client.get_blob_client(blob_name)
    blob_client.upload_blob(
        data,
        overwrite=True,
        content_settings=content_settings,
    )
    print(f"Uploaded: {source_name} -> {blob_name}")


def upload_file_to_azure(container_client, local_file_path, blob_name):
    with open(local_file_path, "rb") as handle:
        upload_bytes_to_azure(container_client, handle, blob_name, local_file_path)


def download_file_from_azure(container_client, blob_name, local_file_path):
    ensure_dir(os.path.dirname(local_file_path))
    blob_client = container_client.get_blob_client(blob_name)
    with open(local_file_path, "wb") as handle:
        download_stream = blob_client.download_blob()
        handle.write(download_stream.readall())
    print(f"Downloaded: {blob_name} -> {local_file_path}")
    return local_file_path


def resolve_input_zip_path():
    local_input_zip = CONFIG["input_zip"]
    prefer_azure = bool(CONFIG.get("prefer_input_zip_from_azure"))
    blob_name = CONFIG.get("input_zip_blob_name") or build_source_archive_blob_name()
    download_filename = CONFIG.get("downloaded_input_zip_filename") or os.path.basename(blob_name)
    downloaded_input_zip = os.path.join(CONFIG["output_dir"], "_downloads", download_filename)

    def download_from_azure():
        blob_service_client = get_blob_service_client()
        container_client = ensure_blob_container(blob_service_client)
        return download_file_from_azure(container_client, blob_name, downloaded_input_zip)

    if prefer_azure:
        try:
            return download_from_azure()
        except Exception as error:
            if os.path.isfile(local_input_zip):
                print(
                    f"Azure source ZIP download failed for {blob_name}; "
                    f"falling back to local file {local_input_zip}: {error}"
                )
                return local_input_zip
            raise FileNotFoundError(
                f"Unable to download source ZIP from Azure blob {blob_name}, "
                f"and local input ZIP does not exist: {local_input_zip}"
            ) from error

    if os.path.isfile(local_input_zip):
        return local_input_zip

    try:
        return download_from_azure()
    except Exception as error:
        raise FileNotFoundError(
            f"Input zip does not exist locally ({local_input_zip}) and Azure "
            f"source ZIP download failed for blob {blob_name}"
        ) from error


def is_supported_entry(zip_entry):
    if zip_entry.is_dir():
        return False

    relative_path = strip_archive_root(zip_entry.filename)
    parts = relative_path.split("/")
    if len(parts) < 2:
        return False

    folder = parts[0].lower()
    ext = os.path.splitext(zip_entry.filename)[1].lower()

    if folder in {"fbx", "animations"}:
        return ext == ".fbx"

    if folder == "textures":
        if ext == ".png":
            return True
        if ext in {".jpg", ".jpeg"}:
            return bool(CONFIG.get("include_uv_reference_images"))
        if ext == ".psd":
            return bool(CONFIG.get("include_psd_sources"))
        return False

    if folder == "unity package":
        return bool(CONFIG.get("include_unity_package"))

    if folder == "tutorials":
        return bool(CONFIG.get("include_tutorials"))

    return False


def classify_fbx(stem):
    for category, pattern in FBX_CATEGORY_PATTERNS:
        match = pattern.match(stem)
        if not match:
            continue

        result = {"category": category}
        groups = match.groups()
        if groups and groups[0].lower() in {"female", "male"}:
            result["gender"] = groups[0].lower()
        if "for hat" in stem.lower():
            result["forHat"] = True
        if category == "weapon":
            result["weaponType"] = groups[0].lower()
        return result

    return {"category": "prop"}


def parse_texture_name(stem):
    match = re.match(r"^([FM])-Cos-(\d+)-(.+)$", stem, re.IGNORECASE)
    if not match:
        return {}

    gender_token, costume_number, color = match.groups()
    return {
        "gender": "female" if gender_token.upper() == "F" else "male",
        "costumeId": f"cos_{int(costume_number):02d}",
        "color": color.lower(),
    }


def parse_hair_texture_name(stem):
    match = re.match(r"^Hair (Black|Blonde|Brown|Grey|Orange)$", stem, re.IGNORECASE)
    if not match:
        return {}

    return {
        "category": "hair",
        "color": match.group(1).lower(),
    }


def category_folder(category):
    return CATEGORY_FOLDERS.get(category, slugify_token(category))


def get_entry_descriptor(zip_entry):
    source_path = strip_archive_root(zip_entry.filename)
    source_folder = source_path.split("/")[0].lower()
    filename = os.path.basename(source_path)
    stem, ext = os.path.splitext(filename)
    ext = ext.lower()
    safe_filename = build_safe_filename(stem, ext)
    safe_preview_filename = f"{slugify_file_stem(stem)}.png"

    if source_folder == "animations":
        kind = "animation"
        category = "animation"
        metadata = parse_animation_metadata(stem)
    elif ext == ".fbx":
        kind = "model"
        classification = classify_fbx(stem)
        category = classification.pop("category")
        metadata = classification
    else:
        kind = "texture"
        metadata = parse_texture_name(stem)
        category = "costume" if re.match(r"^[FM]-Cos-", stem, re.IGNORECASE) else "reference"
        metadata["format"] = ext.lstrip(".")

    folder = category_folder(category)
    if kind == "texture":
        public_path = normalize_rel_path(f"assets/textures/{folder}/{safe_filename}")
        preview_path = normalize_rel_path(f"previews/textures/{folder}/{safe_preview_filename}")
    elif kind == "animation":
        public_path = normalize_rel_path(f"assets/animations/{safe_filename}")
        preview_path = normalize_rel_path(f"previews/animations/{safe_preview_filename}")
    else:
        public_path = normalize_rel_path(f"assets/{folder}/{safe_filename}")
        preview_path = normalize_rel_path(f"previews/{folder}/{safe_preview_filename}")

    return {
        "id": slugify_token(stem),
        "name": stem,
        "kind": kind,
        "category": category,
        "path": public_path,
        "assetPath": public_path,
        "assetBlobPath": build_asset_blob_name(public_path),
        "assetUrlPath": build_character_asset_api_path(public_path),
        "blobPath": build_asset_blob_name(public_path),
        "previewPath": preview_path,
        "previewBlobPath": build_asset_blob_name(preview_path),
        "previewUrlPath": build_character_asset_api_path(preview_path),
        "sourcePath": source_path,
        "sourceFileName": filename,
        "sizeBytes": zip_entry.file_size,
        **metadata,
    }


def get_generated_hair_texture_descriptor(zip_entry):
    source_path = strip_archive_root(zip_entry.filename)
    filename = os.path.basename(source_path)
    stem, _ = os.path.splitext(filename)
    metadata = parse_hair_texture_name(stem)
    if not metadata:
        return None

    safe_filename = f"{slugify_file_stem(stem)}.png"
    public_path = normalize_rel_path(f"assets/textures/hair/{safe_filename}")
    preview_path = normalize_rel_path(f"previews/textures/hair/{safe_filename}")

    return {
        "id": slugify_token(stem),
        "name": stem,
        "kind": "texture",
        "category": metadata["category"],
        "path": public_path,
        "assetPath": public_path,
        "assetBlobPath": build_asset_blob_name(public_path),
        "assetUrlPath": build_character_asset_api_path(public_path),
        "blobPath": build_asset_blob_name(public_path),
        "previewPath": preview_path,
        "previewBlobPath": build_asset_blob_name(preview_path),
        "previewUrlPath": build_character_asset_api_path(preview_path),
        "sourcePath": source_path,
        "sourceFileName": filename,
        "sizeBytes": zip_entry.file_size,
        "generatedFromArchivePath": zip_entry.filename,
        "generatedFromFormat": "psd",
        "format": "png",
        "color": metadata["color"],
    }


def parse_animation_metadata(stem):
    normalized_stem = slugify_file_stem(stem)
    lower_stem = normalized_stem.lower()

    if lower_stem.endswith("-in-place"):
        motion_mode = "in-place"
        base_name = lower_stem[: -len("-in-place")]
    elif lower_stem.endswith("-w-root"):
        motion_mode = "root-motion"
        base_name = lower_stem[: -len("-w-root")]
    else:
        motion_mode = "stationary"
        base_name = lower_stem

    if base_name.startswith("character-"):
        base_name = base_name[len("character-"):]

    display_name = stem.replace("Character@", "")
    gameplay_usable = motion_mode != "root-motion"

    return {
        "animationName": display_name,
        "runtimeClipName": normalized_stem,
        "animationKey": base_name,
        "motionMode": motion_mode,
        "preferredForGameplay": gameplay_usable,
    }


def should_export_runtime_glb(descriptor):
    return (
        CONFIG.get("export_runtime_glb", False)
        and descriptor["kind"] == "model"
        and descriptor["category"] in set(CONFIG.get("runtime_export_categories", []))
    )


def collect_entries(zip_file):
    entries = []
    for zip_entry in zip_file.infolist():
        if not is_supported_entry(zip_entry):
            continue
        descriptor = get_entry_descriptor(zip_entry)
        if should_export_runtime_glb(descriptor):
            runtime_path = normalize_rel_path(
                f"runtime/{category_folder(descriptor['category'])}/{slugify_file_stem(descriptor['name'])}.glb"
            )
            descriptor["runtimePath"] = runtime_path
            descriptor["runtimeBlobPath"] = build_asset_blob_name(runtime_path)
            descriptor["runtimeUrlPath"] = build_character_asset_api_path(runtime_path)
        entries.append((zip_entry, descriptor))

    for zip_entry in zip_file.infolist():
        if zip_entry.is_dir():
            continue
        generated_descriptor = get_generated_hair_texture_descriptor(zip_entry)
        if generated_descriptor:
            entries.append((zip_entry, generated_descriptor))

    entries.sort(key=lambda item: item[1]["path"])
    return entries


def write_manifest(output_dir, manifest):
    ensure_dir(output_dir)
    manifest_path = os.path.join(output_dir, CONFIG["manifest_filename"])
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")

    print(f"Saved manifest: {manifest_path}")
    return manifest_path


def write_json(path, payload):
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    return path


def extract_zip_entries(zip_file, entries, extract_root):
    for zip_entry, descriptor in entries:
        local_path = os.path.join(extract_root, *descriptor["path"].split("/"))
        ensure_dir(os.path.dirname(local_path))
        generated_from_archive_path = descriptor.get("generatedFromArchivePath")
        if generated_from_archive_path:
            with zip_file.open(generated_from_archive_path, "r") as source:
                image = Image.open(io.BytesIO(source.read())).convert("RGBA")
                image.save(local_path, format="PNG")
        else:
            with zip_file.open(zip_entry, "r") as source, open(local_path, "wb") as target:
                shutil.copyfileobj(source, target)
        descriptor["localPath"] = local_path


def copy_texture_previews(entries, extract_root):
    for _, descriptor in entries:
        if descriptor["kind"] != "texture":
            continue
        source_path = os.path.join(extract_root, *descriptor["path"].split("/"))
        preview_path = os.path.join(extract_root, *descriptor["previewPath"].split("/"))
        ensure_dir(os.path.dirname(preview_path))
        shutil.copyfile(source_path, preview_path)
        descriptor["previewLocalPath"] = preview_path


def prepare_blender_texture_search(entries, extract_root, include_psd_preview_sources=True):
    texture_search_root = os.path.join(extract_root, "_blender-texture-search")
    if os.path.isdir(texture_search_root):
        shutil.rmtree(texture_search_root)
    ensure_dir(texture_search_root)

    for _, descriptor in entries:
        if descriptor["kind"] != "texture":
            continue

        source_path = os.path.join(extract_root, *descriptor["path"].split("/"))
        if not os.path.isfile(source_path):
            continue

        safe_copy_path = os.path.join(texture_search_root, os.path.basename(descriptor["path"]))
        shutil.copyfile(source_path, safe_copy_path)

        source_file_name = descriptor.get("sourceFileName")
        if source_file_name:
            original_copy_path = os.path.join(texture_search_root, source_file_name)
            if original_copy_path != safe_copy_path:
                shutil.copyfile(source_path, original_copy_path)

    if include_psd_preview_sources:
        copy_preview_only_texture_sources(texture_search_root)
    return texture_search_root


def copy_preview_only_texture_sources(texture_search_root):
    if not CONFIG.get("include_psd_preview_sources", True):
        return

    input_zip = CONFIG["input_zip"]
    if not os.path.isfile(input_zip):
        return

    with zipfile.ZipFile(input_zip, "r") as zip_file:
        copied = 0
        for zip_entry in zip_file.infolist():
            if zip_entry.is_dir():
                continue

            source_path = strip_archive_root(zip_entry.filename)
            parts = source_path.split("/")
            if len(parts) < 2 or parts[0].lower() != "textures":
                continue

            ext = os.path.splitext(source_path)[1].lower()
            if ext != ".psd":
                continue

            target_path = os.path.join(texture_search_root, os.path.basename(source_path))
            with zip_file.open(zip_entry, "r") as source, open(target_path, "wb") as target:
                shutil.copyfileobj(source, target)
            copied += 1

        if copied:
            print(f"Copied {copied} PSD preview source(s) into Blender texture search.")


def find_blender_executable():
    configured = CONFIG.get("blender_executable")
    if configured and os.path.isfile(configured):
        return configured

    discovered = shutil.which("blender")
    if discovered:
        return discovered

    return None


def render_previews(entries, extract_root):
    jobs = []
    texture_search_root = prepare_blender_texture_search(entries, extract_root)
    default_texture = CONFIG.get("preview_default_texture")
    default_texture_path = (
        os.path.join(extract_root, *normalize_rel_path(default_texture).split("/"))
        if default_texture
        else None
    )
    for _, descriptor in entries:
        if descriptor["kind"] == "texture":
            continue

        preview_path = os.path.join(extract_root, *descriptor["previewPath"].split("/"))
        if CONFIG.get("skip_existing_previews") and os.path.isfile(preview_path):
            descriptor["previewLocalPath"] = preview_path
            continue

        jobs.append({
            "id": descriptor["id"],
            "kind": descriptor["kind"],
            "category": descriptor["category"],
            "inputPath": descriptor["localPath"],
            "outputPath": preview_path,
            "textureSearchRoot": texture_search_root,
            "defaultTexturePath": default_texture_path,
        })
        descriptor["previewLocalPath"] = preview_path

    if not jobs:
        print("No Blender preview jobs needed.")
        return

    blender_executable = find_blender_executable()
    if not blender_executable:
        raise FileNotFoundError(
            "Blender executable was not found. Set blender_executable in config or add blender to PATH."
        )

    job_file = write_json(
        os.path.join(CONFIG["output_dir"], "preview-render-jobs.json"),
        {
            "resolution": int(CONFIG["preview_resolution"]),
            "engine": CONFIG["preview_render_engine"],
            "samples": int(CONFIG["preview_samples"]),
            "jobs": jobs,
        },
    )

    command = [
        blender_executable,
        "-b",
        "--python",
        os.path.abspath(__file__),
        "--",
        "--render-preview-job",
        job_file,
    ]
    print(f"Rendering {len(jobs)} preview(s) with Blender.")
    subprocess.run(
        command,
        check=True,
        env=build_blender_process_env(CONFIG["output_dir"]),
    )


def export_runtime_glbs(entries, extract_root):
    jobs = []
    texture_search_root = prepare_blender_texture_search(
        entries,
        extract_root,
        include_psd_preview_sources=True,
    )
    runtime_output_by_name = {}
    source_input_by_name = {}
    face_descriptors_by_family = {}
    hair_descriptors_by_family = {}
    headwear_descriptors = []
    shoulder_descriptors = []

    for _, descriptor in entries:
        if descriptor.get("localPath"):
            source_input_by_name[descriptor["name"]] = descriptor["localPath"]
        if descriptor.get("category") == "face":
            family = infer_face_family_token(descriptor.get("name"))
            if family:
                face_descriptors_by_family.setdefault(family, []).append(descriptor)
        if descriptor.get("category") == "hair":
            family = infer_hair_family_token(descriptor.get("name"))
            if family:
                hair_descriptors_by_family.setdefault(family, []).append(descriptor)
        if descriptor.get("category") in HEADGEAR_CATEGORIES:
            headwear_descriptors.append(descriptor)
        if descriptor.get("category") in SHOULDER_ATTACHMENT_CATEGORIES:
            shoulder_descriptors.append(descriptor)
        runtime_path = descriptor.get("runtimePath")
        if not runtime_path:
            continue
        runtime_output_by_name[descriptor["name"]] = os.path.join(
            extract_root,
            *runtime_path.split("/"),
        )

    animation_input_paths = [
        descriptor["localPath"]
        for _, descriptor in entries
        if descriptor.get("kind") == "animation" and descriptor.get("localPath")
    ]
    runtime_merge_categories = set(CONFIG.get("runtime_merge_animation_categories", []))
    runtime_default_face_by_body = CONFIG.get("runtime_default_face_by_body", {})

    for _, descriptor in entries:
        runtime_path = descriptor.get("runtimePath")
        if not runtime_path:
            continue

        output_path = os.path.join(extract_root, *runtime_path.split("/"))
        jobs.append({
            "id": descriptor["id"],
            "kind": descriptor["kind"],
            "category": descriptor["category"],
            "inputPath": descriptor["localPath"],
            "outputPath": output_path,
            "textureSearchRoot": texture_search_root,
        })
        if descriptor["category"] in runtime_merge_categories:
            jobs[-1]["animationInputPaths"] = animation_input_paths
        default_face_name = runtime_default_face_by_body.get(descriptor["name"])
        if descriptor["category"] == "body" and default_face_name:
            default_face_family = infer_face_family_token(default_face_name)
            face_descriptors = face_descriptors_by_family.get(default_face_family, [])
            attached_face_descriptors = []
            for face_descriptor in face_descriptors:
                attached_face_descriptors.append({
                    "name": face_descriptor["name"],
                    "runtimeInputPath": runtime_output_by_name.get(face_descriptor["name"]),
                    "sourceInputPath": source_input_by_name.get(face_descriptor["name"]),
                })
            if attached_face_descriptors:
                jobs[-1]["attachedFaceDescriptors"] = attached_face_descriptors
                jobs[-1]["defaultFaceName"] = default_face_name
            hair_descriptors = hair_descriptors_by_family.get(default_face_family, [])
            attached_hair_descriptors = []
            for hair_descriptor in hair_descriptors:
                attached_hair_descriptors.append({
                    "name": hair_descriptor["name"],
                    "sourceInputPath": source_input_by_name.get(hair_descriptor["name"]),
                })
            if attached_hair_descriptors:
                jobs[-1]["attachedHairDescriptors"] = attached_hair_descriptors
            attached_headwear_descriptors = []
            for headwear_descriptor in headwear_descriptors:
                attached_headwear_descriptors.append({
                    "name": headwear_descriptor["name"],
                    "category": headwear_descriptor["category"],
                    "runtimeInputPath": runtime_output_by_name.get(headwear_descriptor["name"]),
                    "sourceInputPath": source_input_by_name.get(headwear_descriptor["name"]),
                })
            if attached_headwear_descriptors:
                jobs[-1]["attachedHeadwearDescriptors"] = attached_headwear_descriptors
            attached_shoulder_descriptors = []
            for shoulder_descriptor in shoulder_descriptors:
                attached_shoulder_descriptors.append({
                    "name": shoulder_descriptor["name"],
                    "category": shoulder_descriptor["category"],
                    "runtimeInputPath": runtime_output_by_name.get(shoulder_descriptor["name"]),
                    "sourceInputPath": source_input_by_name.get(shoulder_descriptor["name"]),
                })
            if attached_shoulder_descriptors:
                jobs[-1]["attachedShoulderDescriptors"] = attached_shoulder_descriptors
        descriptor["runtimeLocalPath"] = output_path

    if not jobs:
        print("No Blender runtime GLB jobs needed.")
        return

    blender_executable = find_blender_executable()
    if not blender_executable:
        raise FileNotFoundError(
            "Blender executable was not found. Set blender_executable in config or add blender to PATH."
        )

    job_file = write_json(
        os.path.join(CONFIG["output_dir"], "runtime-export-jobs.json"),
        {
            "jobs": jobs,
        },
    )

    command = [
        blender_executable,
        "-b",
        "--python",
        os.path.abspath(__file__),
        "--",
        "--export-runtime-job",
        job_file,
    ]
    print(f"Exporting {len(jobs)} runtime GLB(s) with Blender.")
    subprocess.run(
        command,
        check=True,
        env=build_blender_process_env(CONFIG["output_dir"]),
    )


def build_manifest(entries):
    models = []
    animations = []
    textures = []

    for _, descriptor in entries:
        manifest_entry = {
            key: value
            for key, value in descriptor.items()
            if key not in {"localPath", "previewLocalPath", "runtimeLocalPath"}
        }
        if manifest_entry["kind"] == "model":
            models.append(manifest_entry)
        elif manifest_entry["kind"] == "animation":
            animations.append(manifest_entry)
        elif manifest_entry["kind"] == "texture":
            textures.append(manifest_entry)

    models.sort(key=lambda item: (item["category"], item["id"]))
    animations.sort(key=lambda item: item["id"])
    textures.sort(key=lambda item: (item["category"], item["id"]))
    runtime_animation_catalog = build_runtime_animation_catalog(animations)

    catalog_zip_path = build_catalog_blob_name(CONFIG["catalog_zip_filename"])
    manifest_blob_path = build_catalog_blob_name(CONFIG["manifest_filename"])
    archive_blob_path = build_source_archive_blob_name()

    return {
        "id": CONFIG["asset_root"],
        "name": "Meshtint Characters",
        "source": CONFIG["source_name"],
        "assetRoot": CONFIG["asset_blob_prefix"].strip("/"),
        "catalogRoot": CONFIG["catalog_blob_prefix"].strip("/"),
        "manifestPath": manifest_blob_path,
        "bundlePath": catalog_zip_path,
        "catalogZipPath": catalog_zip_path,
        "archivePath": archive_blob_path,
        "loadingMode": "remote-catalog",
        "notes": [
            "Client startup should load this manifest or catalog ZIP only.",
            "FBX and texture files are uploaded as separate Azure blobs and should be loaded lazily after user selection.",
            "Runtime GLB files are published for supported categories and are intended for in-browser PlayCanvas rendering.",
            "Preview PNGs are generated by Blender and organized beside their matching asset categories.",
            "The source archive is retained for publishing/debugging and is not intended for client bootstrap.",
            "PSD files, Unity packages, and tutorial files are excluded by default.",
        ],
        "counts": {
            "models": len(models),
            "animations": len(animations),
            "textures": len(textures),
        },
        "runtime": {
            "embeddedAnimationsInRuntimeGlb": True,
            "runtimeAnimatedCategories": list(CONFIG.get("runtime_merge_animation_categories", [])),
            "preferredMotionMode": CONFIG.get("preferred_runtime_motion_mode", "in-place"),
            "animations": runtime_animation_catalog,
        },
        "models": models,
        "animations": animations,
        "textures": textures,
    }


def build_runtime_animation_catalog(animations):
    catalog = []
    for animation in animations:
        catalog.append({
            "id": animation["id"],
            "name": animation["name"],
            "animationKey": animation.get("animationKey", animation["id"]),
            "runtimeClipName": animation.get("runtimeClipName", animation["id"]),
            "motionMode": animation.get("motionMode", "stationary"),
            "preferredForGameplay": bool(animation.get("preferredForGameplay", False)),
            "assetUrlPath": animation.get("assetUrlPath"),
            "previewUrlPath": animation.get("previewUrlPath"),
        })

    catalog.sort(key=lambda item: (item["animationKey"], item["motionMode"], item["id"]))
    return catalog


def create_catalog_zip(manifest_path, entries, catalog_zip_path):
    ensure_dir(os.path.dirname(catalog_zip_path))
    with zipfile.ZipFile(catalog_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as output_zip:
        output_zip.write(manifest_path, arcname=CONFIG["manifest_filename"])
        for _, descriptor in entries:
            preview_path = descriptor.get("previewLocalPath")
            if preview_path and os.path.isfile(preview_path):
                output_zip.write(preview_path, arcname=descriptor["previewPath"])

    print(f"Saved catalog zip: {catalog_zip_path}")
    return catalog_zip_path


def copy_source_archive(input_zip, archive_path):
    ensure_dir(os.path.dirname(archive_path))
    shutil.copyfile(input_zip, archive_path)
    print(f"Saved source archive copy: {archive_path}")
    return archive_path


def upload_individual_files(container_client, entries):
    for _, descriptor in entries:
        local_path = descriptor.get("localPath")
        if local_path and os.path.isfile(local_path):
            upload_file_to_azure(container_client, local_path, descriptor["assetBlobPath"])

        runtime_path = descriptor.get("runtimeLocalPath")
        runtime_blob_path = descriptor.get("runtimeBlobPath")
        if (
            CONFIG.get("upload_runtime_glb", True)
            and runtime_path
            and runtime_blob_path
            and os.path.isfile(runtime_path)
        ):
            upload_file_to_azure(container_client, runtime_path, runtime_blob_path)

        preview_path = descriptor.get("previewLocalPath")
        if CONFIG.get("upload_previews") and preview_path and os.path.isfile(preview_path):
            upload_file_to_azure(container_client, preview_path, descriptor["previewBlobPath"])


def print_summary(manifest):
    counts = manifest["counts"]
    print(
        "Prepared Meshtint dynamic character catalog: "
        f"{counts['models']} model(s), "
        f"{counts['animations']} animation(s), "
        f"{counts['textures']} texture(s)."
    )
    print(f"Manifest: {CONFIG['azure_container_name']}/{manifest['manifestPath']}")
    print(f"Catalog ZIP: {CONFIG['azure_container_name']}/{manifest['catalogZipPath']}")
    print(f"Asset root: {CONFIG['azure_container_name']}/{manifest['assetRoot']}")


def run_preview_renderer(job_file):
    import bpy
    import math
    from mathutils import Vector

    configure_process_temp_environment(os.path.dirname(job_file))

    with open(job_file, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    resolution = int(payload.get("resolution", 256))
    engine = payload.get("engine", "BLENDER_EEVEE_NEXT")
    samples = int(payload.get("samples", 32))
    jobs = payload.get("jobs", [])

    failures = []

    for job in jobs:
        input_path = job["inputPath"]
        output_path = job["outputPath"]
        texture_search_root = job.get("textureSearchRoot")
        default_texture_path = job.get("defaultTexturePath")
        ensure_dir(os.path.dirname(output_path))

        try:
            bpy.ops.wm.read_factory_settings(use_empty=True)
            scene = bpy.context.scene
            try:
                scene.render.engine = engine
            except TypeError:
                fallback_engine = "BLENDER_EEVEE"
                print(f"Render engine {engine} is unavailable; using {fallback_engine}.")
                scene.render.engine = fallback_engine
            scene.render.resolution_x = resolution
            scene.render.resolution_y = resolution
            scene.render.resolution_percentage = 100
            scene.render.film_transparent = True

            if hasattr(scene, "eevee"):
                scene.eevee.taa_render_samples = samples

            before = set(bpy.data.objects)
            ext = os.path.splitext(input_path)[1].lower()
            if ext == ".fbx":
                bpy.ops.import_scene.fbx(filepath=input_path)
            elif ext in {".glb", ".gltf"}:
                bpy.ops.import_scene.gltf(filepath=input_path)
            else:
                print(f"Skipping unsupported preview input: {input_path}")
                continue

            if texture_search_root and os.path.isdir(texture_search_root):
                bpy.ops.file.find_missing_files(directory=texture_search_root)

            imported = [obj for obj in bpy.data.objects if obj not in before]
            meshes = [obj for obj in imported if obj.type == "MESH"]
            if not meshes:
                raise RuntimeError(f"No mesh objects found for preview: {input_path}")

            apply_preview_material_fallbacks(
                meshes,
                job.get("category"),
                default_texture_path,
            )

            bpy.context.view_layer.update()
            center, radius = get_scene_bounds(meshes)
            target = bpy.data.objects.new("KS_Preview_Target", None)
            bpy.context.collection.objects.link(target)
            target.location = center

            cam_data = bpy.data.cameras.new("KS_Preview_Camera")
            cam_data.type = "ORTHO"
            cam_data.ortho_scale = max(radius * 2.35, 1.0)
            cam = bpy.data.objects.new("KS_Preview_Camera", cam_data)
            bpy.context.collection.objects.link(cam)
            cam.location = center + Vector((radius * 1.8, -radius * 2.4, radius * 1.45))
            direction = center - cam.location
            cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
            scene.camera = cam

            light_data = bpy.data.lights.new("KS_Preview_Key", type="AREA")
            light_data.energy = 450
            light_data.size = max(radius * 2.2, 1.0)
            light = bpy.data.objects.new("KS_Preview_Key", light_data)
            bpy.context.collection.objects.link(light)
            light.location = center + Vector((radius * 1.5, -radius * 2.0, radius * 2.0))
            light.rotation_euler = cam.rotation_euler

            scene.render.filepath = output_path
            bpy.ops.render.render(write_still=True)
            if not os.path.isfile(output_path):
                raise RuntimeError(f"Blender did not write preview output: {output_path}")
            print(f"Rendered preview: {output_path}")
        except Exception as error:
            failures.append({"inputPath": input_path, "outputPath": output_path, "error": str(error)})
            print(f"Preview render failed: {input_path}: {error}")

    if failures:
        failure_path = os.path.splitext(job_file)[0] + "-failures.json"
        with open(failure_path, "w", encoding="utf-8") as handle:
            json.dump(failures, handle, indent=2)
            handle.write("\n")
        raise RuntimeError(
            f"{len(failures)} preview render job(s) failed. See {failure_path}"
        )

    failure_path = os.path.splitext(job_file)[0] + "-failures.json"
    if os.path.isfile(failure_path):
        os.remove(failure_path)


def run_runtime_exporter(job_file):
    import bpy
    import math
    from mathutils import Euler, Matrix, Vector

    configure_process_temp_environment(os.path.dirname(job_file))

    canonical_face_mount_translation = Vector((0.94, 0.03, 0.0))
    canonical_face_mount_rotation = Euler(
        (math.radians(270.0), math.radians(90.0), math.radians(0.0)),
        "XYZ",
    )

    def get_armatures():
        return [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]

    def get_mesh_objects():
        return [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]

    def get_scene_roots():
        return [obj for obj in bpy.context.scene.objects if obj.parent is None]

    def get_bone_signature(armature):
        return [bone.name for bone in armature.data.bones]

    def normalize_lookup_token(value):
        return re.sub(r"[^a-z0-9]+", "", (value or "").lower())

    def find_scene_object_by_names(*names):
        normalized_names = {normalize_lookup_token(name) for name in names if name}
        for obj in bpy.context.scene.objects:
            if normalize_lookup_token(obj.name) in normalized_names:
                return obj
        return None

    def find_bone_by_names(armature, *names):
        normalized_names = {normalize_lookup_token(name) for name in names if name}
        for bone in armature.data.bones:
            if normalize_lookup_token(bone.name) in normalized_names:
                return bone
        return None

    def resolve_face_mount_matrix():
        mount_object = find_scene_object_by_names("+Head", "Head")
        if mount_object is not None:
            return mount_object.matrix_world.copy()

        for armature in get_armatures():
            mount_bone = find_bone_by_names(armature, "+Head", "Head", "RigHead")
            if mount_bone is None:
                continue
            return armature.matrix_world @ mount_bone.matrix_local

        print(
            "No +Head/Head/RigHead mount was found in face source; "
            "using canonical face mount transform."
        )
        return (
            Matrix.Translation(canonical_face_mount_translation)
            @ canonical_face_mount_rotation.to_matrix().to_4x4()
        )

    def ensure_head_attachment_mount():
        mount_object = find_scene_object_by_names("+Head")
        if mount_object is not None:
            return mount_object

        for armature in get_armatures():
            head_bone = find_bone_by_names(armature, "RigHead", "Head")
            if head_bone is None:
                continue

            mount_object = bpy.data.objects.new("+Head", None)
            bpy.context.scene.collection.objects.link(mount_object)
            mount_object.parent = armature
            mount_object.parent_type = "BONE"
            mount_object.parent_bone = head_bone.name
            mount_object.location = canonical_face_mount_translation.copy()
            mount_object.rotation_mode = "XYZ"
            mount_object.rotation_euler = canonical_face_mount_rotation.copy()
            mount_object.scale = (1.0, 1.0, 1.0)
            bpy.context.view_layer.update()
            print(f"Created +Head mount on armature bone: {head_bone.name}")
            return mount_object

        head_object = find_scene_object_by_names("RigHead", "Head")
        if head_object is not None:
            mount_object = bpy.data.objects.new("+Head", None)
            bpy.context.scene.collection.objects.link(mount_object)
            mount_object.parent = head_object
            mount_object.location = canonical_face_mount_translation.copy()
            mount_object.rotation_mode = "XYZ"
            mount_object.rotation_euler = canonical_face_mount_rotation.copy()
            mount_object.scale = (1.0, 1.0, 1.0)
            bpy.context.view_layer.update()
            print(f"Created +Head mount on object: {head_object.name}")
            return mount_object

        raise RuntimeError("Could not find a head target for +Head mount creation")

    def find_object_in_collection_by_names(objects, *names):
        normalized_names = {normalize_lookup_token(name) for name in names if name}
        for obj in objects:
            if normalize_lookup_token(obj.name) in normalized_names:
                return obj
        return None

    def resolve_head_bone_target():
        for armature in get_armatures():
            head_bone = find_bone_by_names(armature, "RigHead", "Head")
            if head_bone is not None:
                return armature, head_bone
        raise RuntimeError("Could not find RigHead/Head bone target in body scene")

    def parent_object_to_bone_preserve_world(object_to_parent, armature, bone):
        world_matrix = object_to_parent.matrix_world.copy()
        bone_world_matrix = armature.matrix_world @ bone.matrix_local
        object_to_parent.parent = armature
        object_to_parent.parent_type = "BONE"
        object_to_parent.parent_bone = bone.name
        object_to_parent.matrix_parent_inverse = bone_world_matrix.inverted()
        object_to_parent.matrix_world = world_matrix

    def parent_object_to_bone_keep_imported_placement(object_to_parent, armature, bone):
        world_matrix = object_to_parent.matrix_world.copy()
        object_to_parent.parent = armature
        object_to_parent.parent_type = "BONE"
        object_to_parent.parent_bone = bone.name
        object_to_parent.matrix_parent_inverse = armature.matrix_world.inverted()
        object_to_parent.matrix_world = world_matrix

    def parent_object_to_bone_relative(object_to_parent, armature, bone):
        view_layer = bpy.context.view_layer
        previous_active_object = view_layer.objects.active
        previous_mode = armature.mode
        previously_selected_objects = list(bpy.context.selected_objects)

        try:
            if previous_mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")

            for selected_object in previously_selected_objects:
                selected_object.select_set(False)

            armature.select_set(True)
            object_to_parent.select_set(True)
            view_layer.objects.active = armature
            bpy.ops.object.mode_set(mode="POSE")

            for pose_bone in armature.pose.bones:
                pose_bone.select = False
            armature.data.bones.active = bone
            armature.pose.bones[bone.name].select = True

            bpy.ops.object.parent_set(type="BONE_RELATIVE")
            bpy.ops.object.mode_set(mode="OBJECT")
        finally:
            if armature.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")

            object_to_parent.select_set(False)
            armature.select_set(False)
            for selected_object in previously_selected_objects:
                if selected_object.name in bpy.data.objects:
                    selected_object.select_set(True)
            if previous_active_object is not None and previous_active_object.name in bpy.data.objects:
                view_layer.objects.active = previous_active_object

    def collect_mesh_objects_in_hierarchy(root_object):
        hierarchy_objects = [root_object]
        hierarchy_objects.extend(root_object.children_recursive)
        return [obj for obj in hierarchy_objects if obj.type == "MESH"]

    def rigid_bind_mesh_to_bone(mesh_object, armature, bone):
        world_matrix = mesh_object.matrix_world.copy()
        mesh_object.parent = None
        mesh_object.matrix_world = world_matrix

        mesh_object.vertex_groups.clear()
        vertex_group = mesh_object.vertex_groups.new(name=bone.name)
        vertex_indices = [vertex.index for vertex in mesh_object.data.vertices]
        if vertex_indices:
            vertex_group.add(vertex_indices, 1.0, "REPLACE")

        armature_modifier = None
        for modifier in mesh_object.modifiers:
            if modifier.type == "ARMATURE":
                armature_modifier = modifier
                break
        if armature_modifier is None:
            armature_modifier = mesh_object.modifiers.new(
                name="ShoulderArmature",
                type="ARMATURE",
            )
        armature_modifier.object = armature

        mesh_object.parent = armature
        mesh_object.matrix_parent_inverse = armature.matrix_world.inverted()
        mesh_object.matrix_world = world_matrix

    def should_keep_face_mesh(mesh_object):
        normalized_name = normalize_lookup_token(mesh_object.name)
        if not normalized_name:
            return False
        return "face" in normalized_name

    def resolve_headwear_mount_matrix():
        mount_object = find_scene_object_by_names("Head_Plus", "Head Plus", "+Head", "Head")
        if mount_object is not None:
            return mount_object.matrix_world.copy()

        return resolve_face_mount_matrix()

    def rebuild_face_scene_for_runtime_export():
        mount_matrix = resolve_face_mount_matrix()
        inverse_mount_matrix = mount_matrix.inverted()
        source_meshes = [obj for obj in get_mesh_objects() if should_keep_face_mesh(obj)]
        if not source_meshes:
            raise RuntimeError("No face mesh objects were found for runtime face export")

        objects_to_keep = set()
        for source_mesh in source_meshes:
            current = source_mesh
            while current is not None:
                objects_to_keep.add(current)
                current = current.parent

            for modifier in source_mesh.modifiers:
                if modifier.type == "ARMATURE" and modifier.object is not None:
                    armature = modifier.object
                    objects_to_keep.add(armature)
                    current = armature.parent
                    while current is not None:
                        objects_to_keep.add(current)
                        current = current.parent

        world_matrices = {
            obj: inverse_mount_matrix @ obj.matrix_world.copy()
            for obj in objects_to_keep
        }

        for obj in objects_to_keep:
            obj.parent = None

        bpy.context.view_layer.update()

    def rebuild_headwear_scene_for_runtime_export():
        mount_matrix = resolve_headwear_mount_matrix()
        inverse_mount_matrix = mount_matrix.inverted()
        source_meshes = [obj for obj in get_mesh_objects() if should_keep_headwear_mesh(obj)]
        if not source_meshes:
            raise RuntimeError("No headwear mesh objects were found for runtime headwear export")

        objects_to_keep = set()
        for source_mesh in source_meshes:
            current = source_mesh
            while current is not None:
                objects_to_keep.add(current)
                current = current.parent

            for modifier in source_mesh.modifiers:
                if modifier.type == "ARMATURE" and modifier.object is not None:
                    armature = modifier.object
                    objects_to_keep.add(armature)
                    current = armature.parent
                    while current is not None:
                        objects_to_keep.add(current)
                        current = current.parent

        world_matrices = {
            obj: inverse_mount_matrix @ obj.matrix_world.copy()
            for obj in objects_to_keep
        }

        for obj in objects_to_keep:
            obj.parent = None

        bpy.context.view_layer.update()

        for obj, rebased_matrix in world_matrices.items():
            obj.matrix_world = rebased_matrix

        for obj in list(bpy.context.scene.objects):
            if obj in objects_to_keep:
                continue
            bpy.data.objects.remove(obj, do_unlink=True)

        runtime_root = bpy.data.objects.new("HeadwearRuntimeRoot", None)
        runtime_root.matrix_world = Matrix.Identity(4)
        bpy.context.scene.collection.objects.link(runtime_root)

        if source_meshes:
            bpy.ops.object.select_all(action="DESELECT")
            for obj in source_meshes:
                obj.select_set(True)
            bpy.context.view_layer.objects.active = source_meshes[0]
            bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

        for obj in source_meshes:
            obj.parent = runtime_root
            obj.matrix_parent_inverse = runtime_root.matrix_world.inverted()
            obj.location = (0.0, 0.0, 0.0)
            obj.rotation_mode = "XYZ"
            obj.rotation_euler = (0.0, 0.0, 0.0)
            obj.scale = (1.0, 1.0, 1.0)

        bpy.context.view_layer.update()

        for obj, rebased_matrix in world_matrices.items():
            obj.matrix_world = rebased_matrix

        for obj in list(bpy.context.scene.objects):
            if obj in objects_to_keep:
                continue
            bpy.data.objects.remove(obj, do_unlink=True)

        runtime_root = bpy.data.objects.new("FaceRuntimeRoot", None)
        runtime_root.matrix_world = Matrix.Identity(4)
        bpy.context.scene.collection.objects.link(runtime_root)

        # Bake the canonical head-relative transform into the face mesh data so
        # the exported runtime face can sit at identity under +Head.
        if source_meshes:
            bpy.ops.object.select_all(action="DESELECT")
            for obj in source_meshes:
                obj.select_set(True)
            bpy.context.view_layer.objects.active = source_meshes[0]
            bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

        for obj in source_meshes:
            obj.parent = runtime_root
            obj.matrix_parent_inverse = runtime_root.matrix_world.inverted()
            obj.location = (0.0, 0.0, 0.0)
            obj.rotation_mode = "XYZ"
            obj.rotation_euler = (0.0, 0.0, 0.0)
            obj.scale = (1.0, 1.0, 1.0)

        bpy.context.view_layer.update()

    def prune_body_scene_for_runtime_export():
        armatures = get_armatures()
        if not armatures:
            return

        objects_to_keep = set()

        for armature in armatures:
            objects_to_keep.add(armature)

            current = armature.parent
            while current is not None:
                objects_to_keep.add(current)
                current = current.parent

            for obj in bpy.context.scene.objects:
                if obj == armature:
                    continue

                ancestor = obj.parent
                while ancestor is not None:
                    if ancestor == armature:
                        objects_to_keep.add(obj)
                        break
                    ancestor = ancestor.parent

                for modifier in obj.modifiers:
                    if modifier.type == "ARMATURE" and modifier.object == armature:
                        objects_to_keep.add(obj)
                        current = obj.parent
                        while current is not None:
                            objects_to_keep.add(current)
                            current = current.parent
                        break

        removed_names = []
        for obj in list(bpy.context.scene.objects):
            if obj in objects_to_keep:
                continue
            removed_names.append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)

        if removed_names:
            print(
                "Removed non-rigged body helper objects: "
                + ", ".join(sorted(removed_names))
            )

        bpy.context.view_layer.update()

    def attach_runtime_face_to_body(face_runtime_input_path, face_name):
        mount_object = ensure_head_attachment_mount()
        existing_root_names = {obj.name for obj in get_scene_roots()}
        bpy.ops.import_scene.gltf(filepath=face_runtime_input_path)
        imported_roots = [
            obj for obj in get_scene_roots() if obj.name not in existing_root_names
        ]

        if not imported_roots:
            raise RuntimeError(
                f"Import did not add a face root from {face_runtime_input_path}"
            )

        imported_face_root = imported_roots[0]
        imported_children = list(imported_face_root.children)
        if not imported_children:
            imported_children = [imported_face_root]

        face_root = bpy.data.objects.new(f"RuntimeVariantRoot_{slugify_token(face_name)}", None)
        bpy.context.scene.collection.objects.link(face_root)
        face_root.parent = mount_object
        face_root.matrix_parent_inverse = mount_object.matrix_world.inverted()
        face_root.matrix_world = mount_object.matrix_world.copy()

        for child in imported_children:
            child.parent = face_root
            child.matrix_parent_inverse = face_root.matrix_world.inverted()
            child.location = (0.0, 0.0, 0.0)
            child.rotation_mode = "XYZ"
            child.rotation_euler = (0.0, 0.0, 0.0)
            child.scale = (1.0, 1.0, 1.0)

        if imported_face_root.name in bpy.data.objects:
            bpy.data.objects.remove(imported_face_root, do_unlink=True)
        bpy.context.view_layer.update()
        print(
            f"Attached runtime face GLB {os.path.basename(face_runtime_input_path)} "
            f"under +Head"
        )

    def attach_runtime_headwear_to_body(headwear_runtime_input_path, headwear_name):
        armature, head_bone = resolve_head_bone_target()
        existing_root_names = {obj.name for obj in get_scene_roots()}
        bpy.ops.import_scene.gltf(filepath=headwear_runtime_input_path)
        imported_roots = [
            obj for obj in get_scene_roots() if obj.name not in existing_root_names
        ]

        if not imported_roots:
            raise RuntimeError(
                f"Import did not add a headwear root from {headwear_runtime_input_path}"
            )

        imported_headwear_root = imported_roots[0]
        imported_headwear_root.name = f"RuntimeVariantRoot_{slugify_token(headwear_name)}"
        parent_object_to_bone_preserve_world(imported_headwear_root, armature, head_bone)
        bpy.context.view_layer.update()
        print(
            f"Attached runtime headwear GLB {os.path.basename(headwear_runtime_input_path)} "
            f"under bone {head_bone.name}"
        )

    def attach_face_fbx_to_body(face_source_input_path, face_name, texture_search_root=None):
        armature, head_bone = resolve_head_bone_target()
        existing_object_names = {obj.name for obj in bpy.context.scene.objects}
        bpy.ops.import_scene.fbx(filepath=face_source_input_path)
        if texture_search_root and os.path.isdir(texture_search_root):
            bpy.ops.file.find_missing_files(directory=texture_search_root)
        imported_objects = [
            obj for obj in bpy.context.scene.objects if obj.name not in existing_object_names
        ]

        if not imported_objects:
            raise RuntimeError(
                f"Import did not add any objects from {face_source_input_path}"
            )

        snap_object = find_object_in_collection_by_names(
            imported_objects,
            "Head_Plus",
            "Head Plus",
            "+Head",
        )
        if snap_object is not None:
            parent_object_to_bone_preserve_world(snap_object, armature, head_bone)
            bpy.context.view_layer.update()
            print(
                f"Attached face source FBX {os.path.basename(face_source_input_path)} "
                f"via authored snap point under bone {head_bone.name}"
            )
            return

        face_meshes = [
            obj for obj in imported_objects if obj.type == "MESH" and should_keep_face_mesh(obj)
        ]
        if not face_meshes:
            raise RuntimeError(
                f"No face mesh objects were found in source FBX: {face_source_input_path}"
            )

        for face_mesh in face_meshes:
            parent_object_to_bone_preserve_world(face_mesh, armature, head_bone)

        bpy.context.view_layer.update()
        print(
            f"Attached face source FBX {os.path.basename(face_source_input_path)} "
            f"using direct face-mesh parenting under bone {head_bone.name}"
        )

    def attach_faces_to_body(attached_face_descriptors, texture_search_root=None):
        if not attached_face_descriptors:
            return

        for face_descriptor in attached_face_descriptors:
            face_name = face_descriptor.get("name") or "face"
            runtime_input_path = face_descriptor.get("runtimeInputPath")
            source_input_path = face_descriptor.get("sourceInputPath")

            if source_input_path and os.path.isfile(source_input_path):
                attach_face_fbx_to_body(source_input_path, face_name, texture_search_root)
                continue

            if runtime_input_path and os.path.isfile(runtime_input_path):
                attach_runtime_face_to_body(runtime_input_path, face_name)
                continue

            raise RuntimeError(
                f"Attached face asset is missing for {face_name}: "
                f"runtime={runtime_input_path} source={source_input_path}"
            )

    def should_keep_hair_mesh(mesh_object):
        if mesh_object.type != "MESH":
            return False
        normalized_name = mesh_object.name.strip().lower()
        return "hair" in normalized_name

    def attach_hair_fbx_to_body(hair_source_input_path, hair_name, texture_search_root=None):
        armature, head_bone = resolve_head_bone_target()
        existing_object_names = {obj.name for obj in bpy.context.scene.objects}
        bpy.ops.import_scene.fbx(filepath=hair_source_input_path)
        if texture_search_root and os.path.isdir(texture_search_root):
            bpy.ops.file.find_missing_files(directory=texture_search_root)
        imported_objects = [
            obj for obj in bpy.context.scene.objects if obj.name not in existing_object_names
        ]

        if not imported_objects:
            raise RuntimeError(
                f"Import did not add any objects from {hair_source_input_path}"
            )

        snap_object = find_object_in_collection_by_names(
            imported_objects,
            "Head_Plus",
            "Head Plus",
            "+Head",
        )
        if snap_object is not None:
            parent_object_to_bone_preserve_world(snap_object, armature, head_bone)
            bpy.context.view_layer.update()
            print(
                f"Attached hair source FBX {os.path.basename(hair_source_input_path)} "
                f"via authored snap point under bone {head_bone.name}"
            )
            return

        hair_meshes = [
            obj for obj in imported_objects if obj.type == "MESH" and should_keep_hair_mesh(obj)
        ]
        if not hair_meshes:
            raise RuntimeError(
                f"No hair mesh objects were found in source FBX: {hair_source_input_path}"
            )

        for hair_mesh in hair_meshes:
            parent_object_to_bone_preserve_world(hair_mesh, armature, head_bone)

        bpy.context.view_layer.update()
        print(
            f"Attached hair source FBX {os.path.basename(hair_source_input_path)} "
            f"using direct hair-mesh parenting under bone {head_bone.name}"
        )

    def attach_hairs_to_body(attached_hair_descriptors, texture_search_root=None):
        if not attached_hair_descriptors:
            return

        for hair_descriptor in attached_hair_descriptors:
            hair_name = hair_descriptor.get("name") or "hair"
            source_input_path = hair_descriptor.get("sourceInputPath")
            if source_input_path and os.path.isfile(source_input_path):
                attach_hair_fbx_to_body(source_input_path, hair_name, texture_search_root)
                continue

            raise RuntimeError(
                f"Attached hair source asset is missing for {hair_name}: "
                f"source={source_input_path}"
            )

    def should_keep_headwear_mesh(mesh_object):
        return mesh_object.type == "MESH"

    def should_keep_shoulder_mesh(mesh_object):
        return mesh_object.type == "MESH"

    def resolve_shoulder_bone_targets():
        for armature in get_armatures():
            left_bone = find_bone_by_names(
                armature,
                "RigLUpperarm",
                "LUpperarm",
                "LeftUpperarm",
                "UpperArm_L",
            )
            right_bone = find_bone_by_names(
                armature,
                "RigRUpperarm",
                "RUpperarm",
                "RightUpperarm",
                "UpperArm_R",
            )
            if left_bone is not None or right_bone is not None:
                return armature, {
                    "left": left_bone,
                    "right": right_bone,
                }
        raise RuntimeError(
            "Could not find shoulder bone targets in body scene "
            "(expected left/right upperarm bones)"
        )

    def log_shoulder_objects(label, objects):
        print(f"{label}: {len(objects)} object(s)")
        for obj in objects:
            location = obj.matrix_world.to_translation()
            parent_name = obj.parent.name if obj.parent is not None else "<none>"
            print(
                "  - "
                f"name={obj.name} type={obj.type} parent={parent_name} "
                f"world=({location.x:.4f}, {location.y:.4f}, {location.z:.4f})"
            )

    def attach_shoulder_object_to_body(shoulder_object, armature, target_bone):
        if target_bone is None:
            raise RuntimeError(
                f"Could not resolve a shoulder bone target for object: {shoulder_object.name}"
            )
        mesh_objects = collect_mesh_objects_in_hierarchy(shoulder_object)
        if mesh_objects:
            for mesh_object in mesh_objects:
                rigid_bind_mesh_to_bone(mesh_object, armature, target_bone)
        else:
            parent_object_to_bone_relative(shoulder_object, armature, target_bone)
        return target_bone.name

    def duplicate_object_hierarchy(root_object):
        duplicated_objects = []

        def duplicate_recursive(source_object, parent_duplicate=None):
            duplicated_object = source_object.copy()
            if getattr(source_object, "data", None) is not None:
                duplicated_object.data = source_object.data.copy()
            bpy.context.scene.collection.objects.link(duplicated_object)
            duplicated_object.parent = parent_duplicate
            duplicated_object.matrix_parent_inverse.identity()
            duplicated_object.matrix_local = source_object.matrix_local.copy()
            duplicated_objects.append(duplicated_object)

            for child_object in source_object.children:
                duplicate_recursive(child_object, duplicated_object)

            return duplicated_object

        return duplicate_recursive(root_object), duplicated_objects

    def mirror_object_hierarchy_on_x(root_object):
        mirror_matrix = Matrix(
            (
                (-1.0, 0.0, 0.0, 0.0),
                (0.0, 1.0, 0.0, 0.0),
                (0.0, 0.0, 1.0, 0.0),
                (0.0, 0.0, 0.0, 1.0),
            )
        )
        root_object.matrix_world = mirror_matrix @ root_object.matrix_world

    def attach_right_authored_shoulder_pair_to_body(shoulder_object, armature, shoulder_bones):
        right_bone = shoulder_bones.get("right") or shoulder_bones.get("left")
        left_bone = shoulder_bones.get("left") or shoulder_bones.get("right")

        if right_bone is None or left_bone is None:
            raise RuntimeError(
                f"Could not resolve both shoulder bone targets for object: {shoulder_object.name}"
            )

        attached_bone_names = []
        mirrored_root, _ = duplicate_object_hierarchy(shoulder_object)
        mirror_object_hierarchy_on_x(mirrored_root)

        attached_bone_names.append(
            attach_shoulder_object_to_body(shoulder_object, armature, right_bone)
        )
        attached_bone_names.append(
            attach_shoulder_object_to_body(mirrored_root, armature, left_bone)
        )

        return attached_bone_names

    def attach_authored_shoulder_snap_points(imported_objects, armature, shoulder_bones):
        left_snap_object = find_object_in_collection_by_names(
            imported_objects,
            "L_Upperarm_Plus",
            "L Upperarm Plus",
            "LeftUpperarm_Plus",
            "Left Upperarm Plus",
            "+L Upperarm",
        )
        right_snap_object = find_object_in_collection_by_names(
            imported_objects,
            "R_Upperarm_Plus",
            "R Upperarm Plus",
            "RightUpperarm_Plus",
            "Right Upperarm Plus",
            "+R Upperarm",
        )

        attached_bone_names = []
        if left_snap_object is not None and shoulder_bones.get("left") is not None:
            attached_bone_names.append(
                attach_shoulder_object_to_body(
                    left_snap_object,
                    armature,
                    shoulder_bones.get("left"),
                )
            )
        if right_snap_object is not None and shoulder_bones.get("right") is not None:
            attached_bone_names.append(
                attach_shoulder_object_to_body(
                    right_snap_object,
                    armature,
                    shoulder_bones.get("right"),
                )
            )

        return attached_bone_names

    def infer_shoulder_side(mesh_object):
        normalized_name = mesh_object.name.strip().lower()
        normalized_parent_name = (
            mesh_object.parent.name.strip().lower() if mesh_object.parent is not None else ""
        )
        combined = f"{normalized_parent_name} {normalized_name}".strip()

        if re.search(r"(^|[^a-z])l(eft)?([^a-z]|$)", combined):
            return "left"
        if re.search(r"(^|[^a-z])r(ight)?([^a-z]|$)", combined):
            return "right"
        return None

    def attach_shoulder_meshes_to_body(shoulder_meshes, armature, shoulder_bones):
        attached_bone_names = []

        for shoulder_mesh in shoulder_meshes:
            side = infer_shoulder_side(shoulder_mesh)
            if side == "left":
                target_bone = shoulder_bones.get("left") or shoulder_bones.get("right")
                attached_bone_names.append(
                    attach_shoulder_object_to_body(shoulder_mesh, armature, target_bone)
                )
                continue

            if side == "right":
                target_bone = shoulder_bones.get("right") or shoulder_bones.get("left")
                attached_bone_names.append(
                    attach_shoulder_object_to_body(shoulder_mesh, armature, target_bone)
                )
                continue

            attached_bone_names.extend(
                attach_right_authored_shoulder_pair_to_body(
                    shoulder_mesh,
                    armature,
                    shoulder_bones,
                )
            )

        return attached_bone_names

    def attach_headwear_fbx_to_body(headwear_source_input_path, headwear_name, texture_search_root=None):
        armature, head_bone = resolve_head_bone_target()
        existing_object_names = {obj.name for obj in bpy.context.scene.objects}
        bpy.ops.import_scene.fbx(filepath=headwear_source_input_path)
        if texture_search_root and os.path.isdir(texture_search_root):
            bpy.ops.file.find_missing_files(directory=texture_search_root)
        imported_objects = [
            obj for obj in bpy.context.scene.objects if obj.name not in existing_object_names
        ]

        if not imported_objects:
            raise RuntimeError(
                f"Import did not add any objects from {headwear_source_input_path}"
            )

        snap_object = find_object_in_collection_by_names(
            imported_objects,
            "Head_Plus",
            "Head Plus",
            "+Head",
        )
        if snap_object is not None:
            parent_object_to_bone_preserve_world(snap_object, armature, head_bone)
            bpy.context.view_layer.update()
            print(
                f"Attached headwear source FBX {os.path.basename(headwear_source_input_path)} "
                f"via authored snap point under bone {head_bone.name}"
            )
            return

        headwear_meshes = [
            obj for obj in imported_objects if should_keep_headwear_mesh(obj)
        ]
        if not headwear_meshes:
            raise RuntimeError(
                f"No headwear mesh objects were found in source FBX: {headwear_source_input_path}"
            )

        for headwear_mesh in headwear_meshes:
            parent_object_to_bone_preserve_world(headwear_mesh, armature, head_bone)

        bpy.context.view_layer.update()
        print(
            f"Attached headwear source FBX {os.path.basename(headwear_source_input_path)} "
            f"using direct headwear-mesh parenting under bone {head_bone.name}"
        )

    def attach_shoulder_fbx_to_body(shoulder_source_input_path, shoulder_name, texture_search_root=None):
        armature, shoulder_bones = resolve_shoulder_bone_targets()
        existing_object_names = {obj.name for obj in bpy.context.scene.objects}
        bpy.ops.import_scene.fbx(filepath=shoulder_source_input_path)
        if texture_search_root and os.path.isdir(texture_search_root):
            bpy.ops.file.find_missing_files(directory=texture_search_root)
        imported_objects = [
            obj for obj in bpy.context.scene.objects if obj.name not in existing_object_names
        ]

        if not imported_objects:
            raise RuntimeError(
                f"Import did not add any objects from {shoulder_source_input_path}"
            )

        log_shoulder_objects(
            f"Imported shoulder objects from source FBX {os.path.basename(shoulder_source_input_path)}",
            imported_objects,
        )
        attached_bone_names = attach_authored_shoulder_snap_points(
            imported_objects,
            armature,
            shoulder_bones,
        )
        if attached_bone_names:
            bpy.context.view_layer.update()
            print(
                f"Attached shoulder source FBX {os.path.basename(shoulder_source_input_path)} "
                f"via authored snap points across bones: {', '.join(sorted(set(attached_bone_names)))}"
            )
            return

        shoulder_meshes = [
            obj for obj in imported_objects if should_keep_shoulder_mesh(obj)
        ]
        if not shoulder_meshes:
            raise RuntimeError(
                f"No shoulder mesh objects were found in source FBX: {shoulder_source_input_path}"
            )

        log_shoulder_objects("Shoulder mesh candidates", shoulder_meshes)
        attached_bone_names = attach_shoulder_meshes_to_body(
            shoulder_meshes,
            armature,
            shoulder_bones,
        )

        bpy.context.view_layer.update()
        print(
            f"Attached shoulder source FBX {os.path.basename(shoulder_source_input_path)} "
            f"across bones: {', '.join(sorted(set(attached_bone_names)))}"
        )

    def attach_runtime_shoulder_to_body(shoulder_runtime_input_path, shoulder_name):
        armature, shoulder_bones = resolve_shoulder_bone_targets()
        existing_object_names = {obj.name for obj in bpy.context.scene.objects}
        bpy.ops.import_scene.gltf(filepath=shoulder_runtime_input_path)
        imported_objects = [
            obj for obj in bpy.context.scene.objects if obj.name not in existing_object_names
        ]

        if not imported_objects:
            raise RuntimeError(
                f"Import did not add any shoulder objects from {shoulder_runtime_input_path}"
            )

        log_shoulder_objects(
            f"Imported shoulder objects from runtime GLB {os.path.basename(shoulder_runtime_input_path)}",
            imported_objects,
        )
        attached_bone_names = attach_authored_shoulder_snap_points(
            imported_objects,
            armature,
            shoulder_bones,
        )
        if attached_bone_names:
            bpy.context.view_layer.update()
            print(
                f"Attached runtime shoulder GLB {os.path.basename(shoulder_runtime_input_path)} "
                f"via authored snap points across bones: {', '.join(sorted(set(attached_bone_names)))}"
            )
            return

        shoulder_meshes = [
            obj for obj in imported_objects if should_keep_shoulder_mesh(obj)
        ]
        if not shoulder_meshes:
            raise RuntimeError(
                f"No shoulder mesh objects were found in runtime GLB: {shoulder_runtime_input_path}"
            )

        log_shoulder_objects("Runtime shoulder mesh candidates", shoulder_meshes)
        attached_bone_names = attach_shoulder_meshes_to_body(
            shoulder_meshes,
            armature,
            shoulder_bones,
        )

        bpy.context.view_layer.update()
        print(
            f"Attached runtime shoulder GLB {os.path.basename(shoulder_runtime_input_path)} "
            f"across bones: {', '.join(sorted(set(attached_bone_names)))}"
        )

    def attach_headwears_to_body(attached_headwear_descriptors, texture_search_root=None):
        if not attached_headwear_descriptors:
            return

        for headwear_descriptor in attached_headwear_descriptors:
            headwear_name = headwear_descriptor.get("name") or "headwear"
            runtime_input_path = headwear_descriptor.get("runtimeInputPath")
            source_input_path = headwear_descriptor.get("sourceInputPath")
            if source_input_path and os.path.isfile(source_input_path):
                attach_headwear_fbx_to_body(source_input_path, headwear_name, texture_search_root)
                continue

            if runtime_input_path and os.path.isfile(runtime_input_path):
                attach_runtime_headwear_to_body(runtime_input_path, headwear_name)
                continue

            raise RuntimeError(
                f"Attached headwear source asset is missing for {headwear_name}: "
                f"runtime={runtime_input_path} source={source_input_path}"
            )

    def attach_shoulders_to_body(attached_shoulder_descriptors, texture_search_root=None):
        if not attached_shoulder_descriptors:
            return

        for shoulder_descriptor in attached_shoulder_descriptors:
            shoulder_name = shoulder_descriptor.get("name") or "shoulder"
            runtime_input_path = shoulder_descriptor.get("runtimeInputPath")
            source_input_path = shoulder_descriptor.get("sourceInputPath")

            if source_input_path and os.path.isfile(source_input_path):
                attach_shoulder_fbx_to_body(source_input_path, shoulder_name, texture_search_root)
                continue

            if runtime_input_path and os.path.isfile(runtime_input_path):
                attach_runtime_shoulder_to_body(runtime_input_path, shoulder_name)
                continue

            raise RuntimeError(
                f"Attached shoulder asset is missing for {shoulder_name}: "
                f"runtime={runtime_input_path} source={source_input_path}"
            )

    def normalize_action_frames(action):
        if not action.layers:
            return

        frames = []
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for fcurve in bag.fcurves:
                        for keyframe in fcurve.keyframe_points:
                            frames.append(keyframe.co.x)

        if not frames:
            return

        offset = -min(frames)

        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for fcurve in bag.fcurves:
                        for keyframe in fcurve.keyframe_points:
                            keyframe.co.x += offset
                            keyframe.handle_left.x += offset
                            keyframe.handle_right.x += offset

        action.update_tag()

    def push_action_to_nla(armature, action):
        armature.animation_data_create()
        animation_data = armature.animation_data
        track = animation_data.nla_tracks.new()
        track.name = action.name
        track.mute = False
        track.is_solo = False

        start, end = action.frame_range
        strip = track.strips.new(action.name, 0, action)
        strip.action_frame_start = start
        strip.action_frame_end = end
        strip.blend_type = "REPLACE"
        strip.extrapolation = "HOLD_FORWARD"
        strip.influence = 1.0
        strip.mute = False
        animation_data.action = None

    def find_new_armature(known_names, main_armature):
        candidates = [
            armature
            for armature in get_armatures()
            if armature != main_armature and armature.name not in known_names
        ]

        if len(candidates) != 1:
            raise RuntimeError(
                f"Expected exactly one imported animation armature, found {len(candidates)}"
            )

        return candidates[0]

    def remove_imported_animation_objects(secondary_armature, main_armature):
        for obj in list(bpy.context.scene.objects):
            if obj == main_armature:
                continue

            if obj == secondary_armature:
                bpy.data.objects.remove(obj, do_unlink=True)
                continue

            ancestor = obj.parent
            while ancestor is not None:
                if ancestor == secondary_armature:
                    bpy.data.objects.remove(obj, do_unlink=True)
                    break
                ancestor = ancestor.parent

    def import_runtime_body(input_path):
        ext = os.path.splitext(input_path)[1].lower()
        if ext == ".fbx":
            bpy.ops.import_scene.fbx(filepath=input_path)
            return
        if ext in {".glb", ".gltf"}:
            bpy.ops.import_scene.gltf(filepath=input_path)
            return
        raise RuntimeError(f"Unsupported runtime merge body input: {input_path}")

    def merge_animation_fbxs_into_body_glb(
        input_path,
        output_path,
        animation_input_paths,
        attached_face_descriptors=None,
        attached_hair_descriptors=None,
        attached_headwear_descriptors=None,
        attached_shoulder_descriptors=None,
    ):
        import_runtime_body(input_path)
        armatures = get_armatures()
        if len(armatures) != 1:
            raise RuntimeError(f"Expected one body armature in {input_path}, found {len(armatures)}")

        main_armature = armatures[0]
        reference_bones = get_bone_signature(main_armature)

        for animation_input_path in animation_input_paths:
            known_names = {armature.name for armature in get_armatures()}
            bpy.ops.import_scene.fbx(filepath=animation_input_path)
            secondary_armature = find_new_armature(known_names, main_armature)

            if get_bone_signature(secondary_armature) != reference_bones:
                raise RuntimeError(
                    f"Bone mismatch for {animation_input_path} against {input_path}"
                )

            animation_data = secondary_armature.animation_data
            if not animation_data or not animation_data.action:
                raise RuntimeError(f"No active action found in animation FBX: {animation_input_path}")

            action = animation_data.action
            action.name = os.path.splitext(os.path.basename(animation_input_path))[0].lower()
            normalize_action_frames(action)
            push_action_to_nla(main_armature, action)
            remove_imported_animation_objects(secondary_armature, main_armature)

        main_armature.animation_data.action = None
        prune_body_scene_for_runtime_export()
        attach_faces_to_body(attached_face_descriptors or [], texture_search_root)
        attach_hairs_to_body(attached_hair_descriptors or [], texture_search_root)
        attach_headwears_to_body(attached_headwear_descriptors or [], texture_search_root)
        attach_shoulders_to_body(attached_shoulder_descriptors or [], texture_search_root)
        bpy.ops.export_scene.gltf(
            filepath=output_path,
            export_format="GLB",
            use_selection=False,
            export_yup=True,
            export_apply=True,
            export_animations=True,
            export_animation_mode="NLA_TRACKS",
            export_force_sampling=True,
            export_skins=True,
        )

    with open(job_file, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    jobs = payload.get("jobs", [])
    failures = []

    job_priority = {
        "face": 0,
        "crown": 0,
        "hat": 0,
        "headdress": 0,
        "helmet": 0,
        "hood": 0,
        "shoulder": 0,
        "body": 1,
    }

    for job in sorted(jobs, key=lambda item: (job_priority.get(item.get("category"), 99), item["outputPath"])):
        input_path = job["inputPath"]
        output_path = job["outputPath"]
        category = job.get("category")
        attached_face_descriptors = job.get("attachedFaceDescriptors") or []
        attached_hair_descriptors = job.get("attachedHairDescriptors") or []
        attached_headwear_descriptors = job.get("attachedHeadwearDescriptors") or []
        attached_shoulder_descriptors = job.get("attachedShoulderDescriptors") or []
        texture_search_root = job.get("textureSearchRoot")
        animation_input_paths = job.get("animationInputPaths") or []
        ensure_dir(os.path.dirname(output_path))

        try:
            bpy.ops.wm.read_factory_settings(use_empty=True)
            ext = os.path.splitext(input_path)[1].lower()
            if animation_input_paths:
                merge_animation_fbxs_into_body_glb(
                    input_path,
                    output_path,
                    animation_input_paths,
                    attached_face_descriptors,
                    attached_hair_descriptors,
                    attached_headwear_descriptors,
                    attached_shoulder_descriptors,
                )
            elif ext == ".fbx":
                bpy.ops.import_scene.fbx(filepath=input_path)
                if texture_search_root and os.path.isdir(texture_search_root):
                    bpy.ops.file.find_missing_files(directory=texture_search_root)
                if category == "face":
                    rebuild_face_scene_for_runtime_export()
                elif category in HEADGEAR_CATEGORIES:
                    rebuild_headwear_scene_for_runtime_export()
                elif category == "body":
                    prune_body_scene_for_runtime_export()
                    attach_faces_to_body(attached_face_descriptors, texture_search_root)
                    attach_hairs_to_body(attached_hair_descriptors, texture_search_root)
                    attach_headwears_to_body(attached_headwear_descriptors, texture_search_root)
                    attach_shoulders_to_body(attached_shoulder_descriptors, texture_search_root)
                bpy.ops.export_scene.gltf(
                    filepath=output_path,
                    export_format="GLB",
                    use_selection=False,
                    export_yup=True,
                )
            elif ext in {".glb", ".gltf"}:
                bpy.ops.import_scene.gltf(filepath=input_path)
                if texture_search_root and os.path.isdir(texture_search_root):
                    bpy.ops.file.find_missing_files(directory=texture_search_root)
                if category == "face":
                    rebuild_face_scene_for_runtime_export()
                elif category in HEADGEAR_CATEGORIES:
                    rebuild_headwear_scene_for_runtime_export()
                elif category == "body":
                    prune_body_scene_for_runtime_export()
                    attach_faces_to_body(attached_face_descriptors, texture_search_root)
                    attach_hairs_to_body(attached_hair_descriptors, texture_search_root)
                    attach_headwears_to_body(attached_headwear_descriptors, texture_search_root)
                    attach_shoulders_to_body(attached_shoulder_descriptors, texture_search_root)
                bpy.ops.export_scene.gltf(
                    filepath=output_path,
                    export_format="GLB",
                    use_selection=False,
                    export_yup=True,
                )
            else:
                raise RuntimeError(f"Unsupported runtime export input: {input_path}")

            if not os.path.isfile(output_path):
                raise RuntimeError(f"Blender did not write runtime output: {output_path}")
            print(f"Exported runtime GLB: {output_path}")
        except Exception as error:
            failures.append({"inputPath": input_path, "outputPath": output_path, "error": str(error)})
            print(f"Runtime export failed: {input_path}: {error}")

    if failures:
        failure_path = os.path.splitext(job_file)[0] + "-failures.json"
        with open(failure_path, "w", encoding="utf-8") as handle:
            json.dump(failures, handle, indent=2)
            handle.write("\n")
        raise RuntimeError(
            f"{len(failures)} runtime export job(s) failed. See {failure_path}"
        )

    failure_path = os.path.splitext(job_file)[0] + "-failures.json"
    if os.path.isfile(failure_path):
        os.remove(failure_path)


def get_scene_bounds(meshes):
    import math
    from mathutils import Vector

    points = []
    for obj in meshes:
        for corner in obj.bound_box:
            points.append(obj.matrix_world @ Vector(corner))

    if not points:
        return Vector((0, 0, 0)), 1.0

    min_point = Vector((
        min(point.x for point in points),
        min(point.y for point in points),
        min(point.z for point in points),
    ))
    max_point = Vector((
        max(point.x for point in points),
        max(point.y for point in points),
        max(point.z for point in points),
    ))
    center = (min_point + max_point) * 0.5
    radius = max((point - center).length for point in points)
    if not math.isfinite(radius) or radius <= 0:
        radius = 1.0
    return center, radius


def apply_preview_material_fallbacks(meshes, category, texture_path):
    material_color = get_preview_category_color(category)

    if material_color is not None:
        for obj in meshes:
            if mesh_has_image_texture(obj):
                continue
            apply_color_material(obj, material_color)
        return

    if texture_path and os.path.isfile(texture_path):
        for obj in meshes:
            if mesh_has_image_texture(obj):
                continue
            apply_texture_material(obj, texture_path)


def apply_texture_material(obj, texture_path):
    import bpy

    material = bpy.data.materials.new(f"{obj.name}_preview_texture")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    principled = nodes.get("Principled BSDF")
    if principled is None:
        return

    image_node = nodes.new("ShaderNodeTexImage")
    image_node.image = bpy.data.images.load(texture_path, check_existing=True)
    links.new(image_node.outputs["Color"], principled.inputs["Base Color"])

    obj.data.materials.clear()
    obj.data.materials.append(material)


def apply_color_material(obj, color):
    import bpy

    material = bpy.data.materials.new(f"{obj.name}_preview_color")
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    if principled is None:
        return

    principled.inputs["Base Color"].default_value = color
    principled.inputs["Roughness"].default_value = 0.72
    if "Metallic" in principled.inputs:
        principled.inputs["Metallic"].default_value = 0.18

    obj.data.materials.clear()
    obj.data.materials.append(material)


def get_preview_category_color(category):
    value = CONFIG.get("preview_category_materials", {}).get(category or "")
    if not isinstance(value, str):
        return None

    return parse_hex_color(value)


def parse_hex_color(value):
    value = value.strip().lstrip("#")
    if len(value) != 6:
        return None

    try:
        red = int(value[0:2], 16) / 255
        green = int(value[2:4], 16) / 255
        blue = int(value[4:6], 16) / 255
    except ValueError:
        return None

    return (red, green, blue, 1.0)


def mesh_has_image_texture(obj):
    import bpy
    import os

    if obj.type != "MESH":
        return False

    for material in obj.data.materials:
        if not material or not material.use_nodes:
            continue
        for node in material.node_tree.nodes:
            if node.type != "TEX_IMAGE":
                continue

            image = getattr(node, "image", None)
            if not image:
                continue

            image_path = bpy.path.abspath(image.filepath) if image.filepath else ""
            if image_path and os.path.isfile(image_path):
                return True

    return False


def run():
    args = parse_cli_args(sys.argv)
    if args["config"]:
        load_config_file(args["config"])

    cli_focus_categories = parse_focus_categories(args.get("categories"))
    config_focus_categories = parse_focus_categories(CONFIG.get("focus_categories"))
    focus_categories = cli_focus_categories or config_focus_categories
    CONFIG["focus_categories"] = focus_categories

    if args["render_job"]:
        run_preview_renderer(args["render_job"])
        return
    if args["runtime_job"]:
        run_runtime_exporter(args["runtime_job"])
        return

    input_zip = resolve_input_zip_path()
    print(f"Using source ZIP: {input_zip}")

    extract_root = os.path.join(CONFIG["output_dir"], "catalog-work")
    if os.path.isdir(extract_root):
        shutil.rmtree(extract_root)
    ensure_dir(extract_root)

    with zipfile.ZipFile(input_zip, "r") as zip_file:
        entries = collect_entries(zip_file)
        entries = filter_entries_by_focus_categories(entries, focus_categories)
        if not entries:
            print("No supported files found for the selected categories.")
            return

        extract_zip_entries(zip_file, entries, extract_root)

    copy_texture_previews(entries, extract_root)
    if CONFIG.get("export_runtime_glb", True):
        export_runtime_glbs(entries, extract_root)
    if CONFIG.get("render_previews", True):
        render_previews(entries, extract_root)

    manifest = build_manifest(entries)
    print_summary(manifest)

    manifest_path = None
    if CONFIG.get("write_manifest", True):
        manifest_path = write_manifest(CONFIG["output_dir"], manifest)

    catalog_zip_path = os.path.join(CONFIG["output_dir"], CONFIG["catalog_zip_filename"])
    if manifest_path:
        create_catalog_zip(manifest_path, entries, catalog_zip_path)

    archive_path = os.path.join(CONFIG["output_dir"], CONFIG["archive_zip_filename"])
    if CONFIG.get("upload_archive_zip", True):
        copy_source_archive(input_zip, archive_path)

    if CONFIG.get("dry_run"):
        print("Dry run enabled; no Azure uploads performed.")
        return

    if CONFIG.get("upload_to_azure"):
        blob_service_client = get_blob_service_client()
        container_client = ensure_blob_container(blob_service_client)

        if CONFIG.get("upload_individual_files", True):
            upload_individual_files(container_client, entries)

        if CONFIG.get("upload_manifest", True) and manifest_path:
            upload_file_to_azure(
                container_client,
                manifest_path,
                build_catalog_blob_name(CONFIG["manifest_filename"]),
            )

        if CONFIG.get("upload_catalog_zip", True) and os.path.isfile(catalog_zip_path):
            upload_file_to_azure(
                container_client,
                catalog_zip_path,
                build_catalog_blob_name(CONFIG["catalog_zip_filename"]),
            )

        if CONFIG.get("upload_archive_zip", True) and os.path.isfile(archive_path):
            upload_file_to_azure(
                container_client,
                archive_path,
                build_source_archive_blob_name(),
            )


if __name__ == "__main__":
    run()




