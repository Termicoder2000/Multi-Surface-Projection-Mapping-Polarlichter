#Select From Folder
#To Do:
#Write information about the image processing in the "Camera.txt"-File to cconfigure that

import cv2
import numpy as np
import os

# --- Konfiguration ---
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080

# Hier den Pfad zu deinem Ordner eintragen
MEDIA_FOLDER = '/home/nils/Desktop/Projects/Beamer/Images' 

# --- Klassen und globale Variablen ---
class MediaSource:
    def __init__(self, path):
        self.path = path
        
        # Kamera erkennen, wenn es eine .txt Datei ist oder der Pfad direkt "camera" heißt (Fallback)
        self.is_camera = path.lower().endswith('.txt') or (path.lower() == 'camera')
        # Videos anhand der Dateiendung erkennen (oder wenn es die Kamera ist)
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
        cv2.putText(self.frame, text, (50, 300), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 4)
        self.h, self.w = self.frame.shape[:2]

    # =========================================================================
    # --- BILDVERARBEITUNG (ZUFÄLLIGE FARBVERTEILUNG) ---
    # =========================================================================
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
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.cap.read()
            return frame
        
        return self.frame


# --- Hilfsfunktion zum Laden und Sortieren der Medien aus dem Ordner ---
def load_media_files_from_folder(folder_path):
    if not os.path.exists(folder_path):
        print(f"WARNUNG: Ordner '{folder_path}' wurde nicht gefunden!")
        return []
        
    valid_files = []
    for filename in os.listdir(folder_path):
        # Überprüfen, ob die Datei mit einer Zahl und einem Unterstrich beginnt (z.B. "1_Bild.png")
        parts = filename.split('_', 1)
        if len(parts) == 2 and parts[0].isdigit():
            # Speichere die Zahl (als Integer für korrekte Sortierung) und den vollen Dateipfad
            order_index = int(parts[0])
            full_path = os.path.join(folder_path, filename)
            valid_files.append((order_index, full_path))
            
    # Liste anhand der ausgelesenen Zahl sortieren (1, 2, 3...)
    valid_files.sort(key=lambda x: x[0])
    
    # Nur die Dateipfade in der richtigen Reihenfolge zurückgeben
    return [file[1] for file in valid_files]


# Medien automatisch laden
media_paths = load_media_files_from_folder(MEDIA_FOLDER)

media_sources = [MediaSource(f) for f in media_paths]
if not media_sources:
    print("Keine gueltigen Medien gefunden, lade Fallback...")
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
