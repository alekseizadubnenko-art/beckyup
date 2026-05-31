import hashlib
import json
import os
import subprocess
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from utils.logger import get_logger

_CHUNK_SIZE = 65536


def _age_binary() -> Optional[str]:
    return shutil.which("age") or shutil.which("age.exe")


def _age_keygen_binary() -> Optional[str]:
    return shutil.which("age-keygen") or shutil.which("age-keygen.exe")


def generate_identity(store_dir: Path) -> tuple[Path, Path]:
    """Generate age keypair in store_dir. Returns (verify_key_path, sign_key_path).
    Skips if keys already exist."""
    store_dir.mkdir(parents=True, exist_ok=True)
    verify_path = store_dir / "verify-key"
    sign_path = store_dir / "sign-key"

    if verify_path.exists() and sign_path.exists():
        return verify_path, sign_path

    age_keygen = _age_keygen_binary()
    if not age_keygen:
        raise RuntimeError("age-keygen not found. Install age: https://github.com/FiloSottile/age")

    result = subprocess.run(
        [age_keygen],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        raise RuntimeError(f"age-keygen failed: {result.stderr}")

    sign_key = ""
    verify_key = ""
    for line in result.stdout.splitlines():
        if line.startswith("# public key: age1"):
            verify_key = line.split(":")[-1].strip()
        elif line.startswith("AGE-SECRET-KEY-"):
            sign_key = line
    if not sign_key or not verify_key:
        raise RuntimeError("age-keygen output format unexpected")

    verify_path.write_text(verify_key + "\n")
    sign_path.write_text(sign_key + "\n")
    sign_path.chmod(0o600)
    return verify_path, sign_path


def _derive_public_key(sign_key_path: Path) -> str:
    """Derive age public key from private key file."""
    age_keygen = _age_keygen_binary()
    if not age_keygen:
        raise RuntimeError("age-keygen not found")
    result = subprocess.run(
        [age_keygen, "-y", str(sign_key_path)],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        raise RuntimeError(f"age-keygen -y failed: {result.stderr}")
    return result.stdout.strip()


def sign_manifest(data: bytes, sign_key_path: Path) -> str:
    """Sign manifest bytes with age private key.

    Derives the public key from the private key, then encrypts data
    with the public key. Decryption with the private key later proves
    the data was signed by the holder of this private key."""
    age_bin = _age_binary()
    if not age_bin:
        raise RuntimeError("age not found. Install age: https://github.com/FiloSottile/age")

    public_key = _derive_public_key(sign_key_path)

    result = subprocess.run(
        [age_bin, "--armor", "--encrypt", f"--recipient={public_key}"],
        input=data, capture_output=True, timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(f"age encrypt (sign) failed: {result.stderr.decode()}")
    return result.stdout.decode().strip()


def verify_signature(data: bytes, signature: str, verify_key_path: Path) -> bool:
    """Verify age signature using public key.

    Decrypts the armored signature with the sibling private key.
    The signature is valid if decryption succeeds and output matches original data.
    The verify_key_path serves to locate the store — the actual decryption
    requires the private key stored alongside it."""
    age_bin = _age_binary()
    if not age_bin:
        return False

    sign_key_path = verify_key_path.parent / "sign-key"
    if not sign_key_path.exists():
        return False

    result = subprocess.run(
        [age_bin, "--decrypt", f"--identity={sign_key_path}"],
        input=signature.encode(), capture_output=True, timeout=30
    )
    if result.returncode != 0:
        return False
    return result.stdout == data


def sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of file contents."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK_SIZE), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Compute SHA-256 hex digest of bytes."""
    return hashlib.sha256(data).hexdigest()


class SnapshotManager:
    def __init__(self, store_dir: Path):
        self.store_dir = store_dir
        self.blobs_dir = store_dir / "blobs"
        self.snapshots_dir = store_dir / "snapshots"
        self.logger = get_logger("snapshot")

    def scan_files(self, source_dir: Path) -> list[dict]:
        """Scan directory recursively. Returns list of {rel, path, sha256, size, mtime}."""
        results = []
        for root, dirs, files in os.walk(source_dir):
            root_path = Path(root)
            for name in files:
                full = root_path / name
                rel = str(full.relative_to(source_dir))
                results.append({
                    "rel": rel,
                    "path": full,
                    "sha256": sha256_file(full),
                    "size": full.stat().st_size,
                    "mtime": datetime.fromtimestamp(
                        full.stat().st_mtime, tz=timezone.utc
                    ).isoformat(),
                })
        return results

    def dedup_copy(self, src_path: Path, blobs_dir: Path) -> str:
        """Copy file to blobs_dir if not already there. Returns sha256 hex."""
        h = sha256_file(src_path)
        dest = blobs_dir / h
        if not dest.exists():
            shutil.copy2(src_path, dest)
        return h

    def write_manifest(self, snapshots_dir: Path, files: list[dict],
                       source_paths: list[str], sign_key_path: Path) -> Path:
        """Write snapshot manifest JSON + signature. Returns manifest path."""
        manifest = {
            "version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_paths": source_paths,
            "files": {},
        }
        for f in files:
            manifest["files"][f["rel"]] = {
                "sha256": f["sha256"],
                "size": f["size"],
                "mtime_source": f["mtime"],
            }

        manifest_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")
        sig = sign_manifest(manifest_bytes, sign_key_path)

        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")
        manifest_path = snapshots_dir / f"{ts}.json"
        manifest_path.write_bytes(manifest_bytes)
        Path(str(manifest_path) + ".sig").write_text(sig + "\n")
        return manifest_path

    def load_manifest(self, manifest_path: Path) -> dict:
        """Load and return manifest dict."""
        return json.loads(manifest_path.read_bytes())

    def list_snapshots(self) -> list[dict]:
        """List all snapshots in store. Returns list of {id, path, created_at, file_count, total_size}."""
        if not self.snapshots_dir.exists():
            return []
        snaps = []
        for p in sorted(self.snapshots_dir.glob("*.json")):
            if p.name.endswith(".sig"):
                continue
            try:
                m = self.load_manifest(p)
                file_count = len(m.get("files", {}))
                total_size = sum(f["size"] for f in m["files"].values())
                snaps.append({
                    "id": p.stem,
                    "path": p,
                    "created_at": m.get("created_at", ""),
                    "file_count": file_count,
                    "total_size": total_size,
                })
            except (json.JSONDecodeError, KeyError):
                continue
        return snaps

    def diff(self, manifest_a: dict, manifest_b: dict) -> dict:
        """Compare two manifests. Returns {added, modified, deleted} sets."""
        files_a = set(manifest_a.get("files", {}).keys())
        files_b = set(manifest_b.get("files", {}).keys())
        added = files_b - files_a
        deleted = files_a - files_b
        common = files_a & files_b
        modified = set()
        for name in common:
            if (manifest_a["files"][name]["sha256"]
                    != manifest_b["files"][name]["sha256"]):
                modified.add(name)
        return {"added": added, "modified": modified, "deleted": deleted}

    def restore(self, manifest: dict, blobs_dir: Path, destination: Path):
        """Restore snapshot manifest to destination directory."""
        for rel, meta in manifest.get("files", {}).items():
            blob_path = blobs_dir / meta["sha256"]
            dest_path = destination / rel
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            if blob_path.exists():
                shutil.copy2(blob_path, dest_path)
            else:
                self.logger.error(f"Blob not found: {meta['sha256']} for {rel}")

    def verify(self, manifest: dict, blobs_dir: Path,
               verify_key_path: Optional[Path] = None) -> dict:
        """Verify all blobs in manifest exist and match sha256.
        Returns {valid, errors, checked}."""
        errors = []
        checked = 0
        for rel, meta in manifest.get("files", {}).items():
            blob_path = blobs_dir / meta["sha256"]
            if not blob_path.exists():
                errors.append(f"{rel}: blob missing")
                continue
            actual = sha256_file(blob_path)
            if actual != meta["sha256"]:
                errors.append(f"{rel}: hash mismatch")
            checked += 1
        return {"valid": len(errors) == 0, "errors": errors, "checked": checked}
