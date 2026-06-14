"""
Subscriber de Pub/Sub que corre en la Raspberry Pi del RAPIRO.

Ejecutar en la Raspberry:
    python subscriber.py

Variables de entorno opcionales:
    RAPIRO_PORT                    — puerto serial (default: /dev/ttyAMA0)
    RAPIRO_BAUD                    — baud rate (default: 57600)
    GOOGLE_APPLICATION_CREDENTIALS — ruta al JSON de la cuenta de servicio
"""

from __future__ import annotations

import json
import logging
import os
import signal
import time
from pathlib import Path

from google.cloud import pubsub_v1

from rapiro_controller import RAPIROController


def _load_env_file() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_ID      = "project-ac5c4157-56cb-4920-98f"
SUBSCRIPTION_ID = "rapiro-robot-events-sub"

PUERTO_SERIAL = os.getenv("RAPIRO_PORT", "/dev/ttyAMA0")
BAUD_RATE     = int(os.getenv("RAPIRO_BAUD", "57600"))

if os.getenv("GOOGLE_APPLICATION_CREDENTIALS_RAPIRO"):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.environ["GOOGLE_APPLICATION_CREDENTIALS_RAPIRO"]

# Identidades que activan la accion M9 (personas conocidas)
IDENTIDADES_CONOCIDAS: set[str] = {"gonzalo", "luciano", "paola"}

SEGUNDOS_POSE = 3.0


def _procesar_mensaje(mensaje: pubsub_v1.subscriber.message.Message, robot: RAPIROController) -> None:
    try:
        data = json.loads(mensaje.data.decode("utf-8"))
        evento    = data.get("evento", "")
        identidad = data.get("identidad", "")
        confianza = data.get("confianza", 0.0)
        identidad_normalizada = str(identidad).strip().lower()

        if evento == "desconocido_detectado":
            logger.info("Desconocido detectado (%.0f%%) — sacudiendo cabeza", confianza)
            robot.luz_roja()
            robot.sacudir_cabeza(repeticiones=2)
            time.sleep(SEGUNDOS_POSE)
            robot.posicion_neutra()

        elif evento == "rostro_detectado" and identidad_normalizada in IDENTIDADES_CONOCIDAS:
            logger.info("Detectado: %s (%.0f%%)", identidad, confianza)
            robot.accion_m9()
            time.sleep(1.0)
            robot.luz_verde()
            time.sleep(SEGUNDOS_POSE)
            robot.posicion_neutra()

        mensaje.ack()

    except Exception as exc:
        logger.error("Error procesando mensaje: %s", exc)
        mensaje.nack()


def main() -> None:
    logger.info("Iniciando subscriber RAPIRO...")
    robot = RAPIROController(puerto=PUERTO_SERIAL, baud=BAUD_RATE)

    cliente = pubsub_v1.SubscriberClient()
    ruta_suscripcion = cliente.subscription_path(PROJECT_ID, SUBSCRIPTION_ID)

    flow_control = pubsub_v1.types.FlowControl(max_messages=1)
    streaming_pull = cliente.subscribe(
        ruta_suscripcion,
        callback=lambda m: _procesar_mensaje(m, robot),
        flow_control=flow_control,
    )
    logger.info("Escuchando en %s ...", ruta_suscripcion)

    def _apagar(sig: int, _frame: object) -> None:
        streaming_pull.cancel()
        robot.cerrar()

    signal.signal(signal.SIGINT, _apagar)
    signal.signal(signal.SIGTERM, _apagar)

    try:
        streaming_pull.result()
    except Exception as exc:
        logger.error("Subscriber detenido: %s", exc)
        robot.cerrar()


if __name__ == "__main__":
    main()
