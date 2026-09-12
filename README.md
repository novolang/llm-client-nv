# llm-client-nv

**Status: NOT IMPLEMENTED — interface only.**

Every public function below is published with its signature and its
effect row, and every body is `todo()`.  Installing this package works;
calling it panics with `not implemented`.

## What this is

One client for the hosted chat APIs.  The two wire dialects that
matter — the OpenAI-compatible chat API and Anthropic's Messages API —
as sans-IO codec modules over the standard library's JSON value:
request bodies, streaming event frames, tool-call and tool-result
turns, usage.  prompt-nv's conversation goes in, a reply value comes
out, retries know what the rate-limit headers said, and a token budget
is checked before the round trip rather than after it.

It is not an agent framework, not a prompt library and not an inference
engine.  novoagent is the first, prompt-nv is the second, and
orbit/novollm is the third.

## Adding it, and checking it

```bash
novo pkg add llm-client-nv    # into your novo.toml
novo pkg build                # type- and effect-check the package
novo test --isolate tests/llmcreply_tests.nv
```

`novo test` is red today and that is the point of the release: every
assertion fails with `not implemented: llm-client-nv.<module>.<fn>`.
They turn green one at a time as bodies land.

## The one example that will work

```novo
use llmcchat
use llmcfault
use llmcreq
use llmchttp
use llmcreply
use promptmsg

// One turn against a hosted model, over the narrow transport.
// `[net]` and nothing else: `std.tls` connects and http-codec-nv does
// the framing.
fn ask(key: Str, question: Str) -> Result<Str, LlmcFault> [net]
    let p = llmcreq.anthropic(key)
    let c = llmcchat.client(p)

    let convo = promptmsg.with_system(
                    promptmsg.convo([promptmsg.user(question)]),
                    "answer in one sentence")
    let r = llmcreq.with_params(llmcreq.request("claude-haiku-4-5", convo),
                                llmcreq.with_max_tokens(llmcreq.params(), 256))

    let t = llmchttp.dial_tls(p, 30000)!
    let reply = llmcchat.send(c, t, r)!

    // READ THIS BEFORE THE TEXT.  A reply that hit the cap is a prefix
    // that reads exactly like an answer.
    if llmcreply.is_truncated(reply)
        return Err(LlmcBadEncoding(llmcreply.stop_note(reply.stop)))
    Ok(reply.text)
```

The key comes from the caller.  This package reads no environment
variable, and the section below says why.

## The layer, and why

`host`, and seven of the nine modules declare nothing.

| module | row | why |
| --- | --- | --- |
| `llmcfault` | `[]` throughout | a fault is a value built from a status and a body |
| `llmcreq` | `[]` throughout | the request, the provider, and the token count |
| `llmcreply` | `[]` throughout | the reply, and the two states a `Str` cannot be in |
| `llmcopenai` | `[]` throughout | the OpenAI chat dialect; sans-IO by construction |
| `llmcanthro` | `[]` throughout | the Anthropic Messages dialect, likewise |
| `llmcsse` | `[]` throughout | the event-frame reader, feed and drain |
| `llmcretry.now_ms` | `[time]` | the one function in the package that reads a clock |
| everything else in `llmcretry` | `[]` | the policy, the headers and the delay arithmetic |
| `llmchttp.dial_tls` | `[net]` | `std.tls`'s own row |
| `LlmcTlsHttp`'s methods | `[net]` | TLS plus http-codec-nv's `[]` framing |
| `LlmcStdHttp`'s methods | `[io, net, time, async]` | `std.http`'s `HttpClient` declares all four |
| every session call in `llmcchat` | `[e]` | effect-POLYMORPHIC: whatever the transport costs |
| `llmcchat.send_retrying` | `[e, time]` | it sleeps between attempts, and a sleep is `[time]` |

`layer = "host"` and **not** `layer = "core"` with `host_modules`.  The
narrower declaration is for a package whose *subject* is the pure half.
This package's subject is talking to a server; the dialects are here
because a request has to be encoded before it travels.

**The headline row is `[net, time]`, and the wide transport is named
rather than hidden.**  A program that uses `LlmcTlsHttp` spends `[net]`
for the socket and `[time]` for the clock and the sleep, and nothing
else.  A program that wants redirects, connection reuse and the
standard library's chunked decoder uses `LlmcStdHttp` and spends
`[io, net, time, async]`, because that is `HttpClient.send`'s own row.
Publishing both is the reason `LlmcTransport[e]` exists: a library that
shipped only the second would have put `[async]` on the row of every
program that asks a model a question, including a synchronous batch job
and a one-shot in a CLI.

## The load-bearing interface

**`LlmcReply.stop`, and `llmcreply.owed_tool_results` beside it.**

`std.llm` answers `?Str`.  So does the convenience accessor on every
provider SDK, and so does nearly every thin wrapper anybody writes over
one.  A `Str` cannot be in the two states a chat reply is most often
in, and **both of them are invisible in the text**.

**A reply that hit the token cap is a truncated answer with no marker
in it.**  The status is 200, `content` is a string, and it stops
wherever the cap fell — sometimes mid-word, sometimes at a sentence
boundary that happened to land there.  A summariser that stored it
stored half a summary.  A structured-output call that hit the cap
produced JSON with no closing brace, and the parse failure gets
reported against the model's competence rather than against the
caller's own `max_tokens`.

**A reply that is a tool call has no text at all**, and the
conversation is now in a state with an obligation in it: the very next
request must carry a result for *every* call id the model emitted.  The
two dialects punish an unmet obligation differently — Anthropic refuses
the next request with a 400 naming the id, and the OpenAI dialect
accepts it and lets the model answer as though the tool had returned
nothing.  The second is the worse failure, because it produces a
plausible sentence and no error anywhere.

So `LlmcReply` carries `stop`, `text`, `tool_calls` and `usage`
together; `llmcreply.is_complete` is one call; and
`owed_tool_results` is **published**, so an agent loop asserts the
obligation rather than remembering it.  `llmcreq.check` is the same
rule at the other end: it refuses a request whose conversation leaves
an obligation open, before the bytes go out.

## What `std.llm` keeps, and how a program moves

`std.llm` is not replaced and this package does not wrap it.  They sit
at different levels, and the table is the whole of the difference.

| | `std.llm` | llm-client-nv |
| --- | --- | --- |
| shape | a handle: `open`, `ask`, `session`, `chat` | values: a provider, a request, a reply |
| transport | a curl subprocess, LLVM only, not embedded | your transport, through `LlmcTransport[e]` |
| effects | `[io, ai]` | `[net, time]`, or the transport's |
| the key | read from `ANTHROPIC_API_KEY` and its siblings | a `Str` the caller supplies |
| a failure | `?Str`, plus a **process-wide** `last_error` | `LlmcFault`, per call, twelve variants |
| history | inside the session handle, across an FFI boundary | a `PromptConvo` the caller owns |
| tool calling | `with_tools` is **not implemented** and always answers `None` | tool calls and results as values, both dialects |
| streaming | a callback, degraded on the compiled leg to one call | frames a caller drains, with the loop where the caller wants it |
| structured output | `ask_json`, which parses and checks nothing | schema-nv's compiled schema, and `validate_format` |
| a truncated reply | indistinguishable from a whole one | `LlmcStopMaxTokens` |

**What `std.llm` keeps**, and should: the one-line ask.
`LlmClient.open("anthropic:claude-haiku-4-5").ask(q)` is three tokens of
ceremony for a script, it needs no dependency, and it works.  The
handle, the subprocess behind it and the `[io, ai]` row are the price
of that, and they are the right price for the thing it is.

**How a program moves.**  A program outgrows it at the first of these:
it needs to know *why* a call failed while another call is in flight
(`last_error` is process-wide); it needs the conversation in its own
hands (novoagent's loop comment records going through the stateless
`ask` for exactly this reason — the transcript grew twice, once inside
its control and once outside it); it needs tool calling at all; or it
needs to know that a reply was cut off.  The move is mechanical:
`llm.open(id)` becomes `llmcreq.anthropic(key)` plus
`llmcchat.client`, `llm.ask(h, q)` becomes a `PromptConvo` and
`llmcchat.send`, and `?Str` becomes `Result<LlmcReply, LlmcFault>`.
The one naming difference is the model id: `std.llm` takes
`openai:gpt-4o-mini` and this package takes the bare `gpt-4o-mini`
with the provider chosen by the `LlmcProvider` value.  `is_model_name`
refuses the qualified form by name, because sending it produces a 404
that reads exactly like a rejected key.

## The provider is a value, and this package reads no environment

`std.llm` reads the key for you.  A library should not, for three
reasons:

- **It decides for the program which key it uses.**  A program that
  talks to two accounts, or one per tenant, or through a gateway with a
  rotating token, cannot say so to an API whose key comes from a name
  it did not choose.
- **It costs `[io]` for a string the program already has.**  Reading
  the environment is `[io]` under SPEC § 5.1, so the label would land
  on every caller — including the ones passing a literal in a test.
- **It is process-global state a test cannot set per case.**  Two tests
  against two fake providers in one process cannot both have
  `OPENAI_API_KEY`.

So the caller reads it, and spends its own `[io]`:

```novo ignore
let p = llmcreq.openai(env.get("OPENAI_API_KEY") ?? "")
```

The variable names the providers document are `OPENAI_API_KEY`,
`ANTHROPIC_API_KEY` and `GROQ_API_KEY`, and that sentence is the whole
of this package's involvement with them.  `llmcreq.redacted` is
published beside the value because the second thing that happens to a
provider is that somebody prints it.

## Two dialects, one client

`LlmcDialect` is a **value**, not a type parameter.  A program that
read its provider out of a configuration file has a `Str` at run time,
and a type parameter would have made it write every call twice under a
`match`.

What the two dialects do not share, each of which is a 400 or a wrong
answer for a client that assumed the other:

| | OpenAI chat | Anthropic Messages |
| --- | --- | --- |
| system prompt | first message in the array | a top-level field; a `system` role is a 400 |
| `max_tokens` | optional, has a default | **required**, no default |
| content | a string, with `tool_calls` beside it | a block list, text and `tool_use` interleaved |
| a tool result | `role: "tool"` with `tool_call_id` | a `user` message with a `tool_result` block |
| "must call a tool" | `tool_choice: "required"` | `tool_choice: {"type": "any"}` |
| JSON with no schema | `response_format: {"type":"json_object"}` | **no spelling at all** |
| JSON with a schema | `json_schema` with `strict` | one forced tool whose input schema is the shape |
| a seed | `seed` | **no spelling at all** |
| usage on a stream | only with `stream_options.include_usage` | always, on `message_delta` |
| stream frames | unnamed; the discriminator is in the data | named in the `event:` field |
| "at capacity" | 503 | **529**, which is not a server error |

`llmcreq.check` refuses every request whose difference has no spelling,
naming both the feature and the dialect, before a byte travels.  A
client that dropped the request quietly is the failure this exists to
prevent: a `seed` silently ignored leaves a caller believing a run is
reproducible, and a `json_object` silently ignored returns prose to a
caller that will parse it.

## `strict` is a promise, and `validate_format` is the proof

OpenAI's own endpoint constrains decoding to the schema.  Several
servers that speak the same dialect accept the field and prompt for it
instead.  The Anthropic dialect has no `response_format` at all, so
this package obtains the shape there by forcing a single tool whose
input schema is the shape — which the model can still fill in wrongly.

So schema-nv is a dependency rather than a suggestion:
`llmcchat.validate_format` answers which instance locations failed, and
a caller that needs a shape checks rather than trusts.

## The retry knows what the response said

Three things a retry loop over an LLM API has to know, none of which is
derivable from the status alone:

- **The server usually says how long.**  `Retry-After`, and the
  provider's own reset headers.  A client using its own exponential
  backoff either waits four seconds when it was told six — and gets a
  second 429 — or waits sixty when it was told two.
- **A 429 is two different limits.**  Requests per minute and *tokens*
  per minute reset at different times, and one large request can
  exhaust the token bucket while the request bucket is untouched.
- **A POST that timed out may have been executed.**  The completion was
  generated and billed and the reply was lost coming back; the retry
  produces and bills a second one.  `LlmcRetry.idempotency_key` is a
  field rather than a convenience, so a loop that retries without one
  left it empty on purpose.

The jitter takes a **uniform as an argument**, the way hnsw-nv,
fake-nv and stats-nv take theirs.  rand-nv is `host` and so is this
package, so the constraint is not a layer rule here — it is a
reproducibility one: a retry schedule is a pure function of the policy,
the attempt and the uniform sequence, so `tests/llmcretry_tests.nv`
asserts numbers instead of ranges.

## Streaming is frames, not a callback

`std.llm.stream` takes a callback, and its own page records the cost:
on the compiled leg the whole reply arrives in one call, so a program
written against it is a program whose streaming silently is not.

A callback also decides for the caller where the loop lives, which is
the one decision a library should not make — a terminal repainting per
delta, an HTTP server forwarding to its own client and an agent
counting tokens all want different loops.  So `llmcsse` is feed and
drain, `LlmcStreamState` is a value the caller threads, and the three
things a wrong reader gets wrong quietly are each an assertion in
`tests/llmcsse_tests.nv`:

- **A frame ends at a blank line**, not at a newline; a reader that
  emitted per line splits one JSON document into pieces.
- **`data: [DONE]` is not JSON**; a reader that parsed every frame
  reports a malformed reply at the end of every *successful* stream.
- **Tool-call arguments arrive split at arbitrary byte boundaries.**
  There is a point in every tool-calling stream at which the arguments
  are `{"city": "Cope`.  They accumulate as text and are parsed once,
  which is also why `LlmcToolCall.arguments` is a `Str`.

And the one that is not quiet: **a stream that ends with no terminal
event is a truncated reply**, so `llmcsse.finish` answers a `Result`.
`partial` is the accessor for a caller that wants to show it anyway,
named so that showing it is a decision.

## The token budget, and what the number is worth

`llmcreq.check_budget` refuses a request locally, before the round
trip, rather than letting it come back as an opaque 400.  What the
count is worth depends on the model:

- against a **local** model whose `tokenizer.json` the caller read, it
  is exact;
- against a **hosted** model it is an estimate, because the provider's
  tokenizer is not published.

`LlmcReply.usage` is the truth in both cases, and it arrives after the
money is spent — which is the whole reason to estimate first.
`llmcreq.tools_tokens` is published separately because it is the number
that surprises people: a thirty-tool catalogue is sent on *every* turn
of an agent loop and is usually the largest single part of the request.
novoagent's own context manager records the same discovery from the
other side — its 33-tool catalogue pins 17 KB of a 40,000-character
budget.

## What this package does not do

- **No `llm-codec-nv` row is asked for.**  The two dialect modules are
  `core`-shaped and `[]` throughout, so the rule is kept without the
  package; they lift out unchanged if a server, a proxy or a recorder
  ever wants them.  A package whose README said "this builds a chat
  request body" is not one anybody browses to.
- **No embeddings.**  `/v1/embeddings` is a different request with a
  different reply and belongs beside embeddings-nv's arithmetic, not
  behind a chat client's retry policy.  A row for it does not exist on
  the grid; this lane's report asks for one.
- **No multimodal content.**  prompt-nv's `PromptMessage` is text plus
  a role, and that package's own note says a multimodal row is what the
  grid needs.  This package would take it the day it exists.
- **No provider registry.**  There is no table of model names and
  context windows here, because such a table is wrong within a month
  and a client that shipped one would be refusing models that exist.
  `check_budget` takes the limit as an argument for the same reason.
- **No sleep outside `send_retrying`.**  Every delay is a number
  `llmcretry` computes and the caller waits for.

## Dependencies

Four, all `core`:

- **prompt-nv** — `PromptConvo`, `PromptMessage` and `PromptRole`.  The
  project's chat message list, which `std.llm` does not have; this
  package renders it into each dialect rather than declaring a second
  one.
- **schema-nv** — compiled JSON Schema, for the structured-output
  request and for `validate_format`'s proof.
- **tokenizers-nv** — the token count behind `check_budget`.
- **http-codec-nv** — HTTP/1.1 framing, which is what keeps
  `LlmcTlsHttp` at `[net]`.

## Licence

Apache-2.0.
