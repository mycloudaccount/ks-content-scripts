import json
import os
import re
import sys
import zipfile


CONFIG = {
    "input_dir": r"C:\myAssets\sounds",
    "output_dir": r"C:\myapps\temp",
    "supported_exts": [
        ".wav",
        ".mp3",
        ".ogg",
        ".flac",
        ".m4a",
        ".aac",
    ],
    "include_subdirectories": True,
    "archive_sound_root": "sounds",
    "manifest_path_prefix": "sounds",
    "write_sounds_manifest": True,
    "sounds_manifest_filename": "sounds.json",
    "sound_defaults": {},
    "category_defaults": {},
    "sound_metadata": {},
    "upload_to_azure": True,
    "azure_storage_account_name": "ksstorage",
    "azure_container_name": "game-assets",
    "azure_blob_prefix": "sounds",
    "azure_zip_filename": "sounds_bundle.zip",
}


def ensure_dir(path):
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
    with open(config_path, "r", encoding="utf-8") as handle:
        loaded = json.load(handle)

    if not isinstance(loaded, dict):
        raise ValueError("Config file must contain a JSON object")

    unknown_keys = sorted(set(loaded) - set(CONFIG))
    if unknown_keys:
        print(
            f"Warning: ignoring unknown config keys: {', '.join(unknown_keys)}"
        )

    CONFIG.update({key: value for key, value in loaded.items() if key in CONFIG})
    print(f"Loaded config: {config_path}")


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


def upload_file_to_azure(container_client, local_file_path, blob_name):
    from azure.storage.blob import ContentSettings

    content_type_map = {
        ".json": "application/json",
        ".zip": "application/zip",
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
    }

    ext = os.path.splitext(local_file_path)[1].lower()
    content_type = content_type_map.get(ext)
    content_settings = None
    if content_type:
        content_settings = ContentSettings(content_type=content_type)

    blob_client = container_client.get_blob_client(blob_name)
    with open(local_file_path, "rb") as data:
        blob_client.upload_blob(
            data,
            overwrite=True,
            content_settings=content_settings,
        )

    print(f"Uploaded to Azure Blob: {blob_name}")


def build_blob_name(filename):
    prefix = CONFIG.get("azure_blob_prefix", "").strip("/")
    if prefix:
        return f"{prefix}/{filename}"
    return filename


def normalize_rel_path(path):
    return path.replace("\\", "/").strip("/")


def slugify_token(value):
    token = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return token or "sound"


def list_sound_files(input_dir):
    supported_exts = {ext.lower() for ext in CONFIG["supported_exts"]}
    include_subdirectories = CONFIG.get("include_subdirectories", True)
    files = []

    if include_subdirectories:
        for root, _, filenames in os.walk(input_dir):
            for filename in filenames:
                ext = os.path.splitext(filename)[1].lower()
                if ext in supported_exts:
                    files.append(os.path.join(root, filename))
    else:
        for filename in os.listdir(input_dir):
            full_path = os.path.join(input_dir, filename)
            if not os.path.isfile(full_path):
                continue
            ext = os.path.splitext(filename)[1].lower()
            if ext in supported_exts:
                files.append(full_path)

    files.sort()
    return files


def build_default_sound_id(relative_path_without_ext):
    # Default ids follow the same underscore style as ui_select, stack_create, etc.
    return slugify_token(relative_path_without_ext.replace("/", "_"))


def build_default_category(relative_path):
    parts = normalize_rel_path(relative_path).split("/")
    if len(parts) > 1:
        return slugify_token(parts[0])
    return "general"


def select_sound_override(relative_path, relative_path_without_ext, default_id):
    metadata = CONFIG.get("sound_metadata", {})
    keys = [
        normalize_rel_path(relative_path_without_ext),
        normalize_rel_path(relative_path),
        default_id,
    ]

    for key in keys:
        if key in metadata:
            return metadata[key]

    return {}


def build_manifest_entry(sound_file, input_dir):
    relative_path = normalize_rel_path(os.path.relpath(sound_file, input_dir))
    stem, _ = os.path.splitext(relative_path)
    default_id = build_default_sound_id(stem)
    category = build_default_category(relative_path)

    entry = {}
    entry.update(CONFIG.get("sound_defaults", {}))
    entry.update(CONFIG.get("category_defaults", {}).get(category, {}))
    entry.update(select_sound_override(relative_path, stem, default_id))

    sound_id = entry.pop("id", default_id)
    category = entry.pop("category", category)

    manifest_path_prefix = CONFIG.get("manifest_path_prefix", "sounds").strip("/")
    manifest_path = normalize_rel_path(f"{manifest_path_prefix}/{relative_path}")

    manifest_entry = {
        "id": sound_id,
        "category": category,
        "path": manifest_path,
    }

    for key, value in entry.items():
        if value is not None:
            manifest_entry[key] = value

    return manifest_entry


def write_sounds_manifest(output_dir, manifest_entries):
    manifest_path = os.path.join(output_dir, CONFIG["sounds_manifest_filename"])
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest_entries, handle, indent=2)
        handle.write("\n")

    print(f"Saved manifest: {manifest_path}")
    return manifest_path


def build_archive_entries(sound_files, input_dir, manifest_path):
    archive_sound_root = CONFIG.get("archive_sound_root", "sounds").strip("/")
    files_to_include = []

    for sound_file in sound_files:
        relative_path = normalize_rel_path(os.path.relpath(sound_file, input_dir))
        archive_name = normalize_rel_path(f"{archive_sound_root}/{relative_path}")
        files_to_include.append((sound_file, archive_name))

    if manifest_path:
        files_to_include.append(
            (manifest_path, os.path.basename(CONFIG["sounds_manifest_filename"]))
        )

    return files_to_include


def create_zip_bundle(bundle_path, files_to_include):
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for local_path, archive_name in files_to_include:
            zf.write(local_path, arcname=archive_name)

    print(f"Saved zip bundle: {bundle_path}")
    return bundle_path


def run():
    args = parse_cli_args(sys.argv)
    if args["config"]:
        load_config_file(args["config"])

    input_dir = CONFIG["input_dir"]
    output_dir = CONFIG["output_dir"]

    if not os.path.isdir(input_dir):
        raise FileNotFoundError(f"Input directory does not exist: {input_dir}")

    ensure_dir(output_dir)

    sound_files = list_sound_files(input_dir)
    if not sound_files:
        print("No sound files found.")
        return
    print(f"Found {len(sound_files)} sound file(s).")
    for sound_file in sound_files:
        relative_path = normalize_rel_path(os.path.relpath(sound_file, input_dir))
        print(f" - {relative_path}")

    manifest_entries = [build_manifest_entry(path, input_dir) for path in sound_files]

    manifest_path = None
    if CONFIG.get("write_sounds_manifest", True):
        manifest_path = write_sounds_manifest(output_dir, manifest_entries)

    zip_filename = CONFIG["azure_zip_filename"]
    zip_path = os.path.join(output_dir, zip_filename)
    archive_entries = build_archive_entries(sound_files, input_dir, manifest_path)
    create_zip_bundle(zip_path, archive_entries)

    if CONFIG.get("upload_to_azure"):
        blob_service_client = get_blob_service_client()
        container_client = ensure_blob_container(blob_service_client)
        zip_blob_name = build_blob_name(zip_filename)
        upload_file_to_azure(container_client, zip_path, zip_blob_name)


if __name__ == "__main__":
    run()
