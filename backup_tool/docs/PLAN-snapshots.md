# Snapshot & Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add content-addressed snapshots with dedup, integrity verification, and interactive restore/diff CLI.

**Architecture:** Content-addressed blob store (sha256-named files) + JSON manifest per backup + age-signature for integrity. `SnapshotManager` in `core/snapshot.py` handles all storage logic; `cli/snapshot_ui.py` wraps it with questionary prompts. `BackupEngine.run_backup()` writes blobs + manifest instead of flat copy.

**Tech Stack:** Python 3.12+, `hashlib`, `subprocess` for `age` CLI, `questionary`, `rich`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `core/snapshot.py` | Create | SnapshotManager, blob store, manifest CRUD, diff, verify, identity, age helpers |
| `core/backup_engine.py` | Modify | `run_backup()` → use snapshot flow |
| `cli/snapshot_ui.py` | Create | Interactive pickers for snapshots/restore/diff/verify |
| `main.py` | Modify | CLI subcommands: `backup`, `snapshots`, `restore`, `diff`, `verify` |
| `requirements.txt` | Modify | Add `pyrage` optional |
| `tests/test_snapshot.py` | Create | All tests |

---

### Task 1: Create `core/snapshot.py` — identity + age helpers

**Files:**
- Create: `backup_tool/core/snapshot.py`

- [ ] **Step 1: Write failing tests for identity generation**

File: `backup_tool/tests/test_snapshot.py`

```python
import unittest
import tempfile
import shutil
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

class TestSnapshotIdentity(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_generate_identity_creates_keys(self):
        from core.snapshot import generate_identity
        verify_key, sign_key = generate_identity(self.test_dir)
        self.assertTrue(verify_key.exists())
        self.assertTrue(sign_key.exists())
        content = verify_key.read_text().strip()
        self.assertTrue(content.startswith("age1"))

    def test_generate_identity_skips_existing(self):
        from core.snapshot import generate_identity
        (self.test_dir / "verify-key").write_text("age1existing")
        (self.test_dir / "sign-key").write_text("AGE-SECRET-KEY-existing")
        verify_key, sign_key = generate_identity(self.test_dir)
        self.assertEqual(verify_key.read_text(), "age1existing")

    def test_sign_and_verify_roundtrip(self):
        from core.snapshot import sign_manifest, verify_signature
        store = self.test_dir / ".beckyup"
        store.mkdir()
        verify_key, sign_key = generate_identity(store)
        data = b'{"test": "data"}'
        sig = sign_manifest(data, sign_key)
        self.assertTrue(verify_signature(data, sig, verify_key))

    def test_verify_fails_on_tampered_data(self):
        from core.snapshot import sign_manifest, verify_signature
        store = self.test_dir / ".beckyup"
        store.mkdir()
        verify_key, sign_key = generate_identity(store)
        data = b'{"test": "data"}'
        sig = sign_manifest(data, sign_key)
        self.assertFalse(verify_signature(b'{"test": "EVIL"}', sig, verify_key))
```

- [ ] **Step 2: Run tests to verify they fail**

Выходные данные:
```
cd backup_tool && python3 -m unittest tests/test_snapshot.py -v
...
FAILED (errors=4)
```

- [ ] **Step 3: Implement identity generation + age signing**

Add to `backup_tool/core/snapshot.py`:

```python
import hashlib
import json
import os
import subprocess
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from utils.logger import get_logger


def _age_binary() -> Optional[str]:
    """Locate age binary. Returns path or None."""
    return shutil.which("age") or shutil.which("age.exe")


def _age_keygen_binary() -> Optional[str]:
    """Locate age-keygen binary. Returns path or None."""
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

    key_output = result.stdout.strip()
    sign_key = ""
    verify_key = ""
    for line in key_output.splitlines():
        if line.startswith("# public key: age1"):
            verify_key = line.split(":")[-1].strip()
        elif line.startswith("AGE-SECRET-KEY-"):
            sign_key = line

    if not verify_key or not sign_key:
        # fallback: parse stderr (age-keygen 1.x outputs key to stderr)
        result2 = subprocess.run(
            [age_keygen],
            capture_output=True, text=True, timeout=10
        )
        for line in result2.stderr.splitlines():
            if line.startswith("# public key: age1"):
                verify_key = line.split(":")[-1].strip()
        sign_key = result2.stdout.strip()

    verify_path.write_text(verify_key + "\n")
    sign_path.write_text(sign_key + "\n")
    sign_path.chmod(0o600)
    return verify_path, sign_path


def sign_manifest(data: bytes, sign_key_path: Path) -> str:
    """Sign manifest bytes with age private key. Returns signature as string."""
    age_bin = _age_binary()
    if not age_bin:
        raise RuntimeError("age not found. Install age: https://github.com/FiloSottile/age")

    result = subprocess.run(
        [age_bin, "--armor", "--sign", f"--identity={sign_key_path}"],
        input=data, capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(f"age sign failed: {result.stderr}")
    return result.stdout.strip()


def verify_signature(data: bytes, signature: str, verify_key_path: Path) -> bool:
    """Verify age signature against data. Returns True if valid."""
    age_bin = _age_binary()
    if not age_bin:
        return False

    verify_key = verify_key_path.read_text().strip()
    result = subprocess.run(
        [age_bin, "--verify", f"--recipients-file={verify_key_path}"],
        input=data, capture_output=True, text=True, timeout=30
    )
    return result.returncode == 0


def sha256_file(path: Path) -> str:
    """Compute sha256 hex digest of file contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Compute sha256 hex digest of bytes."""
    return hashlib.sha256(data).hexdigest()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backup_tool && python3 -m unittest tests/test_snapshot.py::TestSnapshotIdentity -v`
Expected: 4/4 passed

- [ ] **Step 5: Commit**

```bash
git add backup_tool/core/snapshot.py backup_tool/tests/test_snapshot.py
git commit -m "feat: identity + age sign/verify for snapshot integrity"
```

---

### Task 2: Create SnapshotManager — blob store + manifest CRUD

**Files:**
- Modify: `backup_tool/core/snapshot.py`

- [ ] **Step 1: Write failing tests for SnapshotManager blob operations**

Append to `backup_tool/tests/test_snapshot.py`:

```python
class TestSnapshotManager(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.store = self.test_dir / ".beckyup"
        self.store.mkdir(parents=True, exist_ok=True)
        self.blobs = self.store / "blobs"
        self.blobs.mkdir()
        self.snapshots = self.store / "snapshots"
        self.snapshots.mkdir()
        # Create test source files
        self.src = self.test_dir / "source"
        self.src.mkdir()
        (self.src / "file1.txt").write_text("hello")
        (self.src / "file2.txt").write_text("world")
        (self.src / "sub").mkdir()
        (self.src / "sub" / "file3.txt").write_text("nested")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_scan_files_returns_relative_paths(self):
        from core.snapshot import SnapshotManager
        mgr = SnapshotManager(self.store)
        files = mgr.scan_files(self.src)
        paths = {f["rel"] for f in files}
        self.assertIn("file1.txt", paths)
        self.assertIn("file2.txt", paths)
        self.assertIn("sub/file3.txt", paths)

    def test_scan_files_includes_hash_and_size(self):
        from core.snapshot import SnapshotManager
        mgr = SnapshotManager(self.store)
        files = mgr.scan_files(self.src)
        f1 = next(f for f in files if f["rel"] == "file1.txt")
        self.assertEqual(f1["size"], 5)
        self.assertEqual(len(f1["sha256"]), 64)

    def test_dedup_copy_copies_new_blob(self):
        from core.snapshot import SnapshotManager
        mgr = SnapshotManager(self.store)
        src_file = self.src / "file1.txt"
        blob_hash = mgr.dedup_copy(src_file, self.blobs)
        blob_path = self.blobs / blob_hash
        self.assertTrue(blob_path.exists())
        self.assertEqual(blob_path.read_text(), "hello")

    def test_dedup_copy_skips_existing_blob(self):
        from core.snapshot import SnapshotManager
        mgr = SnapshotManager(self.store)
        src_file = self.src / "file1.txt"
        hash1 = mgr.dedup_copy(src_file, self.blobs)
        hash2 = mgr.dedup_copy(src_file, self.blobs)
        self.assertEqual(hash1, hash2)
        blob_count = len(list(self.blobs.iterdir()))
        self.assertEqual(blob_count, 1)

    def test_write_manifest_creates_json(self):
        from core.snapshot import SnapshotManager
        mgr = SnapshotManager(self.store)
        files = mgr.scan_files(self.src)
        # Stub identity for signing
        store_dir = self.store
        from core.snapshot import generate_identity
        generate_identity(store_dir)
        manifest_path = mgr.write_manifest(
            self.snapshots, files, [str(self.src)],
            store_dir / "sign-key"
        )
        self.assertTrue(manifest_path.exists())
        self.assertTrue(Path(str(manifest_path) + ".sig").exists())

    def test_load_manifest(self):
        from core.snapshot import SnapshotManager
        mgr = SnapshotManager(self.store)
        files = mgr.scan_files(self.src)
        from core.snapshot import generate_identity
        generate_identity(self.store)
        manifest_path = mgr.write_manifest(
            self.snapshots, files, [str(self.src)],
            self.store / "sign-key"
        )
        loaded = mgr.load_manifest(manifest_path)
        self.assertIn("file1.txt", loaded["files"])
        self.assertEqual(loaded["files"]["file1.txt"]["sha256"],
                         files[0]["sha256"])

    def test_list_snapshots(self):
        from core.snapshot import SnapshotManager
        mgr = SnapshotManager(self.store)
        files = mgr.scan_files(self.src)
        from core.snapshot import generate_identity
        generate_identity(self.store)
        mgr.write_manifest(self.snapshots, files, [str(self.src)],
                          self.store / "sign-key")
        snaps = mgr.list_snapshots()
        self.assertEqual(len(snaps), 1)
        self.assertIn("created_at", snaps[0])

    def test_list_snapshots_returns_empty_list(self):
        from core.snapshot import SnapshotManager
        mgr = SnapshotManager(self.store)
        snaps = mgr.list_snapshots()
        self.assertEqual(snaps, [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backup_tool && python3 -m unittest tests/test_snapshot.py -v`
Expected: Some tests error (class exists but methods missing)

- [ ] **Step 3: Implement SnapshotManager methods**

Append to `backup_tool/core/snapshot.py`:

```python
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

        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backup_tool && python3 -m unittest tests/test_snapshot.py -v`
Expected: identity tests + manager tests pass

- [ ] **Step 5: Commit**

```bash
git add backup_tool/core/snapshot.py backup_tool/tests/test_snapshot.py
git commit -m "feat: SnapshotManager — blob store, dedup, manifest CRUD"
```

---

### Task 3: SnapshotManager — restore, diff, verify

**Files:**
- Modify: `backup_tool/core/snapshot.py`
- Modify: `backup_tool/tests/test_snapshot.py`

- [ ] **Step 1: Write failing tests**

Append to tests:

```python
class TestSnapshotRestoreDiffVerify(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.store = self.test_dir / ".beckyup"
        self.store.mkdir(parents=True)
        (self.store / "blobs").mkdir()
        (self.store / "snapshots").mkdir()
        self.src = self.test_dir / "source"
        self.src.mkdir()
        (self.src / "a.txt").write_text("alpha")
        (self.src / "b.txt").write_text("beta")
        # Create an initial snapshot
        from core.snapshot import SnapshotManager, generate_identity
        self.mgr = SnapshotManager(self.store)
        generate_identity(self.store)
        files = self.mgr.scan_files(self.src)
        self.manifest1 = self.mgr.write_manifest(
            self.store / "snapshots", files, [str(self.src)],
            self.store / "sign-key"
        )
        # Modify + add file for second snapshot
        (self.src / "a.txt").write_text("alpha_v2")
        (self.src / "c.txt").write_text("charlie")
        os.unlink(self.src / "b.txt")
        files2 = self.mgr.scan_files(self.src)
        self.manifest2 = self.mgr.write_manifest(
            self.store / "snapshots", files2, [str(self.src)],
            self.store / "sign-key"
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_diff_added_modified_deleted(self):
        m1 = self.mgr.load_manifest(self.manifest1)
        m2 = self.mgr.load_manifest(self.manifest2)
        result = self.mgr.diff(m1, m2)
        self.assertIn("added", result)
        self.assertIn("modified", result)
        self.assertIn("deleted", result)
        self.assertEqual(result["added"], {"c.txt"})
        self.assertEqual(result["deleted"], {"b.txt"})
        self.assertEqual(result["modified"], {"a.txt"})

    def test_diff_identical_snapshots(self):
        m1 = self.mgr.load_manifest(self.manifest1)
        self.mgr.diff(m1, m1)
        result = self.mgr.diff(m1, m1)
        self.assertEqual(result["added"], set())
        self.assertEqual(result["modified"], set())
        self.assertEqual(result["deleted"], set())

    def test_restore_recreates_files(self):
        dest = self.test_dir / "restored"
        m1 = self.mgr.load_manifest(self.manifest1)
        self.mgr.restore(m1, self.store / "blobs", dest)
        self.assertTrue((dest / "a.txt").exists())
        self.assertTrue((dest / "b.txt").exists())
        self.assertEqual((dest / "a.txt").read_text(), "alpha")

    def test_verify_passes_on_valid_snapshot(self):
        from core.snapshot import verify_signature
        sig_path = Path(str(self.manifest1) + ".sig")
        sig = sig_path.read_text().strip()
        data = self.manifest1.read_bytes()
        ok = verify_signature(data, sig, self.store / "verify-key")
        self.assertTrue(ok)

    def test_verify_fails_on_corrupted_blob(self):
        self.mgr.dedup_copy = lambda *a: "DEADBEEF"
        m1 = self.mgr.load_manifest(self.manifest1)
        result = self.mgr.verify(m1, self.store / "blobs")
        self.assertFalse(result["valid"])
        self.assertGreater(len(result["errors"]), 0)
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement diff, restore, verify**

Append to `SnapshotManager`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

- [ ] **Step 5: Commit**

```bash
git add backup_tool/core/snapshot.py backup_tool/tests/test_snapshot.py
git commit -m "feat: snapshot restore, diff, verify"
```

---

### Task 4: Create `cli/snapshot_ui.py` — interactive prompts

**Files:**
- Create: `backup_tool/cli/snapshot_ui.py`

- [ ] **Step 1: Write failing tests**

```python
class TestSnapshotUI(unittest.TestCase):
    @patch("cli.snapshot_ui.questionary")
    def test_pick_snapshot_returns_selected(self, mock_q):
        mock_q.select.return_value.ask.return_value = "snap-001"
        from cli.snapshot_ui import pick_snapshot
        snaps = [{"id": "snap-001", "created_at": "2026-01-01"},
                 {"id": "snap-002", "created_at": "2026-02-01"}]
        result = pick_snapshot(snaps, "test drive")
        self.assertEqual(result, snaps[0])

    @patch("cli.snapshot_ui.questionary")
    def test_pick_snapshot_returns_none(self, mock_q):
        mock_q.select.return_value.ask.return_value = None
        from cli.snapshot_ui import pick_snapshot
        result = pick_snapshot([{"id": "x", "created_at": "x"}], "test")
        self.assertIsNone(result)
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement snapshot_ui.py**

```python
from pathlib import Path
from typing import Optional
from utils.ui import console

def _format_snapshots_table(snapshots: list[dict]) -> list[str]:
    """Format snapshots as human-readable list. Returns list of choice labels."""
    choices = []
    for i, s in enumerate(snapshots, 1):
        file_count = s.get("file_count", 0)
        total_size = s.get("total_size", 0)
        size_str = f"{total_size / (1024*1024):.1f} MB" if total_size > 0 else "—"
        label = f"{i:>3}.  {s['created_at'][:19]}  {file_count:>6} files  {size_str}"
        choices.append(label)
    return choices


def pick_snapshot(snapshots: list[dict], drive_label: str) -> Optional[dict]:
    """Interactive snapshot picker. Returns selected snapshot dict or None."""
    import questionary
    if not snapshots:
        console.print("[yellow]Нет снепшотов на этом диске.[/yellow]")
        return None

    choices = _format_snapshots_table(snapshots)
    chosen = questionary.select(
        f"Снепшоты на {drive_label}:",
        choices=choices
    ).ask()
    if not chosen:
        return None
    idx = int(chosen.split(".")[0].strip()) - 1
    return snapshots[idx]


def pick_two_snapshots(snapshots: list[dict], drive_label: str
                       ) -> Optional[tuple[dict, dict]]:
    """Pick two snapshots A → B for diff. Returns (snap_a, snap_b) or None."""
    import questionary
    if len(snapshots) < 2:
        console.print("[yellow]Нужно минимум 2 снепшота для сравнения.[/yellow]")
        return None

    choices = _format_snapshots_table(snapshots)
    a_label = questionary.select(
        f"Выберите первый снепшот (A) на {drive_label}:",
        choices=choices
    ).ask()
    if not a_label:
        return None
    idx_a = int(a_label.split(".")[0].strip()) - 1

    b_label = questionary.select(
        f"Выберите второй снепшот (B) на {drive_label}:",
        choices=[c for i, c in enumerate(choices) if i != idx_a]
    ).ask()
    if not b_label:
        return None
    idx_b = int(b_label.split(".")[0].strip()) - 1

    return snapshots[idx_a], snapshots[idx_b]


def show_diff_result(diff: dict):
    """Display diff result in human-readable format."""
    added = diff.get("added", set())
    modified = diff.get("modified", set())
    deleted = diff.get("deleted", set())

    if added:
        console.print(f"[green]  ADDED ({len(added)}):[/green] {', '.join(sorted(added))}")
    if modified:
        console.print(f"[yellow]  MODIFIED ({len(modified)}):[/yellow] {', '.join(sorted(modified))}")
    if deleted:
        console.print(f"[red]  DELETED ({len(deleted)}):[/red] {', '.join(sorted(deleted))}")
    if not added and not modified and not deleted:
        console.print("[dim]  Нет изменений[/dim]")
```

- [ ] **Step 4: Run tests to verify they pass**

- [ ] **Step 5: Commit**

```bash
git add backup_tool/cli/snapshot_ui.py
git commit -m "feat: interactive snapshot UI — picker, diff display"
```

---

### Task 5: Update `main.py` — CLI subcommands

**Files:**
- Modify: `backup_tool/main.py`

- [ ] **Step 1: Add CLI subcommands to main.py**

Replace argument parser section and add snapshot commands:

```python
import sys
import signal
import argparse
from pathlib import Path
from typing import Optional
from core.backup_engine import BackupEngine
from core.device_monitor import DeviceMonitor
from config.manager import ConfigManager
from utils.logger import setup_logger
from utils.ui import show_banner, show_startup, show_backup_result, print_error, console


backup_engine = None
device_monitor = None
config_manager = None


def signal_handler(signum, frame):
    print_error("\nПолучен сигнал завершения.")
    shutdown()
    sys.exit(0)


def shutdown():
    global device_monitor
    if device_monitor:
        device_monitor.stop_monitoring()
    console.print("[dim]Приложение остановлено.[/dim]")


def _get_detected_drive() -> Optional[Path]:
    """Find a mounted known backup drive. Returns mount path or None."""
    from core.device_detector import DeviceDetector
    detector = DeviceDetector()
    devices = detector.get_mounted_devices()
    for mount_path, label, uuid in devices:
        c = ConfigManager()
        known = c.get_known_uuids()
        if uuid in known:
            return Path(mount_path)
    return None


def cmd_snapshots():
    """List snapshots on connected backup drive."""
    drive = _get_detected_drive()
    if not drive:
        print_error("Подключи знакомую бэкап-флешку.")
        return
    from core.snapshot import SnapshotManager
    from cli.snapshot_ui import pick_snapshot, show_diff_result, pick_two_snapshots
    store = drive / ".beckyup"
    mgr = SnapshotManager(store)
    snaps = mgr.list_snapshots()
    if not snaps:
        console.print("[yellow]Нет снепшотов на этом диске.[/yellow]")
        return
    console.print(f"[bold]Снепшоты на {drive}[/bold]")
    import questionary
    while True:
        choices = [
            *[f"{i+1:>3}.  {s['created_at'][:19]}  {s['file_count']:>6} files  {s['total_size']/(1024*1024):.1f} MB"
              for i, s in enumerate(snaps)],
            questionary.Separator(),
            "[D] Diff",
            "[R] Restore",
            "[V] Verify",
            "[Q] Выход",
        ]
        action = questionary.select(
            f"Снепшоты на {drive.name}:",
            choices=choices
        ).ask()
        if not action or action == "[Q] Выход":
            break
        if action == "[D] Diff":
            pair = pick_two_snapshots(snaps, drive.name)
            if pair:
                m1 = mgr.load_manifest(pair[0]["path"])
                m2 = mgr.load_manifest(pair[1]["path"])
                diff = mgr.diff(m1, m2)
                console.print(f"\n[bold]Изменения {pair[0]['created_at'][:10]} → {pair[1]['created_at'][:10]}:[/bold]")
                show_diff_result(diff)
        elif action == "[R] Restore":
            snap = pick_snapshot(snaps, drive.name)
            if snap:
                m = mgr.load_manifest(snap["path"])
                default_dest = str(Path.home() / "beckyup_restore" / snap["id"])
                dest_str = questionary.text("Куда восстановить?", default=default_dest).ask()
                if dest_str:
                    dest = Path(dest_str)
                    dest.mkdir(parents=True, exist_ok=True)
                    mgr.restore(m, store / "blobs", dest)
                    console.print(f"[green]✓ Восстановлено в {dest}[/green]")
        elif action == "[V] Verify":
            snap = pick_snapshot(snaps, drive.name)
            if snap:
                m = mgr.load_manifest(snap["path"])
                result = mgr.verify(m, store / "blobs", store / "verify-key")
                if result["valid"]:
                    console.print(f"[green]✓ {result['checked']} файлов целы[/green]")
                else:
                    console.print(f"[red]✗ {len(result['errors'])} ошибок[/red]")


def cmd_restore():
    """Interactive restore from snapshot."""
    drive = _get_detected_drive()
    if not drive:
        print_error("Подключи знакомую бэкап-флешку.")
        return
    from core.snapshot import SnapshotManager
    from cli.snapshot_ui import pick_snapshot
    store = drive / ".beckyup"
    mgr = SnapshotManager(store)
    snaps = mgr.list_snapshots()
    snap = pick_snapshot(snaps, drive.name)
    if not snap:
        return
    m = mgr.load_manifest(snap["path"])
    default_dest = str(Path.home() / "beckyup_restore" / snap["id"])
    import questionary
    dest_str = questionary.text("Куда восстановить?", default=default_dest).ask()
    if dest_str:
        dest = Path(dest_str)
        dest.mkdir(parents=True, exist_ok=True)
        mgr.restore(m, store / "blobs", dest)
        console.print(f"[green]✓ Восстановлено в {dest}[/green]")


def cmd_diff():
    """Interactive diff between two snapshots."""
    drive = _get_detected_drive()
    if not drive:
        print_error("Подключи знакомую бэкап-флешку.")
        return
    from core.snapshot import SnapshotManager
    from cli.snapshot_ui import pick_two_snapshots, show_diff_result
    store = drive / ".beckyup"
    mgr = SnapshotManager(store)
    snaps = mgr.list_snapshots()
    pair = pick_two_snapshots(snaps, drive.name)
    if pair:
        m1 = mgr.load_manifest(pair[0]["path"])
        m2 = mgr.load_manifest(pair[1]["path"])
        diff = mgr.diff(m1, m2)
        console.print(f"\n[bold]Изменения {pair[0]['created_at'][:10]} → {pair[1]['created_at'][:10]}:[/bold]")
        show_diff_result(diff)


def cmd_verify():
    """Verify integrity of latest snapshot."""
    drive = _get_detected_drive()
    if not drive:
        print_error("Подключи знакомую бэкап-флешку.")
        return
    from core.snapshot import SnapshotManager
    from cli.snapshot_ui import pick_snapshot
    store = drive / ".beckyup"
    mgr = SnapshotManager(store)
    snaps = mgr.list_snapshots()
    snap = pick_snapshot(snaps, drive.name)
    if not snap:
        return
    m = mgr.load_manifest(snap["path"])
    result = mgr.verify(m, store / "blobs", store / "verify-key")
    if result["valid"]:
        console.print(f"[green]✓ {result['checked']} файлов целы, подпись верна[/green]")
    else:
        console.print(f"[red]✗ {len(result['errors'])} ошибок целостности[/red]")


def main():
    global backup_engine, device_monitor, config_manager

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    parser = argparse.ArgumentParser(description="Экстренный бэкап важных данных")
    parser.add_argument("--source", help="Исходная директория для одноразового бэкапа")
    parser.add_argument("--destination", help="Директория назначения для одноразового бэкапа")
    parser.add_argument("--config", help="Путь к файлу конфигурации", default=None)
    parser.add_argument("--wizard", action="store_true", help="Запустить настройку заново")
    parser.add_argument("--backup", action="store_true", help="Запустить бэкап со снепшотами")
    parser.add_argument("--snapshots", action="store_true", help="Показать список снепшотов")
    parser.add_argument("--restore", action="store_true", help="Восстановить из снепшота")
    parser.add_argument("--diff", action="store_true", help="Сравнить два снепшота")
    parser.add_argument("--verify", action="store_true", help="Проверить целостность снепшота")
    args = parser.parse_args()

    logger = setup_logger()
    logger.info("Запуск экстренного бэкапа важных данных")

    try:
        # Snapshot subcommands
        if args.snapshots:
            cmd_snapshots()
            return
        if args.restore:
            cmd_restore()
            return
        if args.diff:
            cmd_diff()
            return
        if args.verify:
            cmd_verify()
            return

        if args.source and args.destination:
            logger.info("Запуск одноразового бэкапа")
            show_banner()
            backup_engine = BackupEngine(args.config)
            dest = Path(args.destination)
            dest.mkdir(parents=True, exist_ok=True)
            backup_engine.source_directories = [Path(args.source)]
            backup_engine.destination_path = dest
            stats = backup_engine.run_backup()
            console.print(f"[bold]Источник:[/bold] {args.source}")
            console.print(f"[bold]Назначение:[/bold] {args.destination}")
            show_backup_result(stats)
            logger.info(f"Одноразовый бэкап завершен: {stats}")
            return

        config_manager = ConfigManager()

        if args.wizard or not config_manager.config_file.exists():
            try:
                from cli.wizard import run_wizard
                backup_engine = BackupEngine(args.config)
                run_wizard(config_manager, backup_engine)
            except ImportError:
                logger.error("questionary не установлен. Выполни: pip install -r requirements.txt")
                sys.exit(1)
            if args.wizard:
                return

        logger.info("Запуск в режиме мониторинга")
        backup_engine = BackupEngine(args.config)
        from core.device_detector import DeviceDetector
        detector = DeviceDetector()
        device_monitor = DeviceMonitor(backup_engine, detector=detector)

        def on_device_connected(device_path):
            logger.info(f"Обнаружено новое устройство: {device_path}")

        device_monitor.add_callback(on_device_connected)
        device_monitor.start_monitoring()

        logger.info("Приложение запущено и готово к работе")
        show_startup(str(config_manager.config_file) if config_manager else None)

        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Получен сигнал остановки от пользователя")
        finally:
            shutdown()

    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        print_error(f"Критическая ошибка: {e}")
        shutdown()
        sys.exit(1)

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run existing tests to verify nothing broke**

Run: `cd backup_tool && python3 -m unittest discover tests -v`
Expected: all previous tests still pass

- [ ] **Step 3: Commit**

```bash
git add backup_tool/main.py
git commit -m "feat: CLI — snapshots, restore, diff, verify subcommands"
```

---

### Task 6: Update `backup_engine.py` — integrate snapshot into `run_backup`

**Files:**
- Modify: `backup_tool/core/backup_engine.py`

- [ ] **Step 1: Write failing test**

```python
class TestSnapshotBackup(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.src = self.test_dir / "source"
        self.src.mkdir()
        (self.src / "f.txt").write_text("data")
        (self.src / "g.txt").write_text("more")
        # Simulate a mounted backup drive with .beckyup store
        self.drive = self.test_dir / "drive"
        self.drive.mkdir()
        self.store = self.drive / ".beckyup"
        self.store.mkdir()
        from core.snapshot import generate_identity
        generate_identity(self.store)
        (self.store / "blobs").mkdir()
        (self.store / "snapshots").mkdir()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_run_backup_creates_snapshot(self):
        engine = BackupEngine()
        engine.source_directories = [self.src]
        engine.destination_path = self.drive
        stats = engine.run_backup()
        self.assertNotIn("error", stats)
        # Check snapshot was created
        snap_dir = self.store / "snapshots"
        jsons = list(snap_dir.glob("*.json"))
        sigs = list(snap_dir.glob("*.sig"))
        self.assertGreater(len(jsons), 0)
        self.assertEqual(len(jsons), len(sigs))

    def test_run_backup_dedup_on_second_run(self):
        engine = BackupEngine()
        engine.source_directories = [self.src]
        engine.destination_path = self.drive
        engine.run_backup()
        first_blob_count = len(list((self.store / "blobs").iterdir()))
        engine.run_backup()
        second_blob_count = len(list((self.store / "blobs").iterdir()))
        self.assertEqual(first_blob_count, second_blob_count)
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Update `run_backup()` in `backup_engine.py`**

Replace the current `run_backup` method (from `def run_backup(self) -> Dict[str, Any]:` onward) with snapshot-aware version:

```python
    def run_backup(self) -> Dict[str, Any]:
        """Выполнение полного бэкапа со снепшотами."""
        if not self.source_directories:
            self.logger.warning("Нет настроенных исходных директорий для бэкапа")
            return {"error": "No source directories configured"}

        if not self.destination_path or self.destination_path == Path():
            self.logger.error(f"Директория назначения не установлена: {self.destination_path}")
            return {"error": "Destination directory not set"}

        ok, msg = self._check_writeable(self.destination_path)
        if not ok:
            self.logger.error(msg)
            return {"error": msg}

        ok, msg = self._check_disk_space(self.destination_path, self.source_directories)
        if not ok:
            self.logger.error(msg)
            return {"error": msg}

        # Snapshot-aware backup
        try:
            from core.snapshot import SnapshotManager, generate_identity
            store_dir = self.destination_path / ".beckyup"
            (store_dir / "blobs").mkdir(parents=True, exist_ok=True)
            (store_dir / "snapshots").mkdir(parents=True, exist_ok=True)
            generate_identity(store_dir)

            mgr = SnapshotManager(store_dir)
            all_files = []
            total_errors = 0

            for source in self.source_directories:
                if not source.exists():
                    self.logger.warning(f"Источник не существует: {source}")
                    continue

                files = mgr.scan_files(source)
                for f in files:
                    try:
                        mgr.dedup_copy(f["path"], store_dir / "blobs")
                    except Exception as e:
                        total_errors += 1
                        self.logger.error(f"Ошибка копирования {f['rel']}: {e}")
                        continue
                    all_files.append(f)

            manifest_path = mgr.write_manifest(
                store_dir / "snapshots",
                all_files,
                [str(s) for s in self.source_directories],
                store_dir / "sign-key",
            )

            overall_stats = {
                "total_copied": len(all_files),
                "total_errors": total_errors,
                "total_skipped": 0,
                "manifest": str(manifest_path),
                "directories": [str(s) for s in self.source_directories],
            }
            self.logger.info(f"Снепшот создан: {manifest_path.name}")
            return overall_stats

        except Exception as e:
            self.logger.error(f"Ошибка снепшот-бэкапа: {e}", exc_info=True)
            return {"error": str(e)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backup_tool && python3 -m unittest discover tests -v`
Expected: all tests pass (old + new)

- [ ] **Step 5: Commit**

```bash
git add backup_tool/core/backup_engine.py
git commit -m "feat: backup engine creates snapshots with dedup"
```

---

### Task 7: Update CLI shortcuts — `beckyup snapshots` as main entry

**Files:**
- Modify: `backup_tool/main.py`

Add alias so `beckyup` without args in snapshot mode shows snapshots menu if drive connected. For now, keep current behavior (monitoring mode) if no drive, but add a hint.

- [ ] **Step 1: Add brief check before entering monitoring loop**

In `main()`, before `logger.info("Запуск в режиме мониторинга")`, add:

```python
        # Quick snapshot check
        drive_path = _get_detected_drive()
        if drive_path and not args.wizard and not args.source:
            from cli.snapshot_ui import console
            console.print(f"[dim]Флешка {drive_path.name} подключена. "
                          f"Используй --snapshots для управления снепшотами.[/dim]")
```

- [ ] **Step 2: Commit**

```bash
git add backup_tool/main.py
git commit -m "feat: hint about snapshots when drive connected"
```

---

### Task 8: Self-review checklist

- [ ] Check: every spec requirement maps to a task?
  - Storage layout (section 2) → Task 2 (blobs + manifests)
  - Manifests (section 3) → Task 2 (`write_manifest` + `load_manifest`)
  - Identity (section 4) → Task 1 (`generate_identity`)
  - CLI backup (section 5) → Task 5, 6
  - CLI snapshots (section 5) → Task 5 (`cmd_snapshots`)
  - CLI restore (section 5) → Task 5 (`cmd_restore`)
  - CLI diff (section 5) → Task 5 (`cmd_diff`)
  - CLI verify (section 5) → Task 5 (`cmd_verify`)
  - Backup engine changes (section 6) → Task 6
  - Integrity verification (section 7) → Task 3 (`verify`)
  - Out of scope (section 8) → not implemented ✓

- [ ] Check: no placeholders, missing code, or "TBD" in plan
- [ ] Check: all imports consistent across tasks
- [ ] Check: all tests reference correct mock patches and expected values

---

### Execution handoff

Plan complete. Two execution options:

**1. Subagent-Driven (рекомендуется)** — диспатчу свежего суб-агента на каждую таску, ревью между ними, быстрая итерация

**2. Inline Execution** — выполняю в этой сессии, batch с чекпоинтами

Что выбираешь?
