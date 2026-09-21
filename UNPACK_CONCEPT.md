# HP Printer Firmware Unpacking in GitHub Actions CI/CD Concept

This document defines the architectural concept, CI/CD pipeline design, and execution strategy for automated unpacking and verification of HP OfficeJet Pro 8600 series printer firmware packages (`.ful2`, `.rfu`, `.ful`, `.enc`) using GitHub Actions.

---

## 1. Overview & Objectives

The goal of automated firmware unpacking in CI/CD is to streamline firmware reverse engineering, analysis, and build verification by automatically extracting raw payload binaries and configuration XMLs whenever new firmware packages or updates are introduced into the repository or downloaded via automated pipelines.

### Key Objectives
* **Automated Processing**: Automatically process incoming HP firmware images (`.ful2`, `.rfu`, `.ful`) and backup files (`.enc`).
* **Reproducibility**: Standardize the extraction environment using containerized or Python-virtualenv-based GitHub Actions runners.
* **Artifact Accessibility**: Store extracted binaries and manifests as GitHub Actions artifacts or Release assets for downstream analysis (e.g., binwalk, static analysis, diffing).
* **Validation & Verification**: Verify payload integrity against embedded SHA-256 hashes or expected size boundaries during the pipeline.

---

## 2. Pipeline Architecture & Workflow

```
[Trigger Event] (push, workflow_dispatch, release)
       │
       ▼
[Job Setup & Environment Preparation]
       │  • Checkout repository
       │  • Setup Python 3.x
       │  • Install dependencies (pycryptodome, xmltodict)
       │
       ▼
[Firmware Discovery & Matrix Processing]
       │  • Locate target packages in img/ or specified paths
       │
       ▼
[Unpacking Stage (scripts/decode.py)]
       ├─► .ful2  ➜ Decrypt AES-CBC blobs using manifest digests & zlib decompress
       ├─► .rfu   ➜ Extract PJL headers & dump raw firmware payload binary
       └─► .enc   ➜ Decrypt BKST backup header + zlib inflate XML settings
       │
       ▼
[Verification & Integrity Check]
       │  • Generate SHA-256 checksums for decoded outputs
       │  • Validate binary payload sizes and signatures
       │
       ▼
[Artifact Storage & Publishing]
          • Upload output binaries as GitHub Actions artifacts
          • (Optional) Attach extracted outputs to GitHub Releases
```

---

## 3. Workflow Trigger Strategy

The firmware unpacking workflow can be triggered by multiple GitHub events:

1. **`push` / `pull_request`**:
   - Triggers on changes to files under `img/` or updates to decoding tools in `scripts/decode.py`.
   - Ensures any new firmware image committed to the repo is immediately validated and unpacked.

2. **`workflow_dispatch` (Manual Trigger)**:
   - Allows maintainers to run unpacking on demand with configurable parameters (e.g., target file path, optional backup password).

3. **`release` (Published Releases)**:
   - Automated workflow runs when a new repository release tag is published, generating unpacked artifacts for release distribution.

---

## 4. Dependencies & Runtime Requirements

The extraction script (`scripts/decode.py`) requires specific Python libraries for cryptographic operations and manifest parsing:

| Dependency | Purpose | Target Formats |
| :--- | :--- | :--- |
| **Python 3.8+** | Execution runtime | All |
| **`pycryptodome`** | AES-CBC cipher decryption | `.ful2`, `.enc` |
| **`xmltodict`** | XML manifest parsing | `.ful2` |
| **Standard Library** | `hashlib`, `zlib`, `struct`, `base64`, `pathlib` | `.rfu`, `.ful`, `.ful2`, `.enc` |

---

## 5. Firmware Package Unpacking Mechanics

### 5.1 `.ful2` Firmware Packages
- **Manifest Parsing**: Reads embedded XML manifest bounded by `<?xml` and `</manifest>`.
- **Key Derivation**: Constructs 128-bit AES key via SHA-256 hash of secret string `@* WebFWUpdate`, firmware model (e.g., `clp1cn`), and `blob_digest_uncompressed`.
- **Decryption & Decompression**: Decrypts raw blob data using AES-CBC (zero IV) and inflates with zlib.

### 5.2 `.rfu` / `.ful` PJL Containers
- **Header Parsing**: Evaluates PJL statements (`@PJL COMMENT MODEL`, `@PJL UPGRADE SIZE`, `@PJL ENTER LANGUAGE=FWUPDATE`).
- **Payload Extraction**: Strips initial PJL headers and trailing `@PJL EOJ` marker to isolate raw firmware binary.

### 5.3 `.enc` BKST Settings
- **Header Parsing**: Validates `BKST` magic header and extracts file size and timer values at offsets `0x34` and `0x38`.
- **Key Derivation**: Computes SHA-256 hash over size, timer, default secret key `Is_Th1s=9-Gd(S8c$et*K3y?`, and optional password.
- **Decryption**: Decrypts ciphertext with AES-CBC and decompress XML contents.

---

## 6. Conceptual GitHub Actions Workflow Specification

Below is an example workflow configuration (`.github/workflows/unpack_firmware.yml`):

```yaml
name: Unpack Firmware Packages

on:
  push:
    paths:
      - 'img/**'
      - 'scripts/decode.py'
  pull_request:
    paths:
      - 'img/**'
      - 'scripts/decode.py'
  workflow_dispatch:
    inputs:
      target_file:
        description: 'Target firmware file path'
        required: false
        default: 'img'
      backup_password:
        description: 'Password for .enc backup files (optional)'
        required: false
        default: ''

jobs:
  unpack:
    name: Unpack Firmware & Generate Artifacts
    runs-on: ubuntu-latest

    steps:
      - name: Checkout Repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install Dependencies
        run: |
          python -m pip install --upgrade pip
          pip install pycryptodome xmltodict

      - name: Execute Firmware Decoding
        env:
          TARGET: ${{ inputs.target_file || 'img' }}
          PASS: ${{ inputs.backup_password || '' }}
        run: |
          python scripts/decode.py "$TARGET" "$PASS"

      - name: Calculate Output Hashes
        run: |
          if [ -d "decoded_output" ]; then
            echo "### Decrypted Artifacts SHA-256 Hashes" >> $GITHUB_STEP_SUMMARY
            sha256sum decoded_output/* >> $GITHUB_STEP_SUMMARY
          else
            echo "No output directory created." >> $GITHUB_STEP_SUMMARY
          fi

      - name: Upload Unpacked Artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: unpacked-firmware-payloads
          path: decoded_output/
          retention-days: 14
```

---

## 7. Security, Secrets & Best Practices

1. **Password Secrets**: Passwords required for encrypted backup files (`.enc`) should be passed securely via GitHub Repository Secrets (`${{ secrets.BACKUP_PASSWORD }}`) rather than plaintext workflow inputs.
2. **Artifact Retention**: Raw binary files can be large (20MB-100MB+). Set an appropriate retention policy (e.g., 14 days) for CI artifacts to manage GitHub storage consumption.
3. **Execution Safety**: Execute unpacking scripts in unprivileged virtual environments without external network access during the decode step.
4. **Validation Steps**: Always calculate SHA-256 checksums of extracted payloads and append them to `$GITHUB_STEP_SUMMARY` for auditability and quick comparison across build runs.
