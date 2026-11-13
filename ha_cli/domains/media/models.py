"""Data models for the media domain."""

from dataclasses import asdict, dataclass, field
from typing import Any

PLAYED = "played"            # reached playing (and usually back to idle)
NOT_PLAYED = "not_played"    # the call was accepted but the player never started
DISCONNECTED = "disconnected"  # the player dropped off mid-test (e.g. an ESPHome API blip)
UNAVAILABLE = "unavailable"  # unavailable before we started
BUSY = "busy"                # already playing: a result would be meaningless
REJECTED = "rejected"        # HA refused the tts.speak call

OUTCOME_LABELS = {
    PLAYED: "PLAYED",
    NOT_PLAYED: "NOT PLAYED (accepted, never started: can the device fetch the audio from HA's internal URL?)",
    DISCONNECTED: "DISCONNECTED (dropped off mid-test; retry)",
    UNAVAILABLE: "UNAVAILABLE",
    BUSY: "BUSY (already playing; use --force to interrupt)",
    REJECTED: "REJECTED",
}


@dataclass
class TtsEngine:
    """Which TTS engine, language and voice to use."""

    engine: str
    language: str | None = None
    voice: str | None = None
    source: str = "options"  # or "preferred pipeline <name>"


@dataclass
class TtsTestResult:
    """What a player did with one TTS clip."""

    player: str
    outcome: str
    engine: str
    started_after_s: float | None = None
    finished_after_s: float | None = None
    problem: str | None = None
    timeline: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Whether the clip demonstrably played."""
        return self.outcome == PLAYED

    def to_dict(self) -> dict[str, Any]:
        """Serialise."""
        return {**asdict(self), "ok": self.ok}
