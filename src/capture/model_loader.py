"""Load Keras models exported from Colab."""

from __future__ import annotations

from pathlib import Path

import tensorflow as tf


def load_modelo(ruta: str | Path) -> tf.keras.Model:
    ruta = Path(ruta)
    if not ruta.is_file():
        raise FileNotFoundError(f"Archivo de modelo no encontrado: {ruta}")
    return tf.keras.models.load_model(str(ruta))
