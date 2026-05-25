"""
verify_env.py
Verifica que todas las dependencias del proyecto estén instaladas correctamente.
Ejecutar luego de: pip install -r requirements.txt
"""

import sys

checks = []

def check(name, fn):
    try:
        fn()
        checks.append((name, True, ""))
    except Exception as e:
        checks.append((name, False, str(e)))

# TensorFlow
def check_tf():
    import tensorflow as tf
    assert tf.__version__.startswith("2"), f"Se esperaba TF 2.x, se encontró {tf.__version__}"
check("TensorFlow", check_tf)

# OpenCV
def check_cv():
    import cv2
    assert cv2.__version__ is not None
check("OpenCV", check_cv)

# NumPy
def check_np():
    import numpy as np
    _ = np.array([1, 2, 3])
check("NumPy", check_np)

# PySerial
def check_serial():
    import serial
    _ = serial.__version__
check("PySerial", check_serial)

# scikit-learn
def check_sklearn():
    import sklearn
    _ = sklearn.__version__
check("scikit-learn", check_sklearn)

# Pillow
def check_pil():
    from PIL import Image
    _ = Image.__version__
check("Pillow", check_pil)

# Google Cloud
def check_gcloud():
    from google.cloud import pubsub_v1, firestore, storage
check("Google Cloud SDK", check_gcloud)

# Matplotlib
def check_matplotlib():
    import matplotlib
    _ = matplotlib.__version__
check("Matplotlib", check_matplotlib)

# wandb
def check_wandb():
    import wandb
    _ = wandb.__version__
check("Weights & Biases", check_wandb)

# --- Reporte ---
print("\n" + "="*45)
print("  VERIFICACIÓN DE ENTORNO - RAPIRO TPI 2026")
print("="*45)
print(f"  Python: {sys.version.split()[0]}")
print("="*45)

all_ok = True
for name, ok, err in checks:
    status = "✅ OK" if ok else "❌ ERROR"
    print(f"  {status:<10} {name}")
    if not ok:
        print(f"             → {err}")
        all_ok = False

print("="*45)
if all_ok:
    print("  Todo listo. Podés empezar a desarrollar.")
else:
    print("  Hay errores. Revisá el requirements.txt.")
print("="*45 + "\n")
