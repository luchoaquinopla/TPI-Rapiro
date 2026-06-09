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
│   ├── networks/         # Arquitectura y entrenamiento de redes
│   ├── robot/
│   │   ├── rapiro_controller.py  # Control de servos via serial UART
│   │   ├── subscriber.py         # Subscriber de Pub/Sub (corre en la Raspberry Pi)
│   │   └── test_servos.py        # Prueba manual de servos
│   └── cloud/            # Integración GCP (Pub/Sub, Firestore)
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

### Módulo robot (`src/robot/`)

Corre en la **Raspberry Pi** instalada dentro del RAPIRO. Se suscribe al topic de Pub/Sub y traduce cada evento de reconocimiento en un movimiento de servo.

**Flujo:**
```
Google Cloud Pub/Sub
        ↓
  subscriber.py  (Raspberry Pi)
        ↓
  RAPIROController
        ↓
  Serial UART → Shield Arduino → Servos
```

**Lógica de respuesta:**

| Identidad detectada | Acción |
|---|---|
| Persona conocida (`Luciano`) | Levanta brazo derecho |
| Persona desconocida | Levanta brazo izquierdo |

El robot mantiene la pose 3 segundos y vuelve a posición neutra.

#### Dependencias (instalar en la Raspberry Pi)

```bash
pip install pyserial google-cloud-pubsub
```

#### Credenciales GCP

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/ruta/al/service-account.json"
```

#### Cómo testear

**Paso 1 — Verificar conexión serial con el shield:**

```bash
python src/robot/test_servos.py
```

Esto mueve el brazo derecho, vuelve a neutro, mueve el izquierdo y vuelve a neutro. Si el robot no responde, verificar el puerto serial y el baud rate.

**Paso 2 — Ajustar si hace falta:**

Si el servo incorrecto se mueve, editar `rapiro_controller.py`:
```python
SERVO_HOMBRO_DERECHO   = 2   # cambiar al ID correcto
SERVO_HOMBRO_IZQUIERDO = 6   # cambiar al ID correcto
ANGULO_BRAZO_ARRIBA    = 150  # ajustar el ángulo de elevación
```

Para encontrar el ID correcto, descomentar el loop de barrido en `test_servos.py`.

**Paso 3 — Correr el subscriber:**

```bash
python src/robot/subscriber.py
```

**Paso 4 — En la PC, correr el reconocimiento** como de costumbre. Cada detección publica automáticamente al topic de Pub/Sub y el robot reacciona.

#### Variables de entorno opcionales

| Variable | Default | Descripción |
|---|---|---|
| `RAPIRO_PORT` | `/dev/ttyAMA0` | Puerto serial de la Raspberry Pi |
| `RAPIRO_BAUD` | `57600` | Baud rate del shield Arduino |
| `GOOGLE_APPLICATION_CREDENTIALS` | — | Ruta al JSON de la cuenta de servicio |

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
Cámara (webcam local o IP Webcam)
        ↓
OpenCV — captura frames
        ↓
Haar Cascade — detecta rostro → bounding box
        ↓
CNN binaria — clasifica: conocido / desconocido
        ↓
Google Cloud Pub/Sub  ──────────────────────────────┐
        ↓                                            ↓
  Cloud Function                           Raspberry Pi (RAPIRO)
  → persiste en Firestore                  subscriber.py
                                                     ↓
                                           RAPIROController
                                                     ↓
                                           Serial UART → Shield Arduino
                                                     ↓
                                      Conocido → brazo derecho
                                    Desconocido → brazo izquierdo
```

### Diagrama de secuencia

```
PC                  Pub/Sub (GCP)       Raspberry Pi        Arduino Shield
 │                       │                    │                    │
 │── publica evento ─────▶                    │                    │
 │                       │── entrega msg ────▶│                    │
 │                       │                    │── "S2,150\n" ─────▶│
 │                       │                    │                    │── mueve servo
 │                       │                    │   (espera 3 seg)   │
 │                       │                    │── "S2,90\n" ───────▶│
 │                       │                    │                    │── posición neutra
```
