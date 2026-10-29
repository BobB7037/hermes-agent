"""Content-free telemetry for processes Hermes keeps outside any turn: Bot Desktop screens and the child
process groups the owner-death supervisor reaps.

Most of these moments happen where no exporter runs: a screen's own idle check (a short-lived process
the launcher starts), the supervisor reaping after Hermes died, a dashboard backend. :func:`record`
emits in-process when this process exports, and otherwise leaves the event in the home's spool
(``<HERMES_HOME>/monitoring/spool``), which the exporting gateway drains. The spool exists only while
some gateway exports for that home (:func:`set_spooling`), so nothing accumulates with export off.
The shell writers (``launcher.sh``, ``process_supervisor.sh``) write the same JSON shape by hand.

Every field is a closed vocabulary or a small count: an event that does not validate is dropped.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from agent.monitoring import emitter
from agent.monitoring.events import ManagedProcessEvent
from agent.monitoring.gateway_health import GatewayMetric

logger = logging.getLogger(__name__)

BOT_DESKTOP = "bot_desktop"
OWNED_CHILDREN = "owned_children"
# subsystem -> action -> allowed outcomes; actors and reasons are shared closed sets.
_VOCABULARY: dict[str, dict[str, frozenset[str]]] = {
    BOT_DESKTOP: {
        "idle_stop": frozenset({"stopped", "kept"}),
        "lease_handback": frozenset({"released", "kept_newer", "write_failed"}),
        "self_stop_off": frozenset({"sleep_failed"}),
    },
    OWNED_CHILDREN: {
        "orphan_reap": frozenset({"terminated", "killed"}),
        "supervisor_exit": frozenset({"restarted", "not_restarted"}),
        "supervisor_unavailable": frozenset({"spawn_failed"}),
    },
}
_ACTORS = frozenset({"watcher", "screen", "supervisor", "owner"})
_REASONS = frozenset({"idle", "abandoned_lease"})
_MAX_COUNT = 1_000_000
# A spool the gateway stopped draining (it died, export was turned off elsewhere) stops growing here.
_MAX_SPOOLED = 1_000
_MAX_FILE_BYTES = 4096


def spool_dir(home: Optional[Path] = None) -> Path:
    if home is None:
        from hermes_constants import get_hermes_home
        home = get_hermes_home()
    return Path(home) / "monitoring" / "spool"


def _validated(data: Any) -> Optional[ManagedProcessEvent]:
    """The event, or None when any field falls outside the vocabulary (a hand-written or corrupt file)."""
    if not isinstance(data, dict) or data.get("event", ManagedProcessEvent.EVENT) != ManagedProcessEvent.EVENT:
        return None
    outcomes = _VOCABULARY.get(str(data.get("subsystem")), {}).get(str(data.get("action")))
    outcome, actor, reason, count = (data.get(k) for k in ("outcome", "actor", "reason", "count"))
    if outcomes is None or outcome not in outcomes:
        return None
    if actor is not None and actor not in _ACTORS or reason is not None and reason not in _REASONS:
        return None
    if count is not None and (type(count) is not int or not 0 <= count <= _MAX_COUNT):
        return None
    ts_ns = data.get("ts_ns")
    if type(ts_ns) is not int or ts_ns <= 0:
        ts_ns = time.time_ns()
    return ManagedProcessEvent(subsystem=data["subsystem"], action=data["action"], outcome=outcome, actor=actor,
                               reason=reason, count=count, ts_ns=ts_ns)


def record(subsystem: str, action: str, outcome: str, *, actor: Optional[str] = None,
           reason: Optional[str] = None, count: Optional[int] = None) -> None:
    """Report one managed-process moment. Never raises and never blocks on more than one small file write."""
    try:
        event = _validated({"subsystem": subsystem, "action": action, "outcome": outcome, "actor": actor,
                            "reason": reason, "count": count})
        if event is None:
            logger.debug("managed-process event outside the vocabulary dropped: %s/%s/%s", subsystem, action, outcome)
            return
        bus = emitter.get_emitter()
        if bus.enabled:
            bus.emit(event)
            return
        directory = spool_dir()
        if not directory.is_dir():
            return  # no gateway exports for this home: nothing is kept
        if sum(1 for _ in directory.glob("*.json")) >= _MAX_SPOOLED:
            return
        from utils import atomic_json_write
        atomic_json_write(directory / f"{event.ts_ns}-{os.getpid()}.json", event.to_dict())
    except Exception:
        logger.debug("managed-process telemetry record failed", exc_info=True)


def drain_spool(homes: Iterable[Path]) -> list[ManagedProcessEvent]:
    """Collect and remove every spooled event of ``homes``, oldest first. A file that does not validate is
    removed as well: it can never become valid."""
    events: list[ManagedProcessEvent] = []
    for home in homes:
        try:
            paths = sorted(spool_dir(home).glob("*.json"))
        except OSError:
            continue
        for path in paths:
            try:
                raw = path.read_bytes()[:_MAX_FILE_BYTES + 1]
                path.unlink()
            except OSError:
                continue
            try:
                event = _validated(json.loads(raw)) if len(raw) <= _MAX_FILE_BYTES else None
            except ValueError:
                event = None
            if event is not None:
                events.append(event)
    events.sort(key=lambda event: event.ts_ns)
    return events


def set_spooling(homes: Iterable[Path], enabled: bool) -> None:
    """Create (export on) or remove (export off) the spool of each home. Fail-open per home."""
    for home in homes:
        directory = spool_dir(home)
        try:
            if enabled:
                directory.mkdir(parents=True, exist_ok=True)
            elif directory.is_dir():
                shutil.rmtree(directory)
        except OSError:
            logger.debug("managed-process spool %s could not be %s", directory, "created" if enabled else "removed",
                         exc_info=True)


@dataclass(frozen=True, slots=True)
class ManagedProcessSnapshot:
    metrics: list[GatewayMetric]


def _bot_desktop_metrics(homes: Iterable[Path], metrics: list[GatewayMetric]) -> None:
    from hermes_constants import reset_hermes_home_override, set_hermes_home_override
    from tools.bot_desktop import lease, runtime
    running = human_held = 0
    for home in homes:
        token = set_hermes_home_override(home)
        try:
            if runtime.is_running():
                running += 1
                human_held += lease.get().holder == lease.HUMAN
        finally:
            reset_hermes_home_override(token)
    metrics.append(GatewayMetric("hermes.bot_desktop.screens.running", running, {}))
    metrics.append(GatewayMetric("hermes.bot_desktop.screens.human_held", human_held, {}))


def _owned_children_metrics(metrics: list[GatewayMetric]) -> None:
    from hermes_cli.process_identity import supervised_group_count
    metrics.append(GatewayMetric("hermes.owned_children.groups", supervised_group_count(), {}))


def build_managed_process_snapshot(homes: Callable[[], Iterable[Path]]) -> ManagedProcessSnapshot:
    metrics: list[GatewayMetric] = []
    for build, failure_msg in (
        (lambda: _bot_desktop_metrics(list(homes()), metrics), "bot-desktop metrics unavailable"),
        (lambda: _owned_children_metrics(metrics), "owned-children metric unavailable"),
    ):
        try:
            build()
        except Exception:
            logger.debug(failure_msg, exc_info=True)
    return ManagedProcessSnapshot(metrics=metrics)


__all__ = [
    "BOT_DESKTOP",
    "OWNED_CHILDREN",
    "ManagedProcessSnapshot",
    "build_managed_process_snapshot",
    "drain_spool",
    "record",
    "set_spooling",
    "spool_dir",
]
