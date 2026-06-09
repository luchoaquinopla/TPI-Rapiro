"""
Reconocimiento en vivo con integración a Google Cloud Pub/Sub.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from google.cloud import pubsub_v1

from model_loader import load_modelo_binario
from stream_capture import connect_stream, prepare_frame

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_RUTA_PESOS_DEFAULT = _PROJECT_ROOT / "models" / "detection" / "modelo_binario_pesos.weights.h5"

# Configuración de Google Cloud
PROJECT_ID = "project-ac5c4157-56cb-4920-98f"
TOPIC_ID = "rapiro-robot-events"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Clasificación binaria en vivo con Pub/Sub.")
    p.add_argument("--pesos", type=Path, default=_RUTA_PESOS_DEFAULT)
    p.add_argument("--umbral", type=float, default=0.5)
    p.add_argument("--source", default=None)
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    source = args.source
    if source is not None and str(source).isdigit():
        source = int(source)

    print("Iniciando cliente de Pub/Sub...")
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)

    print("Cargando arquitectura y pesos...")
    modelo = load_modelo_binario(args.pesos)
    
    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    nombres = {0: "Luciano", 1: "Paola"}
    umbral = args.umbral

    print("Conectando cámara...")
    cap, src = connect_stream(source)
    print(f"Fuente: {src}")
    print("Q para salir.")

    ultimo_envio = 0.0
    cooldown_segundos = 5.0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame = prepare_frame(frame)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            rostros = face_cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(100, 100)
            )

            for (x, y, w, h) in rostros:
                rostro_recortado = frame[y : y + h, x : x + w]

                img = cv2.resize(rostro_recortado, (96, 96))
                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                img_array = img.astype(np.float32) / 255.0
                img_array = np.expand_dims(img_array, axis=0)

                prediccion = modelo.predict(img_array, verbose=0)
                probabilidad = float(prediccion[0][0])

                if probabilidad < umbral:
                    nombre = nombres[0]
                    confianza = (1 - probabilidad) * 100
                    color = (0, 255, 0)
                else:
                    nombre = nombres[1]
                    confianza = probabilidad * 100
                    color = (255, 0, 0)

                cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
                cv2.rectangle(frame, (x, y - 40), (x + w, y), color, cv2.FILLED)
                texto = f"{nombre} {confianza:.0f}%"
                cv2.putText(frame, texto, (x + 5, y - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

                ahora = time.time()
                if (ahora - ultimo_envio) > cooldown_segundos:
                    payload = {
                        "evento": "rostro_detectado",
                        "identidad": nombre,
                        "confianza": round(confianza, 2),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                    data_bytes = json.dumps(payload).encode("utf-8")
                    
                    try:
                        publisher.publish(topic_path, data=data_bytes)
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] ☁️ ¡Alerta enviada a Pub/Sub! Detectado: {nombre}")
                        ultimo_envio = ahora
                    except Exception as e:
                        print(f"Error al enviar a la nube: {e}")

            cv2.imshow("RAPIRO - Vision Artificial", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()