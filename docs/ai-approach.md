# AI Approach

This document covers the agent design rationale, tool architecture, PII compliance layer, and the reasoning behind key decisions in Simurg's AI stack.

---

## Why agents, not scripts

Most customer support bots in the Turkish market are rule-based: if the message contains "sipariş" go to branch A, else go to branch B. These fail predictably — customers don't write in flowchart language.

Simurg uses LLM agents for two reasons:

**Free-form language understanding.** A customer who writes "1024 nerede kaldı ya" and one who writes "1024 numaralı sipariş hakkında bilgi alabilir miyim" are asking the same question. Pattern matching fails both; an agent handles both correctly.

**Dynamic tool selection.** An agent decides at runtime which tools to call and in what order, based on the user's actual intent. When a shipment hasn't been created yet, the agent correctly omits the `get_shipment` call instead of returning a confusing error.

---

## Three agents, three responsibilities

Simurg runs three distinct agents. They are kept separate intentionally.

### CustomerSupportAgent

Handles inbound Telegram messages from customers. Responds in natural Turkish. Calls `get_order` and `get_shipment` to ground its responses in real data.

**Why `output_type=str`:** The response is a Telegram message — unstructured, conversational text. Structured output would impose unnecessary schema on a free-form reply.

**Why `output_retries=1`:** A string output has no validation to fail. One retry is set as a minimal safety net, not because retries are expected.

**The hallucination guard:** The system prompt explicitly prohibits the agent from producing order status or shipment information without a tool call. If `get_order` returns `None`, the agent says it couldn't find the record — it does not guess.

### ProactiveJobsAgent

Runs on a schedule (or via demo trigger). Scans for cargo anomalies and low-stock SKUs, sends notifications, and presents supplier email drafts to the owner for approval.

**Why `output_type=ProactiveRunSummary`:** This agent orchestrates multiple side effects. A structured summary lets the caller (the HTTP endpoint or the scheduler) log and verify exactly what happened — how many anomalies were found, how many messages were sent, how many were skipped as duplicates.

**Why `output_retries=2`:** Gemini occasionally wraps structured JSON output in a markdown code block. `output_retries=2` gives PydanticAI two chances to parse the response before raising an error.

**Why tools are called sequentially, not in parallel:** The Gemini 2.5 Flash free tier allows 10 requests per minute. Parallel tool calls would exhaust this limit instantly during a demo run with multiple anomalies.

### MorningBriefingAgent

Runs at 08:00 every day (APScheduler in production; `/demo/trigger-briefing` in the MVP). Collects three metrics — order count, shipment status, low-stock count — and sends a single structured summary to the owner.

**Why a separate agent from ProactiveJobsAgent:** The two agents use different tool sets and different output types (`BriefingSummary` vs `ProactiveRunSummary`). Merging them would produce a single bloated agent with a confusing system prompt that tries to describe two fundamentally different workflows. Separate agents stay readable, testable, and independently triggerable.

---

## Tool design principles

Every tool in Simurg follows three rules:

**One job.** `get_order` fetches an order. `get_shipment` fetches a shipment. There is no `get_order_with_shipment` tool. The agent composes them. This matches the KVKK "purpose limitation" principle — each tool accesses only the data it needs.

**PII-free output.** Tool return types (`OrderInfo`, `ShipmentInfo`, `ShipmentAnomaly`) never include customer names, phone numbers, or email addresses. These fields are deliberately absent from the Pydantic models, not just excluded at the query level. The LLM sees `customer_id=17`, never `Ayşe Demir`.

**Idempotent where it matters.** Tools that send messages (`send_proactive_message`, `send_owner_email_draft`) check `notification_log` before acting. A second call for the same entity within 24 hours returns `status="skipped_duplicate"` without sending anything. This decision belongs in the tool, not in the agent's reasoning — an LLM should not be trusted to remember what it sent in a previous run.

### The sub-agent pattern: `prepare_supplier_email`

`prepare_supplier_email` runs its own inner `Agent` with `output_type=SupplierEmailDraft` and `output_retries=2`. It is a tool from the perspective of `ProactiveJobsAgent`, but internally it makes its own LLM call to generate a natural-language supplier email.

This keeps `ProactiveJobsAgent`'s system prompt clean — it does not need to know anything about email tone, subject line conventions, or AI transparency disclosure. The inner agent handles all of that and returns a validated `SupplierEmailDraft` object.

---

## PII redaction layer

### What it does

Every inbound Telegram message passes through `app/security/pii.py` before any agent or LLM sees it.

```
raw_text  →  pii.redact()  →  redacted_text + pii_map
                                      ↓
                              agent.run(redacted_text)
                                      ↓
                              agent response
                                      ↓
                              pii.restore(response, pii_map)
                                      ↓
                              final message to customer
```

Redacted text uses indexed placeholders: `[TEL_REDACTED_0]`, `[IBAN_REDACTED_0]`, `[EMAIL_REDACTED_0]`. If the same message contains two phone numbers, they become `[TEL_REDACTED_0]` and `[TEL_REDACTED_1]` — each independently restorable.

### What is redacted

| Pattern | Example input | Placeholder |
|---|---|---|
| Turkish national ID (11 digits) | `12345678901` | `[TC_REDACTED_0]` |
| Turkish phone number | `0532 111 22 33` / `+90 532...` | `[TEL_REDACTED_0]` |
| IBAN (TR prefix) | `TR33 0006 1005...` | `[IBAN_REDACTED_0]` |
| Credit card (13–16 digit block) | `4111 1111 1111 1111` | `[KART_REDACTED_0]` |
| Email address | `ayse@example.com` | `[EMAIL_REDACTED_0]` |

### Why this approach satisfies KVKK

The March 2026 KVKK Active AI guidelines (Section 4.2) require that personal data be pseudonymised or masked before being processed by an AI system. The redaction layer is placed at the system boundary — between the external channel (Telegram) and any internal processing. The LLM receives only the redacted form; the original data never leaves the application server unmasked.

Logs follow the same rule. The `pii.redact()` output — not the original message — is what gets written to stdout.

---

## Human-in-the-loop design

Simurg sends two types of messages to the owner that require no confirmation: anomaly summaries and morning briefings. These are purely informational.

Supplier email drafts are different. An email sent to a real supplier is an irreversible external action with commercial consequences. The agent prepares the draft, but the owner must explicitly tap **Approve** before anything is sent.

The approval flow uses Telegram inline keyboards. When the owner taps Approve, Telegram sends a `callback_query` to the webhook. The webhook handler extracts the SKU from `callback_data`, writes to `outgoing_emails` (status `sent_mock` in the MVP), and confirms to the owner. The agent is not re-invoked — the callback is handled by a deterministic Python function, not LLM reasoning.

This is intentional. HITL decisions should not involve an LLM. The agent's job is to prepare and present. The decision and its consequences belong to the human.

---

## LLMProvider abstraction

No agent in Simurg imports a model client directly. Every agent calls:

```python
from app.llm.provider import get_llm_model_string

agent = Agent(model=get_llm_model_string(), ...)
```

`get_llm_model_string()` reads `LLM_PROVIDER` and `LLM_MODEL` from environment config and returns a PydanticAI-compatible model string (e.g. `"gemini:gemini-2.5-flash"`).

In Phase 3, a domestic Turkish LLM will be evaluated as an alternative provider. When that time comes, swapping providers is a one-line change in `.env` — zero changes to agent code, system prompts, or tool definitions.

---

## Framework choice: PydanticAI

Simurg uses PydanticAI 1.93 (pinned). Key reasons:

**Native async.** Every FastAPI route is `async def`. PydanticAI's agent loop is async-native — no `asyncio.run()` wrappers, no thread pool workarounds.

**Structured output with validation and retries.** `output_type=ProactiveRunSummary` with `output_retries=2` handles Gemini's occasional tendency to wrap JSON in markdown. PydanticAI parses, validates, and retries transparently.

**Type-safe tool contracts.** Tool function signatures and return types are Python type hints. PydanticAI converts them to LLM-visible JSON schemas automatically. No manual schema writing, no schema drift.

**`RunContext[AgentDeps]` dependency injection.** Tools receive the database session, Telegram token, and owner chat ID through `ctx.deps` — not through global state or module-level singletons. This makes tools testable in isolation and session lifetimes predictable.

---

## Observability

Every tool call produces a structured log line:

```
[INFO] tool_call=get_order args={"order_id":1024} duration_ms=42
[INFO] tool_call=get_shipment args={"tracking_id":"ARS-9981"} duration_ms=38
[INFO] pii_scan matches=[] input_len=34
[INFO] response_sent latency_ms=3420 chat_id=987654321
```

The `notification_log` table provides a persistent audit trail of every proactive message sent — queryable, human-readable, and used directly for idempotency checks.

For deeper tracing, setting `LOGFIRE_TOKEN` in `.env` enables PydanticAI's native Logfire integration: full agent traces with token counts, tool call timing, and retry history.
