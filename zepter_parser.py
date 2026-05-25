"""
Parser for Zepter Bank RTF statements (FMCGOODS OÜ).
Structure (after striprtf):
  line 0: seq_num
  line 1: doc_num
  line 2: date DD.MM.YYYY
  line 3: op_code  (1=transfer in, 6=commission/internal)
  line 4: correspondent BIC
  line 5: account IBAN
  line 6: debit amount  OR credit amount  (only one is present)
  line 7: equiv amount
  line 8: rate
  line 9: description type (OTHR ...)
  line 10: description text
  line 11: Бенефициар/Плательщик line
  then next seq_num starts
"""
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
    amount: float = 0.0        # positive = incoming, negative = outgoing
    currency: str = "EUR"
    description: str = ""
    counterparty: str = ""
    is_commission: bool = False
    is_conversion: bool = False


def _fmt_date(d: str) -> str:
    """DD.MM.YYYY → YYYY-MM-DD"""
    parts = d.strip().split(".")
    if len(parts) == 3:
        return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return d


def _parse_amount(s: str) -> float:
    """'43 891,20' → 43891.20"""
    try:
        return float(s.strip().replace(" ", "").replace("\xa0", "").replace(",", "."))
    except Exception:
        return 0.0


def _is_amount(s: str) -> bool:
    return bool(re.match(r'^[\d\s\xa0]+,\d{2}$', s.strip()))


def parse_zepter_rtf(raw_bytes: bytes) -> tuple[list[ZepterTransaction], dict]:
    """Parse Zepter Bank RTF. Returns (transactions, metadata)."""
    try:
        text_cp = raw_bytes.decode("windows-1251", errors="replace")
    except Exception:
        text_cp = raw_bytes.decode("utf-8", errors="replace")

    plain = rtf_to_text(text_cp)
    lines = [l.strip() for l in plain.replace("|", "\n").split("\n") if l.strip()]

    # ── Metadata ──────────────────────────────────────────────────────────────
    metadata = {}
    for line in lines:
        if "Счет клиента:" in line:
            acc = line.split("Счет клиента:")[-1].strip()
            metadata["account"] = acc
            for cur in ("EUR", "RUB", "USD", "BYN"):
                if cur in acc:
                    metadata["currency"] = cur
                    break
        if "Наименование клиента:" in line:
            metadata["client"] = line.split("Наименование клиента:")[-1].strip()
        dm = re.search(r'с\s+(\d{2}\.\d{2}\.\d{4})\s+по\s+(\d{2}\.\d{2}\.\d{4})', line)
        if dm:
            metadata["date_from"] = _fmt_date(dm.group(1))
            metadata["date_to"] = _fmt_date(dm.group(2))

    currency = metadata.get("currency", "EUR")

    # ── Find data start (after header rows) ───────────────────────────────────
    # Header ends with "Курс" line
    start_idx = 0
    for i, l in enumerate(lines):
        if l == "Курс":
            start_idx = i + 1
            break

    # ── Parse transactions ────────────────────────────────────────────────────
    transactions = []
    i = start_idx

    while i < len(lines):
        # Expect: seq_num (pure integer)
        if not re.match(r'^\d+$', lines[i]):
            i += 1
            continue

        seq = lines[i]
        if i + 1 >= len(lines):
            break
        doc = lines[i + 1]

        # Next must be a date
        if i + 2 >= len(lines) or not re.match(r'^\d{2}\.\d{2}\.\d{4}$', lines[i + 2]):
            i += 1
            continue

        date = _fmt_date(lines[i + 2])

        # op_code
        op_code = lines[i + 3] if i + 3 < len(lines) else ""
        # bic
        bic = lines[i + 4] if i + 4 < len(lines) else ""
        # account
        account = lines[i + 5] if i + 5 < len(lines) else ""

        # Amounts: next 1-3 numeric lines
        j = i + 6
        amounts_raw = []
        while j < len(lines) and len(amounts_raw) < 3 and _is_amount(lines[j]):
            amounts_raw.append(_parse_amount(lines[j]))
            j += 1

        # Determine debit / credit based on op_code and count
        # op_code 1 = incoming (credit only)
        # op_code 6 = outgoing/commission (debit only or debit+equiv)
        debit, credit = 0.0, 0.0
        if amounts_raw:
            if op_code == "1":
                credit = amounts_raw[0]
            else:
                debit = amounts_raw[0]

        # Skip rate line if present
        if j < len(lines) and re.match(r'^\d+,\d+$', lines[j]):
            j += 1

        # Description lines until next seq_num
        desc_lines = []
        while j < len(lines):
            if re.match(r'^\d+$', lines[j]) and j + 2 < len(lines) and re.match(r'^\d{2}\.\d{2}\.\d{4}$', lines[j + 2]):
                break
            desc_lines.append(lines[j])
            j += 1

        full_desc = " ".join(desc_lines)

        # Counterparty
        counterparty = ""
        cp_m = re.search(r'(?:Бенефициар|Плательщик):\s*([^У]+?)(?:УНП:|$)', full_desc)
        if cp_m:
            counterparty = re.sub(r'\s+', ' ', cp_m.group(1)).strip()

        amount = credit if credit > 0 else -debit

        is_comm = "комисси" in full_desc.lower() or "ЦЕПТЕР БАНК" in full_desc
        is_conv = "конверс" in full_desc.lower()

        tx = ZepterTransaction(
            seq_num=seq,
            doc_num=doc,
            date=date,
            op_code=op_code,
            bic=bic,
            account=account,
            debit=debit,
            credit=credit,
            amount=amount,
            currency=currency,
            description=re.sub(r'\s+', ' ', full_desc).strip()[:300],
            counterparty=counterparty[:120],
            is_commission=is_comm,
            is_conversion=is_conv,
        )
        transactions.append(tx)
        i = j

    return transactions, metadata
