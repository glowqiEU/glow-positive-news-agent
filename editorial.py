from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

GENERIC_PATH_MARKERS = {"", "/", "/news", "/search", "/aggregator", "/latest", "/home"}
TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "source"}
VALID_EVIDENCE_LEVELS = {"measured_real_world", "randomized_human_trial", "human_early_phase", "observational_human", "preclinical_animal", "laboratory_model", "policy_or_deployment"}
VALID_IMPACT_STATUSES = {"measured_outcome", "implemented_milestone", "validated_research_result", "planned_only"}
VALID_POSITIVE_PROGRESS = {"outcome_improved", "recovery_or_restoration", "effective_intervention", "capability_or_tool", "enabling_evidence", "problem_characterization"}
VALID_PRIMARY_SOURCE_TYPES = {"peer_reviewed_paper", "government_or_public_agency", "official_dataset_or_report", "university_or_hospital", "responsible_organization", "regulator"}
IMPACT_BONUS = {"measured_outcome": 5, "implemented_milestone": 3, "validated_research_result": 1, "planned_only": -20}
PROGRESS_BONUS = {"outcome_improved": 4, "recovery_or_restoration": 4, "effective_intervention": 4, "capability_or_tool": 2, "enabling_evidence": 0, "problem_characterization": -20}
EVIDENCE_BONUS = {"measured_real_world": 3, "randomized_human_trial": 3, "policy_or_deployment": 1, "human_early_phase": 0, "observational_human": -1, "preclinical_animal": -3, "laboratory_model": -3}
SCORE_FIELDS = ("freshness", "credibility", "positive_impact", "interestingness", "specific_evidence")


def canonicalize_url(url: str) -> str:
    try:
        parsed = urlparse(url.strip())
    except (AttributeError, TypeError, ValueError):
        return ""
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return ""
    host = parsed.hostname.lower()
    if host.startswith("www."):
        host = host[4:]
    try:
        port = parsed.port
    except ValueError:
        return ""
    netloc = host if port is None else f"{host}:{port}"
    path = parsed.path.rstrip("/") or "/"
    query = urlencode(sorted(
        (key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_KEYS and not key.lower().startswith(TRACKING_QUERY_PREFIXES)
    ))
    return urlunparse((parsed.scheme.lower(), netloc, path, "", query, ""))


def is_specific_source_url(url: str) -> bool:
    canonical = canonicalize_url(url)
    if not canonical:
        return False
    parsed = urlparse(canonical)
    path = (parsed.path or "/").lower()
    if path in GENERIC_PATH_MARKERS:
        return False
    lowered = f"{path}?{parsed.query}".lower()
    return not any(fragment in lowered for fragment in ("/search/", "?search=", "?q=", "/tag/", "/tags/", "/category/", "/categories/", "/aggregator/"))


def ordered_sources(story: dict) -> list[str]:
    urls = []
    for raw_url in story.get("source_urls") or []:
        url = canonicalize_url(raw_url)
        if is_specific_source_url(url) and url not in urls:
            urls.append(url)
    primary = canonicalize_url(story.get("primary_source") or "")
    return ([primary] if primary in urls else []) + [url for url in urls if url != primary]


def editorial_score(story: dict) -> int:
    base = _integer(story.get("total_score"), default=0)
    evidence = _normalized(story, "evidence_level")
    impact = _normalized(story, "impact_status")
    progress = _normalized(story, "positive_progress")
    return base + EVIDENCE_BONUS.get(evidence, -5) + IMPACT_BONUS.get(impact, -5) + PROGRESS_BONUS.get(progress, -5)


def rejection_reasons(story: dict, *, now: datetime, lookback_hours: int, min_score: int,
                      min_early_human_score: int, min_observational_score: int,
                      min_weak_evidence_score: int) -> list[str]:
    reasons = []
    title = str(story.get("title_lt") or "").strip()
    summary = str(story.get("summary_lt") or "").strip()
    score = _integer(story.get("total_score"), default=-1)
    urls = ordered_sources(story)
    primary = canonicalize_url(story.get("primary_source") or "")
    evidence = _normalized(story, "evidence_level")
    impact = _normalized(story, "impact_status")
    progress = _normalized(story, "positive_progress")
    if not title:
        reasons.append("missing title")
    if not summary:
        reasons.append("missing summary")
    if score < min_score:
        reasons.append(f"score {score} < {min_score}")
    components = [_integer(story.get(field), default=-1) for field in SCORE_FIELDS]
    if any(value < 0 or value > 10 for value in components):
        reasons.append("component score outside 0-10")
    elif score != sum(components):
        reasons.append(f"total_score {score} != component sum {sum(components)}")
    if not urls:
        reasons.append("no specific source URL")
    if not primary or not is_specific_source_url(primary):
        reasons.append("missing/weak primary source")
    elif primary not in urls:
        reasons.append("primary source not included in source_urls")
    if _normalized(story, "primary_source_type") not in VALID_PRIMARY_SOURCE_TYPES:
        reasons.append("missing/invalid primary source type")
    if not str(story.get("primary_evidence") or "").strip():
        reasons.append("missing primary-source evidence note")
    event_key = str(story.get("event_key") or "").strip()
    if not event_key or len(event_key) > 160:
        reasons.append("missing/invalid event key")
    if evidence not in VALID_EVIDENCE_LEVELS:
        reasons.append("missing/invalid evidence level")
    if impact not in VALID_IMPACT_STATUSES:
        reasons.append("missing/invalid impact status")
    elif impact == "planned_only":
        reasons.append("planned-only story; no realized result or implementation milestone")
    if progress not in VALID_POSITIVE_PROGRESS:
        reasons.append("missing/invalid positive-progress type")
    elif progress == "problem_characterization":
        reasons.append("describes a problem but does not demonstrate positive progress")
    development_at = _parse_datetime(story.get("development_at"))
    if development_at is None:
        reasons.append("missing/invalid development timestamp")
    else:
        now = now.astimezone(timezone.utc)
        if development_at > now + timedelta(hours=1):
            reasons.append("development timestamp is in the future")
        elif development_at < now - timedelta(hours=lookback_hours):
            reasons.append(f"underlying development older than {lookback_hours}h")
    if evidence == "human_early_phase" and score < min_early_human_score:
        reasons.append(f"human_early_phase requires score >= {min_early_human_score}")
    if evidence == "observational_human" and score < min_observational_score:
        reasons.append(f"observational_human requires score >= {min_observational_score}")
    if evidence in {"preclinical_animal", "laboratory_model"} and score < min_weak_evidence_score:
        reasons.append(f"{evidence} requires score >= {min_weak_evidence_score}")
    return reasons


def _normalized(story: dict, key: str) -> str:
    return str(story.get(key) or "").strip().lower()


def _integer(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)
