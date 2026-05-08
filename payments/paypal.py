"""
payments/paypal.py
──────────────────
PayPal Sandbox/Live helper.

Public API
──────────
  get_access_token()
  paypal_request(method, path, json?)
  ensure_usd_payload(payload)
  verify_webhook_signature(headers, raw_body) → bool
  cancel_paypal_order(order_id) → dict
"""

import os
from typing import Any, Dict, Optional

import requests
from django.conf import settings

# ── credentials ───────────────────────────────────────────────────────────────

PAYPAL_CLIENT_ID: str  = getattr(settings, "PAYPAL_CLIENT_ID",  os.getenv("PAYPAL_CLIENT_ID",  ""))
PAYPAL_SECRET: str     = getattr(settings, "PAYPAL_SECRET",     os.getenv("PAYPAL_SECRET",     ""))
PAYPAL_BASE: str       = getattr(settings, "PAYPAL_BASE",       os.getenv("PAYPAL_BASE",       "https://api-m.sandbox.paypal.com"))
PAYPAL_WEBHOOK_ID: str = getattr(settings, "PAYPAL_WEBHOOK_ID", os.getenv("PAYPAL_WEBHOOK_ID", ""))
VND_TO_USD_RATE: float = float(getattr(settings, "PAYPAL_VND_TO_USD_RATE", os.getenv("PAYPAL_VND_TO_USD_RATE", "25000")))


# ── core helpers ──────────────────────────────────────────────────────────────

def get_access_token() -> str:
    """Lấy Bearer token từ PayPal OAuth2."""
    url = f"{PAYPAL_BASE}/v1/oauth2/token"
    response = requests.post(
        url,
        auth=(PAYPAL_CLIENT_ID, PAYPAL_SECRET),
        data={"grant_type": "client_credentials"},
        timeout=15,
    )
    response.raise_for_status()
    return str(response.json().get("access_token", ""))


def paypal_request(
    method: str,
    path: str,
    json: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Gọi PayPal REST API với Bearer token."""
    token = get_access_token()
    url   = f"{PAYPAL_BASE}{path}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    resp = requests.request(method, url, headers=headers, json=json, timeout=20)
    if resp.ok:
        try:
            return resp.json()
        except Exception:
            return {}

    try:
        err = resp.json()
        print(f"[PayPal] {resp.status_code} {resp.reason} {method} {path}")
        print(f"Body: {err}")
    except Exception:
        print(f"[PayPal] {resp.status_code} {resp.reason} {method} {path}")
        print(f"Text: {resp.text}")
    resp.raise_for_status()
    return {}


def ensure_usd_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Chuyển currency VND → USD nếu PayPal sandbox không hỗ trợ VND."""
    pu = payload.get("purchase_units", [])
    if not pu:
        return payload
    amount = pu[0].get("amount", {})
    if amount.get("currency_code") == "VND":
        try:
            vnd = float(amount.get("value", "0"))
            usd = round(vnd / VND_TO_USD_RATE, 2)
            amount["currency_code"] = "USD"
            amount["value"] = f"{usd:.2f}"
            print(f"[PayPal] Converted {vnd} VND → {usd} USD")
        except Exception as e:
            print(f"[PayPal] VND→USD conversion failed: {e}")
    return payload


# ── webhook signature verification ───────────────────────────────────────────

def verify_webhook_signature(
    headers: dict,
    raw_body: bytes,
) -> bool:
    """
    Ask PayPal to verify that the webhook payload was genuinely sent by them.

    PayPal docs: POST /v1/notifications/verify-webhook-signature

    Returns True if valid, False otherwise.
    If PAYPAL_WEBHOOK_ID is not configured we skip verification and return True
    (useful during development – set PAYPAL_WEBHOOK_ID in production).
    """
    if not PAYPAL_WEBHOOK_ID:
        # Verification disabled – accept all (dev only)
        import logging
        logging.getLogger(__name__).warning(
            "[PayPal] PAYPAL_WEBHOOK_ID not set – skipping signature verification!"
        )
        return True

    import json as _json

    try:
        body_dict = _json.loads(raw_body)
    except Exception:
        return False

    verification_payload = {
        "auth_algo":         headers.get("PAYPAL-AUTH-ALGO", ""),
        "cert_url":          headers.get("PAYPAL-CERT-URL", ""),
        "transmission_id":   headers.get("PAYPAL-TRANSMISSION-ID", ""),
        "transmission_sig":  headers.get("PAYPAL-TRANSMISSION-SIG", ""),
        "transmission_time": headers.get("PAYPAL-TRANSMISSION-TIME", ""),
        "webhook_id":        PAYPAL_WEBHOOK_ID,
        "webhook_event":     body_dict,
    }

    try:
        result = paypal_request(
            "POST",
            "/v1/notifications/verify-webhook-signature",
            json=verification_payload,
        )
        return result.get("verification_status") == "SUCCESS"
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("[PayPal] Signature verification error: %s", exc)
        return False
