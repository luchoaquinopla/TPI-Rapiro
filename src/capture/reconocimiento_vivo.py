"""Live face recognition with Google Cloud Pub/Sub integration."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from google.cloud import pubsub_v1

from cloud_notifier import notify_unknown
from model_loader import load_modelo
from stream_capture import connect_stream, prepare_frame

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_MODEL_PATH_DEFAULT = _PROJECT_ROOT / "models" / "detection" / "modelo_tpi.keras"

PROJECT_ID = "project-ac5c4157-56cb-4920-98f"
TOPIC_ID = "rapiro-robot-events"

# debe coincidir con class_indices del entrenamiento: {desconocido:0, luciano:1, paola:2}
CLASSES = {0: "desconocido", 1: "luciano", 2: "paola"}

# segundos mínimos entre publicaciones para no saturar Pub/Sub ni el email
INITIAL_RECOGNITION_DELAY_S = 10.0  # tiempo de gracia al iniciar el programa para no enviar alertas por detecciones iniciales
COOLDOWN_GLOBAL_S = 25.0
COOLDOWN_KNOWN_S = 25.0
COOLDOWN_UNKNOWN_S = 60.0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Multiclass face recognition with Pub/Sub.")
    p.add_argument("--modelo", type=Path, default=_MODEL_PATH_DEFAULT)
    p.add_argument(
        "--umbral_confianza",
        type=float,
        default=0.60,
        help="Confianza mínima para aceptar una predicción como válida (0-1). "
             "Si la CNN no supera este umbral, el rostro se clasifica como desconocido.",
    )
    p.add_argument("--source", default=None)
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    umbral = args.umbral_confianza  # ← ahora sí se usa

    source = args.source
    if source is not None and str(source).isdigit():
        source = int(source)

    print(f"Umbral de confianza: {umbral:.0%}")

    # cliente que publica mensajes al topic de GCP
    print("Starting Pub/Sub client...")
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)

    # carga el modelo multiclase entrenado en Colab (desconocido / luciano / paola)
    print("Loading model...")
    modelo = load_modelo(args.modelo)

    # detector de rostros basado en Haar Cascade (incluido en OpenCV)
    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )

    print("Connecting camera...")
    cap, src = connect_stream(source)
    print(f"Source: {src}")
    print("Press Q to quit.")

    # timestamps del último envío para aplicar cooldown por tipo de evento
    ultimo_envio_global = 0.0
    ultimo_envio_conocido = 0.0
    ultimo_envio_desconocido = 0.0
    primer_envio_habilitado_en = time.time() + INITIAL_RECOGNITION_DELAY_S

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame = prepare_frame(frame)

            # Haar Cascade opera sobre escala de grises para detectar bounding boxes
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            rostros = face_cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(100, 100)
            )

            for (x, y, w, h) in rostros:
                rostro_recortado = frame[y: y + h, x: x + w]

                # preprocesamiento idéntico al usado en el entrenamiento
                img = cv2.resize(rostro_recortado, (96, 96))
                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                img_array = img.astype(np.float32) / 255.0
                img_array = np.expand_dims(img_array, axis=0)

                # el modelo devuelve 3 probabilidades (softmax) — argmax elige la clase ganadora
                prediccion = modelo.predict(img_array, verbose=0)
                clase_idx = int(np.argmax(prediccion[0]))
                confianza = float(prediccion[0][clase_idx])

                # ── FIX UMBRAL ──────────────────────────────────────────────
                # Si la confianza de la mejor clase no supera el umbral,
                # el sistema no se arriesga a confundir identidades:
                # fuerza la clasificación como desconocido.
                # Antes este argumento se parseaba pero nunca se aplicaba.
                if confianza < umbral:
                    clase_idx = 0  # clase desconocido
                # ────────────────────────────────────────────────────────────

                nombre = CLASSES[clase_idx]
                es_desconocido = clase_idx == 0
                confianza_pct = confianza * 100

                # rojo para desconocido, verde para conocido
                color = (0, 0, 255) if es_desconocido else (0, 255, 0)
                cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
                cv2.rectangle(frame, (x, y - 40), (x + w, y), color, cv2.FILLED)

                # si cayó por umbral bajo, lo indica en el overlay
                if es_desconocido and confianza < umbral and clase_idx == 0:
                    label = f"? {confianza_pct:.0f}%"
                else:
                    label = f"{nombre} {confianza_pct:.0f}%"

                cv2.putText(
                    frame,
                    label,
                    (x + 5, y - 12),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 255, 255),
                    2,
                )

                ahora = time.time()

                if ahora < primer_envio_habilitado_en:
                    restante = primer_envio_habilitado_en - ahora
                    cv2.putText(
                        frame,
                        f"Clasificando en {restante:.0f}s",
                        (x, y + h + 25),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        color,
                        2,
                    )
                    continue

                if (ahora - ultimo_envio_global) <= COOLDOWN_GLOBAL_S:
                    continue

                if es_desconocido:
                    if (ahora - ultimo_envio_desconocido) > COOLDOWN_UNKNOWN_S:
                        ultimo_envio_global = ahora
                        ultimo_envio_desconocido = ahora
                        payload = {
                            "evento": "desconocido_detectado",
                            "confianza": round(confianza_pct, 2),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                        try:
                            publisher.publish(topic_path, data=json.dumps(payload).encode())
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] Unknown detected — triggering alert.")
                        except Exception as e:
                            print(f"[ERROR] Pub/Sub: {e}")

                        # sube imagen a Cloud Storage, guarda en Firestore y manda email
                        notify_unknown(rostro_recortado, confianza_pct)
                else:
                    if (ahora - ultimo_envio_conocido) > COOLDOWN_KNOWN_S:
                        ultimo_envio_global = ahora
                        ultimo_envio_conocido = ahora
                        payload = {
                            "evento": "rostro_detectado",
                            "identidad": nombre,
                            "confianza": round(confianza_pct, 2),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                        try:
                            publisher.publish(topic_path, data=json.dumps(payload).encode())
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] Detected: {nombre}")
                        except Exception as e:
                            print(f"[ERROR] Pub/Sub: {e}")

            cv2.imshow("RAPIRO - Vision Artificial", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()