"""Carga modelos exportados desde Colab (Keras 3) en entorno local (Keras 2)."""

from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import tensorflow as tf
from tensorflow.keras import Sequential
from tensorflow.keras.layers import (
    Activation,
    BatchNormalization,
    Conv2D,
    Dense,
    Dropout,
    GlobalAveragePooling2D,
    MaxPooling2D,
)


def build_modelo_binario() -> tf.keras.Model:
    """Arquitectura del clasificador binario Luciano / Paola."""
    return Sequential(
        [
            Conv2D(32, (3, 3), padding="same", input_shape=(96, 96, 3)),
            BatchNormalization(),
            Activation("relu"),
            MaxPooling2D(2, 2),
            Conv2D(64, (3, 3), padding="same"),
            BatchNormalization(),
            Activation("relu"),
            MaxPooling2D(2, 2),
            GlobalAveragePooling2D(),
            Dropout(0.5),
            Dense(1, activation="sigmoid"),
        ]
    )


def _es_formato_keras3(ruta: Path) -> bool:
    with h5py.File(ruta, "r") as f:
        return "layers" in f


def _cargar_pesos_keras3(modelo: tf.keras.Model, ruta: Path) -> None:
    """Lee pesos con estructura layers/<nombre_capa>/vars/N."""
    with h5py.File(ruta, "r") as f:
        for layer in modelo.layers:
            if not layer.weights:
                continue
            base = f"layers/{layer.name}/vars"
            if base not in f:
                raise ValueError(
                    f"No hay pesos para la capa '{layer.name}' en {ruta.name}"
                )
            vars_group = f[base]
            pesos = [np.array(vars_group[str(i)]) for i in range(len(vars_group.keys()))]
            layer.set_weights(pesos)


def _cargar_pesos_keras2(modelo: tf.keras.Model, ruta: Path) -> None:
    """Formato clásico model_weights/... (modelo_binario.h5 completo)."""
    modelo.load_weights(str(ruta))


def load_modelo_binario(ruta: str | Path) -> tf.keras.Model:
    ruta = Path(ruta)
    if not ruta.is_file():
        raise FileNotFoundError(f"No se encontró el archivo de pesos: {ruta}")

    modelo = build_modelo_binario()
    if _es_formato_keras3(ruta):
        _cargar_pesos_keras3(modelo, ruta)
    else:
        _cargar_pesos_keras2(modelo, ruta)
    return modelo
