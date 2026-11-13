"""Data models for the assist domain."""

from dataclasses import asdict, dataclass, field
from typing import Any

LOCAL = "local"      # the built-in agent matched it (prefer local intents)
AGENT = "agent"      # the pipeline's conversation agent (often an LLM) answered
UNKNOWN = "unknown"  # HA didn't say (older versions have no processed_locally)


@dataclass
class Pipeline:
    """An Assist pipeline."""

    id: str
    name: str
    conversation_engine: str
    stt_engine: str | None
    tts_engine: str | None
    tts_voice: str | None
    language: str
    prefer_local_intents: bool
    preferred: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any], preferred_id: str | None = None) -> "Pipeline":
        """Create from an assist_pipeline/pipeline/list item."""
        return cls(
            id=str(data.get("id") or ""),
            name=str(data.get("name") or ""),
            conversation_engine=str(data.get("conversation_engine") or ""),
            stt_engine=data.get("stt_engine"),
            tts_engine=data.get("tts_engine"),
            tts_voice=data.get("tts_voice"),
            language=str(data.get("language") or ""),
            prefer_local_intents=bool(data.get("prefer_local_intents")),
            preferred=data.get("id") == preferred_id,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialise."""
        return asdict(self)


@dataclass
class AssistResult:
    """What happened to one phrase."""

    text: str
    target: str               # pipeline name or agent id
    handled_by: str = UNKNOWN
    agent: str | None = None
    response_type: str | None = None
    speech: str = ""
    intent_seconds: float | None = None
    tts_url: str | None = None
    tts_seconds: float | None = None  # URL creation only: HA renders the audio when it's fetched
    total_seconds: float | None = None
    error: str | None = None
    events: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Whether it produced a non-error response."""
        return self.error is None and self.response_type not in (None, "error")

    def to_dict(self) -> dict[str, Any]:
        """Serialise."""
        return {**asdict(self), "ok": self.ok}
