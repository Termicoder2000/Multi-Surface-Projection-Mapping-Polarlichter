# Multi-Surface Projection Mapping (Python & OpenCV)

A lightweight projection mapping script in Python. It maps images, videos, real-time edge-filtered webcam feeds, and audio-reactive (bass-sensitive) visuals onto multiple custom quad-warped surfaces.

---

## English

### Overview
This tool allows you to calibrate quad projection areas directly on screen using 4-point clicks, warping media sources via perspective transform. Media files are automatically scanned and indexed from a specified directory.

### Installation

```bash
# Ubuntu / Raspberry Pi OS dependencies:
sudo apt-get install -y portaudio19-dev libasound2-dev

# Python dependencies:
pip install opencv-python numpy pyaudio
```

---

### Folder & Media Structure

Point `MEDIA_FOLDER` in the script to your asset directory. Files are sorted by their numeric prefix:

```text
Images/
├── 1_Background.png       -> Standard image
├── 2_Animation.mp4        -> Looping video
├── 3_Camera.txt           -> Activates live webcam + neon edge filter
└── 4_BassSensitive.txt    -> Audio-reactive slot (contains path to folder)
```

#### Media Types:
1. **Images & Videos (`.png`, `.jpg`, `.mp4`, etc.)**: Normal playback.
2. **Webcam Filter (`*.txt` containing `camera` in filename)**: Starts USB camera with live Canny edge detection in red/purple.
3. **Bass-Reactive (`*BassSensitive*.txt`)**: The text file contains the path to another folder with numbered image stages (e.g. generated via *Primitive*):
   ```text
   /path/to/stages/
   ├── 1_low_detail.png     (played at low bass)
   ├── 2_mid_detail.png
   └── 3_high_detail.png    (played at high bass kick)
   ```

#### FFT bass version

Run `ProjectMappingPolarlicht_FFT.py`. It estimates bass level from an FFT.
Adjust `BASS_MIN_HZ` and `BASS_MAX_HZ` to select the frequency range, and
`BASS_FULL_SCALE_RMS` to set the level that reaches the last image stage.
`BASS_MIN_RMS_PERCENT` is the activation threshold relative to full scale. Below
it, image 0 stays selected; above it, the remaining level range maps to the
remaining images (default: 10%).

#### Streaming low-pass (TP) version

Run `ProjectMappingPolarlicht_TP.py`. Set `BASS_FILTER_ORDER` and
`BASS_FILTER_FG_HZ` at the top of the script. `BASS_RMS_WINDOW_SAMPLES` controls
the RMS smoothing window and must be a positive integer; at 44.1 kHz, 32 samples
are about 0.7 ms and 1024 samples about 23 ms. Smaller windows react faster but
can make the bass level less stable. `BASS_FULL_SCALE_RMS` sets the level for
the last image stage. `BASS_MIN_RMS_PERCENT` keeps image 0 selected below the
activation threshold (default: 2%).

---

### Controls & Keybindings

| Key / Action | Function |
| :--- | :--- |
| **Left Click** | Click 4 corner points per surface area (clockwise or counter-clockwise) |
| **ENTER** | Toggle between Alignment Grid and Media Playback |
| **F** | Toggle Fullscreen |
| **Z** | Undo last clicked corner point or area |
| **P** | Reset all calibrated surfaces |
| **Left / Right Arrow (`<` / `>`)** | Move every surface to the previous / next loaded media, including media not currently shown |
| **R / L** | Rotate the current media assignments between surfaces |
| **`1` then `a` (or `a` then `1`)** | Assign Media `1` to Surface `a`; multi-digit media numbers work too, e.g. `10` then `b` |
| **ESC** | Quit application |

---

## Deutsch

### Kurzübersicht
Ein schlankes Projektions-Mapping-Skript in Python. Es projiziert Bilder, Videos, stilisierte Live-Webcam-Streams und bass-reaktive Bildserien auf beliebig viele, frei gezeichnete 4-Punkt-Projektionsflächen (Perspective Warp).

### Installation

```bash
# Systempakete auf Ubuntu / Raspberry Pi OS:
sudo apt-get install -y portaudio19-dev libasound2-dev

# Python-Bibliotheken:
pip install opencv-python numpy pyaudio
```

---

### Medienordner einrichten

Setze den Pfad `MEDIA_FOLDER` im Skript auf deinen Zielordner. Die Sortierung erfolgt über die führende Nummer:

```text
Images/
├── 1_Hintergrund.png      -> Normales Standbild
├── 2_Visual.mp4           -> Video (spielt in Endlosschleife)
├── 3_Camera.txt           -> Aktiviert USB-Kamera mit Neon-Kantenfilter
└── 4_BassSensitive.txt    -> Bass-Reaktiv (enthält Pfad zum Bilderordner)
```

#### Medientypen:
1. **Bilder & Videos (`.png`, `.jpg`, `.mp4` etc.)**: Werden regulär auf die Fläche verzerrt.
2. **Kamera (`*.txt` mit `camera` im Namen)**: Startet die Webcam mit Kantenfilter (Canny) in Rot/Lila.
3. **Bass-Reaktiv (`*BassSensitive*.txt`)**: Die Textdatei enthält als Text den Pfad zu einem Ordner mit durchnummerierten Renderings (z. B. erstellt mit *Primitive*):
   ```text
   /pfad/zu/den/stufen/
   ├── 1_abstrakt.png       (wird bei Stille / wenig Bass angezeigt)
   ├── 2_mittel.png
   └── 3_detailliert.png    (wird bei lautem Bass / Kickdrum angezeigt)
   ```

#### FFT-Bass-Version

Starte `ProjectMappingPolarlicht_FFT.py`. Das Skript ermittelt den Basspegel per
FFT. Mit `BASS_MIN_HZ` und `BASS_MAX_HZ` stellst du den Frequenzbereich ein;
`BASS_FULL_SCALE_RMS` legt den Pegel für die letzte Bildstufe fest.
`BASS_MIN_RMS_PERCENT` ist die Einschaltschwelle relativ zu Full Scale. Darunter
bleibt Bild 0, darüber wird der restliche Pegelbereich auf die weiteren Bilder
verteilt (Standard: 10 %).

#### Streaming-Tiefpass-Version (TP)

Starte `ProjectMappingPolarlicht_TP.py`. Filterordnung und Grenzfrequenz stellst
du oben mit `BASS_FILTER_ORDER` und `BASS_FILTER_FG_HZ` ein.
`BASS_RMS_WINDOW_SAMPLES` steuert die RMS-Glättung und muss eine positive ganze
Zahl sein: Bei 44,1 kHz entsprechen 32 Samples etwa 0,7 ms und 1024 Samples etwa
23 ms. Kleinere Fenster reagieren schneller, können den Basspegel aber
unruhiger machen. `BASS_FULL_SCALE_RMS` legt den Pegel für die letzte Bildstufe
fest. Unter `BASS_MIN_RMS_PERCENT` (Standard: 2 %) bleibt Bild 0 ausgewählt.

---

### Steuerung & Tastenbelegung

| Taste / Aktion | Funktion |
| :--- | :--- |
| **Linksklick** | 4 Eckpunkte pro Projektionsfläche im Fenster anklicken |
| **ENTER** | Umschalten zwischen Gitternetz (Einrichten) und Medien |
| **F** | Vollbildmodus an/aus |
| **Z** | Letzten Klick oder letzte Fläche rückgängig machen (Undo) |
| **P** | Alle Flächen löschen (Reset) |
| **Pfeil links/rechts (`<` / `>`)** | Jede Fläche wechselt zum vorherigen/nächsten geladenen Medium, auch zu aktuell nicht angezeigten |
| **R / L** | Rotiert die aktuellen Medienzuweisungen zwischen den Flächen |
| **`1` dann `a` (oder `a` dann `1`)** | Weist Media `1` der Fläche `a` zu; auch mehrstellige Nummern, z. B. `10` dann `b` |
| **ESC** | Programm beenden |