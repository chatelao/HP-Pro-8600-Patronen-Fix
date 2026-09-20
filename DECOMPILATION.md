# Dokumentation: Dekompilierung der HP OfficeJet Pro 8600 Firmware

## 1. Übersicht & Zielsetzung

Diese Dokumentation fasst das gesammelte Wissen bezüglich der Analyse, Extraktion und Dekompilierung der Firmware der **HP OfficeJet Pro 8600 Serie** (Modelle N911a, N911g und N911n) zusammen.

Ziel des Dekompilierungsprozesses ist es, die interne Funktionsweise des Druckers zu verstehen, Sicherheitsmechanismen (wie z. B. Dynamic Security / Tintenpatronen-Authentifizierung) zu analysieren, Protokoll-Implementierungen nachzuvollziehen und den Boot- bzw. Ausführungsprozess nachzubilden.

---

## 2. Firmware-Dateiformate & Kapselung

### 2.1 Dateiendungen & Quellen
* **Dateiendungen:** `.rfu` (Remote Firmware Update) oder `.ful.rfu`.
* **Quellen:** Offizielle HP-FTP-Server (z. B. `ftp.hp.com/pub/networking/software/pfirmware/`) oder HP Support-Downloads.

### 2.2 PJL (Printer Job Language) Wrapper
Die Firmware-Dateien sind in der Regel nicht sofort reine Binärimages, sondern in PJL-Befehle eingepackt, damit sie direkt über Port 9100 (Raw TCP Socket) oder USB-Bulk an den Drucker gesendet werden können.

Ein typisches Format sieht wie folgt aus:
```text
\x1b%-12345X@PJL JOB NAME = "FIRMWARE_UPDATE"
@PJL ENTER LANGUAGE = POSTSCRIPT
<ROH_FIRMWARE_PAYLOAD_IMAGE>
\x1b%-12345X@PJL EOJ
```

### 2.3 Firmware-Header & Struktur
Innerhalb des PJL-Wrappers befindet sich das eigentliche Firmware-Payload-Image:
* **Magic Bytes:** Häufig gekennzeichnet durch Header-Identifier wie `HP-FW` oder herstellerspezifische Signaturen.
* **Modell-Kennung:** Strings zur Überprüfung der Hardware-Kompatibilität (`N911a`, `N911g`, `N911n`, `CM749A`, `CM750A`, `CN577A`).
* **Prüfsummen & Signaturen:**
  * CRC32 / SHA-256 zur Verifizierung der Payload-Integrität.
  * Cryptographic Signature (RSA/ECC) bei neueren Firmware-Versionen zur Aufdringung von Signaturprüfungen.

---

## 3. Entpacken & Extraktion (Unpacking Workflow)

### 3.1 Schritt 1: Entfernen des PJL-Wrappers
Bevor Werkzeuge wie `binwalk` angesetzt werden, müssen die PJL-Header und -Trailer abgeschnitten werden.

Beispiel mit Python oder `dd`:
```bash
# Suchen nach dem Start des binären Payloads nach den PJL-Headern
grep -a -b -m 1 "@PJL ENTER LANGUAGE" firmware.rfu
# Alternativ mit Python die Bytes vor und nach dem PJL-Container trimmen
```

### 3.2 Schritt 2: Analyse mit Binwalk
Mit `binwalk` lässt sich das rohe Firmware-Image nach bekannten Signaturen (Dateisysteme, Kompressionsblöcke, Kernel-Header) durchsuchen:
```bash
binwalk firmware_raw.bin
binwalk -e --rm firmware_raw.bin
```

### 3.3 Dekompression & Dateisysteme
Häufig anzutreffende Kompressionen und Dateisysteme:
* **Kompressions-Algorithmen:** `zlib`, `gzip`, `LZMA`, `LZW` oder herstellerspezifische RLE-Derivate.
* **Dateisysteme:** `SquashFS`, `CRAMFS`, `JFFS2` oder proprietäre VxWorks/RTOS-Dateisystemstrukturen.

---

## 4. Prozessor-Architektur & System-Spezifikationen

Für die genaue Konfiguration von Dekompilern (Ghidra, IDA Pro, Binary Ninja) müssen die folgenden Hardware-Parameter beachtet werden:

| Parameter | Spezifikation |
|---|---|
| **SoC** | Marvell Armada / Orion Printer SoC Derivat |
| **CPU Core** | ARM v5TE / ARM v7-A (32-Bit RISC) |
| **Endianness** | Little-Endian |
| **Arbeitsspeicher (RAM)** | 128 MB bis 256 MB DDR/DDR2 SDRAM |
| **Flash-Speicher** | 64 MB bis 128 MB NOR / NAND Flash |
| **Betriebssystem (RTOS)** | VxWorks oder proprietäres Embedded OS / Linux-Kernel |

---

## 5. Setup & Analyse in Dekompilern (z. B. Ghidra)

### 5.1 Import-Einstellungen
Beim Importieren eines rohen Kernel-/Firmware-Binärfiles in Ghidra oder IDA Pro:
* **Processor Language:** `ARM:LE:32:v5t` oder `ARM:LE:32:v7` (Default Instruction Set: ARM / Thumb).
* **Endianness:** Little-Endian.

### 5.2 Bestimmung der Basisadresse (Base Address / Rebase)
Da rohe Binärabbilder oft keine ELF-Header besitzen, muss die Basisadresse im Speicher ermittelt werden:
1. **Interrupt-Vektortabelle:** Am Anfang der Binärdatei suchen (ARM Reset Vector `0xEA0000XX` B-Instruction).
2. **String-Referenzen:** Achte darauf, ob absolute Speicheradressen in Pointer-Tabellen auf Pointer-Bereiche wie `0x00000000`, `0x40000000` oder `0x80000000` zeigen.
3. **Rebase in Ghidra:** Über `Memory Map` -> `Move Block` die Basisadresse anpassen, bis String-Referenzen im Code korrekte Ziele anzeigen.

### 5.3 VxWorks / RTOS Symbol-Rekonstruktion
Falls ein VxWorks-RTOS verwendet wird:
* Suche nach integrierten Symboltabellen im Binary (Strings von C-Funktionsnamen gekoppelt mit Speicheradressen).
* Verwendung von Ghidra-Skripten wie `VxWorksGhidra` zur automatischen Rekonstruktion von Funktionsnamen und System-Calls (`taskSpawn`, `semBCreate`, `msgQCreate`).

---

## 6. Wichtige Reverse-Engineering-Ziele

### 6.1 Dynamic Security & Patronen-Authentifizierung
* **Krypto-Elemente:** Kommunikation mit dem Secure Element (Dallas DS28E15 Derivat) auf den Ink-Cartridges über I2C/1-Wire.
* **Schlüsselfunktionen:** Suche nach RSA/ECC Public Key Validierungen, Seriennummern-Prüfungen und Datums- bzw. Gültigkeitsprüfungen für Fremdtinten.

### 6.2 PJL & Netzwerk-Handler
* **Port 9100 / Socket Listener:** Identifikation der Funktionen, die empfangene PJL-Befehle parsen.
* **Firmware-Flashing Routinen:** Analyse der Funktionen, die Aktualisierungen empfangen, verifizieren und im Flash-Speicher überschreiben.

### 6.3 EWS (Embedded Web Server) Assets
* Extrahieren von Weboberflächen-Dateien (HTML, JS, XML-Ressourcen), die oft im Flash als komprimiertes Verzeichnis vorliegen.

---

## 7. Zusammenfassung der Werkzeuge

* **Extraktion:** `binwalk`, `dd`, `pjl-extract` (Python), `7-zip`.
* **Disassembler & Dekompiler:** Ghidra (mit ARM v5t/v7 Module), IDA Pro, Binary Ninja.
* **Skripte & Hilfsmittel:** `VxWorksGhidra`, `arm-none-eabi-objdump`.
