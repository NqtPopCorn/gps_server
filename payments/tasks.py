"""
payments/tasks.py
─────────────────
Huey background tasks for the payments app.

Why a background task?
  PayPal expects the webhook endpoint to respond in < 5 s.
  All DB mutations (Invoice update, poi_credits grant, UserAvailableTour upsert)
  happen here, outside the HTTP request cycle.

Crash safety:
  The WebhookEvent row is saved to DB *before* this task is enqueued.
  If the server dies between "save row" and "enqueue", a periodic recovery
  task (``retry_stuck_webhook_events``) re-enqueues PENDING rows that are
  older than STUCK_AFTER_SECONDS.
  All handler logic checks current DB state before mutating, so replays
  are safe.
"""

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from huey import crontab
from huey.contrib.djhuey import db_task, periodic_task

logger = logging.getLogger(__name__)

# ── constants ─────────────────────────────────────────────────────────────────

# A PENDING webhook older than this is considered "stuck" and gets re-enqueued.
STUCK_AFTER_SECONDS: int = 300   # 5 minutes

# PayPal event types we care about
_CAPTURE_COMPLETED = "PAYMENT.CAPTURE.COMPLETED"
_CAPTURE_DENIED    = "PAYMENT.CAPTURE.DENIED"
_ORDER_CANCELLED   = "CHECKOUT.ORDER.CANCELLED"

# ── helpers ───────────────────────────────────────────────────────────────────

def _get_order_id_from_payload(payload: dict) -> str | None:
    """Extract PayPal Order ID from a webhook payload."""
    try:
        # PAYMENT.CAPTURE.* → resource.supplementary_data.related_ids.order_id
        related = (
            payload
            .get("resource", {})
            .get("supplementary_data", {})
            .get("related_ids", {})
        )
        order_id = related.get("order_id")
        if order_id:
            return order_id

        # Fallback: resource.id when the resource IS the order
        resource_id = payload.get("resource", {}).get("id")
        return resource_id
    except Exception:
        return None


def _grant_poi_credit(invoice) -> None:
    from accounts.models import User
    from payments.models import Invoice

    user = invoice.user
    if not user:
        return
    User.objects.filter(pk=user.pk).update(
        poi_credits=user.poi_credits + Invoice.POI_CREDIT_AMOUNT
    )
    logger.info(
        "[webhook] Granted %d POI credit(s) to %s",
        Invoice.POI_CREDIT_AMOUNT, user.email,
    )


def _upsert_available_tour(invoice) -> None:
    from django.shortcuts import get_object_or_404
    from tours.models import Tour
    from payments.models import UserAvailableTour

    if not invoice.reference_id or not invoice.user:
        return

    tour = Tour.objects.filter(id=invoice.reference_id).first()
    if not tour:
        logger.warning("[webhook] Tour %s not found for invoice %s", invoice.reference_id, invoice.id)
        return

    obj, created = UserAvailableTour.objects.update_or_create(
        user=invoice.user,
        tour=tour,
        defaults={"expired_at": timezone.now() + timedelta(days=7)},
    )
    logger.info(
        "[webhook] UserAvailableTour %s for user=%s tour=%s",
        "created" if created else "updated",
        invoice.user.email, tour.id,
    )


# ── main task ─────────────────────────────────────────────────────────────────

@db_task(retries=5, retry_delay=120)   # retry up to 5× with 2-minute back-off
def process_webhook_event(webhook_event_id: int) -> None:
    """
    Process a single WebhookEvent row identified by its PK.

    Idempotent:
    - If status is already PROCESSED / IGNORED we bail out immediately.
    - We check Invoice.status before updating it, so replaying is safe.
    """
    from payments.models import WebhookEvent, Invoice

    try:
        event = WebhookEvent.objects.get(pk=webhook_event_id)
    except WebhookEvent.DoesNotExist:
        logger.error("[webhook] WebhookEvent %s not found", webhook_event_id)
        return

    # Guard: ignore event that already handled (e.g. duplicate delivery processed in parallel)
    if event.status in (WebhookEvent.Status.PROCESSED, WebhookEvent.Status.IGNORED):
        logger.info("[webhook] Event %s already %s – skip", event.paypal_event_id, event.status)
        return

    # Mark as in-flight so concurrent workers skip it
    WebhookEvent.objects.filter(pk=webhook_event_id, status__in=[
        WebhookEvent.Status.PENDING, WebhookEvent.Status.FAILED
    ]).update(status=WebhookEvent.Status.PROCESSING)

    try:
        _dispatch(event)
        event.refresh_from_db()
        event.status       = WebhookEvent.Status.PROCESSED
        event.processed_at = timezone.now()
        event.error        = None
        event.save(update_fields=["status", "processed_at", "error"])
        logger.info("[webhook] Processed event %s (%s)", event.paypal_event_id, event.event_type)

    except Exception as exc:
        event.refresh_from_db()
        event.status = WebhookEvent.Status.FAILED
        event.error  = str(exc)
        event.save(update_fields=["status", "error"])
        logger.error(
            "[webhook] Failed to process event %s: %s",
            event.paypal_event_id, exc, exc_info=True,
        )
        raise   # re-raise so Huey applies the retry policy


def _dispatch(event) -> None:
    """Route the event to the appropriate handler."""
    from payments.models import Invoice

    et = event.event_type

    if et == _CAPTURE_COMPLETED:
        _handle_capture_completed(event.payload)
    elif et in (_CAPTURE_DENIED, _ORDER_CANCELLED):
        _handle_capture_failed(event.payload)
    else:
        # We received a valid event but don't need to act on it
        from payments.models import WebhookEvent
        WebhookEvent.objects.filter(pk=event.pk).update(status=WebhookEvent.Status.IGNORED)
        logger.debug("[webhook] Ignored event type: %s", et)


def _handle_capture_completed(payload: dict) -> None:
    from payments.models import Invoice

    order_id = _get_order_id_from_payload(payload)
    if not order_id:
        logger.warning("[webhook] Could not extract order_id from payload")
        return

    invoice = Invoice.objects.filter(transaction_code=order_id).first()
    if not invoice:
        logger.warning("[webhook] No invoice found for order_id=%s", order_id)
        return

    # Idempotent: skip if already processed
    if invoice.status == Invoice.Status.SUCCESS:
        logger.info("[webhook] Invoice %s already SUCCESS – skip", invoice.id)
        return

    with transaction.atomic():
        Invoice.objects.filter(pk=invoice.pk, status=Invoice.Status.PENDING).update(
            status=Invoice.Status.SUCCESS,
            paid_at=timezone.now(),
        )
        invoice.refresh_from_db()

        if invoice.status != Invoice.Status.SUCCESS:
            # Another process already moved the status; bail
            return

        if invoice.invoice_type == Invoice.Type.POI_CREDIT:
            _grant_poi_credit(invoice)
        elif invoice.invoice_type == Invoice.Type.START_TOUR:
            _upsert_available_tour(invoice)

    logger.info("[webhook] Invoice %s marked SUCCESS", invoice.id)


def _handle_capture_failed(payload: dict) -> None:
    from payments.models import Invoice

    order_id = _get_order_id_from_payload(payload)
    if not order_id:
        return

    updated = Invoice.objects.filter(
        transaction_code=order_id,
        status=Invoice.Status.PENDING,
    ).update(status=Invoice.Status.FAILED)

    if updated:
        logger.info("[webhook] Invoice for order %s marked FAILED", order_id)


# ── recovery task: re-enqueue stuck PENDING events ────────────────────────────

@periodic_task(crontab(minute="*/5"))   # every 5 minutes
def retry_stuck_webhook_events() -> None:
    """
    If the server was killed after the WebhookEvent row was saved but before
    the Huey task was enqueued (or the worker died before setting status to
    PROCESSING), the row stays PENDING forever.

    This periodic task finds such "stuck" rows and re-enqueues them.
    """
    from payments.models import WebhookEvent

    cutoff = timezone.now() - timedelta(seconds=STUCK_AFTER_SECONDS)
    stuck  = WebhookEvent.objects.filter(
        status__in=[WebhookEvent.Status.PENDING, WebhookEvent.Status.FAILED],
        created_at__lt=cutoff,
    ).values_list("id", flat=True)[:50]   # cap to avoid thundering herd

    if not stuck:
        return

    for event_id in stuck:
        process_webhook_event(event_id)
        logger.info("[webhook] Re-enqueued stuck WebhookEvent id=%s", event_id)