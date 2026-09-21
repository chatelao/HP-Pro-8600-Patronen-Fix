# Mängelbericht: Firmware-Entpackungsstruktur (`UNPACK_ISSUES.md`)

Diese Dokumentation analysiert die Schwachstellen und Mängel der aktuellen Entpackungslogik (`scripts/decode.py`) sowie der daraus resultierenden Verzeichnis- und Dateistruktur für `/img/*.rfu`-Firmwaredateien.

---

## 1. Mängel bei der PJL/RFU-Extraktion (`decode_pjl_rfu`)

### 1.1 Unvollständiges / ungenaues Strippen von PCL/PJL-Escape-Sequenzen & Footern
* **Problem:** Das Skript schneidet den Header ab `@PJL ENTER LANGUAGE=FWUPDATE` ab, entfernt jedoch nicht zuverlässig PCL-Sonderbefehle am Anfang des Payloads (z. B. `\x1bEThis device does not support FWUPDATE!\r\n\x1b*rt...`).
* **Footer-Problem:** Wenn das Dateiende keine exakte Sequenz `\x1b%-12345X@PJL EOJ` enthält, sondern z. B. nur `\x1b*rC\x1bE\x1b%-12345X` (PCL Reset + Universal Exit Language), verbleibt der PCL-Footer in der extrahierten Binärdatei.

### 1.2 Keine Überprüfung der angegebenen Payload-Größe (`UPGRADE SIZE`)
* **Problem:** PJL-Header wie `@PJL UPGRADE SIZE =25569076` deklarieren die exakte Byte-Anzahl des Firmware-Upgrades. Das Skript ignoriert diesen Wert völlig und speichert stattdessen den gesamten Rest der Datei (in diesem Fall 25.569.018 Bytes).
* **Auswirkung:** Es findet keine Validierung statt, ob die Datei beschädigt, abgeschnitten oder mit zusätzlichem Padding versehen ist.

---

## 2. Fehlen tiefergehender Entpackungsschritte (Monolithischer Dump)

### 2.1 Fehlendes Rekursives Entpacken von verschachtelten Formaten
* **Problem:** Der extrahierte Payload (`*.ful.rfu_payload.bin`) ist ein proprietärer monolithischer Binary-Block, der verschachtelte Formate wie Motorola S-Records (`S0...`), Zlib-/Gzip-Datenströme und eingebettete Dateisysteme (z. B. VxWorks RTOS Code/RAM-Disk) enthält.
* **Mangel:** Das Entpackungsskript stoppt nach der Extraktion der äußeren Hülle. Es erfolgt kein automatisches Entpacken/Parse-Step für S-Records oder Zlib-Streams, um verwertbare System-Binaries (`sys/`, `lib/`, Executables) zu gewinnen.

### 2.2 Fehlende Prüfsummen- und Integritätsvalidierung
* **Problem:** Für `.rfu`/`.ful`-Dateien gibt es im Gegensatz zu `.ful2` keine Validierung von SHA256-Prüfsummen oder Signaturen im Skript. Etwaige Fehler beim Herunterladen oder Übertragen bleiben unbemerkt.

---

## 3. Mängel der Ausgabestruktur (`decoded_output/`)

### 3.1 Flache Ordnerstruktur ohne Dateitrennungs-Isolierung
* **Problem:** Alle entpackten Dateien werden direkt in das Wurzelverzeichnis `decoded_output/` geschrieben.
* **Auswirkung:** Bei mehreren Firmwaredateien oder gleichnamigen Sub-Blobs entsteht Namenssalat und potenzielle Überschreibung von Artefakten.

### 3.2 Ungeeignete Dateibenennung
* **Problem:** Dateinamen wie `ojpro_8600_n911_a_1304A_10042013.ful.rfu_payload.bin` beinhalten doppelte Suffixe (`.ful.rfu_payload.bin`) und spiegeln keine inhaltliche Metadaten-Struktur (wie Modell, Datum oder Version) im Pfad wider.

---

## 4. Empfehlungen für künftige Verbesserungen

1. **Integritätsprüfung:** Auslesen von `@PJL UPGRADE SIZE` und exaktes Trimmen des Payloads auf die deklarierte Länge.
2. **Mehrstufiges Entpacken:** Implementierung eines S-Record-Parsers und Zlib-Dekompressors für `.rfu`-Payloads.
3. **Strukturierte Ausgabepfade:** Entpacken in Unterordner nach Schema `decoded_output/<modell>/<version>/`.
4. **CI-Validierung:** Automatisiertes Schemaprüfen der entpackten Artefakte in der GitHub Action.
