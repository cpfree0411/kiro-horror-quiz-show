"""The Live session as the adapter sees it: a small async interface, the Gemini implementation, and a queue base.

The adapter (live.py) knows nothing about the SDK. Tests use a fake with the same interface; they never open a session.
The API key is read inside `GeminiTransport.connect` only, held in a local variable, and never stored, logged or echoed.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator

log = logging.getLogger("khqs.mc")


class LiveError(RuntimeError):
    """A failure with a message that is safe to show and log (no provider text, no key)."""


@dataclass(frozen=True)
class AudioOut:
    pcm: bytes  # 24 kHz mono PCM16


@dataclass(frozen=True)
class OutText:
    text: str  # model output transcription chunk


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass(frozen=True)
class Interrupted:
    pass


@dataclass(frozen=True)
class TurnComplete:
    pass


@dataclass(frozen=True)
class GoAway:
    seconds: float | None = None


@dataclass(frozen=True)
class ResumeHandle:
    handle: str


@dataclass(frozen=True)
class Closed:
    reason: str


TOOLS = (
    ("report_answer", "Report the answer a player just spoke. `heard` is exactly the words spoken, verbatim. `recognition` is clear or unclear.",
     {"heard": "string", "recognition": ["clear", "unclear"]}),
    ("report_reason", "Report the reason a player just spoke for their pick. `heard` is exactly the words spoken, verbatim.", {"heard": "string"}),
    ("report_decision", "Report whether the player said to keep their answer or switch it.", {"decision": ["keep", "switch", "unclear"]}),
    ("report_vote", "Report what the other players just said when asked whether they agree to give a hint. `heard` is exactly the words spoken, verbatim. `recognition` is clear or unclear.",
     {"heard": "string", "recognition": ["clear", "unclear"]}),
)


class QueueTransport:
    """Base: events arrive through a queue; `events()` ends after `Closed`."""

    def __init__(self) -> None:
        self._q: asyncio.Queue = asyncio.Queue()
        self.closed = False

    def push(self, ev) -> None:
        self._q.put_nowait(ev)

    async def events(self) -> AsyncIterator:
        while True:
            ev = await self._q.get()
            yield ev
            if isinstance(ev, Closed):
                return


class GeminiTransport(QueueTransport):
    def __init__(self, env_file: Path, model: str, voice: str, session_log: Path | None = None, purpose: str = "play") -> None:
        super().__init__()
        self.env_file, self.model, self.voice, self.session_log, self.purpose = Path(env_file), model, voice, session_log, purpose
        self._cm = None
        self._session = None
        self._reader: asyncio.Task | None = None

    @staticmethod
    def _safe(exc: BaseException) -> str:
        """Only the exception class and, if present, an HTTP-style code. Provider text can echo request details."""
        code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        return type(exc).__name__ + (f" ({code})" if isinstance(code, int) else "")

    async def connect(self, system_prompt: str, resume: str | None) -> None:
        from dotenv import dotenv_values
        from google import genai
        from google.genai import types as t

        key = dotenv_values(self.env_file).get("GEMINI_API_KEY")  # read now, at connect time, from the configured path
        if not key:
            raise LiveError("GEMINI_API_KEY is not set in the configured env file")
        try:
            client = genai.Client(api_key=key)
        finally:
            del key
        decls = []
        for name, desc, props in TOOLS:
            schema = {k: ({"type": "STRING", "enum": v} if isinstance(v, list) else {"type": "STRING"}) for k, v in props.items()}
            decls.append(t.FunctionDeclaration(name=name, description=desc,
                                               parameters=t.Schema(type="OBJECT", properties={k: t.Schema(**s) for k, s in schema.items()},
                                                                   required=list(props))))
        cfg = t.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=system_prompt,
            speech_config=t.SpeechConfig(voice_config=t.VoiceConfig(prebuilt_voice_config=t.PrebuiltVoiceConfig(voice_name=self.voice))),
            tools=[t.Tool(function_declarations=decls)],
            output_audio_transcription=t.AudioTranscriptionConfig(),  # the MC's own words only; player speech is never transcribed
            realtime_input_config=t.RealtimeInputConfig(automatic_activity_detection=t.AutomaticActivityDetection(disabled=True)),
            session_resumption=t.SessionResumptionConfig(handle=resume),
            context_window_compression=t.ContextWindowCompressionConfig(sliding_window=t.SlidingWindow()),
        )
        try:
            self._cm = client.aio.live.connect(model=self.model, config=cfg)
            self._session = await self._cm.__aenter__()
        except Exception as e:  # noqa: BLE001
            raise LiveError(f"could not open a Live session: {self._safe(e)}") from None
        self._count_session()
        self._reader = asyncio.get_running_loop().create_task(self._read())

    def _count_session(self) -> None:
        log.info("live session opened purpose=%s", self.purpose)
        if self.session_log:
            self.session_log.parent.mkdir(parents=True, exist_ok=True)
            with self.session_log.open("a", encoding="utf-8") as f:  # time and purpose only
                f.write(f"{_dt.datetime.now().isoformat(timespec='seconds')} {self.purpose}\n")

    async def _read(self) -> None:
        from google.genai import types as t  # noqa: F401
        try:
            while True:
                async for msg in self._session.receive():
                    self._map(msg)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            self.push(Closed(self._safe(e)))
        else:
            self.push(Closed("closed"))

    def _map(self, msg) -> None:
        sc = getattr(msg, "server_content", None)
        if sc is not None:
            mt = getattr(sc, "model_turn", None)
            for part in (getattr(mt, "parts", None) or []):
                data = getattr(getattr(part, "inline_data", None), "data", None)
                if data:
                    self.push(AudioOut(bytes(data)))
            ot = getattr(sc, "output_transcription", None)
            if ot is not None and getattr(ot, "text", None):
                self.push(OutText(ot.text))
            if getattr(sc, "interrupted", False):
                self.push(Interrupted())
            if getattr(sc, "turn_complete", False):
                self.push(TurnComplete())
        tc = getattr(msg, "tool_call", None)
        for fc in (getattr(tc, "function_calls", None) or []):
            self.push(ToolCall(fc.id or "", fc.name or "", dict(fc.args or {})))
        ga = getattr(msg, "go_away", None)
        if ga is not None:
            self.push(GoAway(None))
        su = getattr(msg, "session_resumption_update", None)
        if su is not None and getattr(su, "new_handle", None) and getattr(su, "resumable", True):
            self.push(ResumeHandle(su.new_handle))

    async def _wrap(self, coro):
        try:
            return await coro
        except Exception as e:  # noqa: BLE001
            raise LiveError(self._safe(e)) from None

    async def send_turn(self, text: str) -> None:
        from google.genai import types as t
        await self._wrap(self._session.send_client_content(turns=t.Content(role="user", parts=[t.Part(text=text)]), turn_complete=True))

    async def send_context(self, text: str) -> None:
        from google.genai import types as t
        await self._wrap(self._session.send_client_content(turns=t.Content(role="user", parts=[t.Part(text=text)]), turn_complete=False))

    async def send_audio(self, pcm: bytes) -> None:
        from google.genai import types as t
        await self._wrap(self._session.send_realtime_input(audio=t.Blob(data=pcm, mime_type="audio/pcm;rate=16000")))

    async def activity(self, start: bool) -> None:
        from google.genai import types as t
        if start:
            await self._wrap(self._session.send_realtime_input(activity_start=t.ActivityStart()))
        else:
            await self._wrap(self._session.send_realtime_input(activity_end=t.ActivityEnd()))

    async def tool_result(self, call_id: str, name: str) -> None:
        from google.genai import types as t
        # a silent receipt: it must not make the MC speak, and it carries nothing but "received"
        await self._wrap(self._session.send_tool_response(function_responses=[t.FunctionResponse(
            id=call_id, name=name, response={"received": True}, scheduling=t.FunctionResponseScheduling.SILENT)]))

    async def close(self) -> None:
        self.closed = True
        if self._reader:
            self._reader.cancel()
        try:
            if self._cm is not None:
                await self._cm.__aexit__(None, None, None)
        except Exception:  # noqa: BLE001
            pass
        self.push(Closed("closed by us"))
