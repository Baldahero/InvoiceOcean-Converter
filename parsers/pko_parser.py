"""Parser for PKO Bank Polski PDF statements."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

import pdfplumber


@dataclass
class PKOTransaction:
    date: str = ""
    op_type: str = ""
    counterparty_account: str = ""
    counterparty_name: str = ""
    title: str = ""
    tx_id: str = ""
    amount: float = 0.0
    currency: str = "PLN"


def _parse_amount(text: str) -> tuple[float, str]:
    match = re.search(r"(-?[\d\s\xa0]+,\d{2})\s*(EUR|PLN|USD)", text)
    if not match:
        return 0.0, "EUR"

    try:
        amount = float(
            match.group(1)
            .replace("\xa0", "")
            .replace(" ", "")
            .replace(",", ".")
        )
        return amount, match.group(2)
    except ValueError:
        return 0.0, "EUR"


def parse_pko_pdf(pdf_bytes: bytes) -> tuple[list[PKOTransaction], dict]:
    transactions: list[PKOTransaction] = []
    metadata: dict[str, str] = {}

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        all_lines: list[str] = []
        for page in pdf.pages:
            text = page.extract_text() or ""
            all_lines.extend(text.splitlines())

    for line in all_lines:
        if "RACHUNEK EUR" in line:
            metadata["currency"] = "EUR"
        elif "BIZNES PARTNER" in line:
            metadata["currency"] = "PLN"

        date_from = re.search(r"from:\s*(\d{4}-\d{2}-\d{2})", line)
        if date_from:
            metadata["date_from"] = date_from.group(1)

        date_to = re.search(r"to:\s*(\d{4}-\d{2}-\d{2})", line)
        if date_to:
            metadata["date_to"] = date_to.group(1)

    dated_line_re = re.compile(r"^(\d{4}-\d{2}-\d{2})\s+(.+)$")
    operation_types = [
        "Commission",
        "Foreign transfer",
        "Transfer from account",
        "Crediting",
        "Debit",
        "VAT transfer to Tax Office",
        "Transfer to Social Security Institution",
    ]

    for line in all_lines:
        match = dated_line_re.match(line.strip())
        if not match:
            continue

        date, payload = match.group(1), match.group(2)
        op_type = next((op for op in operation_types if op in payload), "")
        if not op_type:
            continue

        amount, currency = _parse_amount(payload)
        if amount == 0.0:
            continue

        if op_type == "Commission" and currency == "PLN" and amount > 0:
            continue

        cp_name_match = re.search(
            r"Counterparty name and address:\s*(.+?)(?=Title:|Transaction identifier|Commission:|$)",
            payload,
        )
        title_match = re.search(
            r"Title:\s*(.+?)(?=Transaction identifier|Commission:|Own references|$)",
            payload,
        )
        account_match = re.search(
            r"Counterparty account:\s*([\w\s]+?)(?=Counterparty name|Title:|$)",
            payload,
        )
        tx_id_match = re.search(r"Transaction identifier:\s*(\d+)", payload)

        transactions.append(
            PKOTransaction(
                date=date,
                op_type=op_type,
                counterparty_account=(account_match.group(1).strip() if account_match else "")[:80],
                counterparty_name=(
                    re.sub(r"\s+", " ", cp_name_match.group(1)).strip() if cp_name_match else ""
                )[:150],
                title=(re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else "")[:200],
                tx_id=tx_id_match.group(1) if tx_id_match else "",
                amount=amount,
                currency=currency,
            )
        )

    return transactions, metadata
