#!/usr/bin/env python3
"""
Firmware and Backup Decoder for HP Printers.

Based on technical details documented at:
https://romern.me/blog/hp-printer-backup-decryption/

Supports:
1. Decrypting HP .ful2 firmware images (AES-CBC + zlib over manifest blobs)
2. Decrypting HP bksettings backup files (.enc)
3. Extracting/decoding PJL wrapped firmware files (.ful / .rfu) with PCL escape sequence stripping & Motorola S-record parsing
4. Full recursive extraction of filesystem assets (Tar, Zip, Gzip, Zlib, S-Records)
5. Packaging extracted filesystem assets into an unencrypted ".zip" asset
"""

import os
import sys
import re
import io
import base64
import struct
import hashlib
import zlib
import gzip
import tarfile
import zipfile
import binascii
from pathlib import Path

try:
    import xmltodict
except ImportError:
    xmltodict = None

try:
    from Crypto.Cipher import AES
except ImportError:
    AES = None


def parse_srecords(data: bytes) -> bytes:
    """Parse Motorola S-records (S0, S1, S2, S3, S7, S8, S9) into a binary memory buffer."""
    matches = re.findall(rb'S[0-9][0-9A-Fa-f]{6,}', data)
    memory = {}
    for m in matches:
        stype = m[1:2].decode('ascii', errors='ignore')
        if stype in ('1', '2', '3'):
            try:
                count = int(m[2:4], 16)
                addr_len = 4 if stype == '1' else (6 if stype == '2' else 8)
                addr = int(m[4:4+addr_len], 16)
                payload_hex = m[4+addr_len:4+count*2-2]
                payload_bytes = binascii.unhexlify(payload_hex)
                memory[addr] = payload_bytes
            except Exception:
                pass

    if not memory:
        return b""

    sorted_addrs = sorted(memory.keys())
    chunks = []
    curr_chunk = bytearray(memory[sorted_addrs[0]])
    curr_addr = sorted_addrs[0] + len(memory[sorted_addrs[0]])

    for a in sorted_addrs[1:]:
        p = memory[a]
        if a == curr_addr:
            curr_chunk.extend(p)
            curr_addr += len(p)
        else:
            chunks.append(bytes(curr_chunk))
            curr_chunk = bytearray(p)
            curr_addr = a + len(p)
    chunks.append(bytes(curr_chunk))

    return max(chunks, key=len) if chunks else b""


def strip_pcl_sequences(data: bytes) -> bytes:
    """Strip PCL reset and raster transfer commands from binary update streams."""
    pos = 0
    assembled = bytearray()
    while True:
        match = re.search(rb'\x1b\*b(\d+)([VWXYZWSA])', data[pos:])
        if not match:
            break
        length = int(match.group(1))
        start_data = pos + match.end()
        chunk_data = data[start_data:start_data + length]
        assembled.extend(chunk_data)
        pos = start_data + length

    if assembled:
        return bytes(assembled)

    cleaned = data
    if cleaned.startswith(b'\x1bE'):
        newline = cleaned.find(b'\n')
        if newline != -1:
            cleaned = cleaned[newline + 1:]
    return cleaned


def extract_filesystem_from_binary(data: bytes, extract_dir: Path, name_prefix: str) -> bool:
    """Recursively extract filesystem archives (Tar, Zip, Gzip, Zlib) from binary data."""
    extract_dir.mkdir(parents=True, exist_ok=True)

    # Check Tar archive
    try:
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            tar.extractall(path=extract_dir)
            print(f"[+] Extracted Tar filesystem archive into {extract_dir}")
            return True
    except Exception:
        pass

    # Check Zip archive
    try:
        if zipfile.is_zipfile(io.BytesIO(data)):
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                zf.extractall(path=extract_dir)
                print(f"[+] Extracted Zip filesystem archive into {extract_dir}")
                return True
    except Exception:
        pass

    # Check Gzip stream
    if data.startswith(b'\x1f\x8b'):
        try:
            decompressed = gzip.decompress(data)
            out_file = extract_dir / f"{name_prefix}_decompressed.bin"
            out_file.write_bytes(decompressed)
            print(f"[+] Decompressed Gzip stream into {out_file} ({len(decompressed)} bytes)")
            extract_filesystem_from_binary(decompressed, extract_dir / f"{name_prefix}_extracted", name_prefix)
            return True
        except Exception:
            pass

    # Check Zlib stream
    if data.startswith(b'\x78\x9c') or data.startswith(b'\x78\x01') or data.startswith(b'\x78\xda'):
        try:
            decompressed = zlib.decompress(data)
            out_file = extract_dir / f"{name_prefix}_zlib.bin"
            out_file.write_bytes(decompressed)
            print(f"[+] Decompressed Zlib stream into {out_file} ({len(decompressed)} bytes)")
            extract_filesystem_from_binary(decompressed, extract_dir / f"{name_prefix}_extracted", name_prefix)
            return True
        except Exception:
            pass

    return False


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

    output_dir.mkdir(parents=True, exist_ok=True)
    fs_dir = output_dir / "extracted_filesystem" / file_path.stem

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

        out_path = output_dir / f"{file_path.name}_{blob_name}.bin"
        out_path.write_bytes(plaintext)
        print(f"[+] Decrypted .ful2 blob saved to: {out_path} ({len(plaintext)} bytes)")
        blobs_extracted += 1

        extract_filesystem_from_binary(plaintext, fs_dir / blob_name, blob_name)

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

    fs_dir = output_dir / "extracted_filesystem" / file_path.stem
    fs_dir.mkdir(parents=True, exist_ok=True)
    (fs_dir / f"{file_path.stem}_configuration.xml").write_bytes(decompressed)
    return True


def decode_pjl_rfu(file_path: Path, output_dir: Path) -> bool:
    """Extract payload from PJL encapsulated firmware file (.ful / .rfu)."""
    data = file_path.read_bytes()

    if b'@PJL' not in data:
        return False

    print(f"[*] Extracting PJL firmware container: {file_path.name}")

    lines = data.splitlines()
    pjl_headers = []
    upgrade_size = None

    for line in lines:
        if line.startswith(b'@PJL') or line.startswith(b'\x1b%-12345X'):
            try:
                hdr_str = line.decode('utf-8', errors='ignore').strip()
                pjl_headers.append(hdr_str)
                if 'UPGRADE SIZE' in hdr_str:
                    match = re.search(r'UPGRADE\s+SIZE\s*=\s*(\d+)', hdr_str)
                    if match:
                        upgrade_size = int(match.group(1))
            except Exception:
                pass

    print(f"    PJL Headers found ({len(pjl_headers)} lines):")
    for hdr in pjl_headers[:10]:
        print(f"      {hdr}")

    if upgrade_size:
        print(f"    Declared PJL UPGRADE SIZE: {upgrade_size} bytes")

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

    if upgrade_size and len(payload) >= upgrade_size:
        payload = payload[:upgrade_size]

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{file_path.name}_payload.bin"
    out_path.write_bytes(payload)
    print(f"[+] Extracted raw firmware payload saved to: {out_path} ({len(payload)} bytes)")

    cleaned_payload = strip_pcl_sequences(payload)

    fs_dir = output_dir / "extracted_filesystem" / file_path.stem
    fs_dir.mkdir(parents=True, exist_ok=True)

    clean_bin_path = fs_dir / f"{file_path.stem}_cleaned.bin"
    clean_bin_path.write_bytes(cleaned_payload)

    srec_bin = parse_srecords(cleaned_payload)
    if srec_bin:
        srec_out_path = fs_dir / f"{file_path.stem}_srecord_parsed.bin"
        srec_out_path.write_bytes(srec_bin)
        print(f"[+] Decoded Motorola S-records into binary memory image: {srec_out_path} ({len(srec_bin)} bytes)")
        extract_filesystem_from_binary(srec_bin, fs_dir / "srecord_extracted", file_path.stem)

    extract_filesystem_from_binary(cleaned_payload, fs_dir / "cleaned_extracted", file_path.stem)

    return True


def create_zip_asset(output_dir: Path, zip_filepath: Path) -> Path:
    """Package output directory into an unencrypted .zip asset."""
    print(f"[*] Packaging extracted filesystem and artifacts into zip asset: {zip_filepath}")
    zip_filepath.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(output_dir):
            for file in files:
                file_p = Path(root) / file
                if file_p.resolve() == zip_filepath.resolve():
                    continue
                arcname = file_p.relative_to(output_dir.parent if output_dir.parent != output_dir else output_dir)
                zf.write(file_p, arcname)

    print(f"[+] Successfully created unencrypted zip asset: {zip_filepath} ({zip_filepath.stat().st_size} bytes)")
    return zip_filepath


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

    zip_filepath = Path("unpacked_filesystem.zip")
    create_zip_asset(output_dir, zip_filepath)


if __name__ == "__main__":
    main()
