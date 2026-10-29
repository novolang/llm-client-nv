# llm-client-nv

A hosted chat API takes a conversation and answers one more turn of it. Two
wire formats cover almost all of them: OpenAI's
[Chat Completions API](https://platform.openai.com/docs/api-reference/chat),
which many other servers also speak, and Anthropic's
[Messages API](https://docs.anthropic.com/en/api/messages). This package is
one client for both, in novo-lang. It is built on
[prompt-nv](https://novo-lang.org/packages/prompt-nv), whose conversation
type is the input, and on
[schema-nv](https://novo-lang.org/packages/schema-nv),
[tokenizers-nv](https://novo-lang.org/packages/tokenizers-nv) and
[http-codec-nv](https://novo-lang.org/packages/http-codec-nv).

## What it is

A **provider** is a base URL, an API key and a **dialect**, which is which
of the two wire formats the server speaks. A **request** is a model name, a
conversation, and the parameters that shape the answer. A **reply** is what
came back: the text, why it stopped, any tool calls, and the **usage**, the
token counts the provider billed.

**Tool calling** is how a model asks the program to do something. The
request carries **tool definitions**, each a name, a description and a JSON
Schema for its arguments. The model may answer with **tool calls** instead
of text. The program runs them and sends the results back as further turns,
and the model answers again. Every call carries an **id**, and the next
request must carry a result for every id the model emitted.

**Structured output** is asking for an answer in a fixed shape. The OpenAI
dialect has a `response_format` field for it. The Anthropic dialect has
none, so this package obtains a shape there by forcing a single tool whose
input schema is the shape.

**Streaming** sends the answer in pieces as it is generated, as
**server-sent events**: a stream of frames, each a set of `field: value`
lines, ending at a blank line. The format is the HTML Living Standard's
`Server-sent events` section.

**Where it runs.** The package is `host`: it has a transport in it. The
two dialects, the reply, the event reader, the retry arithmetic and the
faults are `[]` and use no host service, but this package makes no claim
for a device, and a program that wants those halves on a microcontroller
takes them from the modules directly.

A **transport** is whatever carries the bytes. This package declares a
trait for one and ships two implementations, and the effects a program
spends are the transport's.

| Transport | Effects | What it is |
| --- | --- | --- |
| `LlmcTlsHttp` | `[net]` | `std.tls` for the socket, http-codec-nv for the framing |
| `LlmcStdHttp` | `[io, net, time, async]` | the standard library's `HttpClient`, with redirects and connection reuse |

Six of the nine modules declare no effects at all. `llmcretry.now_ms` is
`[time]`, `llmchttp.dial_tls` is `[net]`, and the session calls in
`llmcchat` cost whatever the transport they are handed costs.

The two dialects differ in eleven places, and each difference is a refused
request or a wrong answer for a client that assumed the other:

| | OpenAI chat | Anthropic Messages |
| --- | --- | --- |
| System prompt | the first message in the array | a top-level field; a `system` role is refused |
| `max_tokens` | optional, with a default | required, with no default |
| Content | a string, with `tool_calls` beside it | a list of blocks, text and tool use interleaved |
| A tool result | a `tool` role with a call id | a `user` message with a tool-result block |
| "Call some tool" | `tool_choice: "required"` | `tool_choice: {"type": "any"}` |
| JSON with no schema | `response_format: {"type":"json_object"}` | no spelling |
| JSON with a schema | `json_schema` with `strict` | one forced tool whose input schema is the shape |
| A seed | `seed` | no spelling |
| Usage on a stream | only with `stream_options.include_usage` | always, on the message delta |
| Stream frames | unnamed; the kind is inside the data | named in the `event:` field |
| "At capacity" | status 503 | status 529 |

## Install

```
novo pkg add llm-client-nv
```

## Example

```novo
use llmcreq
use llmcchat
use llmchttp
use llmcreply
use promptmsg

// Ask a hosted model one question. `[net]` is the whole cost: the TLS
// transport opens the socket and http-codec-nv frames the exchange.
fn ask(key: Str, question: Str) -> Result<Str, LlmcFault> [net]
    // The key is the caller's. This package reads no environment.
    let p = llmcreq.anthropic(key)
    let c = llmcchat.client(p)

    // One user turn, with a system instruction beside it.
    let convo = promptmsg.with_system(
                    promptmsg.convo([promptmsg.user(question)]),
                    "answer in one sentence")

    // The Anthropic dialect requires a token cap, so the request
    // carries one.
    let r = llmcreq.with_params(llmcreq.request("claude-haiku-4-5", convo),
                                llmcreq.with_max_tokens(llmcreq.params(), 256))

    // The type annotation is needed: `send` is generic over the
    // transport, and a binding written from `expr!` does not close it.
    var t: LlmcTlsHttp = llmchttp.dial_tls(p, 30000)!
    let reply = llmcchat.send(c, var t, r)!

    // How the reply ended, before its text is read: one that hit the
    // cap is a prefix that reads like a whole answer.
    if llmcreply.is_truncated(reply)
        return Err(LlmcBadEncoding(llmcreply.stop_note(reply.stop)))
    Ok(reply.text)

fn main() [io, net]
    match ask("your-api-key", "what is the capital of Denmark?")
        Ok(text) => println(text)
        Err(f)   => println(f.message())
```

Build and test with `novo pkg build` and `novo test`. The transport
suite starts a stand-in chat API from `python3`, and makes its
certificate with `openssl`, so both must be on the `PATH`.

## What the package contains

| Module | Contents |
| --- | --- |
| `llmcreq` | The provider, the request and its parameters, tool definitions, the response format, the local checks, and the token estimate. |
| `llmcreply` | Why a reply ended, the tool calls it carried, the usage, and the conversions back into conversation turns. |
| `llmcopenai` | The OpenAI chat dialect: the request body, the reply, the errors and the stream frames. |
| `llmcanthro` | The Anthropic Messages dialect, the same way, with its own base URL, path and version header. |
| `llmcsse` | The server-sent event reader, and the accumulator that turns a stream of events into one reply. |
| `llmcretry` | The retry policy, the rate-limit headers, the backoff arithmetic, the idempotency key, and the one clock read. |
| `llmchttp` | The transport trait and its two implementations, plus the header and origin helpers. |
| `llmcchat` | The client: encoding, decoding, one exchange, one exchange with retries, and a streaming session. |
| `llmcfault` | The twelve ways a call fails, whether each is worth retrying, and the status it came from. |

## How to choose an entry point

**`llmcchat.send` performs one exchange.** Use it when the caller owns the
retry loop or wants none. **`send_retrying` performs the loop**, and it
sleeps between attempts, so its effects are the transport's plus `[time]`.

**`llmcchat.stream_open` and `stream_next` are a streaming session.** They
hold a `LlmcStreamState` the caller threads through its own loop, so the
loop lives where the caller wants it: a terminal repainting per delta, a
server forwarding to its own client, and an agent counting tokens each want
a different one.

**`llmcchat.encode`, `headers_for` and `decode` are the exchange taken
apart**, for a caller with a transport this package does not know, a
recorder, or a test.

**`LlmcTlsHttp` costs `[net]` and `LlmcStdHttp` costs `[io, net, time,
async]`.** Take the first unless you need redirects, connection reuse or
the standard library's chunked decoder. A library that shipped only the
second would put `[async]` on every program that asks a model a question.

**The two dialect modules are usable on their own.** `llmcopenai` and
`llmcanthro` declare no effects and take and answer JSON values, which is
what a proxy, a recorder or a server needs.

## The rules a user needs

1. **Check how a reply ended before reading its text.** A reply that hit
   the token cap is a prefix with no marker in it: the status is 200 and
   the text stops where the cap fell. `llmcreply.is_complete` is true only
   for `LlmcStopEnd` and `LlmcStopSequence`, and `is_truncated` is the
   question the other way round.
2. **A reply that is a tool call usually has no text.** `LlmcStopToolUse`
   means the turn was the calls in `tool_calls`.
3. **The next request must answer every tool call id.**
   `llmcreply.owed_tool_results` lists them and `llmcreq.check` refuses a
   request that leaves one open. The two dialects punish an unmet
   obligation differently: the Anthropic API refuses the request and names
   the id, and the OpenAI dialect accepts it and lets the model answer as
   though the tool returned nothing. The second is worse, because it
   produces a plausible sentence and no error.
4. **`llmcreq.check` runs before a byte travels.** It refuses a request
   with no `max_tokens` against the Anthropic dialect, a seed against the
   Anthropic dialect, two tools with one name, a tool name the providers
   refuse, a forced tool choice with no tools, and a conversation whose
   tool results do not match its tool calls. A client that dropped an
   unsupported field quietly would leave a caller believing a run is
   reproducible when it is not.
5. **A tool name is letters, digits, underscores and hyphens, 1 to 64
   characters.** Both providers refuse anything else.
   `llmcreq.is_tool_name` is the check.
6. **The model name is bare.** This package takes `gpt-4o-mini`, not
   `openai:gpt-4o-mini`, because the provider is the `LlmcProvider` value.
   `is_model_name` refuses the qualified form, which otherwise produces a
   404 that reads exactly like a rejected key.
7. **`strict` is a promise and not a proof.** OpenAI's own endpoint
   constrains decoding to the schema; several servers speaking the same
   dialect accept the field and prompt for it instead, and the forced-tool
   route on the Anthropic dialect can still be filled in wrongly.
   `llmcchat.validate_format` checks the reply against the schema that was
   asked for and answers which instance locations failed.
8. **An SSE frame ends at a blank line, not at a newline.** A reader that
   emitted one frame per line splits a JSON document into pieces.
9. **`data: [DONE]` is not JSON.** A reader that parsed every frame reports
   a malformed reply at the end of every successful stream.
   `llmcsse.is_done` is the check.
10. **Tool-call arguments arrive split at arbitrary byte boundaries.**
    There is a point in every tool-calling stream where the arguments are
    an unfinished JSON fragment. They accumulate as text and are parsed
    once, which is why `LlmcToolCall.arguments` is a `Str` and
    `arguments_json` is a separate call.
11. **A stream that ends with no terminal event is a truncated reply.**
    `llmcsse.finish` answers `LlmcStreamTruncated`, and `partial` is the
    accessor for a caller that wants to show the text anyway.
12. **A retry reads what the response said.** `Retry-After` (RFC 9110
    section 10.2.3) and the providers' own reset headers say how long to
    wait. `llmcretry.limits_of` reads them and `next_delay_ms` uses them. A
    client using only its own backoff either retries too early and gets a
    second refusal, or waits a minute when it was told two seconds.
13. **A 429 is two different limits.** Requests per minute and tokens per
    minute reset at different times, and one large request can exhaust the
    token budget while the request budget is untouched. `LlmcRateLimit`
    carries both.
14. **A POST that timed out may have been executed.** The completion was
    generated and billed and the reply was lost coming back, so a retry
    produces and bills a second one. `LlmcRetry.idempotency_key` is a field
    rather than a convenience, and `llmcretry.idempotency_headers` is what
    a loop sends.
15. **Status 529 is not a server error.** It is the Anthropic API saying it
    is at capacity, and its right answer is a longer wait rather than a
    faster retry. `LlmcOverloaded` is its own variant.
16. **The retry jitter takes a uniform as an argument.** A backoff schedule
    is then a pure function of the policy, the attempt and the uniform
    sequence, so a test asserts numbers rather than ranges.
17. **A token count against a hosted model is an estimate.** The provider's
    tokenizer is not published. Against a local model whose `tokenizer.json`
    the caller read it is exact. `LlmcReply.usage` is the truth in both
    cases, and it arrives after the money is spent.
18. **Tool definitions are usually the largest part of a request.** A
    thirty-tool catalogue is sent on every turn of an agent loop.
    `llmcreq.tools_tokens` counts it on its own.
19. **The key is a `Str` the caller supplies.** This package reads no
    environment variable. Reading one costs `[io]`, it is process-global
    state a test cannot set per case, and it decides for the program which
    key it uses. The names the providers document are `OPENAI_API_KEY`,
    `ANTHROPIC_API_KEY` and `GROQ_API_KEY`. `llmcreq.redacted` is published
    beside the provider value, because the second thing that happens to a
    key is that somebody prints it.
20. **`llmcreq.check_budget` takes the limit as an argument.** There is no
    table of models and context windows in this package, because such a
    table is wrong within a month and a client that shipped one would
    refuse models that exist.

## What is not included

- **Embeddings.** `/v1/embeddings` is a different request with a different
  reply. [embeddings-nv](https://novo-lang.org/packages/embeddings-nv) is
  where that arithmetic lives, and no client for it exists yet.
- **Images, audio and other non-text content.** A `PromptMessage` is text
  and a role. This package will carry more when prompt-nv does.
- **A model registry.** See rule 20.
- **A sleep outside `send_retrying`.** Every delay is a number
  `llmcretry` computes and the caller waits for.
- **Local inference.** This package talks to a server over a socket.
  [ollama-nv](https://novo-lang.org/packages/ollama-nv) talks to a local
  Ollama server, and `std.llm` runs a model through the toolchain's own
  path.
- **A microcontroller build.** The package is `host`: it has a transport in
  it.

## Related packages

- [prompt-nv](https://novo-lang.org/packages/prompt-nv) owns the
  conversation: messages, roles, templates, few-shot examples and the token
  budget. This package renders that conversation into each dialect rather
  than declaring a second message type.
- [schema-nv](https://novo-lang.org/packages/schema-nv) compiles and checks
  JSON Schema. It is what says a response format is a schema before it is
  sent, and what checks the model's answer against it afterwards.
- [tokenizers-nv](https://novo-lang.org/packages/tokenizers-nv) provides
  the token count behind `check_budget`.
- [http-codec-nv](https://novo-lang.org/packages/http-codec-nv) frames
  HTTP/1.1. It is what keeps `LlmcTlsHttp` at `[net]`.
- [ollama-nv](https://novo-lang.org/packages/ollama-nv) speaks to a local
  Ollama server, which has its own API, its own streaming shape and no API
  key.
- [agent-proto-nv](https://novo-lang.org/packages/agent-proto-nv) is the
  Model Context Protocol: what a tool server offers. This package is how a
  model is asked what to do with it.
- `std.llm` in the standard library is the one-line ask:
  `LlmClient.open(id).ask(q)`, with the key read from the environment and
  the transport behind an FFI boundary. It costs `[io, ai]`, answers
  `?Str`, keeps its last error process-wide, has no tool calling, and
  cannot tell a truncated reply from a whole one. It is the right thing for
  a script. A program moves to this package when it needs the conversation
  in its own hands, needs to know why one call failed while another is in
  flight, needs tool calling, or needs to know that a reply was cut off.
- `std.json` is the document type both dialects encode into.

## Tests

```bash
novo test tests/llmcvalue_tests.nv     # providers, requests, replies, faults
novo test tests/llmcwire_tests.nv      # the two dialects' bodies and errors
novo test tests/llmcopenai_tests.nv    # the OpenAI dialect against OpenAI's documented shapes
novo test tests/llmcanthro_tests.nv    # the Anthropic dialect against Anthropic's documented shapes
novo test tests/llmcchat_tests.nv      # the client over an in-memory transport
novo test tests/llmcreply_tests.nv     # how a reply ended and what it owes
novo test tests/llmcretry_tests.nv     # the headers, the backoff and the key
novo test tests/llmcsse_tests.nv       # framing, `[DONE]`, and split arguments
novo test tests/llmcedge_tests.nv      # the boundaries: faults, SSE grammar, checks, dates, durations
novo test tests/llmcnet_tests.nv       # both transports against a stand-in server
bash tests/coverage.sh                 # the merged line coverage over src/
```

The expected values are written out by hand from the published sources, not
produced by this package. The request bodies and the reply and stream
shapes are the examples in OpenAI's and Anthropic's API references. The
SSE grammar is the HTML Living Standard's server-sent events section. The
HTTP date is RFC 9110's own example, and the duration spellings are Go's
`time.ParseDuration`, which is what OpenAI's rate-limit headers use.

The transport suite is checked against an HTTP implementation this package
shares no code with. `tests/fixtures/llmc_server.py` is Python's own
HTTP server on loopback, plain and over TLS, and each test starts one. It
answers what it received, so the suite asserts the framing, headers and
body that `http-codec-nv` and the standard library's client actually put
on the wire. It also chunks, stalls, closes early, sends a `100 Continue`,
sends trailers and sends bytes that are not HTTP.

Because the jitter takes its uniforms as arguments, `llmcretry_tests.nv`
asserts exact delays rather than ranges. Line coverage over `src/` is 100%.

Two things in the transport suite are not this package's. A TLS read that
fails leaks its receive buffer in the runtime
(`tls-recv-leaks-its-receive-buffer-when-the-read-fails`), so three tests
that read a connection until the peer closes pass their assertions and
fail the run's leak check. And the standard library's streaming reader
returns the chunk framing of a chunked body
(`http-reply-reader-read-hands-back-the-chunk-framing-of-a-chunked-body`),
so `LlmcStdHttp` decodes the chunks itself.

## Licence

Apache-2.0. See `LICENSE`.

<!-- docs/writing-a-readme.md is the style guide for this page. -->
