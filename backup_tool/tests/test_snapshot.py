import unittest
import tempfile
import shutil
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

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
        from core.snapshot import generate_identity, sign_manifest, verify_signature
        store = self.test_dir / ".beckyup"
        store.mkdir()
        verify_key, sign_key = generate_identity(store)
        data = b'{"test": "data"}'
        sig = sign_manifest(data, sign_key)
        self.assertTrue(verify_signature(data, sig, verify_key))

    def test_verify_fails_on_tampered_data(self):
        from core.snapshot import generate_identity, sign_manifest, verify_signature
        store = self.test_dir / ".beckyup"
        store.mkdir()
        verify_key, sign_key = generate_identity(store)
        data = b'{"test": "data"}'
        sig = sign_manifest(data, sign_key)
        self.assertFalse(verify_signature(b'{"test": "EVIL"}', sig, verify_key))

class TestSHA256(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_sha256_file_known_value(self):
        from core.snapshot import sha256_file
        f = self.test_dir / "test.bin"
        f.write_bytes(b"hello")
        # sha256 of "hello"
        self.assertEqual(sha256_file(f),
                         "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824")

    def test_sha256_bytes_known_value(self):
        from core.snapshot import sha256_bytes
        self.assertEqual(sha256_bytes(b"hello"),
                         "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824")

    def test_sha256_file_empty(self):
        from core.snapshot import sha256_file
        f = self.test_dir / "empty.bin"
        f.write_text("")
        self.assertEqual(sha256_file(f),
                         "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")

    def test_sha256_bytes_empty(self):
        from core.snapshot import sha256_bytes
        self.assertEqual(sha256_bytes(b""),
                         "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")


class TestSnapshotManager(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.store = self.test_dir / ".beckyup"
        self.store.mkdir(parents=True, exist_ok=True)
        self.blobs = self.store / "blobs"
        self.blobs.mkdir()
        self.snapshots = self.store / "snapshots"
        self.snapshots.mkdir()
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
        from core.snapshot import generate_identity
        generate_identity(self.store)
        manifest_path = mgr.write_manifest(
            self.snapshots, files, [str(self.src)],
            self.store / "sign-key"
        )
        self.assertTrue(manifest_path.exists())
        self.assertTrue(Path(str(manifest_path) + ".sig").exists())

    def test_load_manifest(self):
        from core.snapshot import SnapshotManager
        mgr = SnapshotManager(self.store)
        files = mgr.scan_files(self.src)
        f1 = next(f for f in files if f["rel"] == "file1.txt")
        from core.snapshot import generate_identity
        generate_identity(self.store)
        manifest_path = mgr.write_manifest(
            self.snapshots, files, [str(self.src)],
            self.store / "sign-key"
        )
        loaded = mgr.load_manifest(manifest_path)
        self.assertIn("file1.txt", loaded["files"])
        self.assertEqual(loaded["files"]["file1.txt"]["sha256"], f1["sha256"])

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


if __name__ == '__main__':
    unittest.main()
