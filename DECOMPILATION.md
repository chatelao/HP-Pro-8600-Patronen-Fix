# Dokumentation: Dekompilierung der HP OfficeJet Pro 8600 Firmware & Backup-Analyse

## 1. Übersicht & Zielsetzung

Diese Dokumentation fasst das gesammelte Wissen bezüglich der Analyse, Extraktion, Entschlüsselung und Dekompilierung der Firmware sowie der Konfigurations-Backups der **HP OfficeJet Pro 8600 Serie** (Modelle N911a, N911g und N911n) und verwandter HP-Druckerarchitekturen zusammen.

Primäres Referenzmaterial bildet die Sicherheitsanalyse von [Romern (2026)](https://romern.me/blog/hp-printer-backup-decryption/), welche die Interna des `.ful2`-Firmware-Verschlüsselungsformats sowie das proprietäre `.enc` (`bksettings`)-Format für Einstellungen-Backups aufgedeckt hat.

Ziel des Dekompilierungsprozesses ist es:
* Die interne Funktionsweise des Druckers und des Betriebssystems (VxWorks RTOS / Embedded Linux) zu verstehen.
* Sicherheitsmechanismen (z. B. Dynamic Security / Tintenpatronen-Authentifizierung, Firmware-Signaturprüfungen) zu analysieren.
* Gespeicherte Anmeldedaten (wie SMB Scan-to-Folder Passwörter) aus Konfigurations-Backups zu rekonstruieren.
* Den Flashing-, Boot- und Ausführungsprozess vollständig nachzuvollziehen.

---

## 2. Firmware-Dateiformate & Kapselung

### 2.1 Dateiendungen & Quellen
* **Klassisches Format:** `.rfu` (Remote Firmware Update) oder `.ful.rfu`.
* **Neueres verschlüsseltes Format:** `.ful2` (Eingeführt bei HP Envy Foto, OfficeJet Pro 8000/9000er Serie sowie neueren 8600er Absicherungen).
* **Quellen:** Offizielle HP Support-Downloads, FTP-Server (`ftp.hp.com/pub/networking/software/pfirmware/`) oder extrahierte Update-Exe-Dateien (`7z x OJP8600.exe`).

### 2.2 PJL (Printer Job Language) Wrapper
Sowohl `.rfu` als auch `.ful2` Firmware-Dateien sind in PJL-Befehle eingepackt, um direkt über den Netzwerkkanal (Port 9100 Raw TCP Socket) oder per USB-Bulk an den Drucker gesendet zu werden.

Ein typischer PJL-Firmware-Container sieht wie folgt aus:
```text
\x1b%-12345X@PJL JOB NAME = "FIRMWARE_UPDATE"
@PJL COMMENT MODEL=Officejet Pro 8600 N911a
@PJL COMMENT VERSION=CLP1CN1304AR
@PJL COMMENT DATECODE=20130124
@PJL UPGRADE SIZE=25569076
\x1b%-12345X@PJL COMMENT (null)
@PJL ENTER LANGUAGE=FWUPDATE
<PAYLOAD>
\x1b%-12345X@PJL EOJ
```
Bei `.ful2`-Dateien lautet das Sprachkommando `@PJL ENTER LANGUAGE=FWUPDATE2`.

### 2.3 `.ful2` Verschlüsseltes Firmware-Paket (XML Manifest & Blobs)
Bei `.ful2`-Firmwares folgt auf den PJL-Header ein strukturierter XML-Manifest-Header (`webfwupdate.xsd`), gefolgt von binär verschlüsselten Daten-Blobs (`LBI_blob`, `rootfs_blob`).

#### Manifest-Struktur (Auszug):
```xml
<?xml version='1.0' encoding='UTF-8'?>
<manifest xsi:noNamespaceSchemaLocation='webfwupdate.xsd' xmlns:xsi='http://www.w3.org/2001/XMLSchema-instance'>
    <version>0.9</version>
    <signature>
        <signature_template_id>49be5195-1daa-474a-a957-1aa4ae38d9b1</signature_template_id>
        <public_key_id>bdfcc564-a078-4112-a089-179e73831f27</public_key_id>
        <signature_value>...</signature_value>
        <digest>...</digest>
    </signature>
    <signedInfo>
        <update_type>optional</update_type>
        <current_revision>ANY</current_revision>
        <updated_revision>MANHHIPP1N005.2607A.00</updated_revision>
        <LBI_blob>
            <blob_path>...</blob_path>
            <size_compressed>8083633</size_compressed>
            <size_uncompressed>9009792</size_uncompressed>
            <blob_digest_compressed>...</blob_digest_compressed>
            <blob_digest_uncompressed>oIOs1VSN923xKJ2xnHkMpkdiDcXNAP6hoLLLRXnliKk=</blob_digest_uncompressed>
        </LBI_blob>
        <rootfs_blob>
            <blob_path>...</blob_path>
            <size_compressed>64049556</size_compressed>
            <size_uncompressed>78512128</size_uncompressed>
            <blob_digest_compressed>...</blob_digest_compressed>
            <blob_digest_uncompressed>hxL+s8twRkwnVMwh5uOGwqRp5/8h0tGbYxWwboWnNuI=</blob_digest_uncompressed>
        </rootfs_blob>
    </signedInfo>
</manifest>
```

#### Entschlüsselungs-Algorithmus für `.ful2`:
Die Verschlüsselung nutzt AES-128-CBC über raw `zlib`-komprimierte Daten. Der Schlüssel wird dynamisch aus Manifest-Eigenschaften abgeleitet:

1. **Obfuszierter Secret String:** In der Binary `fwupd` befindet sich das obfuszierte Secret `@* WebFWUpdate`. Es wird durch eine einfache XOR-Operation wiederhergestellt:
   ```python
   ARRAY = [0x00, 0x14, 0x7f, 0x76, 0x00, 0x3d, 0x3b, 0x1c, 0x0c, 0x09, 0x2d, 0x3a, 0x3e, 0x14, 0x04, 0x00]
   j = 0x54
   secret = bytes([b ^ (j + i) for i, b in enumerate(ARRAY[1:-1])]).decode() # '@* WebFWUpdate'
   ```
2. **Modell-Prefix (`fw_model`):** Der Wert aus `updated_revision` wird in Kleinbuchstaben umgewandelt und auf die ersten 6 Zeichen gekürzt (z. B. `ORVILL...` -> `orvill`, `MANHHIPP1N005...` -> `manhhi`, `PALMIN...` -> `palmin`).
3. **Digest:** Der Wert aus `<blob_digest_uncompressed>` wird Base64-dekodiert.
4. **Schlüsselableitung (Key Derivation):**
   $$\text{KeyMaterial} = \text{SHA256}(\text{secret} + \text{fw\_model} + \text{blob\_digest\_uncompressed})$$
   * **AES-Key:** Die ersten 16 Bytes von `KeyMaterial`.
   * **AES-IV:** 16 Null-Bytes (`\x00` * 16).
5. **Dekomprimierung:** Der entschlüsselte Ciphertext wird mittels raw `zlib` (`wbits=-15`) dekodiert.

### 2.4 Modell-Codenamen, `fw_model` & Firmware-Präfixe

Für die Schlüsselableitung (`fw_model`) sowie die Zuordnung der Firmware-Revisionen zu den Druckermodellen dienen interne Codenamen und Modell-Präfixe aus der `fwupd`-Konfiguration (`fwupdConfig::fw_model`):

| Series / Model | Internal Codename | `fwupdConfig::fw_model` | Firmware Version Prefix / Notes | Quelle / Ref |
|---|---|---|---|---|
| **HP OfficeJet Pro 8600** (N911a/g/n) | Orville | `ORVILL` / `OJ8600` | CLP1CN, CKP1CN (Base AIO platform) | romern.me |
| **HP OfficeJet Pro 8100** (N811a) | Wilbur | `WILBUR` / `OJ8100` | TRP1CN (SFP counterpart to 8600) | romern.me |
| **HP OfficeJet Pro 8610 / 8620 / 8630** | Malibu (Orville Refresh) | `MALIBU` | FDP1CN (Mid-generation refresh) | romern.me |
| **HP OfficeJet Pro 8730 / 8740** | Manhattan High | `MANHHI` | EDP1CN (fw_model 6-char Seed für AES-Key in .ful2) | romern.me |
| **HP OfficeJet Pro 8710 / 8720** | Manhattan Low / Mid | `MANHLO` / `MANHMID` | WBP1CN (Manhattan Low/Mid Logische Architektur-Ableitung) | (Struktur-Derivat) |
| **HP ENVY Photo 6232 / 4520 / 5540** | Palmetto / Palm | `PALMIN` | KP1CN (fw_model 6-char Seed für AES-Key in .ful2) | romern.me |
| **HP OfficeJet 6500** (E710n-z) | CHIANTI | `CHIANTI` | Firmware Payload Präfix (`chianti_pp_usr_hf...`) | nullsec.us |
| **HP PSC 1410** | ERIDANI | `ERIDANI` | Hardware-Codename (ARM9 SoC), sichtbar im ThreadX UART-Boot-Banner | elektroda.com |
| **HP OfficeJet Pro 6830 / 6960** | COPPERHEAD | `COPPERHEAD` (CopperheadXLP) | tech-class im Quellcode der HPLIP `models.dat` | HPLIP Repository |
| **HP LaserJet 4050** | LEGOLAS | `LEGOLAS` | Interner Entwicklungs-Codename (Herr der Ringe Nomenklatur) | Reddit Ex-HP-Dev |
| **HP OfficeJet 8028 / 8035** | OASIS | `OASIS` | Marketing- / Plattform-Name für Vertrieb & Farbgebung | B&H Photo Specs |
| **HP-91** (Druckender Rechner) | FELIX | `FELIX` | Entwicklungs-Codename ("Topcat" Familie) | HPCC.org |

---

## 3. Entschlüsselung von Backup-Dateien (`bksettings` / `.enc`)

HP OfficeJet und PageWide Drucker bieten eine Backup/Restore-Funktion für Einstellungen. Die exportierte Backup-Datei (z. B. `usrdata-2.enc`) ist mit dem proprietären Dienst `bksettings` verschlüsselt.

### 3.1 Binäre Datei-Struktur von `.enc` (bksettings)

| Byte-Offset | Feld | Beschreibung |
|---|---|---|
| `0x00 - 0x03` | Magic | Char-Array `"BKST"` (`0x54534b42`) |
| `0x04 - 0x0F` | Timer / Metadata | Zeitstempel- und Header-Informationen |
| `0x10 - 0x2F` | Outer MAC | 32-Byte SHA256 Prüfsumme / HMAC |
| `0x30 - 0x33` | Inner Magic | Magic Value `0x91129215` |
| `0x34 - 0x37` | Uncompressed File Size | 32-Bit Little-Endian Integer (`file_size`) |
| `0x38 - 0x3B` | Timer Value | 32-Bit Little-Endian Integer (`timer`) |
| `0x40 - 0x4F` | Initialization Vector | 16-Byte AES IV |
| `0x50 - ...` | Ciphertext | AES-256-CBC verschlüsselter Payload |

### 3.2 Schlüsselableitung & Entschlüsselungs-Workflow
Der AES-Schlüssel basiert auf Angaben in der Datei, einem fest im Code hinterlegten Schlüssel-String und dem vom Benutzer gewählten Backup-Passwort:

$$\text{AES-Key} = \text{SHA256}(\text{file\_size}_{\text{LE32}} + \text{timer}_{\text{LE32}} + \text{"Is\_Th1s=9-Gd(S8c\$et*K3y?"} + \text{user\_password})$$

#### Entschlüsselungsschritte:
1. AES-256-CBC Entschlüsselung des Ciphertexts ab Offset `0x50`.
2. Überspringen der ersten 32 Bytes des Klartexts (innerer HMAC / Digest).
3. Entnahme der folgenden `file_size` Bytes.
4. Gzip-Dekomprimierung (`zlib.decompress(content, zlib.MAX_WBITS | 16)`).

### 3.3 Extrahieren vertraulicher Daten (z. B. Scan-to-Folder SMB Credentials)
Die dekomprimierte Datei ist ein XML-Dokument. Innerhalb von XML-Elementen befinden sich Base64-kodierte Protobuf-Blobs (`<BlobValue>`), die sensible Zugangsdaten enthalten:

```xml
<CpntName>ScanToFolder</CpntName>
...
<BlobValue>CgIYARLGARgAIOgHWoIBChAaBHRlc3QiACgAMOvBltEGEg1cXHRlc3RwY1x0ZXN0GgEg...</BlobValue>
```

Durch Base64-Dekodierung des Protobuf-Blobs lassen sich SMB-Benutzernamen, Ziel-Pfade (`\\testpc\test`) und Klartext-Passwörter auslesen.

---

## 4. Hardware Flash Extraction & UBIFS File System Unpacking

Wenn kein Firmware-Update vorliegt oder der Bootloader isoliert werden soll, kann der NAND/NOR-Flash direkt von der Platine ausgelesen werden.

### 4.1 Physical NAND Dumping Workflow
1. **Entlöten des Flash-Chips:** Entlöten des NAND Flash ICs (z. B. Macronix MX30LF1G18AC TSOP-48) von der Hauptplatine.
2. **Auslesen mit Programmer:** Einlegen in einen Universal-Programmer (z. B. XGecu T56).
3. **Deaktivierung der Spare Area:** Um eine saubere Datei ohne Out-Of-Band (OOB) / ECC Spare-Bytes für `binwalk` zu erhalten, muss das Auslesen der Spare Area im Programmer deaktiviert werden.

### 4.2 UBI / UBIFS Dateisystem-Extraktion
Ein `binwalk`-Scan eines sauberen NAND-Dumps zeigt die UBI-Image-Partitionen:
```text
DECIMAL     HEXADECIMAL   DESCRIPTION
----------------------------------------------------------------------
10092544    0x9A0000      UBI image, version: 1, image size: 92798976 bytes
102891520   0x6220000     UBI image, version: 1, image size: 22282240 bytes
```

Entpacken des UBIFS-Volumes mittels `ubi_reader`:
```bash
ubireader_extract_files img-87517464_vol-rootfs.ubifs -o ubifs-root
```

---

## 5. Prozessor-Architektur & System-Spezifikationen

Für die Dekompilierung in Ghidra oder IDA Pro gelten folgende Hardware- und System-Parameter:

| Parameter | Spezifikation |
|---|---|
| **SoC** | Marvell Armada / Orion Printer SoC Derivat |
| **CPU Core** | ARM v5TE / ARM v7-A (32-Bit RISC) |
| **Endianness** | Little-Endian |
| **Arbeitsspeicher (RAM)** | 128 MB bis 256 MB DDR/DDR2 SDRAM |
| **Flash-Speicher** | 64 MB bis 128 MB NOR / NAND Flash |
| **Betriebssystem** | VxWorks RTOS (Klassische N911 Serie) / Embedded Linux mit UBIFS (Neuere Architekturen) |

---

## 6. Analyse wichtiger Binärdateien in Dekompilern (Ghidra / IDA Pro)

### 6.1 `fwupd` (Firmware Update Daemon)
Liegt unter `/usr/local/bin/fwupd` in Linux-basierten HP-Firmwares.
* **`fwupd_install`:** Haupt-Installationsroutine für Firmware-Updates.
* **`fwupdCodec::read`:** Führt die AES-CBC Entschlüsselung mittels OpenSSL `AES_cbc_encrypt` durch.
* **`fwupdCodec::configure`:** Initialisiert den AES-Schlüssel via `AES_set_decrypt_key` unter Verwendung des oben beschriebenen SHA256-Key-Derivation-Schemas.

### 6.2 `bksettings` (Backup & Restore Handler)
Verantwortlich für das Lesen und Schreiben verschlüsselter `.enc`-Sicherungsdateien.
* **`FUN_00017af8`:** Verarbeitet die Entschlüsselung.
* Verwendet HP-Crypto-Wrapper um OpenSSL-EVP-Funktionen (`EVP_sha256`, `EVP_aes_256_cbc`).

### 6.3 Patronen-Authentifizierung & Dynamic Security
* **Hardware-Schnittstelle:** I2C / 1-Wire Bus zu den Krypto-Chips auf den Tintenpatronen (Dallas DS28E15 Derivat).
* **Funktionen:** Verifizierung von digitalen RSA/ECC-Signaturen, Seriennummern-Abgleich, Ablaufdatumskontrollroutinen und Zählerabgleich zur Blockade von Fremdtinten.

---

## 7. Skripte & Werkzeuge im Repository

Im Verzeichnis `scripts/` steht das Python-Skript `decode.py` bereit, welches die beschriebenen Entschlüsselungsverfahren automatisiert:

```bash
# Entschlüsseln einer .ful2 Firmware-Datei
python3 scripts/decode.py firmware.ful2

# Entschlüsseln eines .enc Einstellungen-Backups mit Passwort
python3 scripts/decode.py backup.enc mein_passwort

# Extraktion des Payloads aus einer klassischen PJL .ful.rfu Datei
python3 scripts/decode.py img/ojpro_8600_n911_a_1304A_10042013.ful.rfu
```

### Benötigte Python-Bibliotheken:
* `pycryptodome` (`Crypto.Cipher.AES`)
* `xmltodict`

---

## 8. Open-Source-Bibliotheken & Software-Komponenten

Für eine detaillierte Übersicht aller bekannten Open-Source-Bibliotheken, Betriebssystem-Komponenten, Krypto-Pakete, Grafik-Engines und Werkzeuge, die im HP OfficeJet Pro 8600 sowie in der Analyse-Toolchain zum Einsatz kommen, siehe das Referenzdokument:

👉 **[OPEN_SOURCE_LIBRARIES.md](OPEN_SOURCE_LIBRARIES.md)**

---

## 9. Unpack, Decrypt, Encrypt & Pack Logic (Pure Technical Specification)

Dieser Abschnitt fasst die exakte technische Spezifikation der Entschlüsselungs-, Verschlüsselungs- und Packing-Mechanismen für `.ful2`-Firmware-Dateien und `.enc` (`bksettings`)-Sicherungsdateien zusammen.

### 8.1 Unpack algorithms / tools

* **Tools:**
  * `7z` (7-Zip): Extrahieren der `.ful2`-Firmware-Container aus ausführbaren Windows-Installationsdateien (`7z x OJP9020_2607A.exe`).
  * `xmltodict` / Python XML Parser: Extrahieren und Parsen des XML-Manifests im `.ful2`-Header zwischen `<?xml` und `</manifest>`-Tags.
  * `struct` (Python `struct.unpack_from`): Einlesen binärer Little-Endian-Header-Felder aus `.enc` (`bksettings`)-Dateien (`file_size` bei Offset `0x34`, `timer` bei `0x38`, `iv` bei `0x40:0x50`).
  * `zlib` / `gzip`:
    * Raw-Deflate Dekomprimierung (`zlib.decompress(data, wbits=-15)`) für `.ful2`-Blobs.
    * Gzip-Dekomprimierung (`zlib.decompress(content, zlib.MAX_WBITS | 16)`) für den Klartext-Payload aus `.enc`-Dateien.
  * `binwalk`: Analyse und Partitions-Scans entpackter Rohdateien (Identifikation von UBI-Images, Device Tree Blobs `.dtb`, Gzip-Archiven).
  * `ubireader_extract_files` (`ubi_reader`): Extraktion von UBIFS-Dateisystemen aus entpackten UBI-Image-Dateien (`ubireader_extract_files img-..._vol-rootfs.ubifs`).
  * `base64` & Protobuf-Parser / `strings`: Dekodierung von Base64-kodierten Protobuf-Blobs (`<BlobValue>`) im extrahierten Konfigurations-XML zum Auslesen von SMB-Zugangsdaten (Scan-to-Folder).

* **Algorithms:**
  * **PJL Header Stripping:** Auffinden von `@PJL ENTER LANGUAGE=FWUPDATE2` oder `@PJL ENTER LANGUAGE=FWUPDATE` und Entfernen des PJL-Preambels sowie des `\x1b%-12345X@PJL EOJ`-Footers.
  * **Length-Prefixed Chunk Parsing (`.ful2`):** Iterieren über binäre Blobs im Anschluss an das XML-Manifest, wobei jedem verschlüsselten Blob seine Bytelänge als Hexadezimal-String gefolgt von `\n` vorangestellt ist.
  * **Binary Offset Slicing (`bksettings` / `.enc`):**
    * `0x00 - 0x03`: ASCII Magic Check (`"BKST"` / `0x54534b42`).
    * `0x04 - 0x0F`: Timer / Metadaten.
    * `0x10 - 0x2F`: Äußerer SHA256 MAC (32 Bytes).
    * `0x30 - 0x33`: Inner Magic Check (`0x91129215`).
    * `0x34 - 0x37`: `file_size` (32-Bit LE Integer).
    * `0x38 - 0x3B`: `timer` (32-Bit LE Integer).
    * `0x40 - 0x4F`: Initialisierungsvektor IV (16 Bytes).
    * `0x50 - Ende`: AES-256-CBC Ciphertext.
    * Post-Decryption Inner HMAC Stripping: Überspringen der ersten 32 Bytes (innerer HMAC/Digest) des entschlüsselten Datenblocks zur Isolierung der folgenden `file_size` Bytes.

---

### 8.2 Decrypt algorithms / tools

* **Tools:**
  * `pycryptodome` (`Crypto.Cipher.AES`) / OpenSSL EVP C-Bibliothek (`AES_cbc_encrypt`, `EVP_aes_256_cbc`).
  * Python `hashlib` (SHA-256 Berechnung).
  * Ghidra / IDA Pro: Reverse-Engineering-Werkzeuge zur Analyse von `/usr/local/bin/fwupd` (`fwupd_install`, `fwupdCodec::read`, `fwupdCodec::configure`) und `bksettings` (`FUN_00017af8`).

* **Algorithms:**
  * **`.ful2` Decryption Algorithm:**
    * AES-128-CBC Entschlüsselung über den längenpräfixierten verschlüsselten Blob-Payload unter Verwendung von 16 Null-Bytes als IV (`bytes(16)`).
    * Dekomprimierung der entschlüsselten Bytes über Raw Deflate (`zlib.decompress(compressed, wbits=-15)`).
  * **`bksettings` (`.enc`) Decryption Algorithm:**
    * AES-256-CBC Entschlüsselung des Ciphertexts ab Offset `0x50` unter Verwendung des bei Offset `0x40` entnommenen 16-Byte IV.
    * Entnahme von `file_size` Bytes ab Byte-Offset 32 des entschlüsselten Puffers und anschließende Gzip-Dekomprimierung (`zlib.decompress(content, zlib.MAX_WBITS | 16)`).

---

### 8.3 Keys

* **`.ful2` Firmware Keys:**
  * **Hardcoded Secret String:** `@* WebFWUpdate` (In `/usr/local/bin/fwupd` mittels XOR-Schleife obfuszieren: `ARRAY[i] ^ (0x54 + i - 1)`).
  * **Firmware Modell-String (`fw_model`):** Erste 6 Kleinbuchstaben des Tags `<updated_revision>` aus dem XML-Manifest (z. B. `MANHHIPP1N005.2607A.00` -> `manhhi`, `PALMIN...` -> `palmin`).
  * **Uncompressed Blob Digest (`blob_digest_uncompressed`):** Base64-dekodierte Bytefolge aus dem Feld `<blob_digest_uncompressed>` des XML-Manifests für den jeweiligen Blob (`LBI_blob`, `rootfs_blob`).
  * **Key Derivation Formula:**
    $$\text{KeyMaterial} = \text{SHA256}(\text{"@* WebFWUpdate"} + \text{fw\_model} + \text{blob\_digest\_uncompressed})$$
    * **AES-128 Key:** Erste 16 Bytes von `KeyMaterial` (`key_material[:16]`).
    * **Initialization Vector (IV):** 16 Null-Bytes (`\x00` * 16).

* **`bksettings` (`.enc`) Backup Keys:**
  * **Hardcoded Secret String:** `Is_Th1s=9-Gd(S8c$et*K3y?`
  * **User Passwort:** Vom Administrator vergebenes Backup-Passwort (UTF-8 kodiert).
  * **Metadaten-Parameter:** `file_size` (32-Bit LE uint bei Offset `0x34`) und `timer` (32-Bit LE uint bei Offset `0x38`).
  * **Key Derivation Formula:**
    $$\text{AES Key} = \text{SHA256}(\text{file\_size}_{\text{LE32}} + \text{timer}_{\text{LE32}} + \text{"Is\_Th1s=9-Gd(S8c\$et*K3y?"} + \text{user\_password})$$
    * **AES-256 Key:** 32-Byte SHA256 Hashwert.
    * **Initialization Vector (IV):** 16-Byte Bytefolge direkt aus Datei-Offset `0x40:0x50`.

---

### 8.4 Encrypt algorithm / tools

* **Tools:**
  * `pycryptodome` (`Crypto.Cipher.AES`) / OpenSSL C-Bibliothek (`EVP_EncryptInit_ex`, `EVP_EncryptUpdate`, `EVP_EncryptFinal_ex`).
  * Python `zlib` / `gzip` Komprimierungsbibliotheken (`zlib.compress`).
  * `hashlib` / OpenSSL `EVP_sha256` zur SHA-256 Hash-Generierung.

* **Algorithms:**
  * **`.ful2` Encryption Algorithm:**
    1. Komprimierung des unverschlüsselten Binär-Payloads (z. B. RootFS oder LBI-Image) via Raw Deflate (`wbits=-15`).
    2. Berechnung des SHA256-Digests der unkomprimierten Daten (`blob_digest_uncompressed`).
    3. Ableitung des Schlüssels: `SHA256("@* WebFWUpdate" + fw_model + blob_digest_uncompressed)`.
    4. AES-128-CBC Verschlüsselung des komprimierten Datenstroms mit den ersten 16 Bytes des abgeleiteten Schlüssels und 16 Null-Bytes als IV.
  * **`bksettings` (`.enc`) Encryption Algorithm:**
    1. Komprimierung des XML-Konfigurationsdokuments im Gzip-Format (`wbits = MAX_WBITS | 16`).
    2. Berechnung des 32-Byte SHA256 Inner HMAC/Digests über die komprimierten Daten und Voranstellen vor den komprimierten Puffer.
    3. Ableitung des 32-Byte AES-256 Schlüssels: `SHA256(file_size_LE32 + timer_LE32 + "Is_Th1s=9-Gd(S8c$et*K3y?" + user_password)`.
    4. AES-256-CBC Verschlüsselung des zusammengefügten Puffers (Inner HMAC + komprimiertes XML) mit einem zufällig generierten 16-Byte IV.
    5. Berechnung des äußeren 32-Byte SHA256 MACs über den Datei-Header.

---

### 8.5 Pack algorithm / tools

* **Tools:**
  * Python `struct` (`struct.pack("<I", ...)`), `bytearray` und Datei-I/O-Operationen.
  * XML-Generatoren / Formatierer zur Erstellung des Manifests gemäß `webfwupdate.xsd`.
  * PJL-Formatierungswerkzeuge zum Anhängen/Voranstellen von Drucker-Steuerbefehlen.

* **Algorithms:**
  * **`.ful2` Container Packing Algorithm:**
    1. Erstellung des XML-Manifests inklusive `signedInfo`, `updated_revision`, Signaturblöcken und Blob-Metadaten (`size_compressed`, `size_uncompressed`, `blob_digest_compressed`, `blob_digest_uncompressed`).
    2. Formatierung jedes verschlüsselten Blobs durch Voranstellen seiner Bytelänge als Hexadezimal-String gefolgt von `\n`.
    3. Konkatenierung aller Komponenten:
       * PJL-Header: `\x1b%-12345X@PJL COMMENT MODEL=...` ... `@PJL ENTER LANGUAGE=FWUPDATE2\n`
       * Hexadezimale Länge des XML-Manifests + `\n`
       * XML-Manifest-Text + `\n`
       * Hexadezimale Länge von Blob 1 + `\n` + Verschlüsselter Blob 1
       * Hexadezimale Länge von Blob 2 + `\n` + Verschlüsselter Blob 2
       * PJL-Footer: `\x1b%-12345X@PJL EOJ`
  * **`bksettings` (`.enc`) Container Packing Algorithm:**
    1. Erstellung des 0x50-Byte Binärheaders:
       * `0x00 - 0x03`: ASCII String `"BKST"` (`0x54534b42`).
       * `0x04 - 0x0F`: Timer / Metadatenfelder.
       * `0x10 - 0x2F`: Äußerer 32-Byte SHA256 MAC.
       * `0x30 - 0x33`: Inner Magic Bytes `0x91129215` (32-Bit LE Integer).
       * `0x34 - 0x37`: Unkomprimierte Dateigröße `file_size` als 32-Bit Little-Endian uint (`struct.pack("<I", file_size)`).
       * `0x38 - 0x3B`: Zeitstempel-Wert `timer` als 32-Bit Little-Endian uint (`struct.pack("<I", timer)`).
       * `0x40 - 0x4F`: 16-Byte zufälliger Initialisierungsvektor (IV).
    2. Anfügen des AES-256-CBC Ciphertexts unmittelbar nach Offset `0x50`.
