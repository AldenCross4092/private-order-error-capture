from src.order_error_service import CheckoutRequest, OrderErrorService, process_order


class RecordingErrors:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def capture(self, exception: str, idempotency_key: str) -> dict:
        self.calls.append((exception, idempotency_key))
        return {"accepted": True}


def test_receipt_failure_is_grouped_without_customer_identity() -> None:
    recorder = RecordingErrors()
    service = OrderErrorService(recorder)
    checkout = CheckoutRequest("order-42", "patient-like-customer-9", 2599, "USD")

    def fail_receipt(_request: object) -> None:
        raise ValueError("receipt template missing")

    try:
        process_order(
            checkout,
            service,
            reserve_stock=lambda _request: None,
            send_receipt=fail_receipt,
            publish_update=lambda _request: None,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("receipt failure must be re-raised")

    assert len(recorder.calls) == 1
    captured, stable_key = recorder.calls[0]
    assert "order_stage=receipt" in captured
    assert "ValueError: receipt template missing" in captured
    assert "order-42" not in captured
    assert "patient-like-customer-9" not in captured
    assert len(stable_key) == 64
