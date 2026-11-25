"""Tiny HTTP and WebSocket helpers for the server tests (stdlib + websockets)."""
import json
import urllib.error
import urllib.request

from websockets.sync.client import connect


def get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read()


def post(url, body=None, headers=None):
    h = {"content-type": "application/json", "X-KHQS": "1"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=json.dumps(body or {}).encode(), headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"null")
        except ValueError:
            return e.code, None


def ws_open(url, **kw):
    return connect(url, open_timeout=5, **kw)


def hello(role="primary", last=None):
    return json.dumps({"proto": "khqs.stage/1", "type": "stage.hello",
                       "data": {"role": role, "stageVersion": "t", "lastSseq": last, "clientTime": 1.0, "beats": {}}})
