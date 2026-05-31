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


if __name__ == '__main__':
    unittest.main()
