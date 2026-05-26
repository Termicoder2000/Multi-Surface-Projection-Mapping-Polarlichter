import cv2
import numpy as np

# --- Konfiguration ---
# Passe die Auflösung an deinen Beamer an (z.B. 1920x1080)
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080
IMAGE_PATH = 'Beamer/download.jpeg' # Pfad zu deinem Bild

# --- Globale Variablen ---
points = []
mouse_pos = (0, 0)
show_image = False # False = Einstellphase (Raster), True = Laufphase (Bild)

def get_image_to_project():
    """Lädt das Bild oder erstellt ein Testbild, falls es nicht existiert."""
    img = cv2.imread(IMAGE_PATH)
    if img is None:
        # Fallback Testbild generieren, falls kein Bild gefunden wurde
        img = np.zeros((600, 800, 3), dtype=np.uint8)
        img[:] = (50, 100, 200) # Blauer Hintergrund
        cv2.putText(img, "Testbild", (250, 300), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 5)
        cv2.rectangle(img, (10, 10), (790, 590), (0, 255, 0), 10) # Grüner Rand
    return img

def create_grid_image(w, h, grid_size=50):
    """Erstellt ein 2D-Raster, das später transformiert wird."""
    grid = np.zeros((h, w, 3), dtype=np.uint8)
    # Gitterlinien zeichnen
    for x in range(0, w, grid_size):
        cv2.line(grid, (x, 0), (x, h), (255, 255, 255), 2)
    for y in range(0, h, grid_size):
        cv2.line(grid, (0, y), (w, y), (255, 255, 255), 2)
    # Äußerer Rahmen
    cv2.rectangle(grid, (0, 0), (w-1, h-1), (255, 255, 255), 5)
    return grid

def mouse_callback(event, x, y, flags, param):
    global points, mouse_pos
    mouse_pos = (x, y)
    
    if event == cv2.EVENT_LBUTTONDOWN:
        if len(points) < 4:
            points.append([x, y])

# --- Fenster Setup ---
window_name = 'Beamer Projektion'
cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
cv2.setMouseCallback(window_name, mouse_callback)

image = get_image_to_project()
img_h, img_w = image.shape[:2]
grid_image = create_grid_image(img_w, img_h)

while True:
    # Schwarze Leinwand für jeden Frame neu erstellen
    canvas = np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8)
    
    # Roter Mauszeiger (wird immer gezeichnet)
    cv2.circle(canvas, mouse_pos, 4, (0, 0, 255), -1)

    # Phase 1: Punkte sammeln
    if len(points) < 4:
        # Bereits geklickte Punkte und Verbindungslinien zeichnen
        for i in range(len(points)):
            cv2.circle(canvas, tuple(points[i]), 5, (255, 255, 255), -1)
            if i > 0:
                cv2.line(canvas, tuple(points[i-1]), tuple(points[i]), (255, 255, 255), 2)
        
        # Vorschau-Linie vom letzten Punkt zur aktuellen Mausposition
        if len(points) > 0:
            cv2.line(canvas, tuple(points[-1]), mouse_pos, (150, 150, 150), 1)
            
        cv2.putText(canvas, f"Klicke Punkt {len(points)+1}/4 (im Uhrzeigersinn!)", 
                    (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

    # Phase 2 & 3: Transformation (Raster oder Bild)
    elif len(points) == 4:
        # Ausgangspunkte (Die Ecken des Originalbildes/Rasters)
        pts_source = np.float32([[0, 0], [img_w, 0], [img_w, img_h], [0, img_h]])
        # Zielpunkte (Die von dir geklickten Beamer-Koordinaten)
        pts_dest = np.float32(points)
        
        # Transformationsmatrix berechnen
        matrix = cv2.getPerspectiveTransform(pts_source, pts_dest)
        
        if not show_image:
            # Einstellphase: Raster transformieren und anzeigen
            warped = cv2.warpPerspective(grid_image, matrix, (SCREEN_WIDTH, SCREEN_HEIGHT))
            canvas = cv2.add(canvas, warped) # Auf den schwarzen Hintergrund legen
            cv2.putText(canvas, "Druecke ENTER fuer das Bild | 'R' fuer Reset", 
                        (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        else:
            # Laufphase: Echtes Bild transformieren
            warped = cv2.warpPerspective(image, matrix, (SCREEN_WIDTH, SCREEN_HEIGHT))
            canvas = cv2.add(canvas, warped)
            
        # Optional: Mauszeiger weiterhin über dem Bild rendern
        cv2.circle(canvas, mouse_pos, 4, (0, 0, 255), -1)

    cv2.imshow(window_name, canvas)

    # --- Tastatursteuerung ---
    key = cv2.waitKey(1) & 0xFF
    if key == 27:  # ESC-Taste zum Beenden
        break
    elif key == 13 and len(points) == 4:  # Enter-Taste für Laufphase
        show_image = not show_image
    elif key == ord('r') or key == ord('R'):  # R-Taste für Reset
        points = []
        show_image = False

cv2.destroyAllWindows()
