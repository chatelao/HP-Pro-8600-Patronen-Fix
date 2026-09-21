import sys
import zipfile
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from scripts.decompile import (
    disassemble_binary_stream,
    decompile_binary_file,
    decompile_extracted_artifacts,
    create_decompiled_zip_asset,
)


def test_disassemble_binary_stream():
    # Thumb instruction: 0x4800 -> ldr r0, [pc, #0]
    data = b"\x00\x48\x00\x48"
    disasm_text = disassemble_binary_stream(data, base_addr=0x1000)
    assert "; Architecture: ARM (Thumb Mode)" in disasm_text
    assert "ldr" in disasm_text
    assert "0x00001000" in disasm_text


def test_decompile_binary_file(tmp_path):
    bin_file = tmp_path / "sample.bin"
    bin_file.write_bytes(b"\x00\x48\x00\x48")

    out_dir = tmp_path / "decomp_out"
    asm_path = decompile_binary_file(bin_file, out_dir)

    assert asm_path.exists()
    assert asm_path.name == "sample.bin.asm"
    content = asm_path.read_text(encoding="utf-8")
    assert "code_start:" in content
    assert "ldr" in content


def test_decompile_extracted_artifacts(tmp_path):
    input_dir = tmp_path / "decoded_input"
    sub_dir = input_dir / "subdir"
    sub_dir.mkdir(parents=True)

    (input_dir / "file1.bin").write_bytes(b"\x00\x48")
    (sub_dir / "file2.bin").write_bytes(b"\x00\x48")

    out_dir = tmp_path / "decompiled_output"
    decompiled_files = decompile_extracted_artifacts(input_dir, out_dir)

    assert len(decompiled_files) == 2
    assert (out_dir / "file1.bin.asm").exists()
    assert (out_dir / "subdir" / "file2.bin.asm").exists()


def test_create_decompiled_zip_asset(tmp_path):
    out_dir = tmp_path / "decompiled_output"
    out_dir.mkdir()
    (out_dir / "sample.asm").write_text("; Sample Assembly Code\n")

    zip_filepath = tmp_path / "decompiled_source.zip"
    created_zip = create_decompiled_zip_asset(out_dir, zip_filepath)

    assert created_zip.exists()
    assert zipfile.is_zipfile(created_zip)

    with zipfile.ZipFile(created_zip, 'r') as zf:
        namelist = zf.namelist()
        assert any("sample.asm" in name for name in namelist)
