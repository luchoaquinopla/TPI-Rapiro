"""
Generador de dataset por persona.

Cada persona tiene su carpeta en data/own_dataset/<nombre>/
con archivos <nombre>_0000.jpg, <nombre>_0001.jpg, ...

Uso:
  python dataset_generator.py luciano
  python dataset_generator.py gonzalo --max-fotos 200

Controles en la ventana:
  Espacio o P  → pausar / reanudar
  Q            → salir
"""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

import cv2

from stream_capture import connect_stream, prepare_frame

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUTPUT = _PROJECT_ROOT / "data" / "own_dataset"

_WINDOW = "Generador de Dataset TPI"
_FACE_SIZE = (96, 96)


def _siguiente_indice(carpeta: Path, persona: str) -> int:
    """Próximo número para {persona}_NNNN.jpg según lo ya guardado."""
    patron = re.compile(rf"^{re.escape(persona)}_(\d+)$")
    max_idx = -1
    for path in carpeta.glob(f"{persona}_*.jpg"):
        match = patron.match(path.stem)
        if match:
            max_idx = max(max_idx, int(match.group(1)))
    return max_idx + 1


def _draw_overlay(
    frame,
    *,
    persona: str,
    contador: int,
    objetivo: int,
    pausado: bool,
    intervalo_ms: int,
) -> None:
    estado = "PAUSADO" if pausado else "CAPTURANDO"
    color_estado = (0, 165, 255) if pausado else (0, 255, 0)
    lineas = [
        f"Persona: {persona}",
        f"Fotos: {contador}/{objetivo}",
        f"Estado: {estado}",
        f"Intervalo: {intervalo_ms} ms",
        "Espacio/P: pausa | Q: salir",
    ]
    y = 28
    for i, texto in enumerate(lineas):
        color = color_estado if i == 2 else (255, 255, 255)
        cv2.putText(
            frame,
            texto,
            (10, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            color,
            2,
            cv2.LINE_AA,
        )
        y += 28


def capturar_rostros(
    persona: str,
    *,
    max_fotos: int = 400,
    carpeta_salida: str | Path | None = None,
    intervalo_ms: int = 200,
    source: int | str | None = None,
) -> int:
    """
    Crea (o completa) la carpeta de una persona y guarda rostros recortados.

    Estructura:
        data/own_dataset/luciano/luciano_0000.jpg
        data/own_dataset/gonzalo/gonzalo_0000.jpg
    """
    persona = persona.strip().lower()
    if not persona:
        raise ValueError("El nombre de la persona no puede estar vacío.")

    base = Path(carpeta_salida) if carpeta_salida else _DEFAULT_OUTPUT
    ruta_persona = base / persona
    ruta_persona.mkdir(parents=True, exist_ok=True)

    inicio = _siguiente_indice(ruta_persona, persona)
    objetivo = inicio + max_fotos
    if inicio > 0:
        print(f"Ya hay {inicio} fotos de '{persona}'; continuando desde {inicio:04d}.")

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )

    print("Conectando cámara...")
    cap, src = connect_stream(source)
    print(f"Fuente: {src}")
    print(f"Carpeta: {ruta_persona}")
    print("Espacio o P: pausar/reanudar | Q: salir")

    contador = inicio
    guardadas_sesion = 0
    pausado = False
    ultima_guardada = 0.0
    intervalo_seg = intervalo_ms / 1000.0

    try:
        while contador < objetivo:
            ret, frame = cap.read()
            if not ret:
                print("[WARN] No se pudo leer frame.")
                break

            frame = prepare_frame(frame)
            frame_display = frame.copy()
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            ahora = time.monotonic()
            puede_guardar = not pausado and (ahora - ultima_guardada) >= intervalo_seg

            rostros = face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(100, 100),
            )

            for (x, y, w, h) in rostros:
                color = (0, 255, 0) if puede_guardar else (0, 200, 255)
                cv2.rectangle(frame_display, (x, y), (x + w, y + h), color, 2)

                if puede_guardar:
                    rostro = frame[y : y + h, x : x + w]
                    rostro = cv2.resize(rostro, _FACE_SIZE)
                    nombre_archivo = ruta_persona / f"{persona}_{contador:04d}.jpg"
                    cv2.imwrite(str(nombre_archivo), rostro)
                    contador += 1
                    guardadas_sesion += 1
                    ultima_guardada = ahora
                    puede_guardar = False
                    if contador >= objetivo:
                        break

            _draw_overlay(
                frame_display,
                persona=persona,
                contador=contador,
                objetivo=objetivo,
                pausado=pausado,
                intervalo_ms=intervalo_ms,
            )

            cv2.imshow(_WINDOW, frame_display)
            tecla = cv2.waitKey(1) & 0xFF

            if tecla in (ord("q"), ord("Q")):
                break
            if tecla in (ord(" "), ord("p"), ord("P")):
                pausado = not pausado
                estado = "pausada" if pausado else "reanudada"
                print(f"Captura {estado} ({contador}/{objetivo})")
    finally:
        cap.release()
        cv2.destroyAllWindows()

    print(f"Listo: {guardadas_sesion} fotos nuevas en '{ruta_persona}'")
    print(f"Total de '{persona}': {contador} imágenes.")
    return guardadas_sesion


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Captura rostros y arma el dataset en una carpeta por persona.",
    )
    parser.add_argument(
        "persona",
        nargs="?",
        default=None,
        help="Nombre de la persona (ej. luciano, gonzalo). Crea data/own_dataset/<nombre>/",
    )
    parser.add_argument(
        "--max-fotos",
        type=int,
        default=400,
        help="Cuántas fotos guardar en esta sesión (default: 400)",
    )
    parser.add_argument(
        "--intervalo-ms",
        type=int,
        default=200,
        help="Milisegundos entre capturas (default: 200)",
    )
    parser.add_argument(
        "--salida",
        type=Path,
        default=None,
        help=f"Carpeta base (default: {_DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Cámara (índice o URL). Si no se indica, usa CAMERA_SOURCE del .env",
    )
    return parser.parse_args()


def _resolver_persona(persona: str | None) -> str:
    if persona and persona.strip():
        return persona.strip()
    print("Registro de dataset — una carpeta por persona.")
    while True:
        nombre = input("Nombre de la persona: ").strip()
        if nombre:
            return nombre
        print("El nombre no puede estar vacío.")


if __name__ == "__main__":
    args = _parse_args()
    source = args.source
    if source is not None and str(source).isdigit():
        source = int(source)

    capturar_rostros(
        _resolver_persona(args.persona),
        max_fotos=args.max_fotos,
        carpeta_salida=args.salida,
        intervalo_ms=args.intervalo_ms,
        source=source,
    )
