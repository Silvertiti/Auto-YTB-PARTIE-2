from ultralytics import YOLO
import cv2

# Chemin vers ton modèle entraîné
model_path = "runs/detect/train6/weights/best.pt"
model = YOLO(model_path)

# Chemin vers l'image à traiter
image_path = r"C:\Users\methe\OneDrive\Bureau\Auto YTB PARTIE 2\dataset\images\train\clip_155.jpg"

# Lecture de l'image
img = cv2.imread(image_path)

# Détection avec YOLO (pas de show/save ici)
results = model.predict(source=image_path, conf=0.25, save=False, show=False)

# Pour chaque résultat (normalement un seul ici)
for result in results:
    boxes = result.boxes
    for box in boxes:
        # Récupération des coordonnées de la boîte de détection
        x1, y1, x2, y2 = map(int, box.xyxy[0])

        # Ajoute une marge pour inclure le "contour de la caméra"
        marge = 0 # pixels à ajouter autour de la boîte
        x1 = max(0, x1 - marge)
        y1 = max(0, y1 - marge)
        x2 = min(img.shape[1], x2 + marge)
        y2 = min(img.shape[0], y2 + marge)

        # Rogner l'image avec la marge
        cropped_img = img[y1:y2, x1:x2]

        # Sauvegarde du résultat
        output_path = "webcam_crop.jpg"
        cv2.imwrite(output_path, cropped_img)
        print(f"Image rognée avec contour sauvegardée : {output_path}")

print("✅ Découpage terminé avec bordure supplémentaire.")
