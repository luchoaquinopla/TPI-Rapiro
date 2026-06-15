"""
Reconocimiento facial en vivo utilizando DeepFace (FaceNet) e integración con GCP Pub/Sub.
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
import sys
import time
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

# Agregar src/capture al path para reutilizar módulos
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(_PROJECT_ROOT / "src" / "capture"))
os.environ.setdefault("DEEPFACE_HOME", str(_PROJECT_ROOT / "data" / "deepface_home"))

from cloud_notifier import notify_unknown
from google.cloud import pubsub_v1
from stream_capture import connect_stream, prepare_frame

# Intentar importar DeepFace para avisar al usuario si no lo tiene instalado
try:
    from deepface import DeepFace
except ImportError:
    print(
        "\n[WARN] La librería 'deepface' no está instalada en tu entorno virtual."
    )
    print("Por favor instálala antes de ejecutar este script ejecutando:")
    print("👉 pip install deepface\n")

PROJECT_ID = "project-ac5c4157-56cb-4920-98f"
TOPIC_ID = "rapiro-robot-events"

# Ruta de la base de datos de imágenes de referencia
_DB_PATH = _PROJECT_ROOT / "data" / "deepface_db"
_CACHE_PATH = _DB_PATH / "embeddings_cache.pkl"

# Configuración del modelo y métricas
MODEL_NAME = "ArcFace"  # Facenet utiliza 128 o 512 dimensiones
DISTANCE_METRIC = "cosine"
# Umbral recomendado de distancia de coseno para FaceNet en DeepFace:
# Distancias menores a este umbral indican que es la misma persona.
UMBRAL_RECOMENDADO = 0.40

# Segundos mínimos entre publicaciones para no saturar Pub/Sub ni el email (según tu última configuración)
COOLDOWN_KNOWN_S = 25.0
COOLDOWN_UNKNOWN_S = 60.0

INITIAL_DELAY_S = 7.0
IDENTIDADES_IGNORADAS: set[str] = {"paola"}

# Voting buffer: número de frames consecutivos para estabilizar la identidad
VOTING_BUFFER_SIZE = 10
# Mínimo de frames en el buffer antes de aplicar el voto (evita decisiones con muy pocos datos)
VOTING_MIN_FRAMES = 5


def compute_cosine_distance(a: list[float] | np.ndarray, b: list[float] | np.ndarray) -> float:
    """Calcula la distancia de coseno entre dos vectores."""
    a = np.array(a)
    b = np.array(b)
    dot_val = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 1.0
    return float(1.0 - (dot_val / (norm_a * norm_b)))


def cargar_o_generar_embeddings_cache(model_name: str) -> dict[str, list[list[float]]]:
    """
    Carga los embeddings de referencia desde el caché o los genera escaneando data/deepface_db/
    Retorna un diccionario: { "nombre_persona": [embedding1, embedding2, ...] }
    """
    if not _DB_PATH.exists():
        _DB_PATH.mkdir(parents=True, exist_ok=True)
        print(f"[INFO] Carpeta de base de datos creada en: {_DB_PATH}")
        print("Agrega carpetas por persona con fotos (ej: data/deepface_db/luciano/) y vuelve a iniciar.")
        return {}

    # Si el caché existe, cargarlo
    if _CACHE_PATH.exists():
        print(f"[INFO] Cargando embeddings de referencia desde caché ({_CACHE_PATH.name})...")
        try:
            with open(_CACHE_PATH, "rb") as f:
                cache_data = pickle.load(f)
                # Validar que sea para el mismo modelo
                if cache_data.get("model") == model_name:
                    embeddings = cache_data.get("embeddings", {})
                    if embeddings:
                        print(f"[OK] Cargados embeddings para: {list(embeddings.keys())}")
                        return embeddings
        except Exception as e:
            print(f"[WARN] Error al leer el archivo de caché: {e}. Se recalcularán.")

    # Generar embeddings escaneando el directorio
    print(f"[INFO] Generando nuevos embeddings usando el modelo {model_name}...")
    embeddings: dict[str, list[list[float]]] = {}
    formatos = (".jpg", ".jpeg", ".png")

    # Obtener todas las carpetas de personas
    subdirs = [d for d in _DB_PATH.iterdir() if d.is_dir()]
    if not subdirs:
        print("[WARN] No se encontraron subcarpetas de personas en data/deepface_db/")
        return {}

    for persona_dir in subdirs:
        nombre_persona = persona_dir.name.lower()
        image_paths = [p for p in persona_dir.iterdir() if p.suffix.lower() in formatos]
        
        if not image_paths:
            continue
            
        print(f" Procesando {nombre_persona} ({len(image_paths)} imágenes)...")
        persona_embeddings = []
        for img_path in image_paths:
            try:
                # DeepFace.represent extrae las características
                resp = DeepFace.represent(
                    img_path=str(img_path),
                    model_name=model_name,
                    enforce_detection=False
                )
                if resp and len(resp) > 0:
                    persona_embeddings.append(resp[0]["embedding"])
            except Exception as e:
                print(f"  [ERROR] No se pudo procesar {img_path.name}: {e}")

        if persona_embeddings:
            embeddings[nombre_persona] = persona_embeddings

    # Guardar en caché
    if embeddings:
        try:
            with open(_CACHE_PATH, "wb") as f:
                pickle.dump({"model": model_name, "embeddings": embeddings}, f)
            print(f"[OK] Caché guardado correctamente en {_CACHE_PATH.name}")
        except Exception as e:
            print(f"[WARN] No se pudo guardar el archivo caché: {e}")

    return embeddings


def identificar_rostro(
    face_img: np.ndarray,
    db_embeddings: dict[str, list[list[float]]],
    model_name: str,
    umbral: float
) -> tuple[str, float]:
    """
    Compara la imagen recortada del rostro con la base de datos de embeddings.
    Retorna (nombre_identificado, confianza_estimada).
    """
    if not db_embeddings:
        return "desconocido", 0.0

    try:
        # Extraer embedding del rostro de la cámara
        # Pasamos enforce_detection=False porque ya recortamos el rostro usando Haar Cascade
        resp = DeepFace.represent(
            img_path=face_img,
            model_name=model_name,
            enforce_detection=False
        )
        if not resp:
            return "desconocido", 0.0
        
        embedding_actual = resp[0]["embedding"]
    except Exception as e:
        # Si falla el represent de DeepFace
        return "desconocido", 0.0

    mejor_nombre = "desconocido"
    menor_distancia = 999.0

    # Comparar con cada persona y cada uno de sus embeddings de referencia
    for nombre, lista_ref in db_embeddings.items():
        for embedding_ref in lista_ref:
            dist = compute_cosine_distance(embedding_actual, embedding_ref)
            if dist < menor_distancia:
                menor_distancia = dist
                mejor_nombre = nombre

    # Evaluar contra el umbral de distancia
    if menor_distancia <= umbral:
        # Convertir distancia de coseno a un "porcentaje de confianza" aproximado para la UI
        # Una distancia de 0.0 es 100% de confianza. La distancia umbral es 0% de confianza relativa.
        confianza = max(0.0, (1.0 - (menor_distancia / umbral))) * 100
        return mejor_nombre, confianza
    else:
        # Si la menor distancia supera el umbral, se clasifica como desconocido
        # La confianza se calcula de forma inversa para indicar qué tan seguro está de que NO es conocido
        confianza_desconocido = min(100.0, (menor_distancia / umbral) * 50)
        return "desconocido", confianza_desconocido


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Reconocimiento facial en vivo usando DeepFace (FaceNet)")
    p.add_argument(
        "--umbral_distancia",
        type=float,
        default=UMBRAL_RECOMENDADO,
        help=f"Umbral de distancia de coseno (default: {UMBRAL_RECOMENDADO}). Valores menores son más estrictos."
    )
    p.add_argument("--source", default=None, help="Cámara física (índice) o dirección de stream IP.")
    p.add_argument(
        "--recargar_cache",
        action="store_true",
        help="Fuerza el re-escaneo del dataset y cálculo de embeddings borrando el archivo de caché anterior."
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    umbral = args.umbral_distancia
    source = args.source

    if source is not None and str(source).isdigit():
        source = int(source)

    if args.recargar_cache and _CACHE_PATH.exists():
        try:
            _CACHE_PATH.unlink()
            print("[INFO] Archivo de caché de embeddings eliminado.")
        except Exception as e:
            print(f"[ERROR] No se pudo borrar el caché: {e}")

    print(f"Modelo seleccionado: {MODEL_NAME}")
    print(f"Métrica de distancia: {DISTANCE_METRIC}")
    print(f"Umbral de aceptación (Distancia máxima): {umbral:.3f}")

    # Cargar embeddings de la base de datos
    db_embeddings = cargar_o_generar_embeddings_cache(MODEL_NAME)
    if not db_embeddings:
        print("[FATAL] No hay embeddings de referencia cargados. El script se detendrá.")
        return

    # Cliente Pub/Sub
    print("Starting Pub/Sub client...")
    try:
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)
        print(f"[OK] Pub/Sub configurado: {topic_path}")
    except Exception as e:
        print(f"[WARN] No se pudo inicializar cliente Pub/Sub: {e}. Se ejecutará en modo offline.")
        publisher = None
        topic_path = None

    # Inicializar detector de rostro de MediaPipe
    import mediapipe as mp
    mp_face_detection = mp.solutions.face_detection
    face_detector = mp_face_detection.FaceDetection(model_selection=0, min_detection_confidence=0.5)

    print("Connecting camera...")
    cap, src = connect_stream(source)
    print(f"Source: {src}")
    print("Press Q to quit.")

    ultimo_envio_conocido = 0.0
    ultimo_envio_desconocido = 0.0
    primer_envio_habilitado_en = time.time() + INITIAL_DELAY_S

    # Voting buffers por índice de detección (cara 0, cara 1, …)
    vote_buffers: dict[int, deque[str]] = {}

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame = prepare_frame(frame)
            h_frame, w_frame, _ = frame.shape

            # Convertir a RGB ya que MediaPipe trabaja en este espacio de color
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = face_detector.process(rgb_frame)

            # Limpiar buffers de caras que ya no están en escena
            n_detections = len(results.detections) if results.detections else 0
            for idx in list(vote_buffers.keys()):
                if idx >= n_detections:
                    del vote_buffers[idx]

            if results.detections:
                for face_idx, detection in enumerate(results.detections):
                    bbox = detection.location_data.relative_bounding_box
                    x = int(bbox.xmin * w_frame)
                    y = int(bbox.ymin * h_frame)
                    w = int(bbox.width * w_frame)
                    h = int(bbox.height * h_frame)

                    # Forzar límites positivos
                    x = max(0, x)
                    y = max(0, y)
                    w = min(w, w_frame - x)
                    h = min(h, h_frame - y)

                    if w <= 0 or h <= 0:
                        continue

                    # Extraer recorte de rostro
                    rostro_recortado = frame[y:y + h, x:x + w]
                    
                    # Identificar usando DeepFace
                    nombre, confianza_pct = identificar_rostro(
                        rostro_recortado, db_embeddings, MODEL_NAME, umbral
                    )

                    # Voting buffer: acumular resultados y tomar el más frecuente
                    if face_idx not in vote_buffers:
                        vote_buffers[face_idx] = deque(maxlen=VOTING_BUFFER_SIZE)
                    vote_buffers[face_idx].append(nombre)

                    buf = vote_buffers[face_idx]
                    if len(buf) >= VOTING_MIN_FRAMES:
                        nombre = Counter(buf).most_common(1)[0][0]

                    es_desconocido = (nombre == "desconocido")
                    color = (0, 0, 255) if es_desconocido else (0, 255, 0)
                    
                    # Dibujar bounding box y etiqueta
                    cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
                    cv2.rectangle(frame, (x, y - 40), (x + w, y), color, cv2.FILLED)
                    
                    label = f"{nombre.capitalize()} {confianza_pct:.0f}%"
                    cv2.putText(
                        frame,
                        label,
                        (x + 5, y - 12),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (255, 255, 255),
                        1,
                        cv2.LINE_AA
                    )

                    # Publicación a Pub/Sub y alertas en la nube con Cooldowns
                    ahora = time.time()

                    if ahora < primer_envio_habilitado_en:
                        restante = primer_envio_habilitado_en - ahora
                        cv2.putText(frame, f"Iniciando en {restante:.0f}s", (x, y + h + 25),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                        continue

                    if nombre in IDENTIDADES_IGNORADAS:
                        continue

                    if not es_desconocido:
                        # Persona Conocida
                        if ahora - ultimo_envio_conocido >= COOLDOWN_KNOWN_S:
                            ultimo_envio_conocido = ahora
                            payload = {
                                "evento": "rostro_detectado",
                                "identidad": nombre,
                                "confianza": round(confianza_pct, 2),
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            }
                            if publisher and topic_path:
                                try:
                                    publisher.publish(topic_path, data=json.dumps(payload).encode())
                                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Pub/Sub sent: Detected {nombre} ({confianza_pct:.1f}%)")
                                except Exception as e:
                                    print(f"[ERROR] Pub/Sub publish: {e}")
                            else:
                                print(f"[OFFLINE] Detected: {nombre} ({confianza_pct:.1f}%)")
                    else:
                        # Persona Desconocida
                        if ahora - ultimo_envio_desconocido >= COOLDOWN_UNKNOWN_S:
                            ultimo_envio_desconocido = ahora
                            payload = {
                                "evento": "desconocido_detectado",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            }
                            
                            # Alerta en la nube (Cloud Storage + Firestore + Gmail)
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] Unknown face detected! Sending cloud alert...")
                            notify_unknown(rostro_recortado, confianza_pct)
                            
                            if publisher and topic_path:
                                try:
                                    publisher.publish(topic_path, data=json.dumps(payload).encode())
                                    print(f"[OK] Pub/Sub sent: Desconocido detectado")
                                except Exception as e:
                                    print(f"[ERROR] Pub/Sub publish: {e}")

            cv2.imshow("RAPIRO - DeepFace Vision", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
        face_detector.close()


if __name__ == "__main__":
    main()
