from __future__ import annotations

import logging
import time

import serial

logger = logging.getLogger(__name__)

# IDs de servo — ajustar si el cableado del RAPIRO es distinto
SERVO_CABEZA = 0
SERVO_HOMBRO_DERECHO = 2
SERVO_HOMBRO_IZQUIERDO = 5

ANGULO_NEUTRO = 90
ANGULO_BRAZO_ARRIBA = 150
ANGULO_CABEZA_IZQUIERDA = 60
ANGULO_CABEZA_DERECHA = 120
LUZ_TRANSICION_DECIMAS = 5


class RAPIROController:
    def __init__(self, puerto: str = "/dev/ttyAMA0", baud: int = 57600) -> None:
        self.ser = serial.Serial(puerto, baud, timeout=1)
        time.sleep(2)  # el Arduino hace reset al abrir el puerto serial
        logger.info("RAPIRO conectado en %s a %d baud", puerto, baud)

    def _enviar(self, servo_id: int, angulo: int, tiempo_decimas: int = 5) -> None:
        angulo = max(0, min(180, angulo))
        # Formato estándar Rapiro: #PS[ID]A[Ángulo]T[Tiempo]\r
        # ID: 2 dígitos, Ángulo: 3 dígitos, Tiempo: 3 dígitos (en décimas de segundo, ej: 005 = 0.5s)
        cmd = f"#PS{servo_id:02d}A{angulo:03d}T{tiempo_decimas:03d}\r"
        self._enviar_comando(cmd)

    def _enviar_comando(self, cmd: str) -> None:
        self.ser.write(cmd.encode("ascii"))
        self.ser.flush()
        time.sleep(0.05)

    def movimiento_predefinido(self, movimiento_id: int) -> None:
        if not 0 <= movimiento_id <= 9:
            raise ValueError("El movimiento predefinido debe estar entre M0 y M9.")
        logger.info("Accion -> M%d", movimiento_id)
        self._enviar_comando(f"#M{movimiento_id}\r")

    def accion_m9(self) -> None:
        self.movimiento_predefinido(9)

    def cambiar_luz(self, rojo: int, verde: int, azul: int, tiempo_decimas: int = LUZ_TRANSICION_DECIMAS) -> None:
        rojo = max(0, min(255, rojo))
        verde = max(0, min(255, verde))
        azul = max(0, min(255, azul))
        logger.info("AcciÃ³n â†’ cambiar luz RGB (%d, %d, %d)", rojo, verde, azul)
        self._enviar_comando(f"#PR{rojo:03d}G{verde:03d}B{azul:03d}T{tiempo_decimas:03d}\r")

    def luz_roja(self) -> None:
        self.cambiar_luz(255, 0, 0)

    def luz_verde(self) -> None:
        self.cambiar_luz(0, 255, 0)

    def sacudir_cabeza(self, repeticiones: int = 2) -> None:
        logger.info("Acción → sacudir cabeza (no)")
        for _ in range(repeticiones):
            self._enviar(SERVO_CABEZA, ANGULO_CABEZA_IZQUIERDA)
            time.sleep(0.3)
            self._enviar(SERVO_CABEZA, ANGULO_CABEZA_DERECHA)
            time.sleep(0.3)
        self._enviar(SERVO_CABEZA, ANGULO_NEUTRO)

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
