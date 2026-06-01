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
│   └── own_dataset/      # Fotos propias por persona (una carpeta por persona)
│
├── models/
│   └── detection/        # Pesos del clasificador binario (.h5 / .weights.h5)
│
├── src/
│   ├── capture/
│   │   ├── stream_capture.py      # Captura OpenCV: webcam local + IP Webcam
│   │   ├── dataset_generator.py   # Generador de dataset por persona
│   │   ├── model_loader.py        # Carga de modelos Keras 2/3
│   │   └── reconocimiento_vivo.py # Clasificación binaria en tiempo real
│   ├── networks/         # Arquitectura y entrenamiento de redes (pendiente)
│   ├── robot/            # Control RAPIRO via PySerial (pendiente)
│   └── cloud/            # Integración GCP (Pub/Sub, Firestore, FCM) (pendiente)
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

## Módulos implementados

### Captura de video (`stream_capture.py`)

```python
from src.capture.stream_capture import connect_stream, prepare_frame, capture_loop

# Preview en vivo (auto-detecta cámara)
capture_loop()

# Stream IP Webcam
capture_loop("http://192.168.1.5:8080/video")
```

### Generador de dataset (`dataset_generator.py`)

```bash
# Captura 400 fotos de "luciano" (default)
python src/capture/dataset_generator.py luciano

# Fotos de "gonzalo" con configuración personalizada
python src/capture/dataset_generator.py gonzalo --max-fotos 200 --intervalo-ms 300
```

Guarda recortes de rostros (96×96 px) en `data/own_dataset/<persona>/`.  
Controles: **Espacio/P** para pausar · **Q** para salir.

### Reconocimiento en vivo (`reconocimiento_vivo.py`)

```bash
# Usando pesos por defecto (models/detection/modelo_binario_pesos.weights.h5)
python src/capture/reconocimiento_vivo.py

# Con pesos y umbral personalizados
python src/capture/reconocimiento_vivo.py --pesos models/detection/mis_pesos.h5 --umbral 0.45
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
