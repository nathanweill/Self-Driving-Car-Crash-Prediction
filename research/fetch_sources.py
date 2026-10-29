"""Cache public evidence with hashes. No credentials or browser state are used."""
import argparse
import hashlib
import json
import ssl
import certifi
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent


def fetch(url, name, description=""):
    target = ROOT / "raw" / name
    if target.is_absolute() and not target.resolve().is_relative_to((ROOT / "raw").resolve()):
        raise ValueError("Download name must stay within research/raw")
    manifest = ROOT / "sources.json"
    records = json.loads(manifest.read_text()) if manifest.exists() else {}
    if target.exists():
        prior = records.get(name)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if not prior or prior["url"] != url or prior["sha256"] != digest:
            raise ValueError(f"Existing file lacks matching provenance: {name}")
        print(f"cached {name} ({target.stat().st_size} bytes)")
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": "AVCrashResearch/1.0 public academic data review"})
    # Verify TLS against the local environment's maintained CA bundle.
    with urlopen(request, timeout=90, context=ssl.create_default_context(cafile=certifi.where())) as response:
        payload = response.read()
        record = {
            "url": url,
            "resolved_url": response.url,
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": response.status,
            "content_type": response.headers.get("Content-Type"),
            "last_modified": response.headers.get("Last-Modified"),
            "etag": response.headers.get("ETag"),
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "description": description,
        }
    prior = records.get(name)
    if prior and (prior['url'] != url or prior['sha256'] != record['sha256']):
        raise ValueError(f"Source changed since recorded retrieval: {name}; preserve the pinned manifest and use a new filename for a new version")
    target.write_bytes(payload)
    if prior:
        print(f"restored pinned {name} ({len(payload)} bytes)")
        return target
    records[name] = record
    manifest.write_text(json.dumps(records, indent=2) + "\n")
    print(f"downloaded {name} ({len(payload)} bytes)")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("name")
    parser.add_argument("--description", default="")
    args = parser.parse_args()
    fetch(args.url, args.name, args.description)
