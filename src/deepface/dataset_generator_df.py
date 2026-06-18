"""
Generador de dataset por persona para DeepFace / FaceNet.

Cada persona tiene su carpeta en data/deepface_db/<nombre>/
con archivos <nombre>_0000.jpg, <nombre>_0001.jpg, ...

Uso:
  python src/deepface/dataset_generator_df.py luciano
  python src/deepface/dataset_generator_df.py gonzalo --max-fotos 200

Controles en la ventana:
  Espacio o P  → pausar / reanudar
  Q            → salir
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import cv2

# Agregar src/capture al path para reutilizar módulos de captura
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(_PROJECT_ROOT / "src" / "capture"))

from stream_capture import connect_stream, prepare_frame

_DEFAULT_OUTPUT = _PROJECT_ROOT / "data" / "deepface_db"
_WINDOW = "Generador de Dataset DeepFace"
_FACE_SIZE = (224, 224)  # Tamaño óptimo para la mayoría de los modelos de DeepFace (ej. VGG-Face)

# Fases para el modo de 200 fotos con diversidad de poses y accesorios.
# Cada tupla: (fotos_acumuladas_al_terminar_fase, label_display, instruccion_terminal, label_pausa_pantalla)
_FASES_200: list[tuple[int, str, str, str]] = [
    (20,  "1/7 Sin accesorios — Frontal",
          "-> Fase 2/7: SEMI-PERFIL DERECHO. Girá la cabeza ~45° a la derecha y mantené esa posición.",
          "¡GIRÁ A LA DERECHA ~45°! Pulsá Espacio"),
    (40,  "2/7 Sin accesorios — Semi-perfil derecho",
          "-> Fase 3/7: SEMI-PERFIL IZQUIERDO. Girá la cabeza ~45° a la izquierda.",
          "¡GIRÁ A LA IZQUIERDA ~45°! Pulsá Espacio"),
    (60,  "3/7 Sin accesorios — Semi-perfil izquierdo",
          "-> Fase 4/7: ARRIBA / ABAJO. Incliná la cabeza ~30° hacia arriba y luego abajo, alternando.",
          "¡INCLINÁ ARRIBA Y ABAJO! Pulsá Espacio"),
    (80,  "4/7 Sin accesorios — Arriba / Abajo",
          "-> Fase 5/7: PONGASE LA GORRA. Variá los ángulos: frontal, lados, arriba/abajo.",
          "¡PONGASE LA GORRA! Pulsá Espacio"),
    (120, "5/7 Con Gorra — todos los ángulos",
          "-> Fase 6/7: PONGASE LA CAPUCHA. Variá los ángulos lentamente.",
          "¡PONGASE LA CAPUCHA! Pulsá Espacio"),
    (160, "6/7 Con Capucha — todos los ángulos",
          "-> Fase 7/7: PONGASE LOS ANTEOJOS. Variá los ángulos lentamente.",
          "¡PONGASE LOS ANTEOJOS! Pulsá Espacio"),
    (200, "7/7 Con Anteojos — todos los ángulos", "", ""),
]


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
    instruccion_fase: str,
) -> None:
    estado = "PAUSADO" if pausado else "CAPTURANDO"
    color_estado = (0, 165, 255) if pausado else (0, 255, 0)
    lineas = [
        f"Persona: {persona}",
        f"Fotos: {contador}/{objetivo}",
        f"Estado: {estado}",
        f"Fase: {instruccion_fase}",
        "Espacio/P: pausa | Q: salir",
    ]
    
    # Dibujar fondo negro semi-transparente arriba para mejorar legibilidad
    h, w = frame.shape[:2]
    cv2.rectangle(frame, (0, 0), (w, 165), (0, 0, 0), cv2.FILLED)
    
    # Agregar un borde de color en la ventana según el estado
    cv2.rectangle(frame, (0, 0), (w, 165), color_estado, 2)
    
    y = 28
    for i, texto in enumerate(lineas):
        color = color_estado if i == 2 else (255, 255, 255)
        # Si está pausado, pintar la instrucción en amarillo brillante
        if i == 3 and pausado:
            color = (0, 215, 255)
        cv2.putText(
            frame,
            texto,
            (15, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
            cv2.LINE_AA,
        )
        y += 28


def capturar_rostros(
    persona: str,
    *,
    max_fotos: int = 100,  # Con DeepFace se necesitan muchas menos fotos de referencia (default: 100)
    carpeta_salida: str | Path | None = None,
    intervalo_ms: int = 250,
    source: int | str | None = None,
) -> int:
    """
    Crea (o completa) la carpeta de una persona y guarda rostros recortados con mayor resolución.
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

    # Inicializar detector de rostro de MediaPipe
    import mediapipe as mp
    mp_face_detection = mp.solutions.face_detection
    face_detector = mp_face_detection.FaceDetection(model_selection=0, min_detection_confidence=0.5)

    print("Conectando cámara...")
    cap, src = connect_stream(source)
    print(f"Fuente: {src}")
    print(f"Carpeta: {ruta_persona}")
    print("\n--- INICIO DE CAPTURA DE ROSTROS ---")
    if max_fotos == 100:
        print("-> Fase 1/4: Rostro Normal (sin accesorios, gira la cabeza despacio)")
    if max_fotos == 200:
        print("-> Fase 1/7: FRONTAL sin accesorios. Mirá directo a la cámara.")
    print("Presione la tecla ESPACIO en la ventana de la cámara para INICIAR la captura.")

    contador = inicio
    guardadas_sesion = 0
    pausado = True
    ultima_guardada = 0.0
    intervalo_seg = intervalo_ms / 1000.0
    ultimo_pauso_fase = -1  # Rastrea a qué cantidad de fotos pausamos por cambio de fase
    _pausas_200 = {f[0] for f in _FASES_200[:-1]}

    try:
        while contador < objetivo:
            # Control automático de pausas de fase cuando max_fotos es exactamente 100
            if max_fotos == 100 and guardadas_sesion in (25, 50, 75) and ultimo_pauso_fase != guardadas_sesion:
                pausado = True
                ultimo_pauso_fase = guardadas_sesion

                inst_terminal = ""
                if guardadas_sesion == 25:
                    inst_terminal = "-> Fase 2/4: PONGASE LOS ANTEOJOS y gire levemente la cabeza."
                elif guardadas_sesion == 50:
                    inst_terminal = "-> Fase 3/4: PONGASE LA GORRA (asegure buena iluminación en la mirada)."
                elif guardadas_sesion == 75:
                    inst_terminal = "-> Fase 4/4: PONGASE LA CAPUCHA (foco en las facciones internas del rostro)."

                print(f"\n[PAUSA AUTOMÁTICA] Se completaron {guardadas_sesion} fotos de esta sesión.")
                print("==================================================")
                print("   PAUSA - CAMBIO DE FASE REQUERIDO")
                print("==================================================")
                print(inst_terminal)
                print("==================================================")
                print("Presione la tecla ESPACIO en la ventana de la cámara para continuar...")

            # Control automático de pausas para el modo de 200 fotos
            if max_fotos == 200 and guardadas_sesion in _pausas_200 and ultimo_pauso_fase != guardadas_sesion:
                pausado = True
                ultimo_pauso_fase = guardadas_sesion
                fase_actual = next(f for f in _FASES_200 if f[0] == guardadas_sesion)

                print(f"\n[PAUSA AUTOMÁTICA] Se completaron {guardadas_sesion} fotos de esta sesión.")
                print("==================================================")
                print("   PAUSA - CAMBIO DE FASE REQUERIDO")
                print("==================================================")
                print(fase_actual[2])
                print("==================================================")
                print("Presione la tecla ESPACIO en la ventana de la cámara para continuar...")

            # Determinar etiqueta de fase
            if max_fotos == 100:
                if guardadas_sesion < 25:
                    instruccion_fase = "1/4 Normal (Sin accesorios)"
                elif guardadas_sesion < 50:
                    instruccion_fase = "2/4 Con Anteojos"
                elif guardadas_sesion < 75:
                    instruccion_fase = "3/4 Con Gorra"
                else:
                    instruccion_fase = "4/4 Con Capucha"

                if pausado and guardadas_sesion in (25, 50, 75):
                    if guardadas_sesion == 25:
                        instruccion_fase = "¡PONTE LOS ANTEOJOS! y pulsa Espacio"
                    elif guardadas_sesion == 50:
                        instruccion_fase = "¡PONTE LA GORRA! y pulsa Espacio"
                    elif guardadas_sesion == 75:
                        instruccion_fase = "¡PONTE LA CAPUCHA! y pulsa Espacio"
            elif max_fotos == 200:
                fase_info = next((f for f in _FASES_200 if guardadas_sesion < f[0]), _FASES_200[-1])
                instruccion_fase = fase_info[1]

                if pausado and guardadas_sesion in _pausas_200:
                    fase_pausa = next(f for f in _FASES_200 if f[0] == guardadas_sesion)
                    instruccion_fase = fase_pausa[3]
            else:
                instruccion_fase = f"Personalizado ({guardadas_sesion}/{max_fotos})"

            ret, frame = cap.read()
            if not ret:
                print("[WARN] No se pudo leer frame.")
                break

            frame = prepare_frame(frame)
            frame_display = frame.copy()
            h_frame, w_frame, _ = frame.shape

            # Convertir a RGB ya que MediaPipe trabaja en este espacio de color
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = face_detector.process(rgb_frame)

            ahora = time.monotonic()
            puede_guardar = not pausado and (ahora - ultima_guardada) >= intervalo_seg

            if results.detections:
                for detection in results.detections:
                    bbox = detection.location_data.relative_bounding_box
                    x = int(bbox.xmin * w_frame)
                    y = int(bbox.ymin * h_frame)
                    w = int(bbox.width * w_frame)
                    h = int(bbox.height * h_frame)

                    # Forzar límites positivos dentro del frame
                    x = max(0, x)
                    y = max(0, y)
                    w = min(w, w_frame - x)
                    h = min(h, h_frame - y)

                    if w <= 0 or h <= 0:
                        continue

                    color = (0, 255, 0) if puede_guardar else (0, 200, 255)
                    cv2.rectangle(frame_display, (x, y), (x + w, y + h), color, 2)

                    if puede_guardar:
                        # Recortar con un pequeño margen para que DeepFace alinee mejor
                        offset_y = int(h * 0.1)
                        offset_x = int(w * 0.1)
                        y1 = max(0, y - offset_y)
                        y2 = min(h_frame, y + h + offset_y)
                        x1 = max(0, x - offset_x)
                        x2 = min(w_frame, x + w + offset_x)

                        rostro = frame[y1:y2, x1:x2]
                        if rostro.size > 0:
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
                instruccion_fase=instruccion_fase,
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
        face_detector.close()

    print(f"Listo: {guardadas_sesion} fotos nuevas en '{ruta_persona}'")
    print(f"Total de '{persona}': {contador} imágenes.")
    return guardadas_sesion


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Captura rostros y arma el dataset para DeepFace.",
    )
    parser.add_argument(
        "persona",
        nargs="?",
        default=None,
        help="Nombre de la persona (ej. luciano, paola).",
    )
    parser.add_argument(
        "--max-fotos",
        type=int,
        default=100,
        help="Cuántas fotos guardar en esta sesión (default: 100). Usar 200 activa el modo guiado de 7 fases con diversidad de poses y accesorios.",
    )
    parser.add_argument(
        "--intervalo-ms",
        type=int,
        default=250,
        help="Milisegundos entre capturas (default: 250)",
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
    print("Registro de dataset DeepFace — una carpeta por persona.")
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
