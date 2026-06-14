

from __future__ import annotations

import time

from rapiro_controller import (
    RAPIROController,
    SERVO_HOMBRO_DERECHO,
    SERVO_HOMBRO_IZQUIERDO,
)

PUERTO = "/dev/ttyAMA0"
BAUD   = 57600


def main() -> None:
    print(f"Conectando en {PUERTO} a {BAUD} baud...")
    robot = RAPIROController(puerto=PUERTO, baud=BAUD)
    print("Conectado. Iniciando secuencia de prueba...\n")

    print(f"→ Levantar brazo DERECHO (servo {SERVO_HOMBRO_DERECHO})")
    robot.levantar_brazo_derecho()
    time.sleep(2)

    print("→ Posición neutra")
    robot.posicion_neutra()
    time.sleep(1)

    print(f"→ Levantar brazo IZQUIERDO (servo {SERVO_HOMBRO_IZQUIERDO})")
    robot.levantar_brazo_izquierdo()
    time.sleep(2)

    print("→ Posición neutra")
    robot.posicion_neutra()

    # Para encontrar el servo correcto, descomentar esto:
    # for i in range(12):
    #     print(f"  Servo {i}...")
    #     robot._enviar(i, 140)
    #     time.sleep(1)
    #     robot._enviar(i, 90)
    #     time.sleep(0.5)

    robot.cerrar()
    print("\nPrueba finalizada.")


if __name__ == "__main__":
    main()
