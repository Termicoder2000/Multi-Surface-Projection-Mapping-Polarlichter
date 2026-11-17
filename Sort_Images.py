import os

# Verzeichnis angeben, in dem sich die Bilder befinden ('.' steht für das aktuelle Verzeichnis)
verzeichnis = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'SoundSensitive_3')

# Schleife von 0 bis 1000 (range(1001) schließt die 1000 mit ein)
for i in range(1001):
  alter_name = f"image_{i}.jpg"
  neuer_name = f"{i}_image.jpg"

  alt_pfad = os.path.join(verzeichnis, alter_name)
  neu_pfad = os.path.join(verzeichnis, neuer_name)

  # Prüfen, ob die Datei existiert, bevor sie umbenannt wird
  if os.path.exists(alt_pfad):
    os.rename(alt_pfad, neu_pfad)
    print(f"Umbenannt: {alter_name} -> {neuer_name}")

print("Alle verfügbaren Bilder wurden erfolgreich umbenannt!")