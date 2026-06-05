
import json
import os
import sys
import httpx
from pathlib import Path

def push_collection():
    # Load env vars manually from .env if not in environment
    env_vars = {}
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, v = line.strip().split("=", 1)
                    env_vars[k] = v.strip().strip('"').strip("'")

    api_key = os.getenv("POSTMAN_API_KEY") or env_vars.get("POSTMAN_API_KEY")
    collection_uid = os.getenv("POSTMAN_COLLECTION_UID") or env_vars.get("POSTMAN_COLLECTION_UID")
    
    if not api_key or not collection_uid:
        print("ERROR: POSTMAN_API_KEY or POSTMAN_COLLECTION_UID not found in env or .env")
        sys.exit(1)

    collection_path = Path("tests/postman/spectre-api-v1.postman_collection.json")
    if not collection_path.exists():
        print(f"ERROR: Collection file not found at {collection_path}")
        sys.exit(1)

    try:
        with open(collection_path, "r", encoding="utf-8") as f:
            collection_data = json.load(f)
    except Exception as e:
        print(f"ERROR: Failed to parse collection JSON: {e}")
        sys.exit(1)

    payload = {"collection": collection_data}
    
    url = f"https://api.getpostman.com/collections/{collection_uid}"
    headers = {
        "X-Api-Key": api_key,
        "Content-Type": "application/json"
    }

    print(f"Pushing collection to Postman (UID: {collection_uid})...")
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.put(url, headers=headers, json=payload)
            
        if resp.status_code == 200:
            print("SUCCESS: Collection updated on Postman cloud.")
        else:
            print(f"FAILED: HTTP {resp.status_code}")
            print(resp.text)
            sys.exit(1)
    except Exception as e:
        print(f"ERROR: Request failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    push_collection()
