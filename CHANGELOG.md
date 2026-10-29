# Changelog

All notable changes to llm-client-nv are recorded here. The format is
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
package follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
with the pre-1.0 rule that a breaking change bumps the MINOR number.

## 0.1.0 — 2026-10-29

The **implementation**.  Every `todo()` body in the nine modules is
written.  The dependency ranges move to prompt-nv `^0.1.0` and
tokenizers-nv `^0.1.0`, the first releases that have bodies.  The suites
are green, line coverage over `src/` is 100%, and the expected values are
written by hand from the published API references, not produced by this
package.

### Breaking, against the 0.0.3 interface

- **`LlmcTransport`'s four methods take `var self`**, and `send`,
  `send_retrying`, `stream_open` and `stream_next` take `var t`.  A
  streamed exchange has to remember its connection between `llmc_open`
  and `llmc_read`, and the language refuses a write through a plain
  `self`.  An implementor writes `fn llmc_read(var self, …)`; a caller
  writes `llmcchat.send(c, var t, r)`.  The shared state is a one-slot
  list in the transport value, so every copy of it sees the same
  connection.
- **`LlmcTlsHttp` is `{ host, port, timeout_ms, var wire }`** and no longer
  has `conn`.  It dials again when an exchange has used its connection,
  because a request says `Connection: close`; `dial_tls` still connects
  at once so a refusal arrives there.  **`LlmcStdHttp` gains `var live`.**
  `LlmcLive` and `LlmcWire` are new public structs, the values in those
  slots.
- **Anthropic's `input_tokens` is the sum of the three counts** the API
  reports (`input_tokens`, `cache_read_input_tokens` and
  `cache_creation_input_tokens`), and `cached_input_tokens` is the read
  part.  The API's own `input_tokens` counts only the tokens that were not
  read from the cache, so the interface's reading ("the whole input,
  cache included") needed the sum.  `tests/llmcreply_tests.nv` asserted
  1200 for a reply reporting 1200 and a cache read of 1024; it asserts
  2224 now, with the arithmetic beside it.
- **`llmcreply.to_messages` keeps the arguments.**  A tool call is an
  assistant message that carries `name`, `call_id` and the arguments text
  in `text`.  The interface said the arguments do not survive the round
  trip through prompt-nv's message, and a conversation built that way
  could not be sent: both providers refuse a tool result whose call was
  not made.  The encoders now turn those messages back into
  `tool_calls` and `tool_use` blocks, so `append_reply`,
  `append_tool_result` and `send` close an agent loop without a second
  message type.

### Added

- `llmcreq.is_call` (an assistant message that is a tool call),
  `llmcreq.is_qualified_model` (the check behind both `is_model_name`s;
  a provider prefix is refused, an Ollama tag such as `llama3:8b` is
  not) and `llmcchat.settle` (puts the forced schema tool's arguments back
  in `text` for the Anthropic dialect; `send` applies it, a caller that
  drains a stream applies it to `llmcsse.finish`'s reply).

### Behaviour the interface left open

- **`llmcreq.check`** refuses an empty model, a conversation prompt-nv
  refuses, `max_tokens` of zero, a tool result with no call id, a result
  whose call was not made before it, a call with no result after it, a
  forced tool that is not offered, and, for Anthropic, a bare JSON format
  and a schema beside tools.
- **A stream's first stop wins.**  Anthropic names the reason on
  `message_delta` and ends with a bare `message_stop`, which is read as an
  end of turn; the later one does not turn `max_tokens` into an end.
  Usage merges: a field the newer report leaves at zero keeps its earlier
  value.  A tool call that follows a text block starts at index 1, and the
  empty slot at 0 is not a call.
- **`stream_open` refuses a reply that is not an event stream**, naming
  the content type it got: a server that ignores `stream` would otherwise
  read as a truncated stream.  `send` refuses a request that streams.
- **`stream_next` answers `LlmcStreamTruncated` when the peer closes before
  a stop**, and an empty step when it closes after one.
- **An OpenAI reply with tool calls and `finish_reason: "stop"`** is read as
  a tool-use turn, because the results are still owed.  Arguments sent as
  an object (Ollama does) are kept as text.
- **`LlmcOverloaded` waits at least half the ceiling**, and a rate limit
  waits for the reset of the bucket that reports zero remaining.
- **`retry_after_from` takes Unix milliseconds**, because an HTTP date is a
  wall-clock time; `now_ms` is the monotonic clock and is for durations.
- **The Anthropic reset headers are RFC 3339 times**, which need a clock to
  become a delay, so `limits_of` reads them as absent (-1) and the OpenAI
  duration spellings and `Retry-After` as delays.
- Defaults: three attempts, a 500 ms base, a 30 s ceiling and a
  120 second whole-request deadline.

### Known

- **`LlmcStdHttp` decodes chunked bodies itself.**  The standard library's
  `HttpReplyReader.read` returns the chunk size lines with the data
  (`http-reply-reader-read-hands-back-the-chunk-framing-of-a-chunked-body`).
  The decoder is http-codec-nv's reader, primed with a chunked head; the
  site carries the workaround tag.
- **A failed TLS read leaks its buffer in the runtime**
  (`tls-recv-leaks-its-receive-buffer-when-the-read-fails`).  Three tests
  in `tests/llmcnet_tests.nv` read until the peer closes, pass their
  assertions and fail the run's leak check; `tests/coverage.sh` runs with
  the check off, as the other transport suites do.
- **A method call straight on a struct field leaks its receiver**
  (`a-method-call-on-a-struct-field-leaks-the-receiver`).  Three sites
  bind the field to a local first and carry the workaround tag.
- **`tls.recv` cannot tell a receive deadline from an abrupt close**
  (`tls-recv-cannot-tell-a-receive-deadline-from-an-abrupt-close`).  An
  empty read is a close when the detail says the peer ended and a
  deadline otherwise; the site carries the workaround tag.
- The package has no device claim.  It is `host`.

## 0.0.3 — 2026-09-28

The dependency ranges move to the releases published on 2026-09-28:
prompt-nv `^0.0.2`, schema-nv `^0.1.0`, tokenizers-nv `^0.0.2` and
http-codec-nv `^0.1.0`.  Nothing in this package's own interface
changed.

### Fixed

- `tests/llmcchat_tests.nv`: the scripted transport's `llmc_read`
  returns `list.clone(self.body)` rather than `self.body`.  A plain
  return hands the caller a list it may write, and under SPEC § 4.1's
  reference semantics for lists that list has to be a new value or a
  copy, not a field of `self` (E2038), so the suite stopped before its
  first test.

## 0.0.2 — 2026-09-15

README rewritten to the package README style guide (docs/writing-a-readme.md); no change to the interface.

The schema-nv range moves to `^0.0.2`, the version whose `SchFault`
carries the `impl Error` that `Result<_, scherror.SchFault>` has
required since SPEC § 3.4.  Nothing in this package's own interface
changed.

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
