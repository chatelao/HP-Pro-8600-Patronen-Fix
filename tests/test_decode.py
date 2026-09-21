import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import base64
import hashlib
import struct
import zlib
import gzip
import tarfile
import zipfile
import io
import pytest

from scripts.decode import (
    deobfuscate_fwupd_secret,
    parse_srecords,
    strip_pcl_sequences,
    extract_filesystem_from_binary,
    decode_ful2,
    decode_bksettings,
    decode_pjl_rfu,
    create_zip_asset,
)
from Crypto.Cipher import AES


def test_deobfuscate_fwupd_secret():
    secret = deobfuscate_fwupd_secret()
    assert secret == "@* WebFWUpdate"


def test_parse_srecords():
    # S3 record format: S3 <count_hex_2> <addr_8hex> <data_hex> <checksum_hex_2>
    # count = 4 (addr) + 11 (data) + 1 (checksum) = 16 (0x10)
    srec = b"S3100000100048656C6C6F20576F726C64FF\n"
    res = parse_srecords(srec)
    assert res == b"Hello World"

    # Empty / non-matching
    assert parse_srecords(b"NO SRECORDS HERE") == b""


def test_strip_pcl_sequences():
    data = b"\x1bEThis device does not support FWUPDATE!\r\nHello World"
    res = strip_pcl_sequences(data)
    assert res == b"Hello World"

    # PCL raster command: \x1b*b5W12345
    pcl_cmd = b"\x1b*b5W12345"
    assert strip_pcl_sequences(pcl_cmd) == b"12345"


def test_extract_filesystem_from_binary(tmp_path):
    # Test Gzip decompression
    gzip_buf = gzip.compress(b"GZIP_TEST_DATA")
    extracted_dir = tmp_path / "gzip_test"
    assert extract_filesystem_from_binary(gzip_buf, extracted_dir, "test_gzip") is True
    assert (extracted_dir / "test_gzip_decompressed.bin").read_bytes() == b"GZIP_TEST_DATA"

    # Test Zlib decompression
    zlib_buf = zlib.compress(b"ZLIB_TEST_DATA")
    extracted_dir_zlib = tmp_path / "zlib_test"
    assert extract_filesystem_from_binary(zlib_buf, extracted_dir_zlib, "test_zlib") is True
    assert (extracted_dir_zlib / "test_zlib_zlib.bin").read_bytes() == b"ZLIB_TEST_DATA"

    # Test non-archive binary data
    raw_dir = tmp_path / "raw_test"
    assert extract_filesystem_from_binary(b"RANDOM_RAW_BYTES_12345", raw_dir, "test_raw") is False


def test_decode_ful2(tmp_path):
    secret = deobfuscate_fwupd_secret()
    fw_model = "manhhi"
    uncompressed_data = b"MOCK_ROOTFS_FILESYSTEM_CONTENT_12345"
    raw_zlib = zlib.compress(uncompressed_data, wbits=-15)

    digest_uncompressed = hashlib.sha256(uncompressed_data).digest()
    digest_b64 = base64.b64encode(digest_uncompressed).decode('ascii')

    key_material = hashlib.sha256((secret + fw_model).encode('utf-8') + digest_uncompressed).digest()
    aes_key = key_material[:16]
    iv = bytes(16)
    cipher = AES.new(aes_key, AES.MODE_CBC, iv)
    encrypted_blob = cipher.encrypt(raw_zlib + b"\x00" * ((16 - len(raw_zlib) % 16) % 16))

    manifest_xml = f"""<?xml version='1.0' encoding='UTF-8'?>
<manifest>
    <signedInfo>
        <updated_revision>MANHHIPP1N005.2607A.00</updated_revision>
        <rootfs_blob>
            <blob_digest_uncompressed>{digest_b64}</blob_digest_uncompressed>
        </rootfs_blob>
    </signedInfo>
</manifest>"""

    hex_size = f"{len(encrypted_blob):X}"
    ful2_content = manifest_xml.encode('utf-8') + b"\n" + hex_size.encode('utf-8') + b"\n" + encrypted_blob

    ful2_file = tmp_path / "test_firmware.ful2"
    ful2_file.write_bytes(ful2_content)

    out_dir = tmp_path / "ful2_out"
    res = decode_ful2(ful2_file, out_dir)
    assert res is True

    decrypted_blob = out_dir / f"{ful2_file.name}_rootfs_blob.bin"
    assert decrypted_blob.exists()
    assert decrypted_blob.read_bytes().startswith(uncompressed_data)


def test_decode_bksettings(tmp_path):
    password = "testpassword"
    xml_content = b"<Configuration><Setting>TestVal</Setting></Configuration>"
    compressed_content = gzip.compress(xml_content)

    file_size = len(compressed_content)
    timer = 12345678
    iv = b"0123456789abcdef"

    aes_key = hashlib.sha256(
        struct.pack("<I", file_size) +
        struct.pack("<I", timer) +
        b"Is_Th1s=9-Gd(S8c$et*K3y?" +
        password.encode('utf-8')
    ).digest()

    inner_mac = b"\x00" * 32
    plaintext_padded = inner_mac + compressed_content
    pad_len = (16 - len(plaintext_padded) % 16) % 16
    plaintext_padded += b"\x00" * pad_len

    cipher = AES.new(aes_key, AES.MODE_CBC, iv=iv)
    ciphertext = cipher.encrypt(plaintext_padded)

    header = bytearray(0x50)
    header[0:4] = b"BKST"
    struct.pack_into("<I", header, 0x34, file_size)
    struct.pack_into("<I", header, 0x38, timer)
    header[0x40:0x50] = iv

    enc_file = tmp_path / "usrdata.enc"
    enc_file.write_bytes(bytes(header) + ciphertext)

    out_dir = tmp_path / "bk_out"
    res = decode_bksettings(enc_file, out_dir, password)
    assert res is True

    decoded_xml = out_dir / f"{enc_file.name}_decoded.xml"
    assert decoded_xml.exists()
    assert decoded_xml.read_bytes() == xml_content


def test_decode_pjl_rfu(tmp_path):
    pjl_data = (
        b"\x1b%-12345X@PJL\n"
        b"@PJL COMMENT MODEL=HP OfficeJet Pro 8600\n"
        b"@PJL UPGRADE SIZE=11\n"
        b"@PJL ENTER LANGUAGE=FWUPDATE\n"
        b"HELLO WORLD\n"
        b"\x1b%-12345X@PJL EOJ\n"
    )

    rfu_file = tmp_path / "firmware.rfu"
    rfu_file.write_bytes(pjl_data)

    out_dir = tmp_path / "rfu_out"
    res = decode_pjl_rfu(rfu_file, out_dir)
    assert res is True

    payload_file = out_dir / f"{rfu_file.name}_payload.bin"
    assert payload_file.exists()
    assert payload_file.read_bytes() == b"HELLO WORLD"


def test_create_zip_asset(tmp_path):
    out_dir = tmp_path / "output"
    out_dir.mkdir()
    (out_dir / "sample.txt").write_text("sample content")

    zip_file = tmp_path / "asset.zip"
    created = create_zip_asset(out_dir, zip_file)
    assert created.exists()
    assert zipfile.is_zipfile(created)
