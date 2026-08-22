"""Loader for the market-abuse threshold pack (config into a domain value object).

Lives OUTSIDE ``domain/`` because it reads YAML from disk, and the domain core stays pure stdlib
with no I/O. It turns the reference pack at ``rulepacks/surveillance_thresholds.yaml`` (or an
adopter's own file, selected by ``surveillance_pack.path`` in ``config/settings.yaml``) into one
immutable :class:`~trade_comms_surveillance.domain.abuse_patterns.PatternThresholds` the engine
takes as a parameter.

Why a pack rather than engine constants: which abnormal return is suspicious and which
cancellation-ratio z-score is layering are policy a compliance officer owns and must be able to
diff (practice B4), not algorithm. Loading is fail-closed: a missing file, an unknown detector, a
missing threshold, a rule that cites an undefined citation id, or a rule with no citation raises
:class:`SurveillancePackError`. A surveillance gate running on a silently empty pack would wave
abuse through, so it must not start at all.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, NoReturn

import yaml

from .config import Settings
from .domain.abuse_patterns import PatternThresholds
from .domain.kernel import Citation
from .domain.models import PatternType

DEFAULT_PACK_PATH = Path(__file__).resolve().parent / "rulepacks" / "surveillance_thresholds.yaml"

#: The detectors the pack MUST calibrate. A pack missing one refuses to load.
_REQUIRED = (
    PatternType.INSIDER_DEALING,
    PatternType.SPOOFING_LAYERING,
    PatternType.WASH_TRADING,
    PatternType.FRONT_RUNNING,
)


class SurveillancePackError(ValueError):
    """Raised when the threshold pack is missing, malformed, or fails a fail-closed check."""


def _fail(message: str) -> NoReturn:
    raise SurveillancePackError(f"surveillance pack: {message}")


def _citations(doc: dict[str, Any]) -> dict[str, Citation]:
    raw = doc.get("citations") or {}
    if not isinstance(raw, dict) or not raw:
        _fail("no 'citations' block; every detector must name the instrument it comes from")
    out: dict[str, Citation] = {}
    for citation_id, spec in raw.items():
        if not isinstance(spec, dict) or not str(spec.get("title", "")).strip():
            _fail(f"citation {citation_id!r} has no title (a citation must name its instrument)")
        out[str(citation_id)] = Citation(
            source_id=str(citation_id),
            title=str(spec["title"]).strip(),
            snippet=" ".join(str(spec.get("snippet", "")).split()),
        )
    return out


def _cite(block: dict[str, Any], citations: dict[str, Citation], detector: str) -> Citation:
    citation_id = str(block.get("citation", "") or "")
    if not citation_id:
        _fail(f"{detector}: no citation; every detector must cite a named regulator instrument")
    if citation_id not in citations:
        _fail(f"{detector}: citation {citation_id!r} is not defined in the pack")
    return citations[citation_id]


def _num(block: dict[str, Any], key: str, detector: str) -> float:
    if key not in block:
        _fail(f"{detector}: missing threshold {key!r}")
    try:
        return float(block[key])
    except (TypeError, ValueError):
        _fail(f"{detector}: threshold {key!r} is not a number")


def load_pack(path: str | Path | None = None) -> PatternThresholds:
    """Load and validate the threshold pack from ``path`` (default: the reference pack)."""
    pack_path = Path(path) if path else DEFAULT_PACK_PATH
    if not pack_path.exists():
        _fail(f"pack file {pack_path} does not exist; the surveillance gate cannot run without it")
    try:
        doc = yaml.safe_load(pack_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise SurveillancePackError(
            f"surveillance pack: {pack_path} is not valid YAML: {exc}"
        ) from exc
    if not isinstance(doc, dict):
        _fail(f"{pack_path} must contain a mapping")

    citations = _citations(doc)
    thresholds = doc.get("thresholds") or {}
    if not isinstance(thresholds, dict):
        _fail("'thresholds' must be a mapping of detector -> settings")
    for detector in _REQUIRED:
        if detector.value not in thresholds:
            _fail(
                f"no thresholds for detector {detector.value!r}; every detector must be calibrated"
            )

    insider = thresholds[PatternType.INSIDER_DEALING.value]
    spoof = thresholds[PatternType.SPOOFING_LAYERING.value]
    wash = thresholds[PatternType.WASH_TRADING.value]
    front = thresholds[PatternType.FRONT_RUNNING.value]

    return PatternThresholds(
        insider_abnormal_return=_num(insider, "abnormal_return", "insider_dealing"),
        spoof_cancel_ratio_z=_num(spoof, "cancel_ratio_z", "spoofing_layering"),
        spoof_resting_ms_floor=int(_num(spoof, "resting_ms_floor", "spoofing_layering")),
        wash_min_quantity=int(_num(wash, "min_quantity", "wash_trading")),
        frontrun_window_ms=int(_num(front, "window_ms", "front_running")),
        citations={
            PatternType.INSIDER_DEALING: _cite(insider, citations, "insider_dealing"),
            PatternType.SPOOFING_LAYERING: _cite(spoof, citations, "spoofing_layering"),
            PatternType.WASH_TRADING: _cite(wash, citations, "wash_trading"),
            PatternType.FRONT_RUNNING: _cite(front, citations, "front_running"),
        },
    )


@lru_cache(maxsize=4)
def _cached_pack(resolved: str) -> PatternThresholds:
    return load_pack(resolved)


def thresholds_for(settings: Settings) -> PatternThresholds:
    """Resolve the active threshold pack for ``settings`` (adopter override, else the reference)."""
    configured = (settings.pack_path or "").strip()
    return _cached_pack(configured or str(DEFAULT_PACK_PATH))


__all__ = ["DEFAULT_PACK_PATH", "SurveillancePackError", "load_pack", "thresholds_for"]
