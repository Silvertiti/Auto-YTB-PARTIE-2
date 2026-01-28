import cv2
import pytesseract
from PIL import Image

# Charger l'image
image = cv2.imread("captcha.png")

# Convertir en niveaux de gris
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

# Appliquer un seuillage pour améliorer la détection
_, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)

# Sauvegarder l’image traitée si besoin pour debug
cv2.imwrite("processed.png", thresh)

# Appliquer OCR
text = pytesseract.image_to_string(thresh, config='--psm 8')
print("Texte détecté :", text.strip())
