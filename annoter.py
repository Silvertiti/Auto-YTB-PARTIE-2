import cv2
import os
import glob

# Répertoire où sont tes images
image_dir = "thumbnails"
# Répertoire où sauvegarder les annotations
label_dir = "labels"
os.makedirs(label_dir, exist_ok=True)

# Liste des images à annoter
images = glob.glob(os.path.join(image_dir, "*.jpg"))

# Variables globales pour les points du rectangle
ix, iy = -1, -1
drawing = False
rect = (0, 0, 0, 0)

def draw_rectangle(event, x, y, flags, param):
    global ix, iy, drawing, rect

    if event == cv2.EVENT_LBUTTONDOWN:
        drawing = True
        ix, iy = x, y

    elif event == cv2.EVENT_MOUSEMOVE:
        if drawing:
            img_copy = img.copy()
            cv2.rectangle(img_copy, (ix, iy), (x, y), (0, 255, 0), 2)
            cv2.imshow('Image', img_copy)

    elif event == cv2.EVENT_LBUTTONUP:
        drawing = False
        rect = (ix, iy, x, y)
        cv2.rectangle(img, (ix, iy), (x, y), (0, 255, 0), 2)
        cv2.imshow('Image', img)

        # Sauvegarde du label au format YOLO (classe_id x_center y_center width height normalisés)
        h, w, _ = img.shape
        x_center = (ix + x) / 2 / w
        y_center = (iy + y) / 2 / h
        width = abs(x - ix) / w
        height = abs(y - iy) / h
        class_id = 0  # webcam = 0
        label = f"{class_id} {x_center} {y_center} {width} {height}"

        # Nom du fichier label
        img_name = os.path.basename(param)
        label_name = os.path.splitext(img_name)[0] + ".txt"
        with open(os.path.join(label_dir, label_name), 'w') as f:
            f.write(label + '\n')

        print(f"✅ Sauvegardé : {label_name}")

# Boucle sur les images
for img_path in images:
    print(f"🖼️ Annotation de : {img_path}")
    img = cv2.imread(img_path)
    cv2.namedWindow('Image')
    cv2.setMouseCallback('Image', draw_rectangle, param=img_path)

    while True:
        cv2.imshow('Image', img)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('n'):
            break
        elif key == ord('q'):
            exit()

cv2.destroyAllWindows()
print("✅ Annotation terminée.")
