"""
Parser for PKO Bank Polski PDF statements (TENTA TRADE SP. Z O.O.).
"""
import re
from dataclasses import dataclass
import pdfplumber
import io


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


def _parse_amount(s: str) -> tuple[float, str]:
    """Returns (amount, currency)"""
    m = re.search(r'(-?[\d\s\xa0]+,\d{2})\s*(EUR|PLN|USD)', s)
    if not m:
        return 0.0, 'EUR'
    try:
        val = float(m.group(1).replace('\xa0', '').replace(' ', '').replace(',', '.'))
        return val, m.group(2)
    except Exception:
        return 0.0, 'EUR'


def parse_pko_pdf(pdf_bytes: bytes) -> tuple[list[PKOTransaction], dict]:
    transactions = []
    metadata = {}

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        all_lines = []
        for page in pdf.pages:
            text = page.extract_text() or ''
            all_lines.extend(text.split('\n'))

    # Metadata
    for line in all_lines:
        if 'RACHUNEK EUR' in line:
            metadata['currency'] = 'EUR'
        elif 'BIZNES PARTNER' in line:
            metadata['currency'] = 'PLN'
        m = re.search(r'from:\s*(\d{4}-\d{2}-\d{2})', line)
        if m:
            metadata['date_from'] = m.group(1)
        m = re.search(r'to:\s*(\d{4}-\d{2}-\d{2})', line)
        if m:
            metadata['date_to'] = m.group(1)

    currency = metadata.get('currency', 'EUR')

    DATE_RE = re.compile(r'^(\d{4}-\d{2}-\d{2})\s+(.+)$')
    OP_TYPES = ['Commission', 'Foreign transfer', 'Transfer from account',
                'Crediting', 'Debit', 'VAT transfer to Tax Office',
                'Transfer to Social Security Institution']

    dated_lines = []
    for line in all_lines:
        m = DATE_RE.match(line.strip())
        if m:
            dated_lines.append((m.group(1), m.group(2)))

    for date, data in dated_lines:
        # Find operation type
        op_type = ''
        for op in OP_TYPES:
            if op in data:
                op_type = op
                break
        if not op_type:
            continue

        amount, cur = _parse_amount(data)
        if amount == 0.0:
            continue

        # Skip PLN commission description lines (e.g. "Commission: 61,10 PLN")
        # Real EUR commissions are negative small amounts like -14.38 EUR
        if op_type == 'Commission' and cur == 'PLN' and amount > 0:
            continue

        # Counterparty name
        cp_name = ''
        cpn_m = re.search(r'Counterparty name and address:\s*(.+?)(?=Title:|Transaction identifier|Commission:|$)', data)
        if cpn_m:
            cp_name = re.sub(r'\s+', ' ', cpn_m.group(1)).strip()

        # Title
        title = ''
        title_m = re.search(r'Title:\s*(.+?)(?=Transaction identifier|Commission:|Own references|$)', data)
        if title_m:
            title = re.sub(r'\s+', ' ', title_m.group(1)).strip()

        # Counterparty account
        cp_acc = ''
        cpa_m = re.search(r'Counterparty account:\s*([\w\s]+?)(?=Counterparty name|Title:|$)', data)
        if cpa_m:
            cp_acc = cpa_m.group(1).strip()

        # Transaction ID
        tx_id = ''
        txid_m = re.search(r'Transaction identifier:\s*(\d+)', data)
        if txid_m:
            tx_id = txid_m.group(1)

        transactions.append(PKOTransaction(
            date=date,
            op_type=op_type,
            counterparty_account=cp_acc[:80],
            counterparty_name=cp_name[:150],
            title=title[:200],
            tx_id=tx_id,
            amount=amount,
            currency=cur,
        ))

    return transactions, metadata
