import cv2
import numpy as np
import pyaudio
import os
import re
import sys
import threading
import time
from ctypes import CFUNCTYPE, c_char_p, c_int, cdll

# --- ALSA / PortAudio Terminal-Warnungen stummschalten ---
def py_error_handler(filename, line, function, err, fmt):
    pass

try:
    ERROR_HANDLER_FUNC = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int, c_char_p)
    c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)
    asound = cdll.LoadLibrary('libasound.so.2')
    asound.snd_lib_error_set_handler(c_error_handler)
except Exception:
    pass

# --- Konfiguration ---
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080
CLAHE_CLIP_LIMIT = 2.0
CLAHE_TILE_GRID_SIZE = (8, 8)
CANNY_LOWER_THRESHOLD = 30
CANNY_UPPER_THRESHOLD = 40
BASS_FILTER_ORDER = 12
BASS_FILTER_FG_HZ = 80.0
BASS_FULL_SCALE_RMS = 0.06
BASS_RMS_WINDOW_SAMPLES = 1
BASS_MIN_RMS_PERCENT = 2.0

# Images-Ordner neben diesem Skript
MEDIA_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Images')


def natural_sort_key(filename):
    return tuple(
        (1, int(part)) if part.isdigit() else (0, part.lower())
        for part in re.split(r'(\d+)', filename)
    )


def butterworth_lowpass_sections(order, cutoff_hz, sample_rate):
    if not isinstance(order, int) or isinstance(order, bool) or not 1 <= order <= 12:
        raise ValueError("BASS_FILTER_ORDER muss eine ganze Zahl zwischen 1 und 12 sein.")
    if not 0 < cutoff_hz < sample_rate / 2:
        raise ValueError(
            f"BASS_FILTER_FG_HZ muss zwischen 0 und {sample_rate / 2} Hz liegen."
        )

    k = np.tan(np.pi * cutoff_hz / sample_rate)
    sections = []

    if order % 2:
        scale = 1.0 / (1.0 + k)
        sections.append((k * scale, k * scale, 0.0, (k - 1.0) * scale, 0.0))

    for section_index in range(order // 2):
        q = 1.0 / (
            2.0 * np.sin((2 * section_index + 1) * np.pi / (2.0 * order))
        )
        scale = 1.0 / (1.0 + k / q + k * k)
        b0 = k * k * scale
        b1 = 2.0 * b0
        b2 = b0
        a1 = 2.0 * (k * k - 1.0) * scale
        a2 = (1.0 - k / q + k * k) * scale
        sections.append((b0, b1, b2, a1, a2))

    return sections


class ButterworthLowPass:
    def __init__(self, order, cutoff_hz, sample_rate):
        self.sections = butterworth_lowpass_sections(order, cutoff_hz, sample_rate)
        self.state = np.zeros((len(self.sections), 2), dtype=np.float64)

    def process(self, samples):
        output = np.asarray(samples, dtype=np.float32).copy()

        for section_index, (b0, b1, b2, a1, a2) in enumerate(self.sections):
            state_1, state_2 = self.state[section_index]
            for sample_index, sample in enumerate(output):
                result = b0 * sample + state_1
                state_1 = b1 * sample - a1 * result + state_2
                state_2 = b2 * sample - a2 * result
                output[sample_index] = result
            self.state[section_index] = (state_1, state_2)

        return output


class AudioReactiveMediaSource:
    def __init__(
        self,
        folder_path,
        filter_order=BASS_FILTER_ORDER,
        cutoff_hz=BASS_FILTER_FG_HZ,
        full_scale_rms=BASS_FULL_SCALE_RMS,
        rms_window_samples=BASS_RMS_WINDOW_SAMPLES,
        min_rms_percent=BASS_MIN_RMS_PERCENT,
    ):
        self.folder_path = folder_path.strip()
        self.name = f"Bass: {os.path.basename(self.folder_path)}"
        self.full_scale_rms = full_scale_rms
        self.min_rms_percent = min_rms_percent
        self.images = []
        self.is_video = False
        self.is_camera = False

        # 1. Bilder aus dem angegebenen Ordner laden und numerisch sortieren
        self.load_images_from_folder(self.folder_path)

        if not self.images:
            fallback = np.zeros((600, 800, 3), dtype=np.uint8)
            cv2.putText(fallback, "Keine Bilder fuer Bass gefunden", (30, 300),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
            self.images = [fallback]

        self.h, self.w = self.images[0].shape[:2]
        self.current_frame = self.images[0]

        # 2. Audio-Stream initialisieren
        self.chunk = 256
        self.rate = 44100
        if self.full_scale_rms <= 0:
            raise ValueError("BASS_FULL_SCALE_RMS muss groesser als 0 sein.")
        if (
            isinstance(self.min_rms_percent, bool)
            or not isinstance(self.min_rms_percent, (int, float))
            or not 0 <= self.min_rms_percent < 100
        ):
            raise ValueError(
                "BASS_MIN_RMS_PERCENT muss zwischen 0 und kleiner als 100 liegen."
            )
        if (
            not isinstance(rms_window_samples, int)
            or isinstance(rms_window_samples, bool)
            or rms_window_samples < 1
        ):
            raise ValueError(
                "BASS_RMS_WINDOW_SAMPLES muss eine positive ganze Zahl sein."
            )

        self.lowpass = ButterworthLowPass(filter_order, cutoff_hz, self.rate)
        self.rms_buffer = np.zeros(rms_window_samples, dtype=np.float32)
        self.rms_sum = 0.0
        self.rms_write_index = 0
        self.rms_sample_count = 0
        self.rms_lock = threading.Lock()
        self.stop_event = threading.Event()

        self.audio = pyaudio.PyAudio()
        self.has_audio = False
        self.audio_error_reported = False
        self.audio_thread = None

        try:
            self.stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.rate,
                input=True,
                frames_per_buffer=self.chunk
            )
            self.has_audio = True
            print(f"[AudioReactive] Mikrofon erfolgreich gestartet fuer: {self.folder_path}")
            self.audio_thread = threading.Thread(
                target=self._audio_worker,
                name=f"BassAudio-{os.path.basename(self.folder_path)}",
                daemon=True,
            )
            self.audio_thread.start()
        except Exception as e:
            self.has_audio = False
            print(f"[AudioReactive] Kein Mikrofon gefunden oder Audio-Fehler: {e}")

    def load_images_from_folder(self, path):
        if not os.path.isdir(path):
            print(f"[AudioReactive] Zielordner existiert nicht: {path}")
            return

        valid_exts = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')
        matched = []

        for filename in os.listdir(path):
            if filename.lower().endswith(valid_exts):
                parts = filename.split('_', 1)
                # Nach Zahl sortieren ("1_...", "2_...")
                order = int(parts[0]) if (len(parts) == 2 and parts[0].isdigit()) else float('inf')
                matched.append((order, os.path.join(path, filename)))

        matched.sort(key=lambda item: (item[0], natural_sort_key(os.path.basename(item[1]))))

        for _, img_path in matched:
            img = cv2.imread(img_path)
            if img is not None:
                self.images.append(img)

        print(f"[AudioReactive] {len(self.images)} Bilder geladen aus: {path}")

    def _audio_worker(self):
        while not self.stop_event.is_set():
            try:
                raw_data = self.stream.read(self.chunk, exception_on_overflow=False)
                samples = (
                    np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0
                )
                if samples.size != self.chunk:
                    raise RuntimeError(
                        f"Erwartet {self.chunk} Audio-Samples, erhalten: {samples.size}"
                    )

                filtered = self.lowpass.process(samples)
                squared = np.square(filtered)
                with self.rms_lock:
                    window_size = self.rms_buffer.size
                    if squared.size >= window_size:
                        new_write_index = (
                            self.rms_write_index + squared.size
                        ) % window_size
                        positions = (
                            new_write_index + np.arange(window_size)
                        ) % window_size
                        latest_samples = squared[-window_size:]
                        self.rms_buffer[positions] = latest_samples
                        self.rms_sum = float(np.sum(latest_samples))
                        self.rms_sample_count = window_size
                    else:
                        positions = (
                            self.rms_write_index + np.arange(squared.size)
                        ) % window_size
                        old_values = self.rms_buffer[positions].copy()
                        self.rms_buffer[positions] = squared
                        self.rms_sum = max(
                            self.rms_sum + float(np.sum(squared - old_values)),
                            0.0,
                        )
                        self.rms_sample_count = min(
                            self.rms_sample_count + squared.size,
                            window_size,
                        )
                    self.rms_write_index = (
                        self.rms_write_index + squared.size
                    ) % window_size
            except Exception as e:
                if not self.stop_event.is_set() and not self.audio_error_reported:
                    print(f"[AudioReactive] Fehler beim Audio-Auslesen: {e}")
                    self.audio_error_reported = True
                self.has_audio = False
                return

    def get_frame(self):
        if not self.has_audio or len(self.images) <= 1:
            return self.current_frame

        with self.rms_lock:
            if self.rms_sample_count == 0:
                return self.current_frame
            bass_rms = np.sqrt(
                self.rms_sum / self.rms_sample_count
            )

        rms_ratio = np.clip(bass_rms / self.full_scale_rms, 0.0, 1.0)
        minimum_ratio = self.min_rms_percent / 100.0
        if rms_ratio <= minimum_ratio:
            norm_factor = 0.0
        else:
            norm_factor = (rms_ratio - minimum_ratio) / (1.0 - minimum_ratio)
        index = int(norm_factor * (len(self.images) - 1))
        self.current_frame = self.images[index]
        return self.current_frame

    def release(self):
        self.stop_event.set()
        if hasattr(self, 'stream'):
            try:
                self.stream.abort_stream()
            except Exception as e:
                print(f"[AudioReactive] Fehler beim Abbrechen des Audio-Streams: {e}")
            if self.audio_thread is not None and self.audio_thread.is_alive():
                self.audio_thread.join(timeout=1.0)
            try:
                self.stream.close()
            except Exception as e:
                print(f"[AudioReactive] Fehler beim Schliessen des Audio-Streams: {e}")
        try:
            self.audio.terminate()
        except Exception as e:
            print(f"[AudioReactive] Fehler beim Beenden von PyAudio: {e}")



# =========================================================================
# --- KLASSE 2: NORMALE MEDIENQUELLE (Bild, Video, Webcam) ---
# =========================================================================
class MediaSource:
    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        self.clahe = cv2.createCLAHE(
            clipLimit=CLAHE_CLIP_LIMIT,
            tileGridSize=CLAHE_TILE_GRID_SIZE
        )
        self.is_camera = path.lower().endswith('.txt') or (path.lower() == 'camera')
        self.is_video = path.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')) or self.is_camera

        if self.is_camera:
            self.cap = cv2.VideoCapture(0)
            if not self.cap.isOpened():
                self.create_fallback("Kamera nicht gefunden")
            else:
                ret, frame = self.cap.read()
                if ret:
                    self.h, self.w = frame.shape[:2]
                else:
                    self.create_fallback("Kamera fehlerhaft")

        elif self.is_video:
            self.cap = cv2.VideoCapture(path)
            if not self.cap.isOpened():
                self.create_fallback(f"Video Fehler: {os.path.basename(path)}")
            else:
                ret, frame = self.cap.read()
                if ret:
                    self.h, self.w = frame.shape[:2]
                else:
                    self.create_fallback(f"Video leer: {os.path.basename(path)}")
        else:
            self.frame = cv2.imread(path)
            if self.frame is not None:
                self.h, self.w = self.frame.shape[:2]
            else:
                self.create_fallback(f"Nicht gefunden: {os.path.basename(path)}")

    def create_fallback(self, text):
        self.is_video = False
        self.is_camera = False
        self.frame = np.zeros((600, 800, 3), dtype=np.uint8)
        self.frame[:] = (50, 100, 200)
        cv2.putText(self.frame, text, (50, 300), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 3)
        self.h, self.w = self.frame.shape[:2]

    def process_frame(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        enhanced = self.clahe.apply(gray)
        smoothed = cv2.GaussianBlur(enhanced, (5, 5), 0)
        edges = cv2.Canny(smoothed, CANNY_LOWER_THRESHOLD, CANNY_UPPER_THRESHOLD)
        result_frame = np.zeros_like(frame)

        color_red = (0, 0, 255)
        color_purple = (255, 0, 150)

        edge_mask = edges > 0
        random_matrix = np.random.randint(0, 2, size=edges.shape).astype(bool)

        mask_red = edge_mask & random_matrix
        mask_purple = edge_mask & ~random_matrix

        result_frame[mask_red] = color_red
        result_frame[mask_purple] = color_purple
        return result_frame

    def get_frame(self):
        if self.is_video and self.is_camera:
            ret, frame = self.cap.read()
            if not ret:
                return self.process_frame(self.frame)
            return self.process_frame(frame)

        elif self.is_video:
            ret, frame = self.cap.read()
            if not ret:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.cap.read()
            return frame

        return self.frame

    def release(self):
        if (self.is_video or self.is_camera) and hasattr(self, 'cap'):
            self.cap.release()


# =========================================================================
# --- MEDIEN AUS ORDNER LADEN ---
# =========================================================================
def load_media_sources(folder_path):
    if not os.path.exists(folder_path):
        print(f"WARNUNG: Ordner '{folder_path}' existiert nicht!")
        return [MediaSource("fallback")]

    indexed_files = []
    for filename in os.listdir(folder_path):
        if filename.startswith('.'):
            continue
        full_path = os.path.join(folder_path, filename)
        if os.path.isdir(full_path):
            continue

        parts = filename.split('_', 1)
        order = int(parts[0]) if (len(parts) == 2 and parts[0].isdigit()) else 999
        indexed_files.append((order, filename, full_path))

    indexed_files.sort(key=lambda x: (x[0], x[1]))

    sources = []
    for _, filename, full_path in indexed_files:
        # Bass-Sensitive Textdatei erkennen
        if 'basssensitive' in filename.lower() and filename.lower().endswith('.txt'):
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    target_images_folder = f.read().strip()

                if not os.path.isabs(target_images_folder) and not os.path.exists(target_images_folder):
                    alt_path = os.path.join(folder_path, target_images_folder)
                    if os.path.exists(alt_path):
                        target_images_folder = alt_path

                sources.append(
                    AudioReactiveMediaSource(
                        target_images_folder,
                        filter_order=BASS_FILTER_ORDER,
                        cutoff_hz=BASS_FILTER_FG_HZ,
                        full_scale_rms=BASS_FULL_SCALE_RMS,
                        rms_window_samples=BASS_RMS_WINDOW_SAMPLES,
                        min_rms_percent=BASS_MIN_RMS_PERCENT,
                    )
                )
            except Exception as e:
                print(f"Fehler bei {filename}: {e}")
                sources.append(MediaSource(full_path))
        else:
            sources.append(MediaSource(full_path))

    return sources if sources else [MediaSource("fallback")]


# =========================================================================
# --- INITIALISIERUNG ---
# =========================================================================
media_sources = load_media_sources(MEDIA_FOLDER)

# Flächen und deren zugewiesene Medien
completed_areas = []
area_media_indices = []  # Index i speichert, welches Medium Fläche i anzeigt
current_area = []
mouse_pos = (0, 0)
show_media = False
is_fullscreen = False

# Zustand fuer mehrstellige Medianauswahl
pending_media_digits = ""
pending_media_timer = 0.0
pending_area = None
status_msg = ""
status_timer = 0
MEDIA_INPUT_TIMEOUT = 0.8

def get_area_name(i):
    """Gibt für Index 0 -> 'a', 1 -> 'b', 2 -> 'c' zurück."""
    return chr(ord('a') + i) if i < 26 else str(i)


def assign_media_to_area(target_area, target_media):
    global area_media_indices, status_msg, status_timer

    if not 0 <= target_media < len(media_sources):
        status_msg = f"Media {target_media + 1} existiert nicht!"
    elif target_media in area_media_indices:
        other_area = area_media_indices.index(target_media)
        if other_area == target_area:
            status_msg = f"Flaeche {get_area_name(target_area)} zeigt bereits Media {target_media + 1}"
        else:
            area_media_indices[target_area], area_media_indices[other_area] = (
                area_media_indices[other_area],
                area_media_indices[target_area],
            )
            status_msg = (
                f"Getauscht: Flaeche {get_area_name(target_area)} <-> "
                f"Flaeche {get_area_name(other_area)}"
            )
    else:
        area_media_indices[target_area] = target_media
        status_msg = (
            f"Flaeche {get_area_name(target_area)} zeigt jetzt Media {target_media + 1}"
        )

    status_timer = time.time()


def commit_pending_assignment():
    global pending_media_digits, pending_area

    if pending_area is not None and pending_media_digits:
        assign_media_to_area(pending_area, int(pending_media_digits) - 1)
        pending_media_digits = ""
        pending_area = None


def handle_assignment_character(char_code):
    global pending_media_digits, pending_media_timer, pending_area
    global status_msg, status_timer

    if ord('0') <= char_code <= ord('9'):
        pending_media_digits += chr(char_code)
        pending_media_timer = time.time()
    elif ord('a') <= char_code <= ord('z'):
        area_idx = char_code - ord('a')
        if area_idx < len(completed_areas):
            if pending_media_digits:
                assign_media_to_area(area_idx, int(pending_media_digits) - 1)
                pending_media_digits = ""
                pending_area = None
            else:
                pending_area = area_idx
        else:
            status_msg = f"Flaeche '{chr(char_code)}' existiert noch nicht!"
            status_timer = time.time()
    else:
        pending_media_digits = ""
        pending_area = None


def cycle_all_media(direction):
    global area_media_indices, status_msg, status_timer

    if not area_media_indices:
        status_msg = "Zuerst mindestens eine Flaeche zeichnen"
    else:
        area_media_indices = [
            (media_idx + direction) % len(media_sources)
            for media_idx in area_media_indices
        ]
        step = "naechste" if direction > 0 else "vorherige"
        status_msg = f"Alle Flaechen zeigen jetzt das {step} Medium"
    status_timer = time.time()


def rotate_media_between_areas(direction):
    global area_media_indices, status_msg, status_timer

    if len(area_media_indices) > 1:
        if direction > 0:
            area_media_indices = [area_media_indices[-1]] + area_media_indices[:-1]
            status_msg = "Medienzuweisungen zwischen Flaechen nach rechts rotiert"
        else:
            area_media_indices = area_media_indices[1:] + [area_media_indices[0]]
            status_msg = "Medienzuweisungen zwischen Flaechen nach links rotiert"
        status_timer = time.time()


# Konsolen-Übersicht der verfügbaren Medien
print("\n" + "=" * 60)
print("=== VERFÜGBARE MEDIEN ===")
for idx, src in enumerate(media_sources):
    print(f"  Media {idx + 1} : {src.name}")
print("=" * 60)
print("STEUERUNG:")
print("  Pfeile < >        : Wechselt alle Flaechen zum vorherigen/naechsten Medium")
print("  r / l             : Rotiert Zuweisungen zwischen Flaechen")
print("  1 b oder b 1      : Weist Media 1 der Flaeche b zu")
print("  Mehrstellige Media: z. B. 10 b (oder b 10)")
print("  ENTER             : Schaltet zwischen Gitternetz und Medien um")
print("  F                 : Vollbild an/aus | ESC / Q: Beenden")
print("=" * 60 + "\n")

def create_grid_image(w, h, grid_size=50):
    grid = np.zeros((h, w, 3), dtype=np.uint8)
    for x in range(0, w, grid_size):
        cv2.line(grid, (x, 0), (x, h), (255, 255, 255), 2)
    for y in range(0, h, grid_size):
        cv2.line(grid, (0, y), (w, y), (255, 255, 255), 2)
    cv2.rectangle(grid, (0, 0), (w - 1, h - 1), (255, 255, 255), 5)
    return grid

def mouse_callback(event, x, y, flags, param):
    global current_area, completed_areas, area_media_indices, mouse_pos
    mouse_pos = (x, y)

    if event == cv2.EVENT_LBUTTONDOWN:
        current_area.append([x, y])
        if len(current_area) == 4:
            completed_areas.append(current_area)
            # Automatisch nächste Medienquelle zuweisen
            new_idx = (len(completed_areas) - 1) % len(media_sources)
            area_media_indices.append(new_idx)
            current_area = []

window_name = 'Multi-Face Projektion'
cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
cv2.resizeWindow(window_name, 1280, 720)
cv2.setMouseCallback(window_name, mouse_callback)


# =========================================================================
# --- HAUPTSCHLEIFE ---
# =========================================================================
while True:
    if (
        pending_area is not None
        and pending_media_digits
        and time.time() - pending_media_timer >= MEDIA_INPUT_TIMEOUT
    ):
        commit_pending_assignment()

    canvas = np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8)

    # Sicherstellen, dass die Zuordnungsliste vollständig ist
    while len(area_media_indices) < len(completed_areas):
        area_media_indices.append(len(area_media_indices) % len(media_sources))

    # Alle fertig gezeichneten Flächen rendern
    for i, area_points in enumerate(completed_areas):
        source_idx = area_media_indices[i]
        media = media_sources[source_idx]

        pts_dest = np.float32(area_points)
        pts_source = np.float32([[0, 0], [media.w, 0], [media.w, media.h], [0, media.h]])
        matrix = cv2.getPerspectiveTransform(pts_source, pts_dest)

        if show_media:
            frame = media.get_frame()
            warped = cv2.warpPerspective(frame, matrix, (SCREEN_WIDTH, SCREEN_HEIGHT))
        else:
            grid = create_grid_image(media.w, media.h)
            warped = cv2.warpPerspective(grid, matrix, (SCREEN_WIDTH, SCREEN_HEIGHT))

        canvas = cv2.add(canvas, warped)

    # --- Setup-Modus (Punkte, Linien und Flächenbezeichnungen) ---
    if not show_media:
        for i in range(len(current_area)):
            cv2.circle(canvas, tuple(current_area[i]), 5, (255, 255, 255), -1)
            if i > 0:
                cv2.line(canvas, tuple(current_area[i - 1]), tuple(current_area[i]), (255, 255, 255), 2)

        if len(current_area) > 0:
            cv2.line(canvas, tuple(current_area[-1]), mouse_pos, (150, 150, 150), 1)

        # Beschriftung in jeder Fläche mit Buchstabe a, b, c... und aktuellem Medium
        for i, pts in enumerate(completed_areas):
            center_x = int(np.mean([p[0] for p in pts]))
            center_y = int(np.mean([p[1] for p in pts]))
            area_char = get_area_name(i)
            med_num = area_media_indices[i] + 1
            cv2.putText(canvas, f"Flaeche {area_char} (Media {med_num})",
                        (center_x - 90, center_y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

        next_char = get_area_name(len(completed_areas))
        cv2.putText(canvas, f"Flaeche {next_char} | Klicke Punkt {len(current_area) + 1}/4",
                    (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.putText(canvas, "ENTER: Starten | < >: Medien | z.B. 10 b: Zuweisen",
                    (50, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        cv2.circle(canvas, mouse_pos, 4, (0, 0, 255), -1)

    # --- Status- & Tastenmeldungen einblenden ---
    now = time.time()
    if pending_media_digits and pending_area is not None:
        message = (
            f"Media {pending_media_digits} fuer Flaeche "
            f"{get_area_name(pending_area)} wird zugewiesen..."
        )
        color = (0, 255, 255)
    elif pending_media_digits:
        message = f"Media {pending_media_digits} gewaehlt - Flaeche (a-z) druecken"
        color = (0, 255, 255)
    elif pending_area is not None:
        message = f"Flaeche {get_area_name(pending_area)} gewaehlt - Media-Nummer eingeben"
        color = (0, 255, 255)
    elif status_msg and now - status_timer < 2.5:
        message = status_msg
        color = (0, 255, 0)
    else:
        message = ""

    #if message:
        #cv2.putText(
        #    canvas,
        #    message,
        #    (50, SCREEN_HEIGHT - 60),
        #    cv2.FONT_HERSHEY_SIMPLEX,
        #    0.8,
        #    color,
        #    2,
        #)


    cv2.imshow(window_name, canvas)

    # Tastenabfrage mit erweitertem Code (für Pfeiltasten)
    key = cv2.waitKeyEx(16)

    if key != -1:
        if key in (65363, 2555904, ord('>')):
            pending_media_digits = ""
            pending_area = None
            cycle_all_media(1)
        elif key in (65361, 2424832, ord('<')):
            pending_media_digits = ""
            pending_area = None
            cycle_all_media(-1)
        elif key in (ord('r'), ord('R')):
            pending_media_digits = ""
            pending_area = None
            rotate_media_between_areas(1)
        elif key in (ord('l'), ord('L')):
            pending_media_digits = ""
            pending_area = None
            rotate_media_between_areas(-1)
        elif key == 0x01000000 or (key & 0xFF) == 27:
            print("[Steuerung] Escape erkannt, Programm wird beendet.")
            break
        elif key in (ord('q'), ord('Q')):
            break
        elif key == 13:
            commit_pending_assignment()
            pending_media_digits = ""
            pending_area = None
            show_media = not show_media
        elif key in (ord('f'), ord('F')):
            pending_media_digits = ""
            pending_area = None
            is_fullscreen = not is_fullscreen
            prop = cv2.WINDOW_FULLSCREEN if is_fullscreen else cv2.WINDOW_NORMAL
            cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, prop)
        elif key in (ord('p'), ord('P')):
            pending_media_digits = ""
            pending_area = None
            completed_areas = []
            area_media_indices = []
            current_area = []
            show_media = False
        elif key in (ord('z'), ord('Z')):
            pending_media_digits = ""
            pending_area = None
            if len(current_area) > 0:
                current_area.pop()
            elif len(completed_areas) > 0:
                completed_areas.pop()
                current_area.pop()
                if area_media_indices:
                    area_media_indices.pop()
        else:
            handle_assignment_character(key & 0xFF)

# Ressourcen beim Schließen freigeben
for m in media_sources:
    m.release()
cv2.destroyAllWindows()