"""
Generador de dataset para la clase DESCONOCIDO.

Captura 120 imágenes por persona y las guarda en data/own_dataset/desconocido/.
Guía al usuario con instrucciones de iluminación y poses en pantalla.

Uso:
  python src/desconocidos/dataset_generator_desconocido.py --persona "Juan"
  python src/desconocidos/dataset_generator_desconocido.py --persona "Maria" --source 1
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import cv2

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(_PROJECT_ROOT / "src" / "capture"))

from stream_capture import connect_stream, prepare_frame

_OUTPUT_DIR = _PROJECT_ROOT / "data" / "own_dataset" / "desconocido"
_WINDOW = "Dataset Desconocido"
_FACE_SIZE = (96, 96)
_MAX_FOTOS = 120
_INTERVALO_MS = 250

# 4 fases de 30 fotos cada una.
# (limite, label_pantalla, instruccion_pose, instruccion_terminal, label_pausa)
_FASES: list[tuple[int, str, str, str, str]] = [
    (
        30,
        "FASE 1/4 — FRONTAL",
        "Mira directo a la camara. Expresion natural.",
        "-> FASE 2/4: SEMI-PERFIL DERECHO. Gira la cabeza ~45 grados a la derecha.",
        "GIRA A LA DERECHA ~45 grados! Pulsa Espacio",
    ),
    (
        60,
        "FASE 2/4 — SEMI-PERFIL DERECHO",
        "Manten la cabeza girada ~45 grados a la derecha.",
        "-> FASE 3/4: SEMI-PERFIL IZQUIERDO. Gira la cabeza ~45 grados a la izquierda.",
        "GIRA A LA IZQUIERDA ~45 grados! Pulsa Espacio",
    ),
    (
        90,
        "FASE 3/4 — SEMI-PERFIL IZQUIERDO",
        "Manten la cabeza girada ~45 grados a la izquierda.",
        "-> FASE 4/4: ARRIBA / ABAJO. Inclina la cabeza ~30 grados arriba y luego abajo, alternando.",
        "INCLINA ARRIBA Y ABAJO! Pulsa Espacio",
    ),
    (
        120,
        "FASE 4/4 — ARRIBA / ABAJO",
        "Inclina la cabeza ~30 grados arriba y luego abajo, alternando lento.",
        "",
        "",
    ),
]

_PAUSAS = {f[0] for f in _FASES[:-1]}

_CONSEJOS_LUZ = [
    "LUZ: que este delante tuyo, no detras",
    "SOMBRAS: evita sombras en la cara",
    "CAMARA: a la altura de los ojos",
    "DISTANCIA: ~50-80 cm de la camara",
]


def _siguiente_indice(carpeta: Path) -> int:
    patron = re.compile(r"^desconocido_(\d+)$")
    max_idx = -1
    for path in carpeta.glob("desconocido_*.jpg"):
        m = patron.match(path.stem)
        if m:
            max_idx = max(max_idx, int(m.group(1)))
    return max_idx + 1


def _get_fase(guardadas: int) -> tuple[int, str, str, str, str]:
    return next((f for f in _FASES if guardadas < f[0]), _FASES[-1])


def _draw_overlay(
    frame: cv2.Mat,
    *,
    persona: str,
    guardadas: int,
    objetivo: int,
    pausado: bool,
    fase: tuple[int, str, str, str, str],
    pausa_activa: bool,
) -> None:
    h, w = frame.shape[:2]

    # Panel superior — info de fase y pose
    cv2.rectangle(frame, (0, 0), (w, 110), (0, 0, 0), cv2.FILLED)
    color_estado = (0, 165, 255) if pausado else (0, 255, 0)
    cv2.rectangle(frame, (0, 0), (w, 110), color_estado, 2)

    estado_txt = "PAUSADO" if pausado else "CAPTURANDO"
    label_fase = fase[4] if pausa_activa else fase[1]
    instruccion = fase[4] if pausa_activa else fase[2]

    lineas_sup = [
        f"Persona: {persona}   Fotos: {guardadas}/{objetivo}   {estado_txt}",
        label_fase,
        instruccion,
        "ESPACIO: pausar/reanudar  |  Q: salir",
    ]
    y = 22
    for i, txt in enumerate(lineas_sup):
        color = color_estado if i == 0 else (0, 215, 255) if (pausa_activa and i == 1) else (255, 255, 255)
        cv2.putText(frame, txt, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
        y += 24

    # Panel inferior — consejos de iluminación (siempre visibles)
    panel_h = 20 + len(_CONSEJOS_LUZ) * 22
    cv2.rectangle(frame, (0, h - panel_h), (w, h), (20, 20, 20), cv2.FILLED)
    cv2.rectangle(frame, (0, h - panel_h), (w, h), (100, 100, 100), 1)
    cv2.putText(frame, "CONSEJOS DE ILUMINACION:", (10, h - panel_h + 16),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1, cv2.LINE_AA)
    for i, consejo in enumerate(_CONSEJOS_LUZ):
        cv2.putText(frame, consejo, (10, h - panel_h + 16 + (i + 1) * 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 220, 200), 1, cv2.LINE_AA)


def capturar(persona: str, source: int | str | None = None) -> int:
    persona = persona.strip()
    if not persona:
        raise ValueError("El nombre no puede estar vacío.")

    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    inicio = _siguiente_indice(_OUTPUT_DIR)
    objetivo = inicio + _MAX_FOTOS

    if inicio > 0:
        print(f"Ya hay {inicio} fotos en 'desconocido/'. Continuando desde {inicio:04d}.")

    import mediapipe as mp
    mp_face = mp.solutions.face_detection
    detector = mp_face.FaceDetection(model_selection=0, min_detection_confidence=0.5)

    print("Conectando camara...")
    cap, src = connect_stream(source)
    print(f"Fuente: {src}")
    print(f"Salida: {_OUTPUT_DIR}")
    print(f"\nPersona: {persona}")
    print("-> FASE 1/4: FRONTAL. Mira directo a la camara con expresion natural.")
    print("Pulsa ESPACIO en la ventana para iniciar la captura.")

    contador = inicio
    guardadas = 0
    pausado = True
    ultima_guardada = 0.0
    intervalo_seg = _INTERVALO_MS / 1000.0
    ultimo_pauso = -1

    try:
        while contador < objetivo:
            # Auto-pausa al cambiar de fase
            if guardadas in _PAUSAS and ultimo_pauso != guardadas:
                pausado = True
                ultimo_pauso = guardadas
                fase_actual = _get_fase(guardadas)
                print(f"\n[PAUSA] {guardadas} fotos completadas.")
                print("=" * 50)
                print(fase_actual[3])
                print("=" * 50)
                print("Pulsa ESPACIO para continuar...")

            fase = _get_fase(guardadas)
            pausa_activa = pausado and guardadas in _PAUSAS

            ret, frame = cap.read()
            if not ret:
                print("[WARN] No se pudo leer frame.")
                break

            frame = prepare_frame(frame)
            display = frame.copy()
            h_frame, w_frame = frame.shape[:2]

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = detector.process(rgb)

            ahora = time.monotonic()
            puede_guardar = not pausado and (ahora - ultima_guardada) >= intervalo_seg

            if results.detections:
                for detection in results.detections:
                    bbox = detection.location_data.relative_bounding_box
                    x = max(0, int(bbox.xmin * w_frame))
                    y = max(0, int(bbox.ymin * h_frame))
                    w = min(int(bbox.width * w_frame), w_frame - x)
                    h = min(int(bbox.height * h_frame), h_frame - y)

                    if w <= 0 or h <= 0:
                        continue

                    color_bbox = (0, 255, 0) if puede_guardar else (0, 200, 255)
                    cv2.rectangle(display, (x, y), (x + w, y + h), color_bbox, 2)

                    if puede_guardar:
                        ox = int(w * 0.1)
                        oy = int(h * 0.1)
                        x1 = max(0, x - ox)
                        y1 = max(0, y - oy)
                        x2 = min(w_frame, x + w + ox)
                        y2 = min(h_frame, y + h + oy)

                        rostro = frame[y1:y2, x1:x2]
                        if rostro.size > 0:
                            rostro = cv2.resize(rostro, _FACE_SIZE)
                            nombre_arch = _OUTPUT_DIR / f"desconocido_{contador:04d}.jpg"
                            cv2.imwrite(str(nombre_arch), rostro)
                            contador += 1
                            guardadas += 1
                            ultima_guardada = ahora
                            puede_guardar = False
                            if contador >= objetivo:
                                break

            _draw_overlay(
                display,
                persona=persona,
                guardadas=guardadas,
                objetivo=_MAX_FOTOS,
                pausado=pausado,
                fase=fase,
                pausa_activa=pausa_activa,
            )

            cv2.imshow(_WINDOW, display)
            tecla = cv2.waitKey(1) & 0xFF
            if tecla in (ord("q"), ord("Q")):
                break
            if tecla in (ord(" "), ord("p"), ord("P")):
                pausado = not pausado
                print(f"Captura {'pausada' if pausado else 'reanudada'} ({guardadas}/{_MAX_FOTOS})")

    finally:
        cap.release()
        cv2.destroyAllWindows()
        detector.close()

    print(f"\nListo: {guardadas} fotos guardadas en '{_OUTPUT_DIR}'")
    print(f"Total en 'desconocido/': {contador} imagenes.")
    return guardadas


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Captura 120 fotos de una persona desconocida.")
    p.add_argument("--persona", required=True, help="Nombre o etiqueta de la persona (solo para mostrar en pantalla).")
    p.add_argument("--source", default=None, help="Cámara (índice o URL). Default: CAMERA_SOURCE del .env.")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    source = args.source
    if source is not None and str(source).isdigit():
        source = int(source)
    capturar(args.persona, source=source)
