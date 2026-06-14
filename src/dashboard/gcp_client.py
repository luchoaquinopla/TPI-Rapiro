from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore, storage

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "project-ac5c4157-56cb-4920-98f")
BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "rapiro-detecciones")

COLLECTION_EVENTS = "recognition_events"
COLLECTION_UNKNOWNS = "detecciones_desconocidos"


def _ts_to_iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value) if value else ""


def get_recent_events(limit: int = 50) -> list[dict]:
    db = firestore.Client()

    known = (
        db.collection(COLLECTION_EVENTS)
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .stream()
    )
    unknown = (
        db.collection(COLLECTION_UNKNOWNS)
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .stream()
    )

    results = []
    for doc in known:
        d = doc.to_dict()
        results.append({
            "id": doc.id,
            "evento": d.get("evento", ""),
            "identidad": d.get("identidad", ""),
            "confianza": round(float(d.get("confianza", 0)), 1),
            "timestamp": _ts_to_iso(d.get("timestamp", "")),
            "image_url": "",
        })
    for doc in unknown:
        d = doc.to_dict()
        results.append({
            "id": doc.id,
            "evento": d.get("evento", "desconocido_detectado"),
            "identidad": "desconocido",
            "confianza": round(float(d.get("confianza", 0)), 1),
            "timestamp": _ts_to_iso(d.get("timestamp", "")),
            "image_url": d.get("image_url", ""),
        })

    results.sort(key=lambda x: x["timestamp"], reverse=True)
    return results[:limit]


def get_stats() -> dict:
    events = get_recent_events(limit=200)

    total = len(events)
    known_count = sum(1 for e in events if e["evento"] == "rostro_detectado")
    unknown_count = sum(1 for e in events if e["evento"] == "desconocido_detectado")

    confidences = [e["confianza"] for e in events if e["confianza"] > 0]
    avg_confidence = round(sum(confidences) / len(confidences), 1) if confidences else 0.0

    identity_counts: dict[str, int] = {}
    for e in events:
        if e["evento"] == "rostro_detectado":
            name = e["identidad"] or "desconocido"
            identity_counts[name] = identity_counts.get(name, 0) + 1

    return {
        "total": total,
        "conocidos": known_count,
        "desconocidos": unknown_count,
        "confianza_promedio": avg_confidence,
        "por_identidad": identity_counts,
    }


def clear_all_events() -> int:
    db = firestore.Client()
    deleted = 0
    for collection in (COLLECTION_EVENTS, COLLECTION_UNKNOWNS):
        docs = db.collection(collection).stream()
        for doc in docs:
            doc.reference.delete()
            deleted += 1
    return deleted


def get_unknown_images(limit: int = 20) -> list[dict]:
    client = storage.Client()
    bucket = client.bucket(BUCKET_NAME)
    blobs = bucket.list_blobs(prefix="desconocidos/", max_results=limit)

    images = []
    for blob in blobs:
        if not blob.name.endswith(".jpg"):
            continue
        images.append({
            "name": blob.name,
            "url": f"https://storage.googleapis.com/{BUCKET_NAME}/{blob.name}",
            "size_kb": round(blob.size / 1024, 1) if blob.size else 0,
            "updated": blob.updated.isoformat() if blob.updated else "",
        })

    images.sort(key=lambda x: x["updated"], reverse=True)
    return images
