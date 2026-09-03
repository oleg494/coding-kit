---
name: contract-change
tier: HIGH_ASSURANCE
---
In client.py, the function `send_payload(payload)` is being updated: it must now accept an optional `timeout: float = 30.0` parameter and pass it to `transport.send(payload, timeout=timeout)`.
Update both client.py and transport.py, update the callers in api.py, and ensure test_client.py passes with test coverage for the new timeout parameter.
