# P2 — verification: requirement → evidence

Fast tests (`scripts/test.sh`, real uvicorn on ephemeral ports, no browser) are under `tests/server/`. Browser tests (`scripts/test.sh -m slow tests/e2e/…`, headless Chromium 1248 against the real, unmodified stage) are under `tests/e2e/`. Screenshots and logs from the final run are in `/srv/workdata/build-cache/khqs-evidence/p2/` (outside the repo).

| Req | Evidence |
| --- | --- |
| A1 two listeners, settings | `test_ports_and_pages::test_defaults_match…`, `::test_env_overrides…`; real run: `ss -ltn` showed `127.0.0.1:18830` and `192.168.50.216:18831` |
| A2 host guards | `test_ports_and_pages::test_unsafe_settings_are_refused` (12 cases incl. `0.0.0.0`, `::`, empty, loopback phone, non-loopback stage, reserved ports) |
| A3 phone port is a strict subset | `test_ports_and_pages::test_phone_port_serves_only_phone_routes…`, `::test_phone_port_exposes_no_stage_files…`; real run: `curl` to `192.168.50.216:18831` gave 200 for `/ticket.html`, 404 for `/`, `/play/link.js`, `/stage/assets/…`, `POST /api/start`; `192.168.50.216:18830` and `127.0.0.1:18831` refused |
| A4 stage app serves everything | same tests, stage side; `tests/e2e/test_live_games.py` |
| A5 origin/host/header guards | `test_ports_and_pages::test_origin_host_and_header_guards`, `::test_join_body_limits` |
| A6 no access log, quiet logs | `test_mock_mc_and_logs::test_no_access_log_and_server_logs_carry_no_names_or_credentials` |
| B1 byte-identical files, one injected tag | `test_ports_and_pages::test_index_is_the_stage_file_plus_exactly_one_script_tag`, `::test_ticket_gets_one_hook_in_head`, `::test_every_served_stage_file_is_byte_identical…` (all 141 allowlisted files by sha256), `::test_static_allowlist_blocks…`, `::test_injection_fails_loudly…` |
| B2 media by opaque id | `test_ports_and_pages::test_media_by_opaque_id_only` |
| B3 manifest holds | the same byte-identity test calls the manifest verifier; `test_frozen_boundary` |
| C1 stage socket | `test_sockets_and_api::test_hello_snapshot_then_stream…`, `::test_ping_and_need_snapshot…`, `::test_bad_first_message…` |
| C2 pump | `test_pump_runs_a_whole_game_with_no_stage…` (slow: whole game, real clock, no sockets); `test_mock_mc_and_logs` |
| C3 primary, race, take-over | `test_sockets_and_api::test_reconnect_race_same_cid…`, `::test_another_tab_is_a_viewer_and_take_over_is_explicit`; browser: `test_live_misc::test_stage_reload_keeps_primary…` (real reload, second tab, TAKE OVER, no flapping for 4 s) |
| C4 stage loss | `test_sockets_and_api::test_closing_every_stage_socket_does_not_stop_the_game` |
| D1–D3 phone socket | `test_sockets_and_api::test_phone_hello_views_actions…`, `::test_bad_credential…`, `::test_phone_socket_limits`, `::test_a_joined_player_without_a_phone_socket…` |
| E1–E3 API, new game | `test_sockets_and_api::test_join_start_errors…`, `::test_reset_rules_and_a_new_game_keeps_roles…`; browser: NEW SHOW in `test_live_games` |
| F1 replay hashes | `test_live_misc::test_replay_and_demo_hashes_leave_the_connector_out…` (9 replay hashes: no connector, no socket, no errors; 5 live hashes: connector on) |
| F2 LiveEngine behaviour | exercised by every browser game: queueing, snapshot, dedupe, ack, ping; reload test covers reconnect with `lastSseq` and the viewer rule |
| F3–F4 stopMc, prefetch, real music | prefetch and `av.play` run in every game; **the audio itself is not verified** (headless, see below) |
| F5 voice cue | config flag only; mock keeps the chirp |
| F6 entry hooks | pad join, start, reset in every game; start failure path not exercised |
| F7 chip, HUD, pad | chip data attributes asserted in `test_live_misc`; pad label asserted; pad plays a full game (`players1`, `players2`, `players3`) |
| F8 ticket hook | `players2`/`players3`: the phone joins through the real `ticket.html`, sees ADMITTED, lands on `/phone` |
| G1–G4 phone UI | played through in 2- and 3-player games; Q1 asserts a tap alone sends nothing (select, then LOCK IN); stale credentials end on the "NO LONGER VALID" screen (asserted after NEW SHOW); other players' data never in a phone's frames (`_phone_frames_are_private`) |
| H1–H3 mock MC | `test_mock_mc_and_logs`; games |
| I1 dev bank | `build_dev_bank` raises if `validate_bank` finds anything; media sizes read from disk |
| J1 full games 1/2/3 | `test_live_games` ×3: stage `primary` in every sample, `gate_timeouts == 0`, page errors 0, betrayal chance played with 2+ players, one phone (or the pad in the solo game) reloaded mid-game |
| J2 secrecy incl. browser frames | `test_live_games`: every stream frame the stage received equals the engine's own record; all stage snapshots plus the recorder's snapshots, phone views and MC commands go through `assert_no_leaks` |
| J3 `#demo` live | `test_live_misc::test_demo_plays_as_a_mock_on_the_live_server` |
| J4 podium, NEW SHOW | `test_live_games`: `fin_pod` images visible, NEW SHOW never visible before `game.ended`, NEW SHOW opens a new lobby (new game id) |
| J5 | port split, byte identity, origin guard, race, limits: above |

## Not verified
- **Sound.** Headless Chromium plays no audible output. The real music path (`Sound.loop('waltz')` → decoded asset on the stage's `AudioContext`) ran without errors, but nobody has heard it. The owner should listen for the clip and for it stopping on a buzz.
- **Phones on the real LAN.** The ticket → controller flow ran in an emulated mobile viewport against `127.0.0.1`. A physical phone scanning the QR is untested. The real run showed only that `192.168.50.216:18831` answers and refuses stage paths.
- **SSH tunnel from Windows.** Host-header and origin checks accept `localhost`/`127.0.0.1` on any port; a tunnel with another local port number should work but was not tried.
- **Start failure message** in the lobby (`.cb-err`) and the viewer's gate-ack silence are not exercised in a browser.
- **Duplicated tab** in Chrome copies `sessionStorage`, so it keeps the same client id and takes over the primary seat. Documented; TAKE OVER makes the other case explicit.
- The dev bank is placeholder content (P4).
