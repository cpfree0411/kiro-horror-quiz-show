"""The server picks its question bank from a file (KHQS_BANK) and falls back to the dev bank."""
import json
from pathlib import Path

import pytest

from khqs.content.dev_bank import DEV_BANK_PATH
from khqs.server.settings import Settings
from conftest import make_settings
import net


def write(tmp_path, data):
    p = tmp_path / "bank.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_server_picks_the_bank_by_env_and_falls_back_to_the_dev_bank(tmp_path):
    assert Settings().bank_path is None
    assert Settings.from_env({"KHQS_BANK": "~/x.json"}).bank_path == Path("~/x.json").expanduser()
    import asyncio
    from khqs.server.runner import serve
    bad = write(tmp_path, {"format": "nope"})
    with pytest.raises(SystemExit) as e:
        asyncio.run(serve(make_settings(bank_path=bad)))
    assert "is not usable" in str(e.value) and "bank.format" in str(e.value)


def test_server_serves_music_from_the_bank_file(tmp_path):
    from khqs.server.runner import RunningServer
    d = json.loads(DEV_BANK_PATH.read_text(encoding="utf-8"))
    d["tracks"][0]["assetId"] = "a-0123456789ab"
    p = write(tmp_path, d)
    srv = RunningServer(make_settings(bank_path=p)).start()
    try:
        base = f"http://127.0.0.1:{srv.settings.stage_port}"
        assert net.get(base + "/stage/assets/a-0123456789ab")[0] == 200
        assert net.get(base + "/stage/assets/a-3f9c1d2e7b40")[0] == 404
        assert srv.host.bank.tracks[0].asset_id == "a-0123456789ab"
    finally:
        srv.stop()
