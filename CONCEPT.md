# Product Concept: HP Pro 8600 Firmware Lookup & Downgrade Tool

## 1. Goal
Die einzige Aufgabe dieses Projekts ist es, bestehende ältere Firmware-Versionen für HP OfficeJet Pro 8600 Drucker zu finden und auf dem Drucker zu installieren.

---

## 2. Anwendungsfälle (Use Cases)

### UC-1: Ältere Firmware finden
- **Ziel:** Ermitteln und Auffinden verfügbarer, älterer Firmware-Dateien für das entsprechende HP OfficeJet Pro 8600 Modell.
- **Ablauf:**
  1. Das Tool prüft das angeschlossene bzw. angegebene Druckermodell.
  2. Das Tool sucht nach verfügbaren älteren Firmware-Versionen im lokalen Speicher oder bekannten Repositories.
  3. Dem Benutzer wird eine Liste passender älterer Firmware-Versionen zur Auswahl bereitgestellt.

### UC-2: Firmware auf dem Drucker installieren
- **Ziel:** Übertragen und Flashen der ausgewählten älteren Firmware auf den Drucker.
- **Ablauf:**
  1. Der Benutzer wählt die gewünschte ältere Firmware-Version aus.
  2. Das Tool verifiziert die Firmware-Datei (Integritäts- und Modellprüfung).
  3. Das Tool sendet die Firmware über die geeignete Verbindung (Netzwerk/PJL Socket Port 9100 oder USB) an den Drucker.
  4. Der Drucker führt das Firmware-Update/Downgrade durch und startet neu.

---

## 3. Architekturübersicht

```
+-------------------------------------------------------------+
|                      BENUTZEROBERFLÄCHE                     |
|                   (CLI - Command Line Interface)            |
+------------------------------+------------------------------+
                               |
                               v
+-------------------------------------------------------------+
|                         CORE ENGINE                         |
|                                                             |
|  +------------------------+     +------------------------+  |
|  |  Firmware-Suchmodul    |     |   Firmware-Flasher     |  |
|  |  (Findet ältere FW)    |     |   (Überträgt FW)       |  |
|  +------------------------+     +------------------------+  |
+------------------------------+------------------------------+
                               |
                               v
+-------------------------------------------------------------+
|                HP OFFICEJET PRO 8600 DRUCKER                |
|                    (USB / Netzwerkanbindung)                |
+-------------------------------------------------------------+
```
