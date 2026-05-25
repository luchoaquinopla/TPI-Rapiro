# RAPIRO — Sistema Inteligente de Reconocimiento Facial
**TPI Intercátedra 2026 — Ingeniería en Sistemas de Información**
Universidad de la Cuenca del Plata

**Autores:** Mata Gonzalo · Aquino Luciano

---

## Estructura del proyecto

```
rapiro_project/
│
├── data/
│   ├── wider_face/       # Dataset detección de rostros
│   ├── lfw/              # Dataset Labeled Faces in the Wild
│   └── own_dataset/      # Fotos propias por persona registrada
│
├── models/
│   ├── detection/        # Modelo Red de Detección (.h5)
│   ├── embedding/        # Modelo Red de Embedding (.h5)
│   └── classification/   # Modelo Red de Clasificación (.h5)
│
├── src/
│   ├── capture/          # Pipeline captura OpenCV + IP Webcam
│   ├── networks/         # Arquitectura y entrenamiento de redes
│   ├── robot/            # Control RAPIRO via PySerial
│   └── cloud/            # Integración GCP (Pub/Sub, Firestore, FCM)
│
├── tests/                # Pruebas unitarias e integración
├── notebooks/            # Experimentación en Jupyter/Colab
├── infrastructure/
│   └── terraform/        # IaC para GCP
├── docs/                 # Documentación técnica
│
├── requirements.txt
├── verify_env.py
└── README.md
```

---

## Configuración inicial

### 1. Clonar el repositorio
```bash
git clone <url-del-repo>
cd rapiro_project
```

### 2. Crear entorno virtual
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux / macOS
source venv/bin/activate
```

### 3. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 4. Verificar instalación
```bash
python verify_env.py
```

---

## Variables de entorno

Crear un archivo `.env` en la raíz del proyecto:
```
GCP_PROJECT_ID=tu-proyecto-gcp
GCP_PUBSUB_TOPIC=rapiro-events
GCP_FIRESTORE_COLLECTION=detections
RAPIRO_SERIAL_PORT=COM3        # Windows: COM3, Linux: /dev/ttyUSB0
CAMERA_STREAM_URL=http://192.168.X.X:8080/video
```

---

## Pipeline del sistema

```
Cámara móvil (IP Webcam)
        ↓
OpenCV — captura frames
        ↓
Red de Detección (CNN) — localiza rostro → bounding box
        ↓
Red de Embedding (CNN) — convierte rostro → vector 128D
        ↓
Red de Clasificación (Dense) — identifica persona
        ↓
    ┌───────────────┐
    │  Conocido?    │
    └───┬───────────┘
      Sí│            No
        ↓             ↓
    LED verde      LED rojo
    Servo saludo   Servo alerta
        ↓             ↓
         GCP Pub/Sub → Firestore
                      Cloud Storage (captura)
                      FCM (notificación móvil)
```
