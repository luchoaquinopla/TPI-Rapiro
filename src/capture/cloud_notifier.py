

from __future__ import annotations

import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

import cv2
import numpy as np
from google.cloud import firestore, storage

BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "rapiro-detecciones")
FIRESTORE_COLLECTION = "detecciones_desconocidos"


def _upload_image(frame: np.ndarray, timestamp: str) -> tuple[str, str]:
    client = storage.Client()
    bucket = client.bucket(BUCKET_NAME)
    blob_name = f"desconocidos/{timestamp}.jpg"
    blob = bucket.blob(blob_name)

    _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    blob.upload_from_string(buffer.tobytes(), content_type="image/jpeg")

    public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{blob_name}"
    return public_url, blob_name


def _save_firestore(ts_dt: datetime, confianza: float, image_url: str, blob_name: str) -> None:
    db = firestore.Client()
    db.collection(FIRESTORE_COLLECTION).add({
        "timestamp": ts_dt,
        "confianza": round(confianza, 2),
        "image_url": image_url,
        "storage_path": blob_name,
        "evento": "desconocido_detectado",
    })


def _send_email(image_url: str, confianza: float, timestamp: str, frame: np.ndarray) -> None:
    gmail_user = os.getenv("GMAIL_USER")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")
    gmail_to = os.getenv("GMAIL_TO", gmail_user)

    if not gmail_user or not gmail_password:
        print("[WARN] Gmail no configurado — se omite el envío de email.")
        return

    readable_time = datetime.strptime(timestamp, "%Y%m%d_%H%M%S").strftime("%d/%m/%Y %H:%M:%S UTC")

    msg = MIMEMultipart("related")
    msg["From"] = gmail_user
    msg["To"] = gmail_to
    msg["Subject"] = f"⚠️ RAPIRO — Persona desconocida detectada"

    html = f"""
    <html><body style="font-family:sans-serif;color:#222;max-width:600px;margin:auto">
      <h2 style="color:#c0392b">⚠️ Alerta de seguridad — RAPIRO</h2>
      <p>Se detectó una <strong>persona desconocida</strong> frente a la cámara.</p>
      <table style="border-collapse:collapse;width:100%">
        <tr>
          <td style="padding:8px;background:#f5f5f5;font-weight:bold">Fecha y hora</td>
          <td style="padding:8px">{readable_time}</td>
        </tr>
        <tr>
          <td style="padding:8px;background:#f5f5f5;font-weight:bold">Confianza del modelo</td>
          <td style="padding:8px">{confianza:.1f}%</td>
        </tr>
        <tr>
          <td style="padding:8px;background:#f5f5f5;font-weight:bold">Imagen en Cloud</td>
          <td style="padding:8px"><a href="{image_url}">Ver imagen completa</a></td>
        </tr>
      </table>
      <br>
      <img src="cid:rostro" style="border:2px solid #c0392b;border-radius:8px;max-width:300px">
      <p style="color:#888;font-size:12px;margin-top:24px">
        Este mensaje fue generado automáticamente por el sistema RAPIRO.
      </p>
    </body></html>
    """
    msg.attach(MIMEText(html, "html"))

    # adjuntar la imagen del rostro en línea
    _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    img_attachment = MIMEImage(buffer.tobytes(), _subtype="jpeg")
    img_attachment.add_header("Content-ID", "<rostro>")
    img_attachment.add_header("Content-Disposition", "inline", filename="rostro.jpg")
    msg.attach(img_attachment)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, gmail_to, msg.as_string())


def notify_unknown(frame: np.ndarray, confianza: float) -> None:
    """Sube la imagen a Cloud Storage, la registra en Firestore y envía una alerta por Gmail."""
    ts_dt = datetime.now(timezone.utc)
    timestamp = ts_dt.strftime("%Y%m%d_%H%M%S")
    image_url = ""
    blob_name = ""

    try:
        image_url, blob_name = _upload_image(frame, timestamp)
        print(f"[CLOUD] Imagen subida: {image_url}")
    except Exception as e:
        print(f"[ERROR] Cloud Storage: {e}")

    try:
        _save_firestore(ts_dt, confianza, image_url, blob_name)
        print("[CLOUD] Metadatos guardados en Firestore.")
    except Exception as e:
        print(f"[ERROR] Firestore: {e}")

    try:
        _send_email(image_url, confianza, timestamp, frame)
        print("[CLOUD] Email enviado.")
    except Exception as e:
        print(f"[ERROR] Gmail: {e}")
