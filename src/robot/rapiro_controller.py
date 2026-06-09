from __future__ import annotations

import logging
import time

import serial

logger = logging.getLogger(__name__)

# IDs de servo — ajustar si el cableado del RAPIRO es distinto
SERVO_HOMBRO_DERECHO = 2
SERVO_HOMBRO_IZQUIERDO = 6

ANGULO_NEUTRO = 90
ANGULO_BRAZO_ARRIBA = 150


class RAPIROController:
    def __init__(self, puerto: str = "/dev/ttyAMA0", baud: int = 57600) -> None:
        self.ser = serial.Serial(puerto, baud, timeout=1)
        time.sleep(2)  # el Arduino hace reset al abrir el puerto serial
        logger.info("RAPIRO conectado en %s a %d baud", puerto, baud)

    def _enviar(self, servo_id: int, angulo: int) -> None:
        angulo = max(0, min(180, angulo))
        self.ser.write(f"S{servo_id},{angulo}\n".encode("ascii"))
        self.ser.flush()
        time.sleep(0.05)

    def levantar_brazo_derecho(self) -> None:
        logger.info("Acción → levantar brazo derecho")
        self._enviar(SERVO_HOMBRO_DERECHO, ANGULO_BRAZO_ARRIBA)

    def levantar_brazo_izquierdo(self) -> None:
        logger.info("Acción → levantar brazo izquierdo")
        self._enviar(SERVO_HOMBRO_IZQUIERDO, ANGULO_BRAZO_ARRIBA)

    def posicion_neutra(self) -> None:
        logger.info("Acción → posición neutra")
        self._enviar(SERVO_HOMBRO_DERECHO, ANGULO_NEUTRO)
        self._enviar(SERVO_HOMBRO_IZQUIERDO, ANGULO_NEUTRO)

    def cerrar(self) -> None:
        self.posicion_neutra()
        self.ser.close()
