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

    key_output = result.stdout.strip()
    sign_key = ""
    verify_key = ""
    for line in key_output.splitlines():
        if line.startswith("# public key: age1"):
            verify_key = line.split(":")[-1].strip()
        elif line.startswith("AGE-SECRET-KEY-"):
            sign_key = line

    if not verify_key or not sign_key:
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
    """Sign manifest bytes with age. Encrypts data with the corresponding
    public key (verify-key) as recipient. Returns armored encrypted message."""
    age_bin = _age_binary()
    if not age_bin:
        raise RuntimeError("age not found. Install age: https://github.com/FiloSottile/age")

    verify_key_path = sign_key_path.parent / "verify-key"
    if not verify_key_path.exists():
        raise RuntimeError(f"verify-key not found at {verify_key_path}")

    verify_key = verify_key_path.read_text().strip()

    result = subprocess.run(
        [age_bin, "--armor", "--encrypt", f"--recipient={verify_key}"],
        input=data, capture_output=True, timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(f"age encrypt (sign) failed: {result.stderr.decode()}")
    return result.stdout.decode().strip()


def verify_signature(data: bytes, signature: str, verify_key_path: Path) -> bool:
    """Verify age signature against data. Decrypts the armored signature
    using the private key (sign-key) and compares with original data."""
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
    """Compute sha256 hex digest of file contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Compute sha256 hex digest of bytes."""
    return hashlib.sha256(data).hexdigest()
