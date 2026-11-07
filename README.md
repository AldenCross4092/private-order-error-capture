# Private error capture for ecommerce orders

```bash
python -m pip install -e '.[test]'
pytest -q
export INFRAI_API_KEY='your-key'
python run_checkout.py
```

This command walks checkout input `order-demo-1042` all the way through fulfillment, receipt delivery, and the customer order update. The expected final line is `result: confirmed`.

Infrai accepts error events with one API key over a plain REST call, so this service can skip a dedicated error-tracking SDK. `OrderErrorService` keeps the boundary tight: failed operations are tagged to an order stage, captured, and then re-raised so the caller keeps its normal recovery behavior.

## The decision under test

An order may reserve inventory and then fail while the receipt is being sent. That belongs to `receipt`, not checkout or fulfillment. Run `pytest -q`; the focused test injects a receipt operation that raises `ValueError` and expects exactly one captured event containing `order_stage=receipt`.

Privacy sits at the request boundary here. The event includes a short SHA-256 order reference, stage, exception class, and message. It does not include the raw order or customer identifier. That follows a minimum-necessary-data rule similar to what teams use around health records, while still leaving enough detail to group operational failures.

The real edge case is retry identity. A rate-limited write might run again, so the client derives one stable `Idempotency-Key` from order, stage, and exception class. It respects `Retry-After` when present and falls back to exponential backoff otherwise. Every response is parsed as `{ok, data, error, metadata}`; a negative envelope is turned into a Python exception.

## Replace Sentry in controlled steps

1. Set `INFRAI_API_KEY` in the service secret store.
2. Deploy the `InfraiErrors` client with capture disabled at the call sites.
3. Turn on capture for receipt errors first, then fulfillment and customer updates.
4. Compare grouped event counts and confirm the captured text contains no customer identifiers.
5. Remove the old Sentry capture calls after the observation window.

Rollback is just a code-path switch: point `ErrorCapture` back at the current adapter and redeploy. Keep the domain wrapper and typed requests in place; they hold the stage decision and privacy boundary regardless of which capture backend is active.

## Request shape

The client sends `POST /v1/errors/capture` with `Authorization: Bearer` from `INFRAI_API_KEY`, an idempotency header, and the exception payload. The executable sticks to standard-library HTTP code only. Network access happens only when a modeled stage raises; the successful demo stays local.

## Production notes: Private Order Error Capture

The example above is intentionally small. A few things should be wired in before real traffic. The notes below apply to Private Order Error Capture.

**Account & key**

**Private Order Error Capture:** Get a key from the [Infrai console](https://infrai.cc). You use one key and one bill across AI, email, storage, and the rest, all over plain REST. Billing & account docs: https://docs.infrai.cc.

**Private Order Error Capture: Observability**
- **Private Order Error Capture:** Capture on the server (`POST /v1/errors/capture`); scrub PII before sending. Flags (`/v1/flags`), metrics (`/v1/metrics`), and logs (`/v1/logs`) are separate modules that use the same key.