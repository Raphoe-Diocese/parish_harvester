#!/usr/bin/env python3
"""Pack extension/ into a Chrome CRX3. Do not commit the private key."""

from __future__ import annotations

import argparse
import hashlib
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def _varint(n: int) -> bytes:
    out = bytearray()
    while n > 0x7F:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    out.append(n)
    return bytes(out)


def _ld(field: int, data: bytes) -> bytes:
    return _varint((field << 3) | 2) + _varint(len(data)) + data


def extension_id_from_der(public_der: bytes) -> str:
    digest = hashlib.sha256(public_der).digest()[:16]
    return "".join(chr(ord("a") + (b >> 4)) + chr(ord("a") + (b & 0x0F)) for b in digest)


def zip_extension_dir(extension_dir: Path) -> bytes:
    buf = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    buf.close()
    zip_path = Path(buf.name)
    try:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(extension_dir.rglob("*")):
                if not path.is_file():
                    continue
                if path.suffix == ".pem" or path.name == ".DS_Store":
                    continue
                zf.write(path, path.relative_to(extension_dir).as_posix())
        data = zip_path.read_bytes()
    finally:
        zip_path.unlink(missing_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        with zipfile.ZipFile(tmp_path) as zf:
            if "manifest.json" not in zf.namelist():
                raise SystemExit("pack_extension_crx: manifest.json must be at the zip root")
    finally:
        tmp_path.unlink(missing_ok=True)
    return data


def public_der_from_pem(pem_path: Path) -> bytes:
    return subprocess.check_output(
        ["openssl", "rsa", "-in", str(pem_path), "-pubout", "-outform", "DER"],
        stderr=subprocess.DEVNULL,
    )


def sign_crx3(zip_bytes: bytes, pem_path: Path) -> bytes:
    public_der = public_der_from_pem(pem_path)
    crx_id = hashlib.sha256(public_der).digest()[:16]
    signed_header_data = _ld(1, crx_id)
    signed = (
        b"CRX3 SignedData\x00"
        + struct.pack("<I", len(signed_header_data))
        + signed_header_data
        + zip_bytes
    )
    with tempfile.NamedTemporaryFile(delete=False) as payload:
        payload.write(signed)
        payload_path = Path(payload.name)
    sig_path = payload_path.with_suffix(".sig")
    try:
        subprocess.check_call(
            [
                "openssl",
                "dgst",
                "-sha256",
                "-sign",
                str(pem_path),
                "-out",
                str(sig_path),
                str(payload_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        signature = sig_path.read_bytes()
    finally:
        payload_path.unlink(missing_ok=True)
        sig_path.unlink(missing_ok=True)
    proof = _ld(1, public_der) + _ld(2, signature)
    header = _ld(2, proof) + _ld(10000, signed_header_data)
    return b"Cr24" + struct.pack("<I", 3) + struct.pack("<I", len(header)) + header + zip_bytes


def main() -> int:
    parser = argparse.ArgumentParser(description="Pack Parish Trainer as CRX3")
    parser.add_argument("--extension-dir", default="extension")
    parser.add_argument("--pem", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    extension_dir = Path(args.extension_dir)
    pem_path = Path(args.pem)
    out_path = Path(args.out)
    if not extension_dir.is_dir() or not pem_path.is_file():
        print("missing extension dir or pem", file=sys.stderr)
        return 1
    crx = sign_crx3(zip_extension_dir(extension_dir), pem_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(crx)
    print(f"wrote {out_path} ({len(crx)} bytes) id={extension_id_from_der(public_der_from_pem(pem_path))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
