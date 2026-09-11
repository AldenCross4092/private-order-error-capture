"""Run one local order flow; replace the three callables with production adapters."""

from src.order_error_service import CheckoutRequest, InfraiErrors, OrderErrorService, process_order


def fail_receipt(_request: object) -> None:
    raise ValueError("receipt template missing")


def main() -> None:
    checkout = CheckoutRequest(
        order_id="order-demo-1042",
        customer_id="customer-demo-7",
        amount_minor=4599,
        currency="USD",
    )
    service = OrderErrorService(InfraiErrors())
    outcome = process_order(
        checkout,
        service,
        reserve_stock=lambda request: print(f"stock reserved: {request.order_id}"),
        send_receipt=fail_receipt,
        publish_update=lambda request: print(f"order update: {request.status}"),
    )
    print(f"result: {outcome.status}")


if __name__ == "__main__":
    main()
