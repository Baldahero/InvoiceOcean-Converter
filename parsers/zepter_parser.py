"""Parser for Zepter Bank RTF statements."""

from __future__ import annotations

import re
from dataclasses import dataclass

from striprtf.striprtf import rtf_to_text


@dataclass
class ZepterTransaction:
    seq_num: str = ""
    doc_num: str = ""
    date: str = ""
    op_code: str = ""
    bic: str = ""
    account: str = ""
    debit: float = 0.0
    credit: float = 0.0
    amount: float = 0.0
    currency: str = "EUR"
    description: str = ""
    counterparty: str = ""
    counterparty_tax_id: str = ""
    counterparty_role: str = ""
    is_commission: bool = False
    is_conversion: bool = False


def _fmt_date(date_text: str) -> str:
    parts = date_text.strip().split(".")
    if len(parts) == 3:
        return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return date_text


def _parse_amount(amount_text: str) -> float:
    try:
        return float(
            amount_text.strip()
            .replace(" ", "")
            .replace("\xa0", "")
            .replace(",", ".")
        )
    except ValueError:
        return 0.0


def _is_amount(line: str) -> bool:
    return bool(re.match(r"^[\d\s\xa0]+,\d{2}$", line.strip()))


def parse_zepter_rtf(raw_bytes: bytes) -> tuple[list[ZepterTransaction], dict]:
    try:
        text = raw_bytes.decode("windows-1251", errors="replace")
    except UnicodeDecodeError:
        text = raw_bytes.decode("utf-8", errors="replace")

    plain_text = rtf_to_text(text)
    lines = [line.strip() for line in plain_text.replace("|", "\n").splitlines() if line.strip()]

    metadata: dict[str, str] = {}
    for line in lines:
        if "Счет клиента:" in line:
            account = line.split("Счет клиента:")[-1].strip()
            metadata["account"] = account
            for currency in ("EUR", "RUB", "USD", "BYN"):
                if currency in account:
                    metadata["currency"] = currency
                    break

        if "Наименование клиента:" in line:
            metadata["client"] = line.split("Наименование клиента:")[-1].strip()

        date_range = re.search(r"с\s+(\d{2}\.\d{2}\.\d{4})\s+по\s+(\d{2}\.\d{2}\.\d{4})", line)
        if date_range:
            metadata["date_from"] = _fmt_date(date_range.group(1))
            metadata["date_to"] = _fmt_date(date_range.group(2))

    currency = metadata.get("currency", "EUR")

    start_idx = 0
    for index, line in enumerate(lines):
        if line == "Курс":
            start_idx = index + 1
            break

    transactions: list[ZepterTransaction] = []
    index = start_idx

    while index < len(lines):
        if not re.match(r"^\d+$", lines[index]):
            index += 1
            continue

        if index + 2 >= len(lines):
            break

        seq_num = lines[index]
        doc_num = lines[index + 1]
        date_candidate = lines[index + 2]
        if not re.match(r"^\d{2}\.\d{2}\.\d{4}$", date_candidate):
            index += 1
            continue

        date = _fmt_date(date_candidate)
        op_code = lines[index + 3] if index + 3 < len(lines) else ""
        bic = lines[index + 4] if index + 4 < len(lines) else ""
        account = lines[index + 5] if index + 5 < len(lines) else ""

        cursor = index + 6
        amounts: list[float] = []
        while cursor < len(lines) and len(amounts) < 3 and _is_amount(lines[cursor]):
            amounts.append(_parse_amount(lines[cursor]))
            cursor += 1

        debit = 0.0
        credit = 0.0
        if amounts:
            if op_code == "1":
                credit = amounts[0]
            else:
                debit = amounts[0]

        if cursor < len(lines) and re.match(r"^\d+,\d+$", lines[cursor]):
            cursor += 1

        description_lines: list[str] = []
        while cursor < len(lines):
            if (
                re.match(r"^\d+$", lines[cursor])
                and cursor + 2 < len(lines)
                and re.match(r"^\d{2}\.\d{2}\.\d{4}$", lines[cursor + 2])
            ):
                break
            description_lines.append(lines[cursor])
            cursor += 1

        full_description = " ".join(description_lines)
        normalized_description = re.sub(r"\s+", " ", full_description).strip()

        counterparty = ""
        counterparty_role = ""
        counterparty_match = re.search(
            r"(?P<role>Бенефициар|Плательщик):\s*(?P<name>.+?)(?:УНП:|ИНН:|VAT ID:|$)",
            full_description,
        )
        if counterparty_match:
            counterparty = re.sub(r"\s+", " ", counterparty_match.group("name")).strip()
            role_text = counterparty_match.group("role")
            counterparty_role = "beneficiary" if role_text == "Бенефициар" else "payer"

        tax_match = re.search(r"(?:УНП|ИНН|VAT ID):\s*([A-Z0-9\-\s]+)", full_description)
        tax_id = re.sub(r"\s+", "", tax_match.group(1)) if tax_match else ""

        amount = credit if credit > 0 else -debit
        lower_description = normalized_description.lower()
        is_commission = "комисси" in lower_description or "цептер банк" in lower_description
        is_conversion = "конверс" in lower_description

        transactions.append(
            ZepterTransaction(
                seq_num=seq_num,
                doc_num=doc_num,
                date=date,
                op_code=op_code,
                bic=bic,
                account=account,
                debit=debit,
                credit=credit,
                amount=amount,
                currency=currency,
                description=normalized_description[:300],
                counterparty=counterparty[:120],
                counterparty_tax_id=tax_id[:40],
                counterparty_role=counterparty_role,
                is_commission=is_commission,
                is_conversion=is_conversion,
            )
        )

        index = cursor

    return transactions, metadata
