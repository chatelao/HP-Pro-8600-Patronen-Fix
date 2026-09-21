#!/usr/bin/env python3
"""
Firmware Decompiler for HP Printer Binary Images.

Processes extracted binary payloads, Motorola S-record memory images, and firmware code sections
from `decoded_output/`, disassembling ARM/Thumb instructions using Capstone and outputting
decompiled source files (.asm / .s).

Packages generated decompiled source files into `decompiled_source.zip`.
"""

import os
import sys
import glob
import zipfile
from pathlib import Path

try:
    import capstone
except ImportError:
    capstone = None


def disassemble_binary_stream(data: bytes, base_addr: int = 0x0) -> str:
    """
    Disassemble binary data stream into ARM / Thumb assembly source text.
    Evaluates disassembler output to choose optimal ARM vs Thumb mode.
    """
    if not capstone:
        return "; Error: Capstone disassembler library is not installed.\n"

    lines = [
        "; ==========================================================================",
        "; HP Printer Firmware Decompiled Assembly Source Code",
        f"; Base Address: 0x{base_addr:08x}",
        f"; Stream Size:  {len(data)} bytes",
        "; ==========================================================================\n",
    ]

    # Test disassembly in Thumb mode
    md_thumb = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
    insns_thumb = list(md_thumb.disasm(data, base_addr))

    # Test disassembly in ARM mode
    md_arm = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)
    insns_arm = list(md_arm.disasm(data, base_addr))

    # Choose disassembly mode with higher instruction density/count
    if len(insns_thumb) >= len(insns_arm):
        lines.append("; Architecture: ARM (Thumb Mode)\n")
        selected_insns = insns_thumb
    else:
        lines.append("; Architecture: ARM (ARM Mode)\n")
        selected_insns = insns_arm

    if not selected_insns:
        lines.append("; [!] No valid instructions disassembled in sample window.\n")
        return "\n".join(lines)

    lines.append(".text")
    lines.append("code_start:")

    for insn in selected_insns:
        bytes_hex = " ".join(f"{b:02x}" for b in insn.bytes)
        lines.append(f"  0x{insn.address:08x}:  {bytes_hex:<16}  {insn.mnemonic:<8} {insn.op_str}")

    lines.append("\ncode_end:")
    return "\n".join(lines)


def decompile_binary_file(file_path: Path, output_dir: Path) -> Path:
    """
    Decompile a single binary file into an assembly source asset file (.asm).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    asm_path = output_dir / f"{file_path.name}.asm"

    data = file_path.read_bytes()
    if not data:
        asm_path.write_text("; Empty binary file\n", encoding="utf-8")
        return asm_path

    disasm_text = disassemble_binary_stream(data)
    asm_path.write_text(disasm_text, encoding="utf-8")
    print(f"[+] Decompiled binary {file_path.name} -> {asm_path} ({len(disasm_text)} bytes)")
    return asm_path


def decompile_extracted_artifacts(input_dir: Path, output_dir: Path) -> list[Path]:
    """
    Recursively scan input directory for binary artifacts and decompile them into source files.
    """
    if not input_dir.exists():
        print(f"[!] Input directory does not exist: {input_dir}")
        return []

    binary_files = [p for p in input_dir.rglob("*") if p.is_file() and not p.name.endswith(".asm") and not p.name.endswith(".xml")]
    decompiled_files = []

    for bin_file in binary_files:
        rel_parent = bin_file.parent.relative_to(input_dir) if bin_file.parent != input_dir else Path(".")
        target_out_dir = output_dir / rel_parent
        out_asm = decompile_binary_file(bin_file, target_out_dir)
        decompiled_files.append(out_asm)

    return decompiled_files


def create_decompiled_zip_asset(output_dir: Path, zip_filepath: Path) -> Path:
    """
    Package all generated decompiled source files into a `decompiled_source.zip` asset archive.
    """
    print(f"[*] Packaging decompiled source code assets into zip archive: {zip_filepath}")
    zip_filepath.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(output_dir):
            for file in files:
                file_p = Path(root) / file
                if file_p.resolve() == zip_filepath.resolve():
                    continue
                arcname = file_p.relative_to(output_dir.parent if output_dir.parent != output_dir else output_dir)
                zf.write(file_p, arcname)

    print(f"[+] Created decompiled source code zip asset: {zip_filepath} ({zip_filepath.stat().st_size} bytes)")
    return zip_filepath


def main():
    args = [arg for arg in sys.argv[1:] if not arg.startswith('--')]
    input_dir = Path(args[0]) if len(args) > 0 else Path("decoded_output")
    output_dir = Path("decompiled_output")

    print(f"[*] Starting decompilation step for binaries in: {input_dir}")
    decompiled_files = decompile_extracted_artifacts(input_dir, output_dir)

    zip_filepath = Path("decompiled_source.zip")
    create_decompiled_zip_asset(output_dir, zip_filepath)

    print(f"[+] Decompilation step complete. Total source files generated: {len(decompiled_files)}")


if __name__ == "__main__":
    main()
