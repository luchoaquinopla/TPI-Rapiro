import base64
import json
import logging
import os
from datetime import datetime, timezone

from google.cloud import firestore

logger = logging.getLogger(__name__)

_db = None


def _get_db():
    global _db
    if _db is None:
        _db = firestore.Client()
    return _db


def notify_handler(event, context):
    """Pub/Sub trigger — persists recognition events to Firestore."""
    collection = os.environ.get("FIRESTORE_COLLECTION", "recognition_events")

    raw = base64.b64decode(event.get("data", "")).decode("utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("Invalid JSON payload: %s", raw)
        return

    payload.setdefault("received_at", datetime.now(timezone.utc).isoformat())
    payload.setdefault("message_id", context.event_id)

    db = _get_db()
    doc_ref = db.collection(collection).document(context.event_id)
    doc_ref.set(payload)

    logger.info("Event %s saved to %s", context.event_id, collection)
