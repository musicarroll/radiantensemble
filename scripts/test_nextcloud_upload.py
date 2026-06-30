#!/usr/bin/env python3
"""Upload one local file to the configured Nextcloud uploads directory."""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
from urllib.parse import quote

import requests
from requests.exceptions import SSLError


BASE_DIR = Path(__file__).resolve().parent.parent


def load_local_config() -> object:
    config_path = BASE_DIR / ".env" / "config.py"
    if not config_path.exists():
        return object()

    spec = importlib.util.spec_from_file_location("radiantensemble_local_config", config_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {config_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LOCAL_CONFIG = load_local_config()


def config_value(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value not in (None, ""):
        return value
    value = getattr(LOCAL_CONFIG, name, "")
    if value not in (None, ""):
        return str(value)
    return default


def build_remote_url(base_url: str, username: str, remote_path: str) -> str:
    base_url = base_url.rstrip("/")
    safe_username = quote(username.strip("/"), safe="")
    safe_path = "/".join(quote(part, safe="") for part in remote_path.strip("/").split("/"))
    return f"{base_url}/remote.php/dav/files/{safe_username}/{safe_path}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload a local file to Nextcloud using WebDAV PUT."
    )
    parser.add_argument("file", type=Path, help="Local file to upload, for example /tmp/test.pdf")
    parser.add_argument(
        "--remote-path",
        default=".env/test.pdf",
        help="Remote path inside the Nextcloud user's files area. Default: .env/test.pdf",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Request timeout in seconds. Default: 60",
    )
    parser.add_argument(
        "--ca-bundle",
        type=Path,
        help="Path to a PEM CA bundle that should be trusted for this request.",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Skip TLS certificate verification. Use only for temporary local testing.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    username = config_value("NEXTCLOUD_USERNAME")
    app_password = config_value("NEXTCLOUD_APP_PASSWORD")
    base_url = config_value("NEXTCLOUD_BASE_URL", "https://nextcloud.radiantensemble.com")

    missing = [
        name
        for name, value in (
            ("NEXTCLOUD_USERNAME", username),
            ("NEXTCLOUD_APP_PASSWORD", app_password),
        )
        if not value
    ]
    if missing:
        names = ", ".join(missing)
        print(f"Missing required config value(s): {names}")
        print("Add them to .env/config.py or export them in the shell environment.")
        return 2

    local_file = args.file.expanduser()
    if not local_file.is_file():
        print(f"Local file does not exist or is not a regular file: {local_file}")
        return 2

    if args.insecure and args.ca_bundle:
        print("Use either --insecure or --ca-bundle, not both.")
        return 2

    verify: bool | str = True
    if args.insecure:
        verify = False
    elif args.ca_bundle:
        ca_bundle = args.ca_bundle.expanduser()
        if not ca_bundle.is_file():
            print(f"CA bundle does not exist or is not a regular file: {ca_bundle}")
            return 2
        verify = str(ca_bundle)

    url = build_remote_url(base_url, username, args.remote_path)
    try:
        with local_file.open("rb") as file_obj:
            response = requests.put(
                url,
                data=file_obj,
                auth=(username, app_password),
                timeout=args.timeout,
                verify=verify,
            )
    except SSLError as exc:
        print("TLS certificate verification failed.")
        print(f"URL: {base_url}")
        print(f"Error: {exc}")
        print("If this server uses an internal CA, pass it with --ca-bundle /path/to/ca.pem.")
        print("For a temporary connectivity test only, rerun with --insecure.")
        return 1

    print(f"PUT {args.remote_path}")
    print(f"Status: {response.status_code}")
    if response.text.strip():
        print(response.text[:500])
    return 0 if response.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
