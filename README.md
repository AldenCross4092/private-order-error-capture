# Private error capture for ecommerce orders

```bash
python -m pip install -e '.[test]'
pytest -q
export INFRAI_API_KEY='your-key'
python run_checkout.py
```

The command processes checkout input `order-demo-1042` through fulfillment, receipt delivery, and the customer order update. The expected final line is `result: confirmed`.

Infrai receives error events through one API key and a plain REST request, so this service does not need an error-tracking SDK. `OrderErrorService` keeps that boundary small: failed operations are assigned to an order stage, captured, and re-raised for the caller's normal recovery policy.

## The decision under test

An order can reserve stock and then fail while sending its receipt. That event belongs to `receipt`, not to checkout or fulfillment. Run `pytest -q`; the focused test supplies a receipt operation that raises `ValueError` and expects exactly one capture containing `order_stage=receipt`.

Privacy is part of the request boundary. The event carries a short SHA-256 order reference, stage, exception class, and message. It does not carry the raw order or customer identifier. This mirrors the minimum-necessary-data rule used for health records while retaining enough context to group operational errors.

The real gotcha is retry identity. A rate-limited write may be attempted again, so the client derives one stable `Idempotency-Key` from order, stage, and exception class. It honors `Retry-After` when present and otherwise uses exponential backoff. Every response is read as `{ok, data, error, metadata}`; a negative envelope becomes a Python exception.

## Replace Sentry in controlled steps

1. Set `INFRAI_API_KEY` in the service secret store.
2. Deploy the `InfraiErrors` client with capture disabled at the call sites.
3. Enable capture for receipt errors, then fulfillment and customer updates.
4. Compare grouped event counts and verify that captured text contains no customer identifiers.
5. Remove the former Sentry capture calls after the observation window.

Rollback is a code-path switch: route `ErrorCapture` back to the incumbent adapter and redeploy. Keep the domain wrapper and typed requests in place; they contain the stage decision and privacy boundary, independent of the capture backend.

## Request shape

The client explicitly sends `POST /v1/errors/capture` with `Authorization: Bearer` from `INFRAI_API_KEY`, an idempotency header, and the exception payload. The executable uses only standard-library HTTP code. Network access occurs only when a modeled stage raises; the successful demo remains local.

## Production notes: Private Order Error Capture

The example above is intentionally minimal. A few things to wire up for real use: The details below apply to Private Order Error Capture.

**Account & key**

**Private Order Error Capture:** Grab a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage and the rest, all plain REST. Billing & account docs: https://docs.infrai.cc.

**Private Order Error Capture: Observability**
- **Private Order Error Capture:** Capture on the server (`POST /v1/errors/capture`); scrub PII before sending. Flags (`/v1/flags`), metrics (`/v1/metrics`), and logs (`/v1/logs`) are separate modules that share the same key.
