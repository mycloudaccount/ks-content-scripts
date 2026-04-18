import argparse
import json
import os
import uuid
from datetime import datetime, timezone


DEFAULT_STORAGE_ACCOUNT_NAME = "ksstorage"
DEFAULT_CONTAINER_NAME = "editor-messages"
DEFAULT_BLOB_NAME = "messages.json"

DEFAULT_DOCUMENT = {
    "version": 1,
    "updatedAt": None,
    "messages": [
        {
            "id": "welcome-2026-04",
            "audience": "all",
            "title": "Messages are live",
            "body": "Upgrade notes, new stamps, and editor news will appear here.",
            "kind": "news",
            "severity": "info",
            "startsAt": "2026-04-16T00:00:00Z",
            "expiresAt": None,
            "dismissible": True,
            "action": None,
            "createdAt": "2026-04-16T00:00:00Z",
        }
    ],
}


def utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def prompt_text(label, default=None, required=False):
    suffix = f" [{default}]" if default not in (None, "") else ""
    while True:
        value = input(f"{label}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default
        if not required:
            return ""
        print(f"{label} is required.")


def prompt_choice(label, choices, default):
    normalized_choices = {choice.lower(): choice for choice in choices}
    suffix = "/".join(choices)
    while True:
        value = input(f"{label} ({suffix}) [{default}]: ").strip().lower()
        if not value:
            return default
        if value in normalized_choices:
            return normalized_choices[value]
        print(f"Choose one of: {', '.join(choices)}")


def prompt_bool(label, default=True):
    default_label = "Y/n" if default else "y/N"
    while True:
        value = input(f"{label} ({default_label}): ").strip().lower()
        if not value:
            return default
        if value in {"y", "yes", "true", "1"}:
            return True
        if value in {"n", "no", "false", "0"}:
            return False
        print("Enter yes or no.")


def get_blob_service_client(account_name, connection_string=None):
    try:
        from azure.storage.blob import BlobServiceClient
    except ImportError as exc:
        raise RuntimeError(
            "Azure Blob package is not installed. Install with: "
            "python -m pip install azure-storage-blob"
        ) from exc

    if connection_string:
        return BlobServiceClient.from_connection_string(connection_string)

    try:
        from azure.identity import DefaultAzureCredential
    except ImportError as exc:
        raise RuntimeError(
            "Azure Identity package is not installed. Install with: "
            "python -m pip install azure-identity"
        ) from exc

    account_url = f"https://{account_name}.blob.core.windows.net"
    credential = DefaultAzureCredential()
    return BlobServiceClient(account_url=account_url, credential=credential)


def ensure_blob_container(blob_service_client, container_name):
    from azure.core.exceptions import ResourceExistsError

    container_client = blob_service_client.get_container_client(container_name)
    try:
        container_client.create_container()
        print(f"Created Azure container: {container_name}")
    except ResourceExistsError:
        pass
    except Exception as exc:
        raise RuntimeError(
            f"Could not create or access container '{container_name}': {exc}"
        ) from exc
    return container_client


def blob_exists(blob_client):
    try:
        return blob_client.exists()
    except Exception as exc:
        raise RuntimeError(f"Could not check blob existence: {exc}") from exc


def list_container_blobs(container_client):
    try:
        return list(container_client.list_blobs())
    except Exception:
        return []


def load_document(blob_client):
    try:
        downloader = blob_client.download_blob()
        raw = downloader.readall().decode("utf-8")
    except Exception as exc:
        raise RuntimeError(f"Could not download existing messages blob: {exc}") from exc

    if not raw.strip():
        return create_default_document()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Existing blob is not valid JSON: {exc}") from exc

    return normalize_document(data)


def create_default_document():
    document = json.loads(json.dumps(DEFAULT_DOCUMENT))
    document["updatedAt"] = utc_now_iso()
    return document


def normalize_document(data):
    if not isinstance(data, dict):
        raise RuntimeError("Messages document must be a JSON object.")

    messages = data.get("messages")
    if messages is None and isinstance(data.get("items"), list):
        messages = data["items"]
    if messages is None:
        messages = []
    if not isinstance(messages, list):
        raise RuntimeError("'messages' must be a JSON array.")

    return {
        "version": int(data.get("version") or 1),
        "updatedAt": data.get("updatedAt") or utc_now_iso(),
        "messages": messages,
    }


def upload_document(blob_client, document):
    from azure.storage.blob import ContentSettings

    document["updatedAt"] = utc_now_iso()
    payload = json.dumps(document, indent=2) + "\n"
    blob_client.upload_blob(
        payload.encode("utf-8"),
        overwrite=True,
        content_settings=ContentSettings(content_type="application/json"),
    )
    print(f"Uploaded {len(document['messages'])} message(s) to {blob_client.blob_name}")


def build_message(existing_messages):
    now = utc_now_iso()
    title = prompt_text("Title", required=True)
    body = prompt_text("Body", required=True)
    kind = prompt_choice(
        "Kind",
        ["news", "upgrade", "newStamp", "maintenance", "warning"],
        "news",
    )
    severity = prompt_choice(
        "Severity",
        ["info", "success", "warning", "critical"],
        "info",
    )
    audience = prompt_text("Audience", "all")
    starts_at = prompt_text("Starts at UTC ISO", now)
    expires_at = prompt_text("Expires at UTC ISO, blank for none", "")
    dismissible = prompt_bool("Dismissible", True)

    action = None
    if prompt_bool("Add action button", False):
        action_label = prompt_text("Action label", required=True)
        action_url = prompt_text("Action URL, blank for none", "")
        action_route = prompt_text("Action route, blank for none", "")
        action = {"label": action_label}
        if action_url:
            action["url"] = action_url
        if action_route:
            action["route"] = action_route

    default_id = str(uuid.uuid4())
    existing_ids = {
        message.get("id")
        for message in existing_messages
        if isinstance(message, dict)
    }
    message_id = prompt_text("Message id", default_id)
    if message_id in existing_ids:
        print(f"Message id '{message_id}' already exists.")
        if not prompt_bool("Overwrite existing message with this id", False):
            raise RuntimeError("Cancelled because message id already exists.")

    return {
        "id": message_id,
        "audience": audience,
        "title": title,
        "body": body,
        "kind": kind,
        "severity": severity,
        "startsAt": starts_at,
        "expiresAt": expires_at or None,
        "dismissible": dismissible,
        "action": action,
        "createdAt": now,
    }


def upsert_message(document, message):
    messages = document["messages"]
    for index, existing in enumerate(messages):
        if isinstance(existing, dict) and existing.get("id") == message["id"]:
            messages[index] = message
            return "updated"

    messages.insert(0, message)
    return "added"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Push a client message to Azure Blob Storage."
    )
    parser.add_argument("--account-name", default=DEFAULT_STORAGE_ACCOUNT_NAME)
    parser.add_argument("--container", default=DEFAULT_CONTAINER_NAME)
    parser.add_argument("--blob", default=DEFAULT_BLOB_NAME)
    parser.add_argument(
        "--connection-string",
        default=os.environ.get("AZURE_STORAGE_CONNECTION_STRING"),
        help=(
            "Azure Storage connection string. Defaults to the "
            "AZURE_STORAGE_CONNECTION_STRING environment variable. If omitted, "
            "DefaultAzureCredential is used."
        ),
    )
    parser.add_argument(
        "--init-only",
        action="store_true",
        help="Create messages.json if missing, but do not prompt for a new message.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    auth_mode = (
        "connection string"
        if args.connection_string
        else "DefaultAzureCredential"
    )
    print(
        "Azure target: "
        f"account={args.account_name}, container={args.container}, "
        f"blob={args.blob}, auth={auth_mode}"
    )
    blob_service_client = get_blob_service_client(
        args.account_name,
        args.connection_string,
    )
    container_client = ensure_blob_container(blob_service_client, args.container)
    blob_client = container_client.get_blob_client(args.blob)

    if not blob_exists(blob_client):
        blob_count = len(list_container_blobs(container_client))
        document = create_default_document()
        upload_document(blob_client, document)
        print(
            f"No {args.blob} blob was found. "
            f"Initialized default document in container '{args.container}' "
            f"({blob_count} existing blob(s) in container)."
        )
        return

    document = load_document(blob_client)
    print(f"Current message count: {len(document['messages'])}")
    message = build_message(document["messages"])
    action = upsert_message(document, message)
    upload_document(blob_client, document)
    print(f"Message {action}: {message['id']}")


if __name__ == "__main__":
    main()
