# Known Open Source Libraries & Components for HP OfficeJet Pro 8600 Series

This document provides a comprehensive list of known open-source libraries, frameworks, utilities, and components used within the firmware and operating environment of the **HP OfficeJet Pro 8600 Series** (N911a, N911g, N911n) and related HP printer platforms, as well as the open-source libraries utilized in the firmware unpacking and decoding toolchain.

---

## 1. Bootloader & Operating System Kernel

| Component / Library | License | Usage / Purpose in HP OfficeJet Pro 8600 |
|---|---|---|
| **U-Boot (Das U-Boot)** | GPL-2.0-or-later | Primary Stage-1/Stage-2 bootloader executing hardware initialization (DRAM, clocks, storage interfaces) and loading the kernel image into DRAM. |
| **Linux Kernel (Embedded Linux)** | GPL-2.0-only | Embedded Linux kernel (v2.6.x / v3.x series on Linux-based printer revisions) providing CPU scheduling, memory management, DMA transfers, and SoC hardware drivers. |
| **VxWorks Open Components** | Mixed (BSD / Proprietary) | Real-Time Operating System (RTOS) kernel components used on classic N911 hardware board builds for deterministic printhead and motor timing. |

---

## 2. Core Userspace Utilities & System Libraries

| Component / Library | License | Usage / Purpose in HP OfficeJet Pro 8600 |
|---|---|---|
| **BusyBox** | GPL-2.0-only | "The Swiss Army Knife of Embedded Linux" — provides essential POSIX command-line utilities (`sh`, `ash`, `ls`, `cp`, `mv`, `cat`, `grep`, `sed`, `ifconfig`, `route`) in a single binary for recovery and diagnostic shells. |
| **uClibc / glibc** | LGPL-2.1-or-later | C Standard Library implementation providing core system call wrappers, dynamic linking, and runtime library support for ARM architectures. |
| **Libgcc / Libstdc++** | GPL-3.0-with-GCC-exception | GCC compiler runtime libraries required for C++ binary execution and exception handling on ARM RISC targets. |

---

## 3. Cryptography, Security & Network Protocols

| Component / Library | License | Usage / Purpose in HP OfficeJet Pro 8600 |
|---|---|---|
| **OpenSSL** | Apache-1.0 / BSD-style | Cryptographic provider for SSL/TLS network transport, HTTPS Embedded Web Server (EWS), network scanning encryption, and SHA256/AES primitives. |
| **mbed TLS / PolarSSL** | Apache-2.0 / GPL-2.0+ | Lightweight SSL/TLS and crypto library used in embedded firmware subsystems and network service daemons. |
| **libcurl** | curl License (MIT-style) | Multiprotocol file transfer library enabling HTTP/HTTPS web service calls, Cloud Print communication, ePrint service sync, and firmware update checks. |
| **Samba / cifs-utils** | GPL-3.0-or-later | Network filesystem client implementation enabling the **Scan-to-Folder** feature via SMB/CIFS protocol transfers to Windows shares. |
| **Net-SNMP** | BSD / MIT-style | Simple Network Management Protocol (SNMP) agent implementation for network printer status reporting, MIB queries, and enterprise monitoring (HP Web Jetadmin). |
| **lwIP (Lightweight IP)** | BSD-3-Clause | Embedded TCP/IP stack implementation for resource-constrained RTOS firmware builds, handling socket communication over Ethernet/Wi-Fi on Port 9100. |

---

## 4. File Systems, Compression & Data Archives

| Component / Library | License | Usage / Purpose in HP OfficeJet Pro 8600 |
|---|---|---|
| **zlib** | zlib License | Lossless data compression library used for PJL stream decompression, DEFLATE/Zlib inflation of firmware blobs (`.ful2`), and HTTP Gzip response handling. |
| **Gzip** | GPL-3.0-or-later | Compression utility and file format handler used in backup settings (`.enc` / `bksettings`) payloads and system log compression. |
| **UBIFS / mtd-utils** | GPL-2.0-only | Flash memory file system utilities (`ubi_reader`, `mkfs.ubifs`, `ubinize`) for reading, writing, and managing UBI volumes on raw NAND flash memory. |
| **libarchive / tar** | BSD-2-Clause / GPL-3.0+ | Archiving utilities for extracting and packaging firmware file system images and resource archives. |

---

## 5. Graphics, Image Processing & Rendering

| Component / Library | License | Usage / Purpose in HP OfficeJet Pro 8600 |
|---|---|---|
| **libjpeg / libjpeg-turbo** | IJG / BSD-style | Hardware-accelerated JPEG image decoding for processing scanned images, photo printing from USB/SD cards, and GUI image display on the touch LCD screen. |
| **libpng** | libpng-2.0 | PNG image decoding library used for rendering UI icons and touch menu assets on the printer display. |
| **FreeType (libfreetype)** | FTL / GPL-2.0-or-later | Font rendering engine used to display localized text strings and fonts on the control panel screen and in rendered print job overlays. |
| **Expat / libxml2** | MIT / MIT | XML parser libraries used for reading configuration files, EWS Web Services communication, XML manifest parsing in `.ful2` updates, and backup XML decoding. |

---

## 6. Data Serialization & Storage

| Component / Library | License | Usage / Purpose in HP OfficeJet Pro 8600 |
|---|---|---|
| **Protocol Buffers (protobuf)** | BSD-3-Clause | Google binary serialization library used for encoding internal configuration settings, component state blobs, and SMB Scan-to-Folder credentials stored in XML backup archives (`<BlobValue>`). |
| **SQLite** | Public Domain | Embedded SQL database engine used in printer firmware to index print job logs, address books, quick forms, and network configuration profiles. |

---

## 7. Open Source Printing Subsystems & HPLIP

| Component / Library | License | Usage / Purpose in HP OfficeJet Pro 8600 |
|---|---|---|
| **HPLIP (HP Linux Imaging and Printing)** | GPL-2.0 / BSD / MIT | HP official open-source Linux drivers, printer models definition files (`models.dat`), PPD files, and device communication layer for HP OfficeJet Pro 8600 series printers. |
| **CUPS (Common Unix Printing System) Components** | Apache-2.0 with GPL-2.0 Exception | IPP protocol implementation, raster filters, and print job queue management integration. |

---

## 8. Reverse Engineering & Firmware Decoding Toolchain Dependencies

The repository's python decoding toolchain (`scripts/decode.py`) relies on the following open-source Python libraries to unpack, decrypt, and inspect HP OfficeJet Pro 8600 firmware images:

| Library / Tool | License | Role in Toolchain |
|---|---|---|
| **PyCryptodome (`Crypto.Cipher.AES`)** | BSD-2-Clause / Public Domain | Provides AES-128-CBC and AES-256-CBC decryption routines for `.ful2` firmware blobs and `.enc` backup files (`bksettings`). |
| **xmltodict** | MIT | Converts XML manifest files extracted from `.ful2` firmware headers into Python dictionary structures for key derivation calculations. |
| **ubi_reader** | GNU GPLv3 | Python module and CLI tools used to parse and extract UBIFS file system volumes from raw NAND flash dumps. |
| **7-Zip (7z)** | GNU LGPL | Unpacking utility for extracting `.ful2` firmware containers from executable Windows update binaries (`OJP8600.exe`). |
