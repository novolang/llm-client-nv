# Changelog

All notable changes to llm-client-nv are recorded here. The format is
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
package follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
with the pre-1.0 rule that a breaking change bumps the MINOR number.

## 0.0.2 — 2026-09-15

README rewritten to the package README style guide (docs/writing-a-readme.md); no change to the interface.

## 0.0.1 — 2026-09-12

The **interface**: every signature and every effect row, and no bodies.
`stability = "draft"`, and the release is recorded `implemented = false`.

### Added

- `llmcreply` — the reply: `LlmcStop` with one variant per way a reply
  ends, `LlmcToolCall` with the provider's arguments kept as text,
  `LlmcUsage` with the cached input named beside the total, and
  `owed_tool_results`, the package's load-bearing call.
- `llmcreq` — the request and the provider as values: two dialects as
  a field rather than a type parameter, tools, tool choice, response
  format, sampling parameters, and `check`, which refuses everything a
  dialect cannot spell before a byte travels.  The token budget, with
  the tool catalogue counted separately.
- `llmcopenai` — the OpenAI-compatible chat dialect, `[]` throughout.
- `llmcanthro` — Anthropic's Messages dialect, `[]` throughout, with
  the eleven differences from the other one each named in a function.
- `llmcsse` — the event-frame reader, feed and drain, and the
  accumulator that folds events back into one reply.
- `llmcretry` — the policy, the two providers' rate-limit headers,
  three duration spellings, and a backoff whose jitter takes its
  uniform as an argument.
- `llmchttp` — `LlmcTransport[e]`, with `LlmcTlsHttp` at `[net]` and
  `LlmcStdHttp` at `[io, net, time, async]`.
- `llmcchat` — the client: `encode` and `decode` at `[]`, `send` at
  `[e]`, `send_retrying` at `[e, time]`, the streaming pump, and
  `validate_format`.
- `llmcfault` — twelve variants, `is_retryable` and `is_caller_error`.

### Known

- **`LlmcReply.stop` is the load-bearing interface.**  A reply that hit
  the token cap is a truncated answer with no marker in it, and a reply
  that is a tool call leaves an obligation the next request must meet.
  Neither state is one a `?Str` can be in, which is what `std.llm` and
  every thin SDK wrapper answer.
- **`owed_tool_results` is published** so a loop asserts the obligation
  rather than remembering it, and `llmcreq.check` refuses the request
  that leaves one open.
- **The package reads no environment variable.**  The key is a `Str`
  the caller supplies; the README gives three reasons and names the
  variables the providers document.
- **The headline row is `[net, time]`**, and `LlmcStdHttp` is the named
  wider path at `[io, net, time, async]` — `std.http`'s `HttpClient`
  declares all four, and a library that offered only that would have
  put `[async]` on every program that asks a model a question.
- **The dialect is a value, not a type parameter**, because a program
  that read its provider from a configuration file has a `Str` at run
  time.
- **Eleven differences between the two dialects are named**, and the
  ones with no spelling — a `seed` or an unshaped JSON request against
  Anthropic — are refused rather than dropped.
- **`strict` is a provider's promise**, so `validate_format` is
  published and schema-nv is a dependency rather than a suggestion.
- **Streaming is frames a caller drains**, not a callback: `std.llm`'s
  callback degrades to a single call on the compiled leg.
- **The retry jitter takes a uniform as an argument**, so a backoff
  schedule is reproducible and a test asserts numbers.
- **No `llm-codec-nv` row is asked for**: both dialect modules are
  `core`-shaped inside this package and lift out unchanged if a second
  consumer appears.
- **An embeddings row is missing** from the grid.  `/v1/embeddings` is
  a different request with a different reply and belongs beside
  embeddings-nv rather than behind a chat client's retry policy.
- **A multimodal row is missing**, which prompt-nv's own note also
  says: `PromptMessage` is text plus a role.
- **Four `core` dependencies**: prompt-nv, schema-nv, tokenizers-nv and
  http-codec-nv.
- **No device claim.**  The package is `host`.
