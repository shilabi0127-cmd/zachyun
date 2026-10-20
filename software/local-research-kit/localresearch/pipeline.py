"""Bounded context selection and replayable pipeline inputs.

Hashes detect accidental changes to a saved input. They are not signatures.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol

from .generation import answer_from_hits

PROMPT_VERSION = "evidence-v2"
TRACE_VERSION = 1


class Retriever(Protocol):
    def search(self, question: str, k: int = 4) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class ContextPolicy:
    max_chars: int = 2600
    max_per_document: int = 2

    def __post_init__(self) -> None:
        if not 128 <= self.max_chars <= 8000:
            raise ValueError("Context character budget must be 128..8000")
        if not 1 <= self.max_per_document <= 10:
            raise ValueError("Document limit must be 1..10")


def fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def select_context(candidates: list[dict[str, Any]], k: int, policy: ContextPolicy):
    """Keep whole chunks, ranked order, unique IDs and bounded per-document share."""
    selected, seen, counts = [], set(), {}
    used = 0
    skipped = {"duplicate": 0, "document_limit": 0, "budget": 0, "result_limit": 0}
    for candidate in candidates:
        if candidate["id"] in seen:
            skipped["duplicate"] += 1
            continue
        seen.add(candidate["id"])
        if len(selected) >= k:
            skipped["result_limit"] += 1
            continue
        path = candidate["path"]
        if counts.get(path, 0) >= policy.max_per_document:
            skipped["document_limit"] += 1
            continue
        size = len(candidate["text"])
        if used + size > policy.max_chars:
            skipped["budget"] += 1
            continue
        selected.append(dict(candidate))
        used += size
        counts[path] = counts.get(path, 0) + 1
    return selected, {"context_chars": used, "skipped": skipped}


def validate_request(question: str, k: int, backend: str) -> None:
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 1000:
        raise ValueError("Question must contain 1..1000 characters")
    if not isinstance(k, int) or isinstance(k, bool) or not 1 <= k <= 10:
        raise ValueError("k must be 1..10")
    if backend not in {"extractive", "gguf", "ollama"}:
        raise ValueError("Unknown generation backend")


def run(index: Retriever, question: str, k: int = 4, backend: str = "extractive",
        model: str = "", policy: ContextPolicy | None = None) -> dict[str, Any]:
    validate_request(question, k, backend)
    policy = policy or ContextPolicy()
    started = perf_counter()
    candidates = index.search(question, min(10, k * 3))
    retrieved = perf_counter()
    hits, selection = select_context(candidates, k, policy)
    inputs = {"question": question, "k": k, "backend": backend, "model": model,
              "policy": asdict(policy), "hits": hits, "prompt_version": PROMPT_VERSION}
    result = answer_from_hits(question, hits, backend, model)
    finished = perf_counter()
    result["trace"] = {
        "version": TRACE_VERSION, "input_sha256": fingerprint(inputs), "inputs": inputs,
        "candidate_ids": [item["id"] for item in candidates], **selection,
        "timing_ms": {"retrieval": round((retrieved-started)*1000, 3),
                      "selection_and_answer": round((finished-retrieved)*1000, 3),
                      "total": round((finished-started)*1000, 3)},
    }
    return result


def save_record(result: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def replay(record: dict[str, Any], backend: str = "extractive", model: str = "") -> dict[str, Any]:
    trace = record.get("trace", {})
    if trace.get("version") != TRACE_VERSION:
        raise ValueError("Unsupported trace version")
    inputs = trace.get("inputs")
    if not isinstance(inputs, dict) or fingerprint(inputs) != trace.get("input_sha256"):
        raise ValueError("Trace input hash mismatch")
    if inputs.get("prompt_version") != PROMPT_VERSION:
        raise ValueError("Prompt version differs; replay with the matching release")
    validate_request(inputs["question"], inputs["k"], backend)
    policy = ContextPolicy(**inputs["policy"])
    hits, _ = select_context(inputs["hits"], inputs["k"], policy)
    if hits != inputs["hits"]:
        raise ValueError("Saved context violates its declared policy")
    result = answer_from_hits(inputs["question"], hits, backend, model)
    result["replay_of"] = trace["input_sha256"]
    result["replay_backend"] = backend
    return result
