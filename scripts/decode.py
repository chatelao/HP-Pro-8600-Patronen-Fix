#!/usr/bin/env python3
"""
Firmware and Backup Decoder for HP Printers.

Based on technical details documented at:
https://romern.me/blog/hp-printer-backup-decryption/

Supports:
1. Decrypting HP .ful2 firmware images (AES-CBC + zlib over manifest blobs)
2. Decrypting HP bksettings backup files (.enc)
3. Extracting/decoding PJL wrapped firmware files (.ful / .rfu)
"""

import os
import sys
import base64
import struct
import hashlib
import zlib
from pathlib import Path

try:
    import xmltodict
except ImportError:
    xmltodict = None

try:
    from Crypto.Cipher import AES
except ImportError:
    AES = None


def decode_ful2(file_path: Path, output_dir: Path) -> bool:
    """Decrypt HP .ful2 firmware image containing XML manifest and AES-CBC encrypted blobs."""
    data = file_path.read_bytes()

    if b'<?xml' not in data or b'</manifest>' not in data:
        return False

    xml_start = data.index(b'<?xml')
    xml_end_tag = b'</manifest>'
    xml_end = data.index(xml_end_tag) + len(xml_end_tag)

    if xml_end < len(data) and data[xml_end:xml_end+1] == b'\n':
        xml_end += 1

    xml_data = data[xml_start:data.index(xml_end_tag) + len(xml_end_tag)]

    if xmltodict is None:
        print("[!] xmltodict module missing, skipping .ful2 manifest parsing.")
        return False
    if AES is None:
        print("[!] pycryptodome (Crypto.Cipher.AES) module missing, skipping .ful2 decryption.")
        return False

    parsed_xml = xmltodict.parse(xml_data)
    signed_info = parsed_xml.get('manifest', {}).get('signedInfo', {})
    updated_revision = signed_info.get('updated_revision', '')

    fw_model = updated_revision.lower()[:6]
    secret = '@* WebFWUpdate'

    cur_data_end = xml_end
    blobs_extracted = 0

    blob_keys = [k for k in signed_info.keys() if k.endswith('_blob') or k == 'LBI_blob' or k == 'rootfs_blob']
    if not blob_keys:
        blob_keys = ['LBI_blob', 'rootfs_blob']

    for blob_name in blob_keys:
        if blob_name not in signed_info:
            continue

        blob_info = signed_info[blob_name]
        digest_b64 = blob_info.get('blob_digest_uncompressed')
        if not digest_b64:
            continue

        blob_digest_uncompressed = base64.b64decode(digest_b64)

        key_material = hashlib.sha256((secret + fw_model).encode('utf-8') + blob_digest_uncompressed).digest()
        aes_key = key_material[:16]
        iv = bytes(16)
        cipher = AES.new(aes_key, AES.MODE_CBC, iv)

        size_end = data.find(b'\n', cur_data_end)
        if size_end == -1:
            break

        size_str = data[cur_data_end:size_end].strip()
        try:
            size = int(size_str, 16)
        except ValueError:
            break

        cur_data_end = size_end + 1 + size
        cur_data = data[size_end + 1:cur_data_end]

        compressed = cipher.decrypt(cur_data)
        try:
            plaintext = zlib.decompress(compressed, wbits=-15)
        except Exception:
            plaintext = zlib.decompress(compressed)

        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"{file_path.name}_{blob_name}.bin"
        out_path.write_bytes(plaintext)
        print(f"[+] Decrypted .ful2 blob saved to: {out_path} ({len(plaintext)} bytes)")
        blobs_extracted += 1

    return blobs_extracted > 0


def decode_bksettings(file_path: Path, output_dir: Path, password: str = "") -> bool:
    """Decrypt HP bksettings backup file (.enc) starting with BKST header."""
    data = file_path.read_bytes()

    if not data.startswith(b"BKST"):
        return False

    if AES is None:
        print("[!] pycryptodome (Crypto.Cipher.AES) module missing, skipping bksettings decryption.")
        return False

    file_size = struct.unpack_from("<I", data, 0x34)[0]
    timer = struct.unpack_from("<I", data, 0x38)[0]
    iv = data[0x40:0x50]
    ciphertext = data[0x50:]

    aes_key = hashlib.sha256(
        struct.pack("<I", file_size) +
        struct.pack("<I", timer) +
        b"Is_Th1s=9-Gd(S8c$et*K3y?" +
        password.encode('utf-8')
    ).digest()

    cipher = AES.new(aes_key, AES.MODE_CBC, iv=iv)
    plaintext = cipher.decrypt(ciphertext)

    content = plaintext[32:32 + file_size]
    try:
        decompressed = zlib.decompress(content, zlib.MAX_WBITS | 16)
    except Exception:
        decompressed = content

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{file_path.name}_decoded.xml"
    out_path.write_bytes(decompressed)
    print(f"[+] Decrypted bksettings saved to: {out_path} ({len(decompressed)} bytes)")
    return True


def decode_pjl_rfu(file_path: Path, output_dir: Path) -> bool:
    """Extract payload from PJL encapsulated firmware file (.ful / .rfu)."""
    data = file_path.read_bytes()

    if b'@PJL' not in data:
        return False

    print(f"[*] Extracting PJL firmware container: {file_path.name}")

    lines = data.splitlines()
    pjl_headers = []
    for line in lines:
        if line.startswith(b'@PJL') or line.startswith(b'\x1b%-12345X'):
            try:
                pjl_headers.append(line.decode('utf-8', errors='ignore').strip())
            except Exception:
                pass

    print(f"    PJL Headers found ({len(pjl_headers)} lines):")
    for hdr in pjl_headers[:10]:
        print(f"      {hdr}")

    enter_lang_idx = data.find(b'@PJL ENTER LANGUAGE')
    if enter_lang_idx != -1:
        newline_idx = data.find(b'\n', enter_lang_idx)
        payload_start = newline_idx + 1 if newline_idx != -1 else enter_lang_idx
    else:
        payload_start = 0

    eoj_idx = data.rfind(b'\x1b%-12345X@PJL EOJ')
    if eoj_idx != -1 and eoj_idx > payload_start:
        payload_end = eoj_idx
    else:
        payload_end = len(data)

    payload = data[payload_start:payload_end]
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{file_path.name}_payload.bin"
    out_path.write_bytes(payload)
    print(f"[+] Extracted raw firmware payload saved to: {out_path} ({len(payload)} bytes)")
    return True


def process_file(file_path: Path, output_dir: Path, password: str = ""):
    """Attempt decoding a file using supported format handlers."""
    print(f"[*] Processing: {file_path}")

    if decode_ful2(file_path, output_dir):
        return
    if decode_bksettings(file_path, output_dir, password):
        return
    if decode_pjl_rfu(file_path, output_dir):
        return

    print(f"[-] Unknown or unhandled firmware format: {file_path}")


def main():
    args = [arg for arg in sys.argv[1:] if not arg.startswith('--')]

    target_path = Path(args[0]) if len(args) > 0 else Path("img")
    password = args[1] if len(args) > 1 else ""

    if not target_path.exists():
        print(f"[!] Target path does not exist: {target_path}")
        sys.exit(1)

    output_dir = Path("decoded_output")

    if target_path.is_dir():
        files = [p for p in target_path.iterdir() if p.is_file() and not p.name.endswith('.md')]
        for file in files:
            process_file(file, output_dir, password)
    else:
        process_file(target_path, output_dir, password)


if __name__ == "__main__":
    main()
