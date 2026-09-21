# Concept: Unpacking HP Firmware Packages & Backups in GitHub CI/CD

## 1. Executive Summary & Objective

This document outlines the conceptual framework, execution pipeline, and CI/CD workflow specification for unpacking and extracting HP OfficeJet Pro 8600 series and related HP printer firmware packages (`.ful2`, `.rfu`, `.ful`) and configuration backup files (`.enc`).

Integrating these unpacking mechanisms into a GitHub Actions CI/CD workflow provides automated verification, decomposition, and analysis of printer firmware images as part of automated security reviews, regression checks, or legacy firmware archiving.

---

## 2. Target File Formats & Unpacking Mechanics

The unpacking architecture supports three primary file structures as described in `DECOMPILATION.md` and implemented in `scripts/decode.py`:

### 2.1 Encrypted Firmware Packages (`.ful2`)
* **Container Structure:** PJL wrapper + XML Manifest (`webfwupdate.xsd`) + AES-128-CBC encrypted binary blobs (such as `LBI_blob` or `rootfs_blob`).
* **Key Derivation Strategy:**
  $$\text{KeyMaterial} = \text{SHA256}(\text{Secret} + \text{fw\_model} + \text{blob\_digest\_uncompressed})$$
  * `Secret`: Obfuscated string `@* WebFWUpdate`.
  * `fw_model`: First 6 lowercase characters of the `<updated_revision>` tag in the XML manifest (e.g., `orvill`, `manhhi`).
  * `blob_digest_uncompressed`: Base64-decoded byte value from the XML manifest's `<blob_digest_uncompressed>` element.
* **Decryption & Decompression:**
  * AES Key: First 16 bytes of `KeyMaterial`.
  * IV: 16 null bytes (`\x00` * 16).
  * Payload: AES-128-CBC decrypted, followed by raw `zlib` decompress (`wbits=-15`).

### 2.2 Backup Settings Files (`.enc` / `bksettings`)
* **Container Structure:** `BKST` magic header + Metadata offsets + 16-byte IV + AES-256-CBC ciphertext.
* **Key Derivation Strategy:**
  $$\text{KeyMaterial} = \text{SHA256}(\text{file\_size}_{\text{LE32}} + \text{timer}_{\text{LE32}} + \text{"Is\_Th1s=9-Gd(S8c\$et*K3y?"} + \text{user\_password})$$
* **Decryption & Decompression:**
  * AES Key: 32-byte `KeyMaterial`.
  * IV: Extracted from offset `0x40..0x50`.
  * Post-processing: Strip 32-byte inner MAC header, extract `file_size` bytes, and decompress using Gzip / `zlib`.

### 2.3 Legacy PJL Firmware Updates (`.ful` / `.rfu`)
* **Container Structure:** PJL command header block + raw binary payload + PJL End-of-Job marker.
* **Unpacking Strategy:**
  * Parse `@PJL COMMENT` headers to record model, datecode, and version metadata.
  * Locate `@PJL ENTER LANGUAGE=FWUPDATE` and strip preceding header text.
  * Strip `\x1b%-12345X@PJL EOJ` footer to yield raw binary update payload.

---

## 3. GitHub CI/CD Workflow Architecture

The automated unpacking pipeline is designed as a modular GitHub Actions workflow.

### 3.1 Pipeline Execution Flow

```
+-------------------------------------------------------+
| Trigger: Push / Workflow Dispatch / Release           |
+-------------------------------------------------------+
                           |
                           v
+-------------------------------------------------------+
| Job: Unpack & Inspect Firmware                        |
|   1. Checkout repository code & firmware images       |
|   2. Set up Python environment & dependencies         |
|   3. Run `scripts/decode.py` on target firmware       |
|   4. Verify extracted binary artifacts digest         |
|   5. Upload unpacked artifacts via actions/upload     |
+-------------------------------------------------------+
```

### 3.2 Workflow Specification Example

```yaml
name: Unpack Firmware Packages

on:
  workflow_dispatch:
    inputs:
      target_path:
        description: 'Path to firmware or backup file/directory'
        required: false
        default: 'img'
      backup_password:
        description: 'Password for .enc backup decryption (optional)'
        required: false
        default: ''
  push:
    paths:
      - 'img/**'

jobs:
  unpack:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install Dependencies
        run: |
          python -m pip install --upgrade pip
          pip install pycryptodome xmltodict

      - name: Run Firmware Decoder
        run: |
          python3 scripts/decode.py "${{ github.event.inputs.target_path || 'img' }}" "${{ github.event.inputs.backup_password || '' }}"

      - name: Verify Decrypted Artifacts
        run: |
          if [ -d "decoded_output" ] && [ "$(ls -A decoded_output)" ]; then
            echo "Unpacking succeeded. Extracted artifacts:"
            ls -lh decoded_output/
          else
            echo "No artifacts unpacked or output directory empty."
          fi

      - name: Upload Unpacked Artifacts
        uses: actions/upload-artifact@v4
        with:
          name: unpacked-firmware-artifacts
          path: decoded_output/
```

---

## 4. Verification, Error Handling & Integrity Security

1. **Digest Verification:**
   - Unpacked `.ful2` binary blobs are validated by comparing calculated SHA256 digests of decompressed data against the XML manifest digest tags (`<blob_digest_uncompressed>`).
2. **Missing Dependencies & Secrets:**
   - Fallbacks handle missing Python modules (`pycryptodome`, `xmltodict`) gracefully with informative warnings.
   - Backup passphrases for `.enc` decoding can be securely passed via repository secrets or workflow inputs.
3. **Format Detection:**
   - Sequential format evaluation ensures input files (`.ful2`, `.enc`, `.ful`, `.rfu`) are automatically routed to the correct decoder module.
