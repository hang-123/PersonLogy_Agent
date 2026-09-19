# Shared contracts

该目录保存与实现语言无关的 REST / Context Pack 契约。M0 完成后，以 JSON Schema 和 OpenAPI 为事实来源生成或校验前后端类型，避免手工复制产生漂移。

## Capture event contract

`capture-event.schema.json` and `capture-event-response.schema.json` define the v1 request
and response bodies for `POST /v1/capture/events`. The request is a batch of at most 100
immutable events. Event identity is carried by
`event_id` and the source tuple; retries must reuse both the event ID and payload hash.

The response is intentionally not part of the request schema. The server returns one
result per event with one of `accepted`, `already_received`, `conflict`, `rejected`, or
`retryable`. Clients may only mark a delivery as received for the first two statuses.
