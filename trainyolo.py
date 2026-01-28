from ultralytics import YOLO

def train_yolo():
    # 🔗 Chemin vers ton fichier data.yaml
    data_yaml = "dataset/data.yaml"
    
    # 🔗 Choisir le modèle de base (yolov8n.pt, yolov8s.pt, etc.)
    model_name = "yolov8n.pt"
    
    # 🔧 Paramètres d'entraînement
    model = YOLO(model_name)
    
    # 🏃‍♂️ Lance l'entraînement (CPU forcé)
    results = model.train(
        data=data_yaml,
        epochs=50,
        imgsz=640,
        device='cpu'  # ⚠️ Entraînement forcé sur CPU
    )
    
    print("✅ Entraînement terminé !")
    print(f"📂 Résultats dans : {results.save_dir}")

if __name__ == "__main__":
    train_yolo()
