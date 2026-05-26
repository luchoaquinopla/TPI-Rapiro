"""
Reconocimiento en vivo con el mismo preprocesamiento que dataset_generator
(espejo + rotación vía prepare_frame), para que coincida con el entrenamiento.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

from model_loader import load_modelo_binario
from stream_capture import connect_stream, prepare_frame

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_RUTA_PESOS_DEFAULT = _PROJECT_ROOT / "models" / "detection" / "modelo_binario_pesos.weights.h5"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Clasificación binaria en vivo (Luciano / Paola).")
    p.add_argument(
        "--pesos",
        type=Path,
        default=_RUTA_PESOS_DEFAULT,
        help="Ruta al .weights.h5 o .h5 de pesos",
    )
    p.add_argument(
        "--umbral",
        type=float,
        default=0.5,
        help="Umbral sigmoid: < umbral → clase 0, ≥ umbral → clase 1 (default 0.5)",
    )
    p.add_argument(
        "--source",
        default=None,
        help="Cámara (número o URL). Por defecto: CAMERA_SOURCE del .env o auto-detección",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    source = args.source
    if source is not None and str(source).isdigit():
        source = int(source)

    print("Cargando arquitectura y pesos...")
    modelo = load_modelo_binario(args.pesos)
    print("Modelo cargado correctamente.")

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    # Misma convención que en el script original (verificar en Colab si invertís carpetas)
    nombres = {0: "Luciano", 1: "Paola"}
    umbral = args.umbral

    print("Conectando cámara (mismo pipeline que dataset_generator)...")
    cap, src = connect_stream(source)
    print(f"Fuente: {src}")
    print("Q para salir. Si falla mucho: iluminación parecida al dataset, cara frontal, probá --umbral 0.45")

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
                texto = f"{nombre} {confianza:.0f}%  (p={probabilidad:.2f})"
                cv2.putText(
                    frame,
                    texto,
                    (x + 5, y - 12),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 255, 255),
                    2,
                )

            cv2.imshow("RAPIRO - Vision Artificial", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
