"""
Parser for PKO Bank Polski PDF statements (TENTA TRADE SP. Z O.O.).
Handles PLN and EUR accounts.
Requires: pdfplumber
"""
import re
from dataclasses import dataclass


@dataclass
class PKOTransaction:
    date: str = ""           # YYYY-MM-DD
    value_date: str = ""
    op_type: str = ""
    counterparty_account: str = ""
    counterparty_name: str = ""
    title: str = ""
    tx_id: str = ""
    amount: float = 0.0
    currency: str = "PLN"
    balance: float = 0.0


def parse_pko_pdf(pdf_bytes: bytes) -> tuple[list[PKOTransaction], dict]:
    """
    Parse PKO Bank Polski PDF statement.
    Returns (transactions, metadata).
    Requires pdfplumber installed.
    """
    try:
        import pdfplumber
        import io
    except ImportError:
        raise ImportError("pdfplumber not installed. Run: pip install pdfplumber")

    transactions = []
    metadata = {}

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        full_text = ""
        for page in pdf.pages:
            full_text += page.extract_text() or ""
            full_text += "\n"

    # Detect currency from account name
    if "RACHUNEK EUR" in full_text:
        currency = "EUR"
    else:
        currency = "PLN"
    metadata["currency"] = currency

    # Extract account number
    acc_m = re.search(r'Account:\s*([A-Z\s\d]+(?:\d{2}\s*\d{4}\s*\d{4}\s*\d{4}\s*\d{4}\s*\d{4}\s*\d{4}))', full_text)
    if acc_m:
        metadata["account"] = acc_m.group(1).strip()

    # Extract company name
    comp_m = re.search(r'Company name:\s*(.+)', full_text)
    if comp_m:
        metadata["company"] = comp_m.group(1).strip()

    # Extract date range
    dates = re.findall(r'Operation date - (?:from|to):\s*(\d{4}-\d{2}-\d{2})', full_text)
    if len(dates) >= 2:
        metadata["date_from"] = dates[0]
        metadata["date_to"] = dates[1]

    # Parse transaction blocks
    # Each transaction starts with a date pair YYYY-MM-DD
    lines = full_text.split("\n")

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Transaction date line: two identical dates on consecutive lines
        date_m = re.match(r'^(\d{4}-\d{2}-\d{2})$', line)
        if date_m:
            date = date_m.group(1)
            # Next line should also be a date (value date)
            if i + 1 < len(lines) and re.match(r'^\d{4}-\d{2}-\d{2}$', lines[i + 1].strip()):
                value_date = lines[i + 1].strip()
                # Collect block until next date pair
                block_lines = []
                j = i + 2
                while j < len(lines):
                    next_line = lines[j].strip()
                    if re.match(r'^\d{4}-\d{2}-\d{2}$', next_line):
                        break
                    if "Electronic document" in next_line or "Page " in next_line:
                        j += 1
                        continue
                    if next_line:
                        block_lines.append(next_line)
                    j += 1

                tx = _parse_pko_block(date, value_date, block_lines, currency)
                if tx:
                    transactions.append(tx)
                i = j
                continue
        i += 1

    return transactions, metadata


def _parse_pko_block(date: str, value_date: str, lines: list[str], currency: str) -> PKOTransaction | None:
    """Parse a single transaction block."""
    full_text = " ".join(lines)

    # Extract amount — last monetary value in the block
    # Pattern: number with spaces/commas like "4 225,60 PLN" or "-528,90 PLN"
    amounts = re.findall(r'(-?[\d\s]+,\d{2})\s*(PLN|EUR)', full_text)
    if not amounts:
        return None

    # First amount = transaction amount, second = balance
    try:
        tx_amount_str = amounts[0][0].replace(" ", "").replace(",", ".")
        amount = float(tx_amount_str)
        cur = amounts[0][1]
    except Exception:
        return None

    # Operation type
    op_type = ""
    for ot in ["Crediting", "Transfer from account", "Foreign transfer",
               "Commission", "VAT transfer to Tax Office",
               "Transfer to Social Security Institution", "Debit"]:
        if ot in full_text:
            op_type = ot
            break

    # Counterparty account
    cp_acc = ""
    cp_m = re.search(r'Counterparty account:\s*([\d\s]+)', full_text)
    if cp_m:
        cp_acc = cp_m.group(1).strip()

    # Counterparty name
    cp_name = ""
    cpn_m = re.search(r'Counterparty name[^:]*:\s*(.+?)(?=Title:|Transaction|$)', full_text, re.DOTALL)
    if cpn_m:
        cp_name = re.sub(r'\s+', ' ', cpn_m.group(1)).strip()[:150]

    # Title / description
    title = ""
    title_m = re.search(r'Title:\s*(.+?)(?=Transaction|Commission|Own references|$)', full_text, re.DOTALL)
    if title_m:
        title = re.sub(r'\s+', ' ', title_m.group(1)).strip()[:200]

    # Transaction ID
    tx_id = ""
    txid_m = re.search(r'Transaction identifier:\s*(\d+)', full_text)
    if txid_m:
        tx_id = txid_m.group(1)

    return PKOTransaction(
        date=date,
        value_date=value_date,
        op_type=op_type,
        counterparty_account=cp_acc,
        counterparty_name=cp_name,
        title=title,
        tx_id=tx_id,
        amount=amount,
        currency=cur,
    )
