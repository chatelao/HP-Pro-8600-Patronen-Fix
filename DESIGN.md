# Software Design Specification: HP OfficeJet Pro 8600 Firmware Lookup & Downgrade Tool

## 1. Overview
This document specifies the technical design for the HP OfficeJet Pro 8600 Firmware Lookup & Downgrade Tool. The tool enables users to locate older firmware versions for HP OfficeJet Pro 8600 series printers (e.g. N911a, N911g, N911n) and flash them onto connected printer devices via network or USB interfaces.

---

## 2. System Architecture

```
+-------------------------------------------------------------+
|                Command Line Interface (CLI)                 |
+------------------------------+------------------------------+
                               |
                               v
+-------------------------------------------------------------+
|                         Core Engine                         |
|                                                             |
|  +------------------------+     +------------------------+  |
|  |  Firmware Lookup      |     |  Firmware Flasher      |  |
|  |  Engine                |     |  Engine                |  |
|  +-----------+------------+     +-----------+------------+  |
|              |                              |               |
|              v                              v               |
|  +------------------------+     +------------------------+  |
|  | Verification & Header  |     | Transport / Protocol   |  |
|  | Parser                 |     | (PJL Socket / USB)     |  |
|  +------------------------+     +------------------------+  |
+------------------------------+------------------------------+
                               |
                               v
+-------------------------------------------------------------+
|                HP OfficeJet Pro 8600 Device                 |
|             (Network TCP/9100 or USB Connection)            |
+-------------------------------------------------------------+
```

### Core Components

1. **CLI Layer (`src/cli.py`)**
   - Parses command-line arguments (subcommands, options, arguments).
   - Handles user output, interactive selections, progress display, and error reporting.

2. **Firmware Lookup Engine (`src/lookup.py`)**
   - Discovers available legacy firmware binaries for the HP OfficeJet Pro 8600 series.
   - Searches local firmware storage/cache and remote repositories/mirrors.
   - Filters and ranks firmware candidates by version and target model variant.

3. **Firmware Flasher Engine (`src/flasher.py`)**
   - Coordinates the verification and transfer of firmware payloads to target printers.
   - Manages connection lifecycle (connect, handshake, transmit stream, disconnect).

4. **Verification Module (`src/verifier.py`)**
   - Validates firmware binary integrity via checksums (SHA-256 / MD5).
   - Parses firmware headers to verify model compatibility before sending payload.

5. **Transport Module (`src/transport.py`)**
   - Implements PJL (Printer Job Language) wrapper and direct socket streaming over TCP port 9100.
   - Implements raw USB communication interface when attached via USB.

---

## 3. Communication Protocols & Interfaces

### Network Connection (TCP Port 9100 / PJL)
- **Protocol:** Raw TCP Socket connection to printer IP address on Port 9100.
- **Envelope / Job Framing:** PJL (Printer Job Language) commands encapsulate the raw firmware payload.
- **Example PJL Sequence:**
  ```
  \x1b%-12345X@PJL JOB NAME = "FIRMWARE_UPDATE"
  @PJL ENTER LANGUAGE = POSTSCRIPT
  <RAW_FIRMWARE_PAYLOAD_BYTES>
  \x1b%-12345X@PJL EOJ
  ```

### USB Connection
- **Protocol:** USB Direct Printing class / Raw bulk USB endpoint.
- Transmits raw firmware stream directly to the bulk output endpoint of the attached HP 8600 printer device.

---

## 4. Firmware Verification Specification

Before any flashing operation occurs, the file must pass validation:
1. **File Integrity:** Verify file hash against known expected SHA-256 checksums.
2. **Header Parsing:** Validate magic bytes and firmware header metadata.
3. **Model Matching:** Ensure the target model string matches the HP OfficeJet Pro 8600 series identifier (e.g., `HP OfficeJet Pro 8600 Premium N911g`, `N911a`, `N911n`).

---

## 5. Command-Line Interface (CLI) Design

The CLI supports searching available firmware and flashing a selected firmware payload.

### Command Syntax
```bash
# Search available legacy firmware for a model
hp8600-fw lookup [--model <model_name>] [--local-only]

# Flash firmware onto a connected printer via Network IP
hp8600-fw flash --ip <printer_ip> --firmware <path_or_version>

# Flash firmware onto a connected printer via USB
hp8600-fw flash --usb --firmware <path_or_version>
```

### Command Options
- `-h, --help`: Show help message and exit.
- `-v, --version`: Show tool version.
- `-m, --model`: Target HP 8600 sub-model (e.g. `N911a`, `N911g`, `N911n`).
- `-i, --ip`: Target printer IP address for network flashing (Port 9100).
- `-u, --usb`: Use USB connection for flashing.
- `-f, --firmware`: Path to firmware binary file or version string.
- `-y, --yes`: Skip confirmation prompt.
