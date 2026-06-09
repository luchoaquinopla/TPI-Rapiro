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
│   ├── lfw/              # Dataset Labeled Faces in the Wild (clase "desconocido")
│   └── own_dataset/      # Fotos propias por persona (una carpeta por persona)
│
├── models/
│   └── detection/
│       └── modelo_tpi.keras   # Clasificador multiclase entrenado en Colab (Keras 3)
│
├── src/
│   ├── capture/
│   │   ├── stream_capture.py      # Captura OpenCV: webcam local + IP Webcam
│   │   ├── dataset_generator.py   # Generador de dataset por persona
│   │   ├── model_loader.py        # Carga de modelo Keras con load_model()
│   │   ├── cloud_notifier.py      # Alertas: Cloud Storage + Firestore + Gmail
│   │   └── reconocimiento_vivo.py # Clasificación multiclase en tiempo real
│   ├── networks/         # Arquitectura y entrenamiento de redes
│   ├── robot/
│   │   ├── rapiro_controller.py  # Control de servos via serial UART
│   │   ├── subscriber.py         # Subscriber de Pub/Sub (corre en la Raspberry Pi)
│   │   └── test_servos.py        # Prueba manual de servos
│   └── cloud/            # Integración GCP
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

Clasificador **multiclase** con tres clases: `desconocido` (0) · `luciano` (1) · `paola` (2).  
Entrenado en Google Colab con dataset propio + LFW crowd (clase desconocido).

```bash
# Usando modelo por defecto (models/detection/modelo_tpi.keras)
python src/capture/reconocimiento_vivo.py

# Con modelo alternativo
python src/capture/reconocimiento_vivo.py --modelo models/detection/otro_modelo.keras
```

**Cooldowns de publicación a Pub/Sub:**

| Evento | Cooldown |
|---|---|
| Persona conocida detectada | 5 segundos |
| Persona desconocida detectada | 30 segundos |

Cuando se detecta un desconocido, además de publicar en Pub/Sub se ejecuta automáticamente `cloud_notifier.notify_unknown()`.

### Notificaciones de desconocidos (`cloud_notifier.py`)

Al detectar una persona desconocida el sistema:

1. **Sube la imagen del rostro** a Google Cloud Storage (`gs://rapiro-detecciones/desconocidos/<timestamp>.jpg`)
2. **Guarda el registro** en Firestore (colección `detecciones_desconocidos`) con timestamp, confianza e imagen URL
3. **Envía un email HTML** vía Gmail SMTP con la imagen del rostro embebida y link directo a Cloud Storage

Requiere las siguientes variables de entorno (ver sección Variables de entorno).

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

| Evento recibido | Acción del RAPIRO |
|---|---|
| `rostro_detectado` (persona conocida) | Levanta brazo derecho · 3 s · posición neutra |
| `desconocido_detectado` | Sacude la cabeza (no × 2) · levanta ambos brazos · 3 s · posición neutra |

El movimiento de cabeza usa el servo `SERVO_CABEZA = 0` (ajustar si el cableado es distinto).

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
SERVO_CABEZA           = 0   # servo de rotación de cabeza (izquierda/derecha)
SERVO_HOMBRO_DERECHO   = 2   # cambiar al ID correcto
SERVO_HOMBRO_IZQUIERDO = 6   # cambiar al ID correcto
ANGULO_BRAZO_ARRIBA    = 150  # ajustar el ángulo de elevación
ANGULO_CABEZA_IZQUIERDA = 60  # ángulo de giro izquierdo para el "no"
ANGULO_CABEZA_DERECHA   = 120 # ángulo de giro derecho para el "no"
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

## Cómo ejecutar con el RAPIRO físico

### Configuración inicial (hacer una sola vez)

**1. Conectarse a la Raspberry Pi**

Conectá un teclado USB y monitor HDMI a la Raspberry Pi para la primera configuración. Una vez configurada, todo lo demás se hace por SSH.

**2. Configurar las redes WiFi**

```bash
sudo nano /etc/wpa_supplicant/wpa_supplicant.conf
```

Agregá las redes que vas a usar:

```
network={
    ssid="NombreHotspotCelular"
    psk="contraseñaHotspot"
}

network={
    ssid="WiFi-Casa"
    psk="contraseñaCasa"
}
```

Guardá con `Ctrl+O`, salís con `Ctrl+X` y reiniciás:

```bash
sudo reboot
```

**3. Clonar el repo e instalar dependencias**

```bash
git clone https://github.com/luchoaquinopla/TPI-Rapiro.git
cd TPI-Rapiro
pip install pyserial google-cloud-pubsub
```

**4. Copiar las credenciales GCP**

Desde tu laptop:
```bash
scp infrastructure/keys/gcp-key.json pi@<IP-raspberry>:~/TPI-Rapiro/infrastructure/keys/
```

---

### El día de la demo

**Paso 1 — Activar hotspot en el celular**

Tanto tu laptop como la Raspberry Pi deben estar conectadas al mismo hotspot.

**Paso 2 — Obtener la IP de la Raspberry Pi**

Revisá los dispositivos conectados en la configuración del hotspot de tu celular, o desde la Raspberry Pi (si tenés acceso directo):
```bash
hostname -I
```

**Paso 3 — Conectarse a la Raspberry por SSH**

```bash
ssh pi@<IP-raspberry>
```

**Paso 4 — Correr el subscriber en la Raspberry**

```bash
cd TPI-Rapiro/src/robot
export GOOGLE_APPLICATION_CREDENTIALS="../../infrastructure/keys/gcp-key.json"
python subscriber.py
```

Vas a ver: `Escuchando en projects/...` — el RAPIRO está listo.

**Paso 5 — Correr el reconocimiento en tu laptop**

```bash
python src/capture/reconocimiento_vivo.py
```

A partir de este momento: cada cara detectada publica en Pub/Sub y el RAPIRO reacciona en ~1-2 segundos.

---

## Variables de entorno

Crear un archivo `.env` en la raíz del proyecto:

```
# Google Cloud
GOOGLE_APPLICATION_CREDENTIALS=infrastructure/keys/gcp-key.json
GCS_BUCKET_NAME=rapiro-detecciones

# Gmail — requiere App Password (no la contraseña normal)
# Generala en: myaccount.google.com → Seguridad → Contraseñas de aplicación
GMAIL_USER=tu@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
GMAIL_TO=tu@gmail.com

# Cámara (opcional — se auto-detecta si no se define)
# CAMERA_SOURCE=0
# CAMERA_SOURCE=http://192.168.1.x:8080/video
```

---

## Pipeline del sistema

```
Cámara (webcam local o IP Webcam)
        │
        ▼
OpenCV — captura frames
        │
        ▼
Haar Cascade — detecta rostro → bounding box
        │
        ▼
CNN multiclase (softmax) — clasifica: desconocido / luciano / paola
        │
        ├── CONOCIDO (cooldown 5 s)
        │       │
        │       ▼
        │   Pub/Sub → Raspberry Pi → brazo derecho
        │
        └── DESCONOCIDO (cooldown 30 s)
                │
                ▼
            Pub/Sub ──────────────────────────────────┐
                                                      ▼
            Cloud Storage ← sube imagen JPG     Raspberry Pi
                │                                     │
                ▼                                     ▼
            Firestore ← guarda URL + metadata   sacude cabeza (no)
                │                               levanta ambos brazos
                ▼
            Gmail ← envía email HTML con imagen embebida
```

### Diagrama de secuencia

**Flujo — persona conocida:**

```
PC                    Pub/Sub           Raspberry Pi       Arduino Shield
 │                       │                    │                    │
 │ detecta rostro        │                    │                    │
 │── rostro_detectado ──►│                    │                    │
 │                       │── entrega msg ────►│                    │
 │                       │                    │── S2,150\n ───────►│ brazo derecho arriba
 │                       │                    │   (3 s)            │
 │                       │                    │── S2,90\n ────────►│ posición neutra
```

**Flujo — persona desconocida:**

```
PC               Pub/Sub     Cloud Storage    Firestore    Gmail    Raspberry Pi    Arduino Shield
 │                  │               │              │          │           │                │
 │ detecta desc.    │               │              │          │           │                │
 │── sube imagen ──────────────────►│              │          │           │                │
 │                  │               │── URL ───────►│          │           │                │
 │── envía email ─────────────────────────────────────────────►│           │                │
 │── desconocido_detectado ────────►│              │          │           │                │
 │                  │── entrega ───────────────────────────────────────────►│                │
 │                  │               │              │          │           │── S0,60\n ────►│ cabeza izq
 │                  │               │              │          │           │── S0,120\n ───►│ cabeza der (×2)
 │                  │               │              │          │           │── S0,90\n ────►│ cabeza centro
 │                  │               │              │          │           │── S2,150\n ───►│ brazo der arriba
 │                  │               │              │          │           │── S6,150\n ───►│ brazo izq arriba
 │                  │               │              │          │           │   (3 s)        │
 │                  │               │              │          │           │── S2,90\n ────►│
 │                  │               │              │          │           │── S6,90\n ────►│ posición neutra
```
