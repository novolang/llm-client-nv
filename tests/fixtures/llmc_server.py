#!/usr/bin/env python3
"""A chat-API stand-in for the transport suite: plain HTTP and HTTPS on
loopback, written against Python's own HTTP implementation so that what
llm-client-nv puts on the wire is judged by a parser it does not share
code with.

    llmc_server.py CERT KEY PORTFILE

Binds two ephemeral ports, writes "HTTP_PORT HTTPS_PORT" to PORTFILE and
serves until killed, or for 180 seconds.

Routes (all POST unless noted):
  /echo          200 JSON of what the server received (method, path,
                 headers, body)
  /chunked       200 JSON in three chunks of a chunked body
  /sse           200 text/event-stream in chunked frames, with pauses
  /sse-json      200 application/json to a streaming request
  /status/<n>    status n, a JSON error body, Retry-After: 2
  /text-error    503 with a plain-text body
  /redirect      302 to /echo
  /stall         head, then silence for 3 s
  /truncated     Content-Length 100, 5 bytes, then close
  /empty-sse     200 event-stream, headers only, then close
  /flaky         503 the first time per process, 200 after
  /sse-close     event-stream ended by closing the socket
  /sse-dribble   a chunk delivered in three separate writes
  /interim       a 100 Continue head, then the final 200
  /garbage       bytes that are not HTTP
  /silent        close after reading the request, with no answer
  /big-sse       chunked event-stream whose first frame is 5000 bytes

An X-Route of /hangup closes the connection without reading the body.

A request may carry X-Route: <route> to pick a behaviour while posting
to the chat path the client fixes for itself.
"""
import json
import socket
import ssl
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FLAKY = {"n": 0}
LOCK = threading.Lock()

OK_BODY = json.dumps({
    "id": "chatcmpl-1", "model": "gpt-4o-mini",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "Copenhagen."},
                 "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 9, "completion_tokens": 2, "total_tokens": 11}})


ANTHROPIC_BODY = json.dumps({
    "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-haiku-4-5",
    "content": [{"type": "text", "text": "Copenhagen."}], "stop_reason": "end_turn",
    "stop_sequence": None, "usage": {"input_tokens": 9, "output_tokens": 2}})


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def send_plain(self, status, data, ctype="application/json", extra=()):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def chunked_head(self, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

    def chunk(self, data):
        self.wfile.write(b"%x\r\n" % len(data) + data + b"\r\n")
        self.wfile.flush()

    def do_POST(self):
        if self.headers.get("X-Route") == "/hangup":
            # Close without reading the body: the client's send fails.
            self.close_connection = True
            self.connection.close()
            return
        data = self.body()
        # A request may name the behaviour it wants in X-Route, so the
        # chat paths the client fixes for itself can still be steered.
        path = self.headers.get("X-Route") or self.path
        if path == "/v1/messages":
            self.send_plain(200, ANTHROPIC_BODY.encode())
        elif path == "/v1/chat/completions":
            self.send_plain(200, OK_BODY.encode())
        elif path == "/echo":
            doc = {"method": "POST", "path": path,
                   "headers": {k.lower(): v for k, v in self.headers.items()},
                   "body": data.decode("utf-8", "replace")}
            self.send_plain(200, json.dumps(doc).encode())
        elif path == "/ok":
            self.send_plain(200, OK_BODY.encode())
        elif path == "/chunked":
            self.chunked_head("application/json")
            raw = OK_BODY.encode()
            third = len(raw) // 3
            for part in (raw[:third], raw[third:2 * third], raw[2 * third:]):
                self.chunk(part)
                time.sleep(0.02)
            self.wfile.write(b"0\r\n\r\n")
        elif path in ("/sse", "/big-sse"):
            self.chunked_head("text/event-stream")
            frames = [
                {"id": "chatcmpl-9", "model": "gpt-4o-mini",
                 "choices": [{"index": 0, "delta": {"role": "assistant", "content": "Cope"}}]},
                {"choices": [{"index": 0, "delta": {"content": "nhagen"}}]},
                {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
                {"choices": [], "usage": {"prompt_tokens": 9, "completion_tokens": 3}},
            ]
            out = b""
            for f in frames:
                out += b"data: " + json.dumps(f).encode() + b"\n\n"
            out += b"data: [DONE]\n\n"
            if path == "/big-sse":
                self.chunk(b"data: " + b"x" * 5000 + b"\n\n")
            else:
                cut = len(out) // 2
                self.chunk(out[:cut])
                time.sleep(0.05)
                self.chunk(out[cut:])
            self.wfile.write(b"0\r\nX-Trailer: done\r\n\r\n")
        elif path == "/sse-close":
            # No length and no chunking: the body ends when the socket does.
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(b'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\ndata: [DONE]\n\n')
            self.wfile.flush()
            self.close_connection = True
        elif path == "/sse-dribble":
            # A chunk delivered in three writes: its size line, then
            # half its data, then the rest.
            self.chunked_head("text/event-stream")
            payload = b'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\n'
            self.wfile.write(b"%x\r\n" % len(payload))
            self.wfile.flush()
            time.sleep(0.1)
            self.wfile.write(payload[:10])
            self.wfile.flush()
            time.sleep(0.1)
            self.wfile.write(payload[10:] + b"\r\n")
            self.wfile.flush()
            time.sleep(0.05)
            self.wfile.write(b"0\r\n\r\n")
        elif path == "/interim":
            self.send_response_only(100)
            self.end_headers()
            self.send_plain(200, OK_BODY.encode())
        elif path == "/silent":
            # Read the request, then close without answering.
            self.close_connection = True
            self.connection.close()
        elif path == "/garbage":
            self.wfile.write(b"this is not http\r\n\r\n")
            self.wfile.flush()
            self.close_connection = True
        elif path == "/sse-json":
            self.send_plain(200, OK_BODY.encode())
        elif path.startswith("/status/"):
            status = int(path.split("/")[2])
            body = json.dumps({"error": {"message": "stand-in refused", "type": "invalid_request_error",
                                         "code": "context_length_exceeded"}}).encode()
            self.send_plain(status, body, extra=[("Retry-After", "2")])
        elif path == "/text-error":
            self.send_plain(503, b"upstream connect error", ctype="text/plain")
        elif path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/echo")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif path == "/stall":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "10")
            self.end_headers()
            self.wfile.flush()
            time.sleep(3)
        elif path == "/truncated":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "100")
            self.end_headers()
            self.wfile.write(b"12345")
            self.wfile.flush()
            self.close_connection = True
        elif path == "/empty-sse":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.flush()
            self.close_connection = True
        elif path == "/flaky":
            with LOCK:
                FLAKY["n"] += 1
                first = FLAKY["n"] == 1
            if first:
                self.send_plain(503, b'{"error":{"message":"try again"}}')
            else:
                self.send_plain(200, OK_BODY.encode())
        else:
            self.send_plain(404, b'{"error":{"message":"no such stand-in route"}}')


class DualStackServer(ThreadingHTTPServer):
    # `localhost` resolves to ::1 first on most hosts, and the TLS
    # client verifies the certificate against the NAME it dialled, so the
    # secure listener answers on both families.
    address_family = socket.AF_INET6


def serve(server):
    server.serve_forever()


def main():
    cert, key, portfile = sys.argv[1:4]
    plain = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    secure = DualStackServer(("::", 0), Handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    secure.socket = ctx.wrap_socket(secure.socket, server_side=True)
    for s in (plain, secure):
        threading.Thread(target=serve, args=(s,), daemon=True).start()
    with open(portfile, "w") as f:
        f.write("%d %d\n" % (plain.server_address[1], secure.server_address[1]))
    # A suite that died without killing this process must not leave it
    # behind for long.
    time.sleep(180)


main()
