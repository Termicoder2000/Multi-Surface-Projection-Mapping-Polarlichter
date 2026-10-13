# Fehlt nur noch umschalten der Bilder auf die Flächen mit Tastenkombinationen.
# wenn man z.B. 1 a) druckt, ist Media (Bild, Video, usw...) auf Fläche a)
# wenn Media 1 schon verwendet wird, dann wird einfach die Position getauscht.

# Mit -> oder <- kann man alles einfach verschieben.

import cv2
import numpy as np
import pyaudio
import os

# --- Konfiguration ---
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080

# Pfad zu deinem Haupt-Medienordner
MEDIA_FOLDER = '/home/nils/Desktop/Projects/Beamer/Images' 


# =========================================================================
# --- KLASSE 1: BASS-REAKTIVE BILDQUELLE ---
# =========================================================================
class AudioReactiveMediaSource:
    def __init__(self, folder_path, bass_min=10, bass_max=20000, max_bass_expected=30000.0):
        self.folder_path = folder_path.strip()
        self.bass_min = bass_min
        self.bass_max = bass_max
        self.max_bass_expected = max_bass_expected
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
        self.chunk = 1024
        self.rate = 44100
        self.audio = pyaudio.PyAudio()
        self.has_audio = False

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
        except Exception as e:
            print(f"[AudioReactive] Kein Mikrofon gefunden oder Audio-Fehler: {e}")

        # FFT Frequenzmaske
        freqs = np.fft.rfftfreq(self.chunk, 1.0 / self.rate)
        self.bass_mask = (freqs >= self.bass_min) & (freqs <= self.bass_max)

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

        matched.sort(key=lambda x: (x[0], x[1]))

        for _, img_path in matched:
            img = cv2.imread(img_path)
            if img is not None:
                self.images.append(img)

        print(f"[AudioReactive] {len(self.images)} Bilder geladen aus: {path}")

    def get_frame(self):
        if not self.has_audio or len(self.images) <= 1:
            return self.current_frame

        try:
            # Nur lesen, wenn genug Audio-Samples bereitstehen (verhindert FPS-Lag)
            if self.stream.get_read_available() >= self.chunk:
                raw_data = self.stream.read(self.chunk, exception_on_overflow=False)
                audio_samples = np.frombuffer(raw_data, dtype=np.int16)
                
                # Bass-Energie per FFT ermitteln
                fft_vals = np.abs(np.fft.rfft(audio_samples))
                bass_energy = np.mean(fft_vals[self.bass_mask])
                
                # Normalisierung auf 0.0 bis 1.0
                norm_factor = np.clip(bass_energy / self.max_bass_expected, 0.0, 1.0)

                print(norm_factor)

                index = int(norm_factor * (len(self.images) - 1))
                self.current_frame = self.images[index]
        except Exception:
            pass

        return self.current_frame

    def release(self):
        if self.has_audio:
            try:
                self.stream.stop_stream()
                self.stream.close()
                self.audio.terminate()
            except Exception:
                pass


# =========================================================================
# --- KLASSE 2: NORMALE MEDIENQUELLE (Bild, Video, Webcam) ---
# =========================================================================
class MediaSource:
    def __init__(self, path):
        self.path = path
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
        edges = cv2.Canny(gray, 10, 40)
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
# --- ORDNER-PARSER & QUELLEN-LADEN ---
# =========================================================================
def load_media_sources(folder_path):
    if not os.path.exists(folder_path):
        print(f"WARNUNG: Ordner '{folder_path}' nicht gefunden!")
        return [MediaSource("fallback")]

    indexed_files = []
    for filename in os.listdir(folder_path):
        if filename.startswith('.'):
            continue
        parts = filename.split('_', 1)
        # Sortierungs-Index ermitteln (z.B. "1_..." -> 1)
        order = int(parts[0]) if (len(parts) == 2 and parts[0].isdigit()) else 999
        indexed_files.append((order, filename, os.path.join(folder_path, filename)))

    indexed_files.sort(key=lambda x: (x[0], x[1]))

    sources = []
    for _, filename, full_path in indexed_files:
        # Prüfen, ob es sich um BassSensitive.txt handelt
        if 'basssensitive' in filename.lower() and filename.lower().endswith('.txt'):
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    target_images_folder = f.read().strip()

                # Falls der Pfad relativ angegeben wurde:
                if not os.path.isabs(target_images_folder) and not os.path.exists(target_images_folder):
                    alt_path = os.path.join(folder_path, target_images_folder)
                    if os.path.exists(alt_path):
                        target_images_folder = alt_path

                print(f"Lade Bass-Reaktive Quelle aus: {target_images_folder}")
                sources.append(AudioReactiveMediaSource(target_images_folder))
            except Exception as e:
                print(f"Fehler beim Lesen von {filename}: {e}")
                sources.append(MediaSource("fallback"))
        else:
            # Normale Datei (Bild, Video oder Kamera-Textdatei)
            sources.append(MediaSource(full_path))

    return sources if sources else [MediaSource("fallback")]


# =========================================================================
# --- PROJECTION MAPPING INITIALISIERUNG & LOOP ---
# =========================================================================
media_sources = load_media_sources(MEDIA_FOLDER)

completed_areas = [] 
current_area = []    
mouse_pos = (0, 0)
show_media = False   

def create_grid_image(w, h, grid_size=50):
    grid = np.zeros((h, w, 3), dtype=np.uint8)
    for x in range(0, w, grid_size):
        cv2.line(grid, (x, 0), (x, h), (255, 255, 255), 2)
    for y in range(0, h, grid_size):
        cv2.line(grid, (0, y), (w, y), (255, 255, 255), 2)
    cv2.rectangle(grid, (0, 0), (w - 1, h - 1), (255, 255, 255), 5)
    return grid

def mouse_callback(event, x, y, flags, param):
    global current_area, completed_areas, mouse_pos
    mouse_pos = (x, y)
    
    if event == cv2.EVENT_LBUTTONDOWN:
        current_area.append([x, y])
        if len(current_area) == 4:
            completed_areas.append(current_area)
            current_area = [] 

window_name = 'Multi-Face Projektion'
cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
cv2.setMouseCallback(window_name, mouse_callback)

while True:
    canvas = np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8)
    
    for i, area_points in enumerate(completed_areas):
        media = media_sources[i % len(media_sources)]
        
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

    if not show_media:
        for i in range(len(current_area)):
            cv2.circle(canvas, tuple(current_area[i]), 5, (255, 255, 255), -1)
            if i > 0:
                cv2.line(canvas, tuple(current_area[i - 1]), tuple(current_area[i]), (255, 255, 255), 2)
        
        if len(current_area) > 0:
            cv2.line(canvas, tuple(current_area[-1]), mouse_pos, (150, 150, 150), 1)

        cv2.putText(canvas, f"Flaeche {len(completed_areas) + 1} | Klicke Punkt {len(current_area) + 1}/4", 
                    (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.putText(canvas, "ENTER: Media starten | Z: Undo Klick | R: Alles loeschen", 
                    (50, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                    
        cv2.circle(canvas, mouse_pos, 4, (0, 0, 255), -1)

    cv2.imshow(window_name, canvas)

    key = cv2.waitKey(16) & 0xFF
    if key == 27:  # ESC
        break
    elif key == 13:  # ENTER
        show_media = not show_media
    elif key in (ord('r'), ord('R')): 
        completed_areas = []
        current_area = []
        show_media = False
    elif key in (ord('z'), ord('Z')):  
        if len(current_area) > 0:
            current_area.pop()
        elif len(completed_areas) > 0:
            current_area = completed_areas.pop()
            current_area.pop()

# Resourcen sauber freigeben
for m in media_sources:
    m.release()
cv2.destroyAllWindows()