"""
Subscriber de Pub/Sub por REST para Raspberry Pi.

Evita google-cloud-pubsub/grpc, util cuando grpcio falla en Python 3.13
en Raspberry Pi armv7l con "Bus error".
"""

from __future__ import annotations

import base64
import json
import logging
import os
import signal
import time
from pathlib import Path

import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account

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

PROJECT_ID = "project-ac5c4157-56cb-4920-98f"
SUBSCRIPTION_ID = "rapiro-robot-events-sub"

PUERTO_SERIAL = os.getenv("RAPIRO_PORT", "/dev/ttyAMA0")
BAUD_RATE = int(os.getenv("RAPIRO_BAUD", "57600"))

if os.getenv("GOOGLE_APPLICATION_CREDENTIALS_RAPIRO"):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.environ["GOOGLE_APPLICATION_CREDENTIALS_RAPIRO"]

IDENTIDADES_CONOCIDAS: set[str] = {"gonzalo", "luciano", "paola"}
SEGUNDOS_POSE = 3.0
SCOPES = ("https://www.googleapis.com/auth/pubsub",)
BASE_URL = "https://pubsub.googleapis.com/v1"

_running = True


def _credentials() -> service_account.Credentials:
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials_path:
        raise RuntimeError("Falta GOOGLE_APPLICATION_CREDENTIALS en el entorno o .env")

    path = Path(credentials_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path

    return service_account.Credentials.from_service_account_file(
        str(path),
        scopes=SCOPES,
    )


def _headers(credentials: service_account.Credentials) -> dict[str, str]:
    if not credentials.valid:
        credentials.refresh(Request())
    return {"Authorization": f"Bearer {credentials.token}"}


def _subscription_path() -> str:
    return f"projects/{PROJECT_ID}/subscriptions/{SUBSCRIPTION_ID}"


def _pull(credentials: service_account.Credentials) -> list[dict]:
    url = f"{BASE_URL}/{_subscription_path()}:pull"
    response = requests.post(
        url,
        headers=_headers(credentials),
        json={"maxMessages": 1},
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("receivedMessages", [])


def _ack(credentials: service_account.Credentials, ack_id: str) -> None:
    url = f"{BASE_URL}/{_subscription_path()}:acknowledge"
    response = requests.post(
        url,
        headers=_headers(credentials),
        json={"ackIds": [ack_id]},
        timeout=15,
    )
    response.raise_for_status()


def _nack(credentials: service_account.Credentials, ack_id: str) -> None:
    url = f"{BASE_URL}/{_subscription_path()}:modifyAckDeadline"
    response = requests.post(
        url,
        headers=_headers(credentials),
        json={"ackIds": [ack_id], "ackDeadlineSeconds": 0},
        timeout=15,
    )
    response.raise_for_status()


def _procesar_payload(data: dict, robot: RAPIROController) -> None:
    evento = data.get("evento", "")
    identidad = data.get("identidad", "")
    confianza = data.get("confianza", 0.0)
    identidad_normalizada = str(identidad).strip().lower()

    if evento == "desconocido_detectado":
        logger.info("Desconocido detectado (%.0f%%) - sacudiendo cabeza", confianza)
        robot.luz_roja()
        robot.sacudir_cabeza(repeticiones=2)
        time.sleep(SEGUNDOS_POSE)
        robot.movimiento_predefinido(0)

    elif evento == "rostro_detectado" and identidad_normalizada in IDENTIDADES_CONOCIDAS:
        logger.info("Detectado: %s (%.0f%%)", identidad, confianza)
        robot.accion_m9()
        time.sleep(1.0)
        robot.luz_verde()
        time.sleep(SEGUNDOS_POSE)
        robot.movimiento_predefinido(0)

    else:
        logger.info("Mensaje ignorado: %s", data)


def _apagar(_sig: int, _frame: object) -> None:
    global _running
    logger.info("Cierre solicitado. RAPIRO ira a M0 antes de cerrar...")
    _running = False


def main() -> None:
    logger.info("Iniciando subscriber RAPIRO por REST...")
    credentials = _credentials()
    robot = RAPIROController(puerto=PUERTO_SERIAL, baud=BAUD_RATE)

    signal.signal(signal.SIGINT, _apagar)
    signal.signal(signal.SIGTERM, _apagar)

    logger.info("Escuchando en %s ...", _subscription_path())

    try:
        while _running:
            try:
                messages = _pull(credentials)
                if not messages:
                    time.sleep(1.0)
                    continue

                for received in messages:
                    ack_id = received["ackId"]
                    raw_data = received.get("message", {}).get("data", "")
                    payload = json.loads(base64.b64decode(raw_data).decode("utf-8"))

                    try:
                        _procesar_payload(payload, robot)
                        _ack(credentials, ack_id)
                    except Exception as exc:
                        logger.error("Error procesando mensaje: %s", exc)
                        _nack(credentials, ack_id)

            except requests.RequestException as exc:
                logger.error("Error Pub/Sub REST: %s", exc)
                time.sleep(5.0)
    except KeyboardInterrupt:
        logger.info("Subscriber interrumpido por teclado.")
    finally:
        logger.info("Enviando RAPIRO a M0 antes de cerrar...")
        robot.movimiento_predefinido(0)
        time.sleep(0.5)
        robot.cerrar(enviar_neutra=False)


if __name__ == "__main__":
    main()
