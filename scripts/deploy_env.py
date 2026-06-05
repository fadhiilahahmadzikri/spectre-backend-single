#!/usr/bin/env python3
"""
Spectre — HF Space Environment Deployer
========================================
Single-purpose script to push .env secrets to a HuggingFace Space.

Usage:
    python scripts/deploy_env.py                          # Interactive (auto-detect .env.spaces)
    python scripts/deploy_env.py --env .env.spaces        # Specify env file
    python scripts/deploy_env.py --env .env.spaces --yes  # Skip confirmation
    python scripts/deploy_env.py --list                   # List current secrets on HF
    python scripts/deploy_env.py --delete KEY_NAME        # Delete a secret

Requires:
    pip install huggingface_hub
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    from huggingface_hub import HfApi
except ImportError:
    print("ERROR: pip install huggingface_hub")
    sys.exit(1)


# ── Config ───────────────────────────────────────────────────────────────────
SPACE_ID = "thewhitenigs/spectre-backend"
DEFAULT_ENV_FILE = ".env.spaces"
SKIP_VALUES = {"set-via-hf-secrets", "<CHANGE_THIS>", "", "changeme"}


def get_api() -> tuple[HfApi, str]:
    """Authenticate with HuggingFace and return (api, username)."""
    api = HfApi()
    try:
        user = api.whoami()
        return api, user["name"]
    except Exception:
        print("ERROR: Not authenticated. Run: huggingface-cli login")
        sys.exit(1)


def parse_env_file(filepath: Path) -> dict[str, str]:
    """Parse a .env file into a dict, skipping comments and placeholder values."""
    secrets: dict[str, str] = {}
    if not filepath.exists():
        print(f"ERROR: File not found: {filepath}")
        sys.exit(1)

    with open(filepath, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue

            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")

            # Validate key format
            if not re.match(r"^[a-zA-Z][_a-zA-Z0-9]*$", key):
                continue

            # Skip placeholder values
            if val.lower() in SKIP_VALUES or val.startswith("<CHANGE_THIS"):
                continue

            secrets[key] = val

    return secrets


def list_secrets(api: HfApi, repo_id: str) -> list[str]:
    """List secret keys on the HF Space."""
    try:
        if hasattr(api, "list_space_secrets"):
            return [s.key for s in api.list_space_secrets(repo_id=repo_id)]
        # Fallback via REST API
        import requests
        token = getattr(api, "token", None)
        if not token:
            from huggingface_hub import HfFolder
            token = HfFolder.get_token()
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        resp = requests.get(
            f"https://huggingface.co/api/spaces/{repo_id}/secrets",
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 200:
            return list(resp.json().keys())
        return []
    except Exception:
        return []


def cmd_push(args: argparse.Namespace) -> None:
    """Push env secrets to HF Space."""
    api, username = get_api()
    repo_id = args.repo or SPACE_ID
    env_path = Path(args.env).expanduser().resolve()

    print(f"╔══════════════════════════════════════════════╗")
    print(f"║  Spectre — HF Space Env Deployer             ║")
    print(f"╚══════════════════════════════════════════════╝")
    print(f"  User     : {username}")
    print(f"  Space    : {repo_id}")
    print(f"  Env file : {env_path}")
    print()

    secrets = parse_env_file(env_path)
    if not secrets:
        print("No valid secrets found in file.")
        sys.exit(0)

    # Display preview
    print(f"  Found {len(secrets)} secrets to push:")
    print(f"  {'─' * 50}")
    for key, val in secrets.items():
        preview = val[:30] + "..." if len(val) > 30 else val
        print(f"  {key:<35} = {preview}")
    print(f"  {'─' * 50}")
    print()

    if not args.yes:
        confirm = input(f"  Push {len(secrets)} secrets to {repo_id}? [y/N] ").strip().lower()
        if confirm not in ("y", "yes"):
            print("  Cancelled.")
            sys.exit(0)

    # Push secrets
    print()
    success = 0
    failed = 0
    for key, value in secrets.items():
        try:
            api.add_space_secret(repo_id=repo_id, key=key, value=value)
            print(f"  ✓ {key}")
            success += 1
        except Exception as e:
            print(f"  ✗ {key} — {str(e)[:60]}")
            failed += 1

    print()
    print(f"  Done: {success} pushed, {failed} failed.")
    if success > 0:
        print(f"  Space will rebuild automatically.")


def cmd_list(args: argparse.Namespace) -> None:
    """List current secrets on HF Space."""
    api, username = get_api()
    repo_id = args.repo or SPACE_ID

    print(f"  Secrets on {repo_id}:")
    print(f"  {'─' * 40}")

    keys = list_secrets(api, repo_id)
    if not keys:
        print("  (none found or access denied)")
    else:
        for i, key in enumerate(keys, 1):
            print(f"  {i:3}. {key}")
    print(f"  {'─' * 40}")
    print(f"  Total: {len(keys)} secrets")


def cmd_delete(args: argparse.Namespace) -> None:
    """Delete a secret from HF Space."""
    api, _ = get_api()
    repo_id = args.repo or SPACE_ID
    key = args.delete

    confirm = input(f"  Delete '{key}' from {repo_id}? [y/N] ").strip().lower()
    if confirm not in ("y", "yes"):
        print("  Cancelled.")
        return

    try:
        api.delete_space_secret(repo_id=repo_id, key=key)
        print(f"  ✓ Deleted: {key}")
    except Exception as e:
        print(f"  ✗ Failed: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Spectre — Push .env secrets to HuggingFace Space",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/deploy_env.py                           # Push .env.spaces (interactive)
  python scripts/deploy_env.py --env .env.production     # Push custom env file
  python scripts/deploy_env.py --yes                     # Skip confirmation
  python scripts/deploy_env.py --list                    # List current secrets
  python scripts/deploy_env.py --delete SECRET_KEY       # Delete a secret
  python scripts/deploy_env.py --repo user/other-space   # Target different space
        """,
    )
    parser.add_argument(
        "--env", "-e",
        default=DEFAULT_ENV_FILE,
        metavar="FILE",
        help=f"Path to .env file (default: {DEFAULT_ENV_FILE})",
    )
    parser.add_argument(
        "--repo", "-r",
        default=None,
        metavar="USER/SPACE",
        help=f"Target HF Space (default: {SPACE_ID})",
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip confirmation prompt",
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        dest="list_secrets",
        help="List current secrets on the Space",
    )
    parser.add_argument(
        "--delete", "-d",
        metavar="KEY",
        help="Delete a specific secret",
    )

    args = parser.parse_args()

    if args.list_secrets:
        cmd_list(args)
    elif args.delete:
        cmd_delete(args)
    else:
        cmd_push(args)


if __name__ == "__main__":
    main()
