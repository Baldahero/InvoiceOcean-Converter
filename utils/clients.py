"""Client helpers and seller profiles."""

from __future__ import annotations

import io
import re
from typing import Any

import pandas as pd


CLIENTS = {
    "Tenta Trade sp z o.o.": {
        "vat_id": "PL5423456230",
        "street": "Ludwika Zamenhofa 29",
        "postcode": "15435",
        "city": "Białystok",
        "country": "Poland",
        "email": "purchase@tentatrade.com",
        "phone": "",
        "invoiceocean_id": "160865575",
        "legal_name": "Tenta Trade sp z o.o.",
    },
    "PILOT INTERNATIONAL SP. Z O.O.": {
        "vat_id": "5242950541",
        "street": "UL.STANIEWICKA 5",
        "postcode": "03-310",
        "city": "Warszawa",
        "country": "Poland",
        "email": "",
        "phone": "",
        "invoiceocean_id": "160919372",
        "legal_name": "PILOT INTERNATIONAL SP. Z O.O.",
    },
    'LLC "Interopt"': {
        "vat_id": "9718077310",
        "street": "Beregovaya pass, h. 5A, b.1",
        "postcode": "127282",
        "city": "Moscow",
        "country": "Russia",
        "email": "",
        "phone": "",
        "invoiceocean_id": "198757610",
        "legal_name": 'LLC "Interopt"',
    },
    "Brandshandel Limited Liability Company": {
        "vat_id": "193674952",
        "street": "Damashevski zavulak, 11 A, room 712",
        "postcode": "220036",
        "city": "Minsk",
        "country": "Belarus",
        "email": "",
        "phone": "",
        "invoiceocean_id": "225997324",
        "legal_name": "Brandshandel Limited Liability Company",
    },
    'ООО "Селеритас"': {
        "vat_id": "193902397",
        "street": "Пр-т Газеты Звязда, 16-29",
        "postcode": "220117",
        "city": "Minsk",
        "country": "Belarus",
        "email": "",
        "phone": "",
        "invoiceocean_id": "210698971",
        "legal_name": 'ООО "Селеритас"',
    },
}


SELLERS = {
    "FMCGOODS OÜ": {
        "name": "FMCGOODS OÜ",
        "tax_id": "EE102627019",
        "bank": "Zepter Bank",
        "account_eur": "BY13 ZEPT 3024 0025 2251 0978 0000",
        "account_rub": "BY94 ZEPT 3024 0025 2281 0643 0000",
        "currency_default": "EUR",
    },
    "FMCGOODS OU": {
        "name": "FMCGOODS OÜ",
        "tax_id": "EE102627019",
        "bank": "Zepter Bank",
        "account_eur": "BY13 ZEPT 3024 0025 2251 0978 0000",
        "account_rub": "BY94 ZEPT 3024 0025 2281 0643 0000",
        "currency_default": "EUR",
    },
    "TENTA TRADE SP. Z O.O.": {
        "name": "TENTA TRADE SP. Z O.O.",
        "tax_id": "PL5423456230",
        "bank": "PKO Bank Polski",
        "account_pln": "47 1020 1332 0000 1802 1389 3625",
        "account_eur": "52 1020 1332 0000 1602 1389 3633",
        "currency_default": "PLN",
    },
}


def _clean_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def normalize_tax_id(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", _clean_string(value).upper())


def _normalize_name(value: str) -> str:
    lowered = _clean_string(value).lower()
    return re.sub(r"[^a-zа-яё0-9]+", " ", lowered).strip()


def _read_csv_any_encoding(raw_bytes: bytes) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp1251", "cp866", "latin1"):
        try:
            return pd.read_csv(io.BytesIO(raw_bytes), encoding=encoding, sep=None, engine="python")
        except Exception as exc:
            last_error = exc
    raise ValueError(f"Could not read CSV export: {last_error}")


def load_clients_from_export(raw_bytes: bytes, filename: str) -> dict[str, dict[str, str]]:
    lower_name = filename.lower()
    if lower_name.endswith((".xls", ".xlsx")):
        frame = pd.read_excel(io.BytesIO(raw_bytes))
    elif lower_name.endswith(".csv"):
        frame = _read_csv_any_encoding(raw_bytes)
    else:
        raise ValueError("Unsupported client export format. Use xls, xlsx, or csv.")

    frame.columns = [_clean_string(column) for column in frame.columns]
    frame = frame.fillna("")

    clients: dict[str, dict[str, str]] = {}
    for _, row in frame.iterrows():
        short_name = _clean_string(
            row.get("Short name")
            or row.get("Buyer")
            or row.get("Seller")
            or row.get("Client")
            or row.get("Name")
        )
        legal_name = _clean_string(
            row.get("Client")
            or row.get("Buyer")
            or row.get("Seller")
            or row.get("Company")
            or row.get("Name")
        )
        display_name = short_name or legal_name
        if not display_name:
            continue

        clients[display_name] = {
            "vat_id": _clean_string(row.get("TAX ID") or row.get("VAT ID")),
            "street": _clean_string(row.get("Street")),
            "postcode": _clean_string(row.get("Postcode")),
            "city": _clean_string(row.get("City")),
            "country": _clean_string(row.get("Country")),
            "email": _clean_string(row.get("E-mail") or row.get("Client e-mail")),
            "phone": _clean_string(row.get("Phone number") or row.get("Client's phone")),
            "invoiceocean_id": _clean_string(row.get("ID") or row.get("Client ID")),
            "legal_name": legal_name or display_name,
        }

    return clients


def merge_clients(*client_sets: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    for client_set in client_sets:
        merged.update(client_set)
    return merged


def find_best_client_match(
    counterparty_name: str,
    clients: dict[str, dict[str, str]],
    counterparty_tax_id: str = "",
) -> str:
    if not clients:
        return ""

    normalized_tax = normalize_tax_id(counterparty_tax_id)
    if normalized_tax:
        for client_name, client_data in clients.items():
            if normalize_tax_id(client_data.get("vat_id", "")) == normalized_tax:
                return client_name

    target = _normalize_name(counterparty_name)
    if not target:
        return ""

    best_name = ""
    best_score = 0
    for client_name, client_data in clients.items():
        variants = [
            _normalize_name(client_name),
            _normalize_name(client_data.get("legal_name", "")),
        ]
        for variant in filter(None, variants):
            if target == variant:
                return client_name
            if variant in target or target in variant:
                shorter = min(len(variant), len(target))
                score = 5 if shorter >= 8 else 0
            else:
                words = [word for word in variant.split() if len(word) > 3]
                score = sum(1 for word in words[:5] if word in target)
                if score < 2:
                    score = 0
            if score > best_score:
                best_score = score
                best_name = client_name

    return best_name if best_score > 0 else ""
