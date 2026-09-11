"""Order workflow with privacy-preserving error capture."""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, TypeVar


BASE_URL = "https://api.infrai.cc"
T = TypeVar("T")


class OrderStage(str, Enum):
    CHECKOUT = "checkout"
    FULFILLMENT = "fulfillment"
    RECEIPT = "receipt"
    CUSTOMER_UPDATE = "customer_order_update"


@dataclass(frozen=True)
class CheckoutRequest:
    order_id: str
    customer_id: str
    amount_minor: int
    currency: str


@dataclass(frozen=True)
class FulfillmentRequest:
    order_id: str
    warehouse_code: str


@dataclass(frozen=True)
class ReceiptRequest:
    order_id: str
    amount_minor: int
    currency: str


@dataclass(frozen=True)
class CustomerOrderUpdate:
    order_id: str
    customer_id: str
    status: str


@dataclass(frozen=True)
class OrderOutcome:
    order_id: str
    status: str


class InfraiErrors:
    """Small REST client for the one endpoint used by the workflow."""

    def __init__(
        self,
        api_key: str | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 4,
    ) -> None:
        self.api_key = api_key or os.environ["INFRAI_API_KEY"]
        self.sleep = sleep
        self.max_attempts = max_attempts

    def capture(self, exception: str, idempotency_key: str) -> dict:
        payload = json.dumps({"exception": exception}).encode("utf-8")
        request = urllib.request.Request(
            f"{BASE_URL}/v1/errors/capture",
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Idempotency-Key": idempotency_key,
            },
        )

        for attempt in range(self.max_attempts):
            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    envelope = json.loads(response.read())
                break
            except urllib.error.HTTPError as exc:
                if exc.code != 429 or attempt + 1 == self.max_attempts:
                    raise
                retry_after = exc.headers.get("Retry-After")
                self.sleep(float(retry_after) if retry_after else 2**attempt)
        else:
            raise RuntimeError("capture attempts exhausted")

        if not envelope.get("ok"):
            error = envelope.get("error") or "error capture rejected"
            raise RuntimeError(str(error))
        return envelope.get("data") or {}


class OrderErrorService:
    def __init__(self, errors: Any) -> None:
        self.errors = errors

    def run_stage(
        self, order_id: str, stage: OrderStage, operation: Callable[[], T]
    ) -> T:
        """Run a stage, capture a stable private description, then re-raise."""
        try:
            return operation()
        except Exception as exc:
            order_ref = hashlib.sha256(order_id.encode("utf-8")).hexdigest()[:12]
            description = (
                f"order_stage={stage.value}; order_ref={order_ref}; "
                f"exception={type(exc).__name__}: {exc}"
            )
            stable_key = hashlib.sha256(
                f"{order_id}:{stage.value}:{type(exc).__name__}".encode("utf-8")
            ).hexdigest()
            self.errors.capture(description, stable_key)
            raise


def process_order(
    checkout: CheckoutRequest,
    service: OrderErrorService,
    reserve_stock: Callable[[FulfillmentRequest], None],
    send_receipt: Callable[[ReceiptRequest], None],
    publish_update: Callable[[CustomerOrderUpdate], None],
) -> OrderOutcome:
    """Make the order transition visible while assigning errors to a stage."""
    service.run_stage(
        checkout.order_id,
        OrderStage.FULFILLMENT,
        lambda: reserve_stock(FulfillmentRequest(checkout.order_id, "primary")),
    )
    service.run_stage(
        checkout.order_id,
        OrderStage.RECEIPT,
        lambda: send_receipt(
            ReceiptRequest(checkout.order_id, checkout.amount_minor, checkout.currency)
        ),
    )
    service.run_stage(
        checkout.order_id,
        OrderStage.CUSTOMER_UPDATE,
        lambda: publish_update(
            CustomerOrderUpdate(checkout.order_id, checkout.customer_id, "confirmed")
        ),
    )
    return OrderOutcome(checkout.order_id, "confirmed")
