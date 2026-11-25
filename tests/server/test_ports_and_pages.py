"""The 18830/18831 split, injection byte-identity, static allowlist, media route, origin guard."""
import hashlib
import json
from pathlib import Path

import pytest
from websockets.exceptions import InvalidStatus, InvalidHandshake

from khqs.server import pages
from khqs.server.app import PHONE_PATHS, STAGE_ONLY_PATHS
from khqs.server.settings import Settings, SettingsError
from net import get, post, ws_open

REPO = Path(__file__).resolve().parents[2]
STAGE = REPO / "stage"


# ---------------------------------------------------------------- settings guards
def test_defaults_match_the_readme_and_the_owner_decision():
    s = Settings()
    assert (s.stage_host, s.stage_port, s.phone_host, s.phone_port) == ("127.0.0.1", 18830, "192.168.50.216", 18831)
    assert s.validate() is s and s.join_url == "http://192.168.50.216:18831/ticket.html"


@pytest.mark.parametrize("kw", [dict(phone_host="0.0.0.0"), dict(phone_host="::"), dict(phone_host=""), dict(phone_host="lan.example"),
                                dict(phone_host="127.0.0.1"), dict(stage_host="192.168.50.216"), dict(stage_host="0.0.0.0"),
                                dict(stage_port=8814), dict(phone_port=18815), dict(stage_port=18817), dict(phone_port=18818),
                                dict(phone_port=18830)])
def test_unsafe_settings_are_refused(kw):
    with pytest.raises(SettingsError):
        Settings(**kw).validate()


def test_env_overrides_and_loopback_phone_only_with_the_test_switch():
    s = Settings.from_env({"KHQS_PHONE_HOST": "10.0.0.5", "KHQS_PHONE_PORT": "19000", "KHQS_STAGE_PORT": "19001", "KHQS_SEED": "5"})
    assert (s.phone_host, s.phone_port, s.stage_port, s.seed) == ("10.0.0.5", 19000, 19001, 5)
    with pytest.raises(SettingsError):
        Settings.from_env({"KHQS_PHONE_HOST": "0.0.0.0"})
    assert Settings.from_env({"KHQS_PHONE_HOST": "127.0.0.1", "KHQS_ALLOW_LOOPBACK_PHONE": "1"}).allow_loopback_phone


# ---------------------------------------------------------------- port split
def urls(srv):
    s = srv.settings
    return f"http://127.0.0.1:{s.stage_port}", f"http://127.0.0.1:{s.phone_port}"


def test_phone_port_serves_only_phone_routes_and_stage_port_serves_everything(server):
    stage, phone = urls(server)
    for path in PHONE_PATHS:
        if path in ("/api/join", "/ws/phone"):
            continue
        assert get(phone + path)[0] == 200, f"phone port should serve {path}"
        assert get(stage + path)[0] == 200, f"stage port should serve {path}"
    for path in STAGE_ONLY_PATHS:
        if path in ("/ws/stage", "/ws/mc", "/api/start", "/api/reset", "/api/mc/connect", "/api/mc/disconnect"):
            continue
        assert get(stage + path)[0] == 200, f"stage port should serve {path}"
        assert get(phone + path)[0] == 404, f"phone port must NOT serve {path}"
    for path in ("/api/start", "/api/reset"):
        assert post(phone + path, {})[0] in (404, 405), path
        assert post(stage + path, {})[0] == 200
    assert post(phone + "/api/join", {"name": "A"})[0] == 200  # join is a phone route
    # websockets: /ws/stage is not reachable on the phone port; /ws/phone is on both
    with pytest.raises((InvalidStatus, InvalidHandshake)):
        ws_open(f"ws://127.0.0.1:{server.settings.phone_port}/ws/stage")
    for port in (server.settings.stage_port, server.settings.phone_port):
        ws = ws_open(f"ws://127.0.0.1:{port}/ws/phone")
        ws.close()


def test_phone_port_exposes_no_stage_files_or_operator_actions(server):
    _, phone = urls(server)
    for path in ("/", "/index.html", "/stage.js", "/stage.css", "/sound.js", "/assets/manifest.js", "/assets/lobby.webp",
                 "/play/link.js", "/stage/assets/a-3f9c1d2e7b40", "/tools/make_loop.py", "/README.md", "/api/config", "/api/state"):
        assert get(phone + path)[0] == 404, path


# ---------------------------------------------------------------- injection and byte identity
def test_index_is_the_stage_file_plus_exactly_one_script_tag(server):
    stage, _ = urls(server)
    st, headers, body = get(stage + "/")
    orig = (STAGE / "index.html").read_bytes().decode()
    anchor = '<script src="mock-engine.js"></script>'
    assert st == 200 and body.decode() == orig.replace(anchor, anchor + '\n<script src="/play/link.js"></script>')
    assert body.decode().index("mock-engine.js") < body.decode().index("/play/link.js") < body.decode().index("src=\"qr.js\"")
    assert get(stage + "/index.html")[2] == body
    assert headers["cache-control"] == "no-store"


def test_ticket_gets_one_hook_in_head(server):
    for base in urls(server):
        st, _, body = get(base + "/ticket.html")
        orig = (STAGE / "ticket.html").read_bytes().decode()
        assert st == 200 and body.decode() == orig.replace("</head>", '<script src="/play/ticket-hook.js"></script>\n</head>')
        assert body.decode().index("ticket-hook.js") < body.decode().index("KHQS_TICKET_JOIN || demoJoin")


def test_every_served_stage_file_is_byte_identical_and_the_manifest_still_holds(server):
    stage, _ = urls(server)
    served = []
    for rel in sorted(pages.STATIC_TOP) + sorted(p.relative_to(STAGE).as_posix() for p in (STAGE / "assets").rglob("*") if p.is_file()):
        p = pages.static_path(STAGE, rel)
        assert p is not None, rel
        st, _, body = get(f"{stage}/{rel}")
        assert st == 200 and hashlib.sha256(body).digest() == hashlib.sha256(p.read_bytes()).digest(), rel
        served.append(rel)
    assert len(served) > 120
    from manifest_check import verify_manifest
    assert verify_manifest(REPO) == []


def test_static_allowlist_blocks_tools_docs_hidden_and_traversal(server):
    stage, _ = urls(server)
    for rel in ("tools/make_loop.py", "tools/sound_lab.html", "README.md", "CREDITS.md", "index.html.bak", "assets/../tools/make_loop.py",
                "../MANIFEST.sha256", "assets/../../docs/HANDOFF.md", ".git/config", "assets/.hidden", "assets/", "assets", "nope.js", "stage.py"):
        assert pages.static_path(STAGE, rel) is None, rel
    for path in ("/tools/make_loop.py", "/README.md", "/MANIFEST.sha256", "/docs/HANDOFF.md", "/interface/KHQS_STAGE_INTERFACE.md", "/media/bwv565.mp3"):
        assert get(stage + path)[0] == 404, path


def test_injection_fails_loudly_when_an_anchor_is_missing_or_doubled():
    with pytest.raises(pages.InjectionError):
        pages.inject_once("<html></html>", pages.INDEX_ANCHOR, pages.INDEX_TAG, True)
    with pytest.raises(pages.InjectionError):
        pages.inject_once(pages.INDEX_ANCHOR * 2, pages.INDEX_ANCHOR, pages.INDEX_TAG, True)


def test_link_js_carries_config_and_the_replay_guard(server):
    stage, _ = urls(server)
    st, h, body = get(stage + "/play/link.js")
    text = body.decode()
    assert st == 200 and "__KHQS_CONFIG__" not in text and server.settings.join_url in text
    assert "act=|step=|opening|showtime|clean|verdict=|demo|finale=|trans=" in text


# ---------------------------------------------------------------- media
def test_media_by_opaque_id_only(server):
    stage, _ = urls(server)
    st, h, body = get(stage + "/stage/assets/a-3f9c1d2e7b40")
    assert st == 200 and h["content-type"] == "audio/mpeg" and body == (REPO / "media" / "danse_macabre.mp3").read_bytes()
    assert "content-disposition" not in h
    assert "danse" not in json.dumps(h).lower() and "macabre" not in json.dumps(h).lower()
    for bad in ("a-00000000", "a-zzzzzzzz", "danse_macabre.mp3", "a-3f9c1d2e7b40.mp3", "..", "a-3F9C1D2E7B40"):
        assert get(f"{stage}/stage/assets/{bad}")[0] == 404, bad


# ---------------------------------------------------------------- origin and host guards
def test_origin_host_and_header_guards(server):
    stage, phone = urls(server)
    port = server.settings.stage_port
    assert get(stage + "/", {"Host": "evil.example"})[0] == 403  # DNS rebinding
    assert get(stage + "/", {"Host": f"localhost:{port}"})[0] == 200
    assert post(stage + "/api/start", {}, {"X-KHQS": ""})[0] == 403  # no custom header
    assert post(stage + "/api/start", {}, {"Origin": "http://evil.example"})[0] == 403
    assert post(stage + "/api/reset", {"force": True}, {"Origin": "http://evil.example"})[0] == 403
    assert post(stage + "/api/reset", {"force": True}, {"Origin": f"http://127.0.0.1:{port}"})[0] == 200
    assert post(stage + "/api/join", {"name": "A"}, {"X-KHQS": ""})[0] == 403
    assert post(phone + "/api/join", {"name": "A"}, {"Origin": "http://evil.example"})[0] == 403
    with pytest.raises((InvalidStatus, InvalidHandshake)):
        ws_open(f"ws://127.0.0.1:{port}/ws/stage", additional_headers={"Origin": "http://evil.example"})
    with pytest.raises((InvalidStatus, InvalidHandshake)):
        ws_open(f"ws://127.0.0.1:{server.settings.phone_port}/ws/phone", additional_headers={"Origin": "http://evil.example"})
    ok = ws_open(f"ws://127.0.0.1:{port}/ws/stage", additional_headers={"Origin": f"http://127.0.0.1:{port}"})
    ok.close()


def test_join_body_limits(server):
    stage, _ = urls(server)
    assert post(stage + "/api/join", {"name": "x" * 2000})[0] == 413
    import urllib.request
    req = urllib.request.Request(stage + "/api/join", data=b"not json", headers={"X-KHQS": "1"}, method="POST")
    try:
        urllib.request.urlopen(req)
    except Exception as e:  # noqa: BLE001
        assert getattr(e, "code", None) == 400
