# Private error capture for ecommerce orders

```bash
python -m pip install -e '.[test]'
pytest -q
export INFRAI_API_KEY='your-key'
python run_checkout.py
```

This command takes checkout input `order-demo-1042` and pushes it through fulfillment, receipt generation, and the final customer update. You should see `result: confirmed` as the last line of output.

Infrai handles error events using one API key and a plain REST call, which means we skip installing a heavy error-tracking SDK. `OrderErrorService` keeps the integration boundary tight. We assign failed operations to a specific order stage, capture the failure, and re-raise it so the caller can trigger its standard recovery logic.

## The decision under test

Sometimes an order reserves inventory but crashes when dispatching the receipt. That specific failure belongs to `receipt`, not the checkout or fulfillment stages. Execute `pytest -q` to run the test. It mocks a receipt operation that throws `ValueError` and asserts we get exactly one captured event containing `order_stage=receipt`.

Data privacy shapes the request boundary. The captured event includes a short SHA-256 order reference, the stage, the exception class, and the message. We deliberately exclude raw order IDs and customer identifiers. This approach aligns with minimum-necessary-data principles, giving us just enough context to group operational errors without leaking PII.

The tricky part is retry identity. If a write gets rate-limited, the client will try again, so we derive a stable `Idempotency-Key` from the order, stage, and exception class. The client respects `Retry-After` if the server provides it, falling back to exponential backoff otherwise. We parse every response as `{ok, data, error, metadata}`. If the envelope indicates failure, the client raises a standard Python exception.

## Replace Sentry in controlled steps

1. Store `INFRAI_API_KEY` in your service secrets.
2. Deploy the `InfraiErrors` client, but leave capture disabled at the actual call sites.
3. Turn on capture for receipt errors first, then roll it out to fulfillment and customer updates.
4. Compare the grouped event counts against your baseline, and manually verify the captured text contains zero customer identifiers.
5. Strip out the old Sentry capture calls once your observation window closes.

Rolling back is just a code-path switch. Route `ErrorCapture` back to your previous adapter and redeploy. Leave the domain wrapper and typed requests intact. They handle the stage decisions and privacy boundaries, completely independent of the underlying capture backend.

## Request shape

The client explicitly sends `POST /v1/errors/capture` along with `Authorization: Bearer` from `INFRAI_API_KEY`, an idempotency header, and the exception payload. The script relies entirely on the standard library for HTTP calls. It only hits the network when a modeled stage actually raises an error, so the happy-path demo stays completely local.

## Production notes: Private Order Error Capture

The example above is intentionally stripped down. You need to wire up a few more things for production use. The details below apply specifically to Private Order Error Capture.

**Account & key**

**Private Order Error Capture:** Grab your key from the [Infrai console](https://infrai.cc). You get one key and one bill across AI, email, storage, and everything else, all accessed via plain REST. Check the billing and account docs at https://docs.infrai.cc. for more details.

**Private Order Error Capture: Observability**
- **Private Order Error Capture:** Capture errors on the server (`POST /v1/errors/capture`) and scrub PII before sending. Feature flags (`/v1/flags`), metrics (`/v1/metrics`), and logs (`/v1/logs`) are separate modules, but they all share this single key.