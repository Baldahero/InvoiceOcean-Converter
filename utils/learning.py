"""Persistent learning memory for recurring statement corrections."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
LEARNING_PATH = REPO_ROOT / "data" / "learning_memory.json"

LEARNED_FIELDS = [
    "Document side",
    "No. (invoice)",
    "Kind",
    "Status",
    "Issue date",
    "Due date",
    "Buyer",
    "Seller",
    "VAT ID",
    "Street",
    "Postcode",
    "City",
    "Country",
    "Client e-mail",
    "Client's phone",
    "Product / Service",
    "Qty",
    "Quantity unit",
    "Currency",
    "Payment type",
]


def _normalize_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[^a-zа-яё0-9]+", " ", text).strip()


def _normalize_tax_id(value: Any) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "", str(value or "").upper())


def _load_store() -> dict[str, list[dict[str, Any]]]:
    if not LEARNING_PATH.exists():
        return {"examples": []}

    try:
        return json.loads(LEARNING_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"examples": []}


def _save_store(store: dict[str, list[dict[str, Any]]]) -> None:
    LEARNING_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEARNING_PATH.write_text(
        json.dumps(store, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _score_example(
    example: dict[str, Any],
    company_key: str,
    source_counterparty: str,
    source_tax_id: str,
    source_text: str,
) -> int:
    if example.get("company_key") != company_key:
        return -1

    target_counterparty = _normalize_text(source_counterparty)
    target_tax_id = _normalize_tax_id(source_tax_id)
    target_text = _normalize_text(source_text)

    example_counterparty = example.get("source_counterparty", "")
    example_tax_id = example.get("source_tax_id", "")
    example_text = example.get("source_text", "")

    score = 0

    if target_tax_id and example_tax_id:
        if target_tax_id == example_tax_id:
            score += 12
        else:
            return -1

    if target_counterparty and example_counterparty:
        if target_counterparty == example_counterparty:
            score += 10
        elif target_counterparty in example_counterparty or example_counterparty in target_counterparty:
            score += 6
        else:
            target_words = set(target_counterparty.split())
            example_words = set(example_counterparty.split())
            score += min(len(target_words & example_words), 4)

    if target_text and example_text:
        target_words = {word for word in target_text.split() if len(word) > 2}
        example_words = {word for word in example_text.split() if len(word) > 2}
        score += min(len(target_words & example_words), 6)

    return score


def find_learning_match(
    company_key: str,
    source_counterparty: str,
    source_tax_id: str = "",
    source_text: str = "",
) -> dict[str, Any]:
    store = _load_store()
    best_example: dict[str, Any] | None = None
    best_score = 0

    for example in store.get("examples", []):
        score = _score_example(example, company_key, source_counterparty, source_tax_id, source_text)
        if score > best_score:
            best_score = score
            best_example = example

    if not best_example or best_score < 8:
        return {}

    return dict(best_example.get("target", {}))


def remember_learning_rows(
    company_key: str,
    rows: list[dict[str, Any]],
) -> int:
    store = _load_store()
    examples = store.setdefault("examples", [])
    updated = 0

    for row in rows:
        source_counterparty = _normalize_text(row.get("Source counterparty", ""))
        source_tax_id = _normalize_tax_id(row.get("Source tax ID", ""))
        source_text = _normalize_text(
            row.get("Source description", "")
            or row.get("Product / Service", "")
        )

        if not source_counterparty and not source_text:
            continue

        target = {}
        for field in LEARNED_FIELDS:
            value = row.get(field)
            if value not in (None, ""):
                target[field] = value

        record = {
            "company_key": company_key,
            "source_counterparty": source_counterparty,
            "source_tax_id": source_tax_id,
            "source_text": source_text,
            "target": target,
        }

        replaced = False
        for index, example in enumerate(examples):
            if (
                example.get("company_key") == company_key
                and example.get("source_counterparty") == source_counterparty
                and example.get("source_tax_id") == source_tax_id
                and example.get("source_text") == source_text
            ):
                examples[index] = record
                replaced = True
                break

        if not replaced:
            examples.append(record)
        updated += 1

    if updated:
        store["examples"] = examples[-1000:]
        _save_store(store)

    return updated


def learning_examples_count() -> int:
    return len(_load_store().get("examples", []))
