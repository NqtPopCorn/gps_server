"""PayPal Sandbox helper.

Reads credentials from Django settings (which reads from .env).
Exposes:
  - get_access_token()
  - paypal_request(method, path, json)
  - ensure_usd_payload(payload)
"""

import os
from typing import Any, Dict

import requests
from django.conf import settings


PAYPAL_CLIENT_ID: str = getattr(settings, 'PAYPAL_CLIENT_ID', os.getenv('PAYPAL_CLIENT_ID', ''))
PAYPAL_SECRET: str = getattr(settings, 'PAYPAL_SECRET', os.getenv('PAYPAL_SECRET', ''))
PAYPAL_BASE: str = getattr(settings, 'PAYPAL_BASE', os.getenv('PAYPAL_BASE', 'https://api-m.sandbox.paypal.com'))
VND_TO_USD_RATE: float = float(getattr(settings, 'PAYPAL_VND_TO_USD_RATE', os.getenv('PAYPAL_VND_TO_USD_RATE', '25000')))


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
    data = response.json()
    return str(data.get('access_token', ''))


def paypal_request(method: str, path: str, json: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Gọi PayPal REST API với Bearer token."""
    token = get_access_token()
    url = f"{PAYPAL_BASE}{path}"
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f"Bearer {token}",
    }
    resp = requests.request(method, url, headers=headers, json=json, timeout=20)
    if resp.ok:
        # capture-order trả về 201 No Content khi không có body
        try:
            return resp.json()
        except Exception:
            return {}
    # Log lỗi chi tiết
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
    pu = payload.get('purchase_units', [])
    if not pu:
        return payload
    amount = pu[0].get('amount', {})
    if amount.get('currency_code') == 'VND':
        try:
            vnd = float(amount.get('value', '0'))
            usd = round(vnd / VND_TO_USD_RATE, 2)
            amount['currency_code'] = 'USD'
            amount['value'] = f"{usd:.2f}"
            print(f"[PayPal] Converted {vnd} VND → {usd} USD")
        except Exception as e:
            print(f"[PayPal] VND→USD conversion failed: {e}")
    return payload
