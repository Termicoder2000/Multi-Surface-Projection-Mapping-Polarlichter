# https://github.com/fogleman/primitive images with shapes

import cv2
import numpy as np

# --- Konfiguration ---
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080

MEDIA_FILES = [
    'Camera',
    'Beamer/test.mp4',
    'Beamer/download.jpeg'
]

# --- Klassen und globale Variablen ---
class MediaSource:
    def __init__(self, path):
        self.path = path
        self.is_camera = (path.lower() == 'camera')
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
                self.create_fallback(f"Video Fehler: {path}")
            else:
                ret, frame = self.cap.read()
                if ret:
                    self.h, self.w = frame.shape[:2]
                else:
                    self.create_fallback(f"Video leer: {path}")
        else:
            self.frame = cv2.imread(path)
            if self.frame is not None:
                self.h, self.w = self.frame.shape[:2]
            else:
                self.create_fallback(f"Nicht gefunden: {path}")

    def create_fallback(self, text):
        self.is_video = False
        self.is_camera = False
        self.frame = np.zeros((600, 800, 3), dtype=np.uint8)
        self.frame[:] = (50, 100, 200)
        cv2.putText(self.frame, text, (50, 300), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 4)
        self.h, self.w = self.frame.shape[:2]

    # =========================================================================
    # --- HIER STARTET DIE BILDVERARBEITUNG (ZUFÄLLIGE FARBVERTEILUNG) ---
    # =========================================================================
    def process_frame(self, frame):
        # 1. Bild in Graustufen umwandeln
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # 2. Umrisse finden (hier mit 10 und 40 für maximal viele Linien)
        edges = cv2.Canny(gray, 10, 40)
        
        # 3. Leere schwarze Leinwand in der Größe des Frames erstellen
        result_frame = np.zeros_like(frame)
        
        # 4. Farben definieren (BGR-Format)
        color_red = (0, 0, 255)
        color_purple = (255, 0, 150)
        
        # Eine "Maske" erstellen, wo überall Kanten sind (True/False)
        edge_mask = edges > 0
        
        # Eine Matrix mit reinem Zufall (Werte 0 oder 1) in der Größe des Bildes erstellen
        random_matrix = np.random.randint(0, 2, size=edges.shape).astype(bool)
        
        # Kanten zufällig in zwei Gruppen aufteilen
        # mask_red: Ist eine Kante UND der Zufallswert ist 1 (True)
        mask_red = edge_mask & random_matrix
        
        # mask_purple: Ist eine Kante UND der Zufallswert ist 0 (False)
        mask_purple = edge_mask & ~random_matrix
        
        # Die Farben auf die entsprechenden Pixel anwenden
        result_frame[mask_red] = color_red
        result_frame[mask_purple] = color_purple
        
        return result_frame
    # =========================================================================
    # --- ENDE DER BILDVERARBEITUNG ---
    # =========================================================================

    def get_frame(self):
        if self.is_video and self.is_camera:
            ret, frame = self.cap.read()
            if not ret:
                return self.process_frame(self.frame) 
            return self.process_frame(frame)
        
        elif self.is_video:
            ret, frame = self.cap.read()
            if not ret:
                # Video-Loop
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.cap.read()
            return frame
        
        # Auch normale Bilder durch den Filter schicken
        return self.frame

# --- Ab hier bleibt alles wie im vorherigen Code ---

media_sources = [MediaSource(f) for f in MEDIA_FILES]
if not media_sources:
    media_sources = [MediaSource("fallback")]

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
    cv2.rectangle(grid, (0, 0), (w-1, h-1), (255, 255, 255), 5)
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
                cv2.line(canvas, tuple(current_area[i-1]), tuple(current_area[i]), (255, 255, 255), 2)
        
        if len(current_area) > 0:
            cv2.line(canvas, tuple(current_area[-1]), mouse_pos, (150, 150, 150), 1)

        cv2.putText(canvas, f"Flaeche {len(completed_areas)+1} | Klicke Punkt {len(current_area)+1}/4", 
                    (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.putText(canvas, "ENTER: Media starten | Z: Undo Klick | R: Alles loeschen", 
                    (50, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                    
        cv2.circle(canvas, mouse_pos, 4, (0, 0, 255), -1)

    cv2.imshow(window_name, canvas)

    key = cv2.waitKey(16) & 0xFF
    if key == 27:  
        break
    elif key == 13:  
        show_media = not show_media
    elif key == ord('r') or key == ord('R'): 
        completed_areas = []
        current_area = []
        show_media = False
    elif key == ord('z') or key == ord('Z'):  
        if len(current_area) > 0:
            current_area.pop()
        elif len(completed_areas) > 0:
            current_area = completed_areas.pop()
            current_area.pop()

for m in media_sources:
    if (m.is_video or m.is_camera) and hasattr(m, 'cap'):
        m.cap.release()
cv2.destroyAllWindows()
