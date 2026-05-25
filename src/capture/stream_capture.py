"""
Pipeline de captura de video.

Soporta dos fuentes:
  - Webcam local  → CAMERA_SOURCE=0   (índice entero)
  - IP Webcam WiFi → CAMERA_SOURCE=http://192.168.x.x:8080/video

Configurar en .env o pasar el valor directamente a connect_stream().
"""

import os

import cv2
import numpy as np
from dotenv import load_dotenv

load_dotenv()

_STREAM_TIMEOUT_MS = 5000  # tiempo máximo para abrir un stream IP


_WIN_BACKENDS = [cv2.CAP_MSMF, cv2.CAP_DSHOW, cv2.CAP_ANY]


def detect_camera_index(max_index: int = 4) -> int:
    """Prueba índices 0-max_index con múltiples backends y retorna el primero disponible."""
    for idx in range(max_index + 1):
        for backend in _WIN_BACKENDS:
            try:
                cap = cv2.VideoCapture(idx, backend)
                if cap.isOpened():
                    ret, _ = cap.read()
                    cap.release()
                    if ret:
                        return idx
                else:
                    cap.release()
            except Exception:
                pass
    raise RuntimeError("No se encontró ninguna cámara local (índices 0-4).")


def _resolve_source(source: int | str | None) -> int | str:
    """
    Resuelve la fuente de video en este orden:
      1. Argumento explícito
      2. Variable de entorno CAMERA_SOURCE
      3. Auto-detección de webcam local
    """
    if source is None:
        source = os.getenv("CAMERA_SOURCE")

    if source is None:
        return detect_camera_index()

    # Si es string y empieza con http → stream IP
    if isinstance(source, str):
        if source.lower().startswith("http"):
            return source
        # Si es string numérico → tratar como índice
        if source.isdigit():
            return int(source)

    return source


def connect_stream(source: int | str | None = None) -> tuple[cv2.VideoCapture, int | str]:
    """
    Abre la fuente de video (webcam local o stream IP).
    Retorna (VideoCapture, fuente_usada).

    Ejemplos:
        cap, src = connect_stream()                              # auto-detecta
        cap, src = connect_stream(0)                            # webcam índice 0
        cap, src = connect_stream("http://192.168.1.5:8080/video")  # IP Webcam
    """
    resolved = _resolve_source(source)

    if isinstance(resolved, str):
        cap = cv2.VideoCapture(resolved)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, _STREAM_TIMEOUT_MS)
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, _STREAM_TIMEOUT_MS)
    else:
        cap = None
        for backend in _WIN_BACKENDS:
            try:
                cap = cv2.VideoCapture(resolved, backend)
                if cap.isOpened():
                    break
                cap.release()
                cap = None
            except Exception:
                cap = None

    if cap is None or not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir la fuente de video: {resolved!r}")

    # Descarta los primeros frames — la cámara necesita unos ciclos para inicializar.
    for _ in range(10):
        cap.read()

    return cap, resolved


def preprocess_frame(frame: np.ndarray) -> np.ndarray:
    """Convierte BGR→RGB y normaliza a [0, 1]."""
    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return frame.astype(np.float32) / 255.0


def _apply_rotation(frame: np.ndarray) -> np.ndarray:
    """Rota 90° si el frame está en horizontal (ancho > alto)."""
    h, w = frame.shape[:2]
    if w > h:
        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    return frame


def capture_loop(source: int | str | None = None, window_name: str = "RAPIRO Preview") -> None:
    """
    Loop de captura con preview.
    Muestra fuente y dimensiones en pantalla. Presioná 'q' para salir.
    """
    cap, src = connect_stream(source)
    src_label = f"http" if isinstance(src, str) else f"cam:{src}"

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print(f"[WARN] No se pudo leer frame de '{src}'.")
                break

            frame = _apply_rotation(frame)
            h, w = frame.shape[:2]

            label = f"{src_label}  |  {w}x{h}"
            cv2.putText(frame, label, (10, 25), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, (0, 255, 0), 2, cv2.LINE_AA)

            cv2.imshow(window_name, frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


def capture_single_frame(source: int | str | None = None) -> np.ndarray:
    """
    Captura un único frame (con rotación aplicada) y lo retorna en BGR.
    """
    cap, src = connect_stream(source)
    try:
        ret, frame = cap.read()
        if not ret:
            raise RuntimeError(f"No se pudo capturar frame de '{src}'.")
        return _apply_rotation(frame)
    finally:
        cap.release()

if __name__ == "__main__":
    capture_loop()