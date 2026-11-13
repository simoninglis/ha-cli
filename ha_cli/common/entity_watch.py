"""Follow live entity state from a ``subscribe_entities`` stream.

HA sends compressed state: an ``a`` (added) map with the full state, then ``c``
(changed) maps holding ``+`` (set) and ``-`` (removed attribute keys) diffs, and
``r`` for removed entities. ``EntityTracker`` folds those into plain state and
attribute dicts, so a watcher can ask "what is this entity now?".
"""

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EntityState:
    """Current state of one entity, as far as the stream has told us."""

    state: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    removed: bool = False


class EntityTracker:
    """Apply ``subscribe_entities`` events to a set of entity states."""

    def __init__(self) -> None:
        """Start with nothing known."""
        self.entities: dict[str, EntityState] = {}

    def get(self, entity_id: str) -> EntityState:
        """The entity's current state (empty if nothing has arrived yet)."""
        return self.entities.setdefault(entity_id, EntityState())

    def apply(self, event: dict[str, Any]) -> set[str]:
        """Fold one event in. Returns the entity ids whose state or attributes changed."""
        changed: set[str] = set()
        for eid, full in (event.get("a") or {}).items():
            ent = self.get(eid)
            ent.state = full.get("s")
            ent.attributes = dict(full.get("a") or {})
            ent.removed = False
            changed.add(eid)
        for eid, diff in (event.get("c") or {}).items():
            ent = self.get(eid)
            plus = diff.get("+") or {}
            if "s" in plus:
                ent.state = plus["s"]
            ent.attributes.update(plus.get("a") or {})
            for key in (diff.get("-") or {}).get("a") or []:
                ent.attributes.pop(key, None)
            changed.add(eid)
        for eid in event.get("r") or []:
            self.get(eid).removed = True
            changed.add(eid)
        return changed


async def watch_entities(
    stream: AsyncIterator[dict[str, Any]],
    tracker: EntityTracker,
    on_change: Callable[[set[str]], bool],
) -> None:
    """Feed a ``subscribe_entities`` stream into ``tracker`` until ``on_change`` returns True."""
    async for event in stream:
        changed = tracker.apply(event)
        if changed and on_change(changed):
            return
