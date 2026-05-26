import cv2
import numpy as np

# --- Konfiguration ---
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080

# Trage hier deine Bilder oder Videos ein (.mp4, .avi, .jpg, .png etc.)
# Erstes File -> Erste Fläche, Zweites File -> Zweite Fläche, usw.
MEDIA_FILES = [
    'Beamer/test.mp4',
    'Beamer/download.jpeg'
]

# --- Klassen und globale Variablen ---
class MediaSource:
    def __init__(self, path):
        self.path = path
        # Einfache Prüfung auf Video-Endungen
        self.is_video = path.lower().endswith(('.mp4', '.avi', '.mov', '.mkv'))
        
        if self.is_video:
            self.cap = cv2.VideoCapture(path)
            ret, frame = self.cap.read()
            if ret:
                self.h, self.w = frame.shape[:2]
            else:
                self.create_fallback(f"Fehler: {path}")
        else:
            self.frame = cv2.imread(path)
            if self.frame is not None:
                self.h, self.w = self.frame.shape[:2]
            else:
                self.create_fallback(f"Nicht gefunden: {path}")

    def create_fallback(self, text):
        self.is_video = False
        self.frame = np.zeros((600, 800, 3), dtype=np.uint8)
        self.frame[:] = (50, 100, 200)
        cv2.putText(self.frame, text, (50, 300), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 4)
        self.h, self.w = self.frame.shape[:2]

    def get_frame(self):
        if self.is_video:
            ret, frame = self.cap.read()
            if not ret: # Video zu Ende -> Loop
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.cap.read()
            return frame
        return self.frame

# Lade alle Medien
media_sources = [MediaSource(f) for f in MEDIA_FILES]
if not media_sources:
    media_sources = [MediaSource("fallback")] # Falls Liste leer ist

completed_areas = [] # Liste von 4er-Punkt-Listen: [[p1,p2,p3,p4], [p1,p2,p3,p4]]
current_area = []    # Punkte der aktuell in Bearbeitung befindlichen Fläche
mouse_pos = (0, 0)
show_media = False   # False = Gitter, True = Videos/Bilder

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
            current_area = [] # Reset für die nächste Fläche

# --- Fenster Setup ---
window_name = 'Multi-Face Projektion'
cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
cv2.setMouseCallback(window_name, mouse_callback)

while True:
    canvas = np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8)
    
    # 1. Fertige Flächen rendern
    for i, area_points in enumerate(completed_areas):
        # Passendes Medium für diese Fläche wählen (mit Loop, falls mehr Flächen als Medien)
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

    # 2. Aktuell zu zeichnende Fläche anzeigen (Einstellphase)
    if not show_media:
        # Linien der unfertigen Fläche
        for i in range(len(current_area)):
            cv2.circle(canvas, tuple(current_area[i]), 5, (255, 255, 255), -1)
            if i > 0:
                cv2.line(canvas, tuple(current_area[i-1]), tuple(current_area[i]), (255, 255, 255), 2)
        
        # Linie zur Maus
        if len(current_area) > 0:
            cv2.line(canvas, tuple(current_area[-1]), mouse_pos, (150, 150, 150), 1)

        # UI Texte
        cv2.putText(canvas, f"Flaeche {len(completed_areas)+1} | Klicke Punkt {len(current_area)+1}/4", 
                    (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.putText(canvas, "ENTER: Media starten | Z: Undo Klick | R: Alles loeschen", 
                    (50, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                    
        # Roter Mauszeiger
        cv2.circle(canvas, mouse_pos, 4, (0, 0, 255), -1)

    cv2.imshow(window_name, canvas)

    # --- Tastatursteuerung ---
    # waitKey(16) sorgt für ca. 60 FPS (1000ms / 16ms) - wichtig für flüssige Videos
    key = cv2.waitKey(16) & 0xFF
    if key == 27:  # ESC
        break
    elif key == 13:  # Enter
        show_media = not show_media
    elif key == ord('r') or key == ord('R'):  # Alles Reset
        completed_areas = []
        current_area = []
        show_media = False
    elif key == ord('z') or key == ord('Z'):  # Undo letzter Klick
        if len(current_area) > 0:
            current_area.pop()
        elif len(completed_areas) > 0:
            current_area = completed_areas.pop()
            current_area.pop()

# Aufräumen
for m in media_sources:
    if m.is_video and hasattr(m, 'cap'):
        m.cap.release()
cv2.destroyAllWindows()