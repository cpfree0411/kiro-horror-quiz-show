"""Generate interface/stage-protocol.schema.json (khqs.stage/1)."""
import json, sys

PROTO = "khqs.stage/1"
R = lambda name: {"$ref": f"#/$defs/{name}"}
INT0 = {"type": "integer", "minimum": 0}
MS = {"type": "integer", "minimum": 0, "description": "server epoch milliseconds"}

def obj(props, required=None, desc=None):
    o = {"type": "object", "properties": props, "required": list(props) if required is None else required, "additionalProperties": False}
    if desc: o["description"] = desc
    return o

def nullable(s):
    return {"anyOf": [s, {"type": "null"}]}

defs = {}
defs["seatIndex"] = {"type": "integer", "enum": [0, 1, 2], "description": "Three fixed seats. 0=left, 1=middle, 2=right"}
defs["oxChoice"] = {"enum": ["O", "X"]}
defs["finalChoice"] = {"enum": ["A", "B", "C", "D"]}
defs["fanType"] = {"enum": ["vampire", "sack", "bolt", "moth", "fish", "mummy", "crone", "tophat_skull"],
                   "description": "Monster fan puppet type. Assigned by the engine at join and fixed for the game"}
defs["player"] = obj({
    "id": {"type": "string", "minLength": 1},
    "name": {"type": "string", "minLength": 1, "maxLength": 12},
    "fanType": R("fanType"),
    "score": {"type": "integer"},
    "rank": {"type": "integer", "minimum": 1, "description": "Ties share a rank"},
    "connected": {"type": "boolean"},
})
defs["seat"] = {"oneOf": [
    obj({"seat": R("seatIndex"), "status": {"const": "occupied"}, "player": R("player")}),
    obj({"seat": R("seatIndex"), "status": {"const": "vacant"}, "player": {"type": "null"}}),
]}
defs["seats"] = {"type": "array", "items": R("seat"), "minItems": 3, "maxItems": 3}
defs["phase"] = {"enum": [
    "lobby", "opening", "act_intro",
    "ox.presenting", "ox.answering", "ox.revealing_choices", "ox.betrayal", "ox.suspense", "ox.revealing_answer", "ox.settling",
    "buzzer.presenting", "buzzer.reading", "buzzer.open", "buzzer.media", "buzzer.answering", "buzzer.judging", "buzzer.hint",
    "buzzer.suspense", "buzzer.revealing_answer", "buzzer.settling",
    "final.intro", "final.category", "final.betting", "final.question", "final.answering", "final.revealing_choices",
    "final.revealing_bets", "final.suspense", "final.revealing_answer", "final.settling",
    "finale.winner", "finale.curtain", "paused", "ended"]}
defs["gate"] = obj({"id": {"type": "string", "pattern": "^g-[0-9]+$"}, "timeoutMs": {"type": "integer", "minimum": 500, "maximum": 90000, "description": "Only the opening is long (about 50 s); the rest are mostly 5-12 s"}})
defs["revealSpec"] = obj({"mode": {"enum": ["tiles", "blur", "zoom", "silhouette", "full"]},
                          "amount": {"type": "number", "minimum": 0, "maximum": 1}})
defs["mediaRef"] = obj({
    "assetId": {"type": "string", "pattern": "^a-[0-9a-f]{8,32}$", "description": "Opaque id. No names that hint at the answer"},
    "mediaType": {"enum": ["image", "audio"]},
    "reveal": R("revealSpec"),
}, required=["assetId", "mediaType"])
defs["question"] = obj({
    "id": {"type": "string", "pattern": "^q-[A-Za-z0-9-]+$"},
    "kind": {"enum": ["ox", "buzzer", "av", "final"]},
    "number": {"type": "integer", "minimum": 1, "maximum": 8, "description": "Question number in the whole game (1-8)"},
    "act": {"enum": [1, 2, 3]},
    "indexInAct": {"type": "integer", "minimum": 1, "maximum": 4, "description": "Position within the act"},
    "category": nullable({"type": "string"}),
    "text": nullable({"type": "string", "minLength": 1}),
    "textHidden": {"type": "boolean", "description": "true: the info board shows no text until the reading ends (text is null too)"},
    "choices": nullable({"type": "array", "items": {"type": "string"}, "minItems": 4, "maxItems": 4}),
    "media": nullable(R("mediaRef")),
    "hintLevel": INT0,
    "maxHintLevel": INT0,
})
defs["seatList"] = {"type": "array", "items": R("seatIndex"), "uniqueItems": True, "maxItems": 3}
defs["oxPick"] = obj({"seat": R("seatIndex"), "choice": R("oxChoice")})
defs["finalPick"] = obj({"seat": R("seatIndex"), "choice": nullable(R("finalChoice")), "description_": {}}, required=["seat", "choice"])
del defs["finalPick"]["properties"]["description_"]
defs["betReveal"] = obj({"seat": R("seatIndex"), "bet": INT0, "allIn": {"type": "boolean"}})
defs["betrayalState"] = obj({
    "seat": R("seatIndex"),
    "selection": {"enum": ["lowest", "tied_random"], "description": "tied_random: picked at random among those tied for the lowest score. Never say 'last place' on screen or in speech"},
    "status": {"enum": ["offered", "listening", "decided"]},
    "from": R("oxChoice"),
    "to": nullable(R("oxChoice")),
})
defs["roundOx"] = obj({
    "kind": {"const": "ox"},
    "submitted": R("seatList"),
    "revealedChoices": nullable({"type": "array", "items": R("oxPick")}),
    "unanimousStreak": INT0,
    "betrayal": nullable(R("betrayalState")),
})
defs["roundBuzzer"] = obj({
    "kind": {"const": "buzzer"},
    "buzzerOpen": {"type": "boolean"},
    "holder": nullable(R("seatIndex")),
    "lockedOut": R("seatList"),
    "attempts": {"type": "array", "items": obj({"seat": R("seatIndex"), "correct": {"type": "boolean"}})},
    "mediaPlaying": {"type": "boolean"},
})
defs["roundFinal"] = obj({
    "kind": {"const": "final"},
    "category": nullable({"type": "string"}),
    "betPlaced": R("seatList"),
    "answerPlaced": R("seatList"),
    "revealedChoices": nullable({"type": "array", "items": R("finalPick")}),
    "revealedBets": nullable({"type": "array", "items": R("betReveal")}),
})
defs["round"] = nullable({"oneOf": [R("roundOx"), R("roundBuzzer"), R("roundFinal")]})
defs["result"] = obj({"seat": R("seatIndex"), "correct": {"type": "boolean"}})
defs["scoreDelta"] = obj({"seat": R("seatIndex"), "delta": {"type": "integer"}, "score": {"type": "integer"}, "rank": {"type": "integer", "minimum": 1}})
defs["credit"] = obj({"title": {"type": "string"}, "author": {"type": "string"}, "performer": {"type": "string"},
                      "license": {"type": "string"}, "source": {"type": "string"}}, required=["title", "license"])
defs["standing"] = obj({"seat": R("seatIndex"), "playerId": {"type": "string", "minLength": 1},
                        "name": {"type": "string", "minLength": 1, "maxLength": 12}, "fanType": R("fanType"),
                        "score": {"type": "integer"}, "rank": {"type": "integer", "minimum": 1}, "winner": {"type": "boolean"}})
defs["assetEntry"] = obj({"assetId": {"type": "string", "pattern": "^a-[0-9a-f]{8,32}$"}, "mediaType": {"enum": ["image", "audio"]},
                          "bytes": {"type": "integer", "minimum": 1}, "durationSec": {"type": "number", "minimum": 0}},
                         required=["assetId", "mediaType", "bytes"])

defs["streamFields"] = {
    "type": "object",
    "properties": {
        "proto": {"const": PROTO},
        "type": {"type": "string"},
        "sseq": {"type": "integer", "minimum": 1, "description": "Stage stream sequence. +1 for every message sent to the stage channel in this game, no gaps"},
        "at": MS,
        "data": {"type": "object"},
        "gate": R("gate"),
    },
    "required": ["type", "data"],
}

GATED = {
    "show.opening", "act.started", "question.presented", "ox.choices_revealed", "betrayal.offered", "betrayal.decided",
    "answer.revealed", "score.settled", "buzzer.judged", "av.hint", "final.category", "final.choices_revealed",
    "final.bet_revealed", "finale.winner",
    "finale.results",  # rev 1.1 (2026-11-08)
}
EVENTS = {
    "seat.joined": obj({"seat": R("seatIndex"), "player": R("player")}),
    "seat.left": obj({"seat": R("seatIndex")}),
    "seat.connection": obj({"seat": R("seatIndex"), "connected": {"type": "boolean"}}),
    "show.opening": obj({"seats": R("seats"), "mode": {"enum": ["solo", "competitive"]}}),
    "act.started": obj({"act": {"enum": [1, 2, 3]}, "title": {"type": "string"}, "questionCount": {"type": "integer", "minimum": 1},
                        "assets": {"type": "array", "items": R("assetEntry")}}),
    "phase.changed": obj({"phase": R("phase"), "deadline": nullable(MS)}),
    "mc.status": obj({"status": {"enum": ["idle", "speaking", "listening", "thinking"]}}),
    "question.presented": {**obj({"question": R("question")}),
        "allOf": [{"if": {"properties": {"question": {"properties": {"kind": {"const": "buzzer"}}}}},
                   "then": {"properties": {"question": {"properties": {"textHidden": {"const": True}, "text": {"type": "null"}}}}},
                   "description": "A buzzer question's text is not sent until the reading ends"}]},
    "question.text_revealed": obj({"questionId": {"type": "string"}, "text": {"type": "string", "minLength": 1}}),
    "ox.submitted": obj({"seat": R("seatIndex")}),
    "ox.choices_revealed": obj({"choices": {"type": "array", "items": R("oxPick"), "minItems": 1, "maxItems": 3}}),
    "ox.unanimous": obj({"choice": R("oxChoice"), "streak": {"type": "integer", "minimum": 1}}),
    "betrayal.offered": obj({"seat": R("seatIndex"), "selection": {"enum": ["lowest", "tied_random"]}, "currentChoice": R("oxChoice"),
                             "tiedSeats": R("seatList")}),
    "betrayal.listening": obj({"seat": R("seatIndex")}),
    "betrayal.decided": obj({"seat": R("seatIndex"), "from": R("oxChoice"), "to": R("oxChoice"), "changed": {"type": "boolean"}}),
    "answer.suspense": obj({"questionId": {"type": "string"}}),
    "answer.revealed": obj({"questionId": {"type": "string"},
                            "answer": {"anyOf": [R("oxChoice"), R("finalChoice"), {"type": "string", "minLength": 1}]},
                            "answerText": nullable({"type": "string"}),
                            "results": {"type": "array", "items": R("result")},
                            "credit": nullable(R("credit"))}),
    "score.settled": obj({"deltas": {"type": "array", "items": R("scoreDelta"), "maxItems": 3}, "leadChange": {"type": "boolean"}}),
    "buzzer.armed": obj({"questionId": {"type": "string"}}),
    "buzzer.pressed": obj({"seat": R("seatIndex"), "mediaInterrupted": {"type": "boolean"}, "mcInterrupted": {"type": "boolean"}}),
    "buzzer.answer_heard": obj({"seat": R("seatIndex"), "text": {"type": "string"}}),
    "buzzer.judged": obj({"seat": R("seatIndex"), "correct": {"type": "boolean"}, "lockedOut": R("seatList")}),
    "av.play": obj({"assetId": {"type": "string", "pattern": "^a-[0-9a-f]{8,32}$"}, "level": INT0,
                    "startSec": {"type": "number", "minimum": 0}, "endSec": {"type": "number", "minimum": 0}}),
    "av.hint": obj({"level": {"type": "integer", "minimum": 1}, "media": R("mediaRef")}),
    "final.category": obj({"category": {"type": "string", "minLength": 1}}),
    "final.bet_placed": obj({"seat": R("seatIndex")}),
    "final.bets_locked": obj({}),
    "final.answer_placed": obj({"seat": R("seatIndex")}),
    "final.answers_locked": obj({}),
    "final.choices_revealed": obj({"choices": {"type": "array", "items": R("finalPick"), "minItems": 1, "maxItems": 3}}),
    "final.bet_revealed": obj({"seat": R("seatIndex"), "bet": INT0, "allIn": {"type": "boolean"}, "remaining": INT0}),
    "finale.winner": obj({"winners": {"type": "array", "items": R("seatIndex"), "minItems": 1}, "tie": {"type": "boolean"},
                          "finalScores": {"type": "array", "items": R("scoreDelta")}}),
    # rev 1.1 (2026-11-08): only new message types added. Existing message fields are unchanged.
    "finale.results": obj({
        "mode": {"enum": ["solo", "competitive"]},
        "winners": {"type": "array", "items": R("seatIndex"), "minItems": 1, "uniqueItems": True},
        "tie": {"type": "boolean"},
        "standings": {"type": "array", "minItems": 1, "maxItems": 3, "items": R("standing"),
                      "description": "Ascending rank (ties by seat number). The stage finale is drawn from this array alone"},
    }),
    "mc.caption": obj({
        "utteranceId": {"type": "string", "pattern": "^u-[0-9]+$", "description": "One MC utterance. A later message with the same id replaces the earlier text"},
        "text": {"type": "string", "minLength": 1, "maxLength": 300, "description": "MC sentence heard so far (cumulative). The engine filters out unrevealed answers and hidden text"},
        "final": {"type": "boolean", "description": "true: this utterance is complete"},
    }),
    "game.paused": obj({"reason": {"enum": ["host", "mc_recovery", "stage_lost", "engine"]}}),
    "game.resumed": obj({}),
    "game.ended": obj({}),
}

engine_refs = []
for t, data in EVENTS.items():
    name = "ev:" + t
    props = {"type": {"const": t}, "data": data}
    m = {"allOf": [R("streamFields")], "properties": props, "unevaluatedProperties": False}
    if t in GATED:
        m["required"] = ["gate"]
        m["description"] = "Gate event: the stage sends stage.beat_done when its animation ends"
    else:
        props["gate"] = False
    defs[name] = m
    engine_refs.append(R(name))

defs["ev:snapshot"] = {
    "allOf": [R("streamFields")],
    "properties": {
        "type": {"const": "snapshot"},
        "gate": False,
        "data": obj({
            "game": obj({
                "id": {"type": "string"},
                "mode": {"enum": ["solo", "competitive"]},
                "act": {"enum": [0, 1, 2, 3, 4]},
                "phase": R("phase"),
                "phaseStartedAt": MS,
                "deadline": nullable(MS),
                "questionNo": INT0,
                "questionTotal": {"const": 8},
            }),
            "seats": R("seats"),
            "question": nullable(R("question")),
            "round": R("round"),
            "mc": obj({"status": {"enum": ["idle", "speaking", "listening", "thinking"]}}),
            "openGate": nullable(obj({"id": {"type": "string", "pattern": "^g-[0-9]+$"}, "type": {"type": "string"}})),
            "revealedAnswer": nullable({"type": "string"}),
        }),
    },
    "description": "Full current state. sseq means 'the stream up to this point' and is not incremented (resend reference point).",
    "unevaluatedProperties": False,
}
engine_refs.insert(0, R("ev:snapshot"))

defs["control:pong"] = obj({"proto": {"const": PROTO}, "type": {"const": "pong"},
                            "data": obj({"clientTime": {"type": "number"}, "serverTime": MS})})
defs["control:error"] = obj({"proto": {"const": PROTO}, "type": {"const": "error"},
                             "data": obj({"code": {"type": "string"}, "message": {"type": "string"}})})
engine_refs += [R("control:pong"), R("control:error")]
defs["engineStreamMessage"] = {"oneOf": [r for r in engine_refs if "control:" not in r["$ref"]]}
defs["engineMessage"] = {"oneOf": engine_refs, "description": "Engine → stage. Stream messages carry sseq/at; control messages (pong, error) have no sseq"}
defs["engineMessageWire"] = {"allOf": [R("engineMessage"),
                                       {"if": {"properties": {"type": {"enum": ["pong", "error"]}}},
                                        "then": {"required": ["proto"]},
                                        "else": {"required": ["proto", "sseq", "at"]}}]}

def smsg(t, data):
    return obj({"proto": {"const": PROTO}, "type": {"const": t}, "data": data})
defs["st:hello"] = smsg("stage.hello", obj({
    "role": {"enum": ["primary", "viewer"], "description": "Only the primary's gate replies count"},
    "stageVersion": {"type": "string"},
    "lastSseq": nullable({"type": "integer", "minimum": 0}),
    "clientTime": {"type": "number"},
    "beats": {"type": "object", "additionalProperties": {"type": "integer", "minimum": 0}, "description": "Event type → expected animation length (ms)"},
}))
defs["st:beat_done"] = smsg("stage.beat_done", obj({"gate": {"type": "string", "pattern": "^g-[0-9]+$"}, "sseq": {"type": "integer", "minimum": 1},
                                                      "skipped": {"type": "boolean", "description": "true if it jumped straight to the rest pose"}},
                                                     required=["gate", "sseq"]))
defs["st:need_snapshot"] = smsg("stage.need_snapshot", obj({"lastSseq": nullable({"type": "integer", "minimum": 0}),
                                                             "receivedSseq": nullable({"type": "integer", "minimum": 1})}))
defs["st:media_ready"] = smsg("stage.media_ready", obj({"assetIds": {"type": "array", "items": {"type": "string"}}}))
defs["st:media_ended"] = smsg("stage.media_ended", obj({"assetId": {"type": "string"}, "level": INT0,
                                                         "reason": {"enum": ["ended", "interrupted", "error"]},
                                                         "positionSec": {"type": "number", "minimum": 0}}))
defs["st:ping"] = smsg("stage.ping", obj({"clientTime": {"type": "number"}}))
defs["stageMessage"] = {"oneOf": [R(k) for k in defs if k.startswith("st:")], "description": "Stage → engine"}

# Mock-engine scenario files
defs["scenario"] = obj({
    "$schema": {"type": "string"},
    "name": {"type": "string", "pattern": "^[a-z0-9-]+$"},
    "title": {"type": "string"},
    "description": {"type": "string"},
    "steps": {"type": "array", "minItems": 1, "items": {"oneOf": [
        obj({"delayMs": INT0, "send": R("engineMessage"), "note": {"type": "string"}}, required=["send"]),
        obj({"delayMs": INT0, "await": {"enum": ["stage.media_ended", "stage.beat_done", "stage.media_ready"]},
             "timeoutMs": {"type": "integer", "minimum": 100}, "note": {"type": "string"}}, required=["await", "timeoutMs"]),
        obj({"label": {"type": "string", "pattern": "^[a-z0-9-]+$"}, "note": {"type": "string"}}, required=["label"]),
    ]}},
}, required=["name", "title", "steps"])

schema = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://kiro-horror-quiz-show.local/schema/stage-protocol.schema.json",
    "title": "Kiro Horror Quiz Show — Stage protocol khqs.stage/1",
    "description": "Engine (server) ↔ stage (main screen) WebSocket messages. The root validates one message. Scenario files use #/$defs/scenario.",
    "oneOf": [R("engineMessageWire"), R("stageMessage")],
    "$defs": defs,
}
json.dump(schema, open(sys.argv[1], "w", encoding="utf-8", newline="\r\n"), ensure_ascii=False, indent=2)
print("events:", len(EVENTS) + 1, "gated:", len(GATED), "stage msgs:", sum(k.startswith("st:") for k in defs))
