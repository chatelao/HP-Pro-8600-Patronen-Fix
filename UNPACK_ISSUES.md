# Mängelbericht: Firmware-Entpackungsstruktur (`UNPACK_ISSUES.md`)

Diese Dokumentation analysiert die Schwachstellen, Mängel und Qualitätsmerkmale der aktuellen Entpackungslogik (`scripts/decode.py`) sowie der daraus resultierenden Verzeichnis- und Dateistruktur für `/img/*.rfu`-Firmwaredateien, `.ful2`-Firmware-Images und `.enc`-Sicherungsdateien.

---

## 1. Mängel bei der PJL/RFU-Extraktion (`decode_pjl_rfu`)

### 1.1 Unvollständiges / ungenaues Strippen von PCL/PJL-Escape-Sequenzen & Footern
* **Problem:** Das Skript schneidet den PJL-Header ab `@PJL ENTER LANGUAGE=FWUPDATE` ab, entfernt jedoch nicht zuverlässig PCL-Sonderbefehle am Anfang des Payloads.
* **Befund:** Im extrahierten Payload (`ojpro_8600_n911_a_1304A_10042013.ful.rfu_payload.bin`) befinden sich in den ersten 658 Bytes verbleibende PCL-Escape-Sequenzen wie:
  `\x1bEThis device does not support FWUPDATE!\r\n\x1b*rt16384sA\x1b*b16542Y...`
* **Footer-Problem:** Das Dateiende enthält ebenfalls ungestrippten PCL-Reset-Code (`\x1b*b+1ym... \x1b*rC\x1bE\x1b%-12345X`), da der Marker `\x1b%-12345X@PJL EOJ` variieren kann.

### 1.2 Ignorierung der deklarierten Payload-Größe (`UPGRADE SIZE`)
* **Problem:** Im PJL-Header ist die exakte Byte-Anzahl des Upgrades angegeben (z. B. `@PJL UPGRADE SIZE =25569076`). Das Entpackungsskript ignoriert diesen Wert völlig und speichert stattdessen den gesamten Dateirest (in diesem Beispiel 25.569.018 Bytes, Abweichung von 58 Bytes).
* **Auswirkung:** Es findet keine Validierung statt, ob die Datei beschädigt, abgeschnitten oder mit zusätzlichem Padding versehen ist.

---

## 2. Lesbarkeit & Struktur der entpackten Daten

### 2.1 Motorola S-Record Kapselung (Kein flacher Binär-Image)
* **Befund:** Der extrahierte Payload ist kein direkt ausfagbares ELF/RTOS-Image, sondern enthält über 5.200 Motorola S-Records (`S0`, `S3`, `SA` Zeilen).
* **Lesbarkeit:** Ohne einen dedizierten S-Record-zu-Binär-Konverter (S-Record-Parser) ist der Payload für Disassembler (z. B. Ghidra/IDA Pro) nur eingeschränkt lesbar und nicht direkt ausführbar.
* **Dekomprimierung:** Zlib-Kompressionsmarker (`0x789c` / `0x7801`) sind an zahlreichen Offsets innerhalb der S-Records vorhanden, werden aber nicht automatisch entpackt.

### 2.2 Fehlendes Rekursives Entpacken von verschachtelten Formaten
* **Problem:** Das Entpackungsskript stoppt nach der Extraktion der äußeren Hülle. Es erfolgt kein automatisches Entpacken für verschachtelte Formate wie S-Records, Gzip/Zlib-Streams oder Dateisystem-Blobs (`LBI_blob`, `rootfs_blob`).

### 2.3 Fehlen von Prüfsummen- und Integritätsvalidierung
* **Problem:** Für `.rfu`/`.ful`-Dateien gibt es keine Validierung von SHA256-Prüfsummen oder Signaturen im Skript. Etwaige Fehler beim Herunterladen oder Übertragen bleiben unbemerkt.

---

## 3. Mängel der Ausgabestruktur (`decoded_output/`)

### 3.1 Flache Ordnerstruktur ohne Dateitrennungs-Isolierung
* **Problem:** Alle entpackten Dateien werden direkt in das Wurzelverzeichnis `decoded_output/` geschrieben.
* **Auswirkung:** Bei mehreren Firmwaredateien oder gleichnamigen Sub-Blobs entsteht Namenssalat und potenzielle Überschreibung von Artefakten.

### 3.2 Ungeeignete Dateibenennung
* **Problem:** Dateinamen wie `ojpro_8600_n911_a_1304A_10042013.ful.rfu_payload.bin` beinhalten doppelte Suffixe (`.ful.rfu_payload.bin`) und spiegeln keine inhaltliche Metadaten-Struktur (wie Modell, Datum oder Version) im Pfad wider.

---

## 4. CI/CD Validierung und Empfehlungen

1. **Prüfung im CI-Workflow:** Der CI/CD-Workflow prüft nun die Existenz und Lesbarkeit der entpackten Artefakte, ermittelt PCL/PJL-Reste und warnt bei unvollständig konvertierten Motorola S-Records.
2. **Integritätsprüfung:** Auslesen von `@PJL UPGRADE SIZE` und exaktes Trimmen des Payloads auf die deklarierte Länge.
3. **Mehrstufiges Entpacken:** Implementierung eines S-Record-Parsers und Zlib-Dekompressors für `.rfu`-Payloads.
4. **Strukturierte Ausgabepfade:** Entpacken in Unterordner nach Schema `decoded_output/<modell>/<version>/`.
