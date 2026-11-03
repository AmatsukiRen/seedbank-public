"""Read-only, day-granularity projection of explicitly dated claims.

Recording time never supplies a missing effective date. Projections use current
source permissions and corrections, not a historical snapshot of permissions.
"""
from __future__ import annotations

import re

from .memory_state import effective_date
from .pack_lock import serialized
from .util import SeedError


def query_day(value):
    if value is not None and not isinstance(value, str):
        raise SeedError("回查日期需要 YYYY-MM-DD，也可以留空查看时间线。")
    return effective_date(value or "")


def explicit_day(text):
    """Only one unambiguous literal date; never invent a date for 'back then'."""
    matches = re.findall(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)|(?<!\d)(\d{4})年(\d{1,2})月(\d{1,2})日", str(text))
    dates = {f"{int(y):04d}-{int(m):02d}-{int(d):02d}" for match in matches
             for y, m, d in [match[:3] if match[0] else match[3:]]}
    if len(dates) != 1:
        return ""
    try:
        return query_day(next(iter(dates)))
    except SeedError:
        return ""


def project(group, on="", *, limit=8, offset=0):
    """Derive a view; uncertainty is computed before any display truncation."""
    claims = {row["id"]: row for row in group["history"]}
    decisions = [row for row in group["decisions"] if row.get("usable_for_time")
                 and row["selected"] in claims and not claims[row["selected"]]["unavailable"]
                 and claims[row["selected"]].get("change_type") != "correction"]
    records = []
    for claim in group["history"]:
        if claim["unavailable"]:
            continue
        removed = next((d for d in reversed(decisions)
                        if claim["id"] in d["targets"] and claim["id"] != d["selected"]), None)
        # Never bring a withdrawn assertion back through an unavailable decision.
        if claim.get("superseded_by") and removed is None:
            continue
        if removed and removed["change_type"] == "correction":
            continue
        supporting = [d for d in decisions if d["selected"] == claim["id"]]
        choosing = [d for d in supporting if d["change_type"] == "change"]
        starts = {claim["starts_on"]} if claim.get("starts_on") else set()
        starts.update(d["effective_on"] for d in choosing if d.get("effective_on"))
        begin = next(iter(starts)) if len(starts) == 1 else ""
        end = removed.get("effective_on", "") if removed else ""
        reasons = []
        if len(starts) > 1:
            reasons.append("conflicting_start_dates")
        elif not begin:
            reasons.append("unknown_start")
        if removed and not end:
            reasons.append("unknown_end")
        if begin and end and begin > end:
            reasons.append("reversed_dates")
        if begin and end and begin == end:
            reasons.append("same_day_changes")
        if any(r.get("date_state") == "unavailable" for r in [claim] + supporting + ([removed] if removed else [])):
            reasons.append("date_revision_unavailable")
        refs = {r["id"]: r for r in claim["evidence"]}
        refs.update({r["id"]: r for r in claim.get("date_evidence", [])})
        for decision in supporting + ([removed] if removed else []):
            refs.update({r["id"]: r for r in decision["evidence"]})
            refs.update({r["id"]: r for r in decision.get("date_evidence", [])})
        match = "not_queried"
        if on:
            invalid = any(r in reasons for r in ("conflicting_start_dates", "reversed_dates", "date_revision_unavailable"))
            if invalid or (begin == end == on):
                match = "possible"
            elif (begin and on < begin) or (end and on >= end):
                match = "outside"
            elif not begin or (removed and not end):
                match = "possible"
            else:
                match = "covered"
        records.append({"id": claim["id"], "value": claim["value"], "quote": claim["quote"],
                        "recorded_at": claim["at"], "starts_on": begin, "until_on": end,
                        "open_end": not bool(removed), "reasons": reasons, "match": match,
                        "date_state": claim.get("date_state", "original"),
                        "origin": claim["origin"], "evidence": list(refs.values())})
    covered = [r for r in records if r["match"] == "covered"]
    possible = [r for r in records if r["match"] == "possible"]
    exact_values = list(dict.fromkeys(r["value"] for r in covered))
    possible_values = {r["value"] for r in possible}
    status = "timeline"
    if on:
        status = ("conflict" if len(exact_values) > 1 else "uncertain"
                  if exact_values and possible_values - set(exact_values) else "reported"
                  if exact_values else "unknown")
        # Two transitions within one day do not establish the whole day's value,
        # even if the intermediate value happens to equal the final value.
        if any("same_day_changes" in r["reasons"] and r["starts_on"] == on for r in possible):
            status = "uncertain"
    records.sort(key=lambda r: (r["match"] in ("covered", "possible"), r["recorded_at"], r["id"]), reverse=True)
    start = max(0, int(offset))
    page = records[start:start + max(1, min(100, int(limit)))]
    values = exact_values if status in ("reported", "conflict") else []
    return {"on": on, "status": status, "values": values[:4], "value_count": len(values),
            "covered_count": len(covered), "possible_count": len(possible),
            "records": page, "total": len(records), "offset": start,
            "omitted": len(page) < len(records), "basis": "currently_available_recorded_changes",
            # All contributing sources also cover uncertainty caused by omitted
            # candidates. They are IDs, not hidden text or a confidence score.
            "dependency_ids": sorted({ref["id"] for r in records for ref in r["evidence"]})}


@serialized
def listing(pack, query="", *, on="", slot="", limit=30, offset=0, record_offset=0, policy=None):
    from .facts import _state
    from . import requests
    on = query_day(on)
    _, groups = _state(pack, policy)
    needle = str(query or "").strip().casefold()
    selected = []
    for group in groups.values():
        if slot and group["id"] != slot:
            continue
        view = project(group, on, limit=30, offset=record_offset if slot else 0)
        if not view["total"]:
            continue
        visible_text = group["label"] + " " + group["aspect"] + " " + " ".join(
            r["value"] for r in group["history"] if not r["unavailable"])
        if needle and needle not in visible_text.casefold():
            continue
        selected.append({k: group[k] for k in ("id", "subject", "label", "aspect")} | {"temporal": view})
    selected.sort(key=lambda g: (g["temporal"]["status"] not in ("conflict", "uncertain"), g["id"]))
    start = max(0, int(offset))
    return {"on": on, "query": str(query or ""), "groups": selected[start:start + max(1, min(100, int(limit)))],
            "total": len(selected), "offset": start, "slot": slot,
            "pending": [] if getattr(policy, "restricted", False) else [r for r in requests.pending(pack) if r["payload"].get("kind") == "fact_time_edit"],
            "scope": "current_sources_about_a_past_day"}
