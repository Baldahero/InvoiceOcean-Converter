"""
Parser for PKO Bank Polski WYCIĄG (Polish monthly statement) PDF.
Format: DD.MM.YYYY  TxID  TYP OPERACJI  amount  balance
Used for FMCGOODS OÜ accounts at PKO.
"""
import re
import pdfplumber
import io
from dataclasses import dataclass, field


@dataclass
class PKOWyciagTransaction:
    date:              str   = ""   # YYYY-MM-DD
    tx_id:             str   = ""
    op_type:           str   = ""
    amount:            float = 0.0
    currency:          str   = "EUR"
    beneficiary:       str   = ""
    account:           str   = ""
    title:             str   = ""
    is_commission:     bool  = False
    is_fx:             bool  = False


def _fmt_date(d: str) -> str:
    """DD.MM.YYYY → YYYY-MM-DD"""
    p = d.strip().split('.')
    return f"{p[2]}-{p[1]}-{p[0]}" if len(p) == 3 else d


def _amt(s: str) -> float:
    try:
        return float(s.replace('\xa0','').replace(' ','').replace(',','.'))
    except:
        return 0.0


# Polish op type → English
OP_MAP = {
    'OBC.KWOTĄ WYSYŁ. PRZEL.ZAGRANICZNY': 'Foreign transfer',
    'OBC. PROW. OD WYSYŁ. PRZEL. ZAGR':  'Commission',
    'PRZELEW PRZYCHODZĄCY':               'Incoming transfer',
    'PRZELEW WYCHODZĄCY':                 'Outgoing transfer',
    'OBCIĄŻENIE OPERACJĄ SKARBOWĄ':       'FX debit',
    'UZNANIE OPERACJĄ SKARBOWĄ':          'FX credit',
    'SPŁ.NIEAUT.ODS.ZAPADŁYCH NIESPŁAC.': 'Interest',
    'OPŁATA MIESIĘCZNA ZA KARTĘ':         'Card fee',
    'OPŁATA ZA PROWADZENIE RACHUNKU':     'Account fee',
}


def parse_pko_wyciag(pdf_bytes: bytes) -> tuple[list[PKOWyciagTransaction], dict]:
    transactions = []
    metadata = {}

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        all_lines = []
        for page in pdf.pages:
            text = page.extract_text() or ''
            all_lines.extend(text.split('\n'))

    # Metadata
    for line in all_lines:
        if 'WYCIĄG za okres' in line:
            m = re.search(r'(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}\.\d{2}\.\d{4})', line)
            if m:
                metadata['date_from'] = _fmt_date(m.group(1))
                metadata['date_to']   = _fmt_date(m.group(2))
        if 'Waluta rachunku:' in line:
            for cur in ('EUR', 'PLN', 'USD'):
                if cur in line:
                    metadata['currency'] = cur
                    break
        if 'Nr rachunku/karty:' in line:
            m = re.search(r'Nr rachunku/karty:\s*([\d\s]+)', line)
            if m:
                metadata['account'] = m.group(1).strip()

    currency = metadata.get('currency', 'EUR')

    # Transaction line: "04.05.2026 6624GP07900000838 OBCIĄŻENIE OPERACJĄ SKARBOWĄ -24,00 900,28"
    # Two dates on consecutive lines = one transaction (date operacji + data waluty)
    TX_RE = re.compile(
        r'^(\d{2}\.\d{2}\.\d{4})\s+(\S+)\s+(.+?)\s+(-?[\d\s]+,\d{2})\s+(-?[\d\s]+,\d{2})\s*$'
    )

    i = 0
    while i < len(all_lines):
        line = all_lines[i].strip()
        m = TX_RE.match(line)
        if m:
            date    = _fmt_date(m.group(1))
            tx_id   = m.group(2)
            op_raw  = m.group(3).strip()
            amount  = _amt(m.group(4))

            # Map Polish → English op type
            op_type = op_raw
            for pl, en in OP_MAP.items():
                if pl in op_raw:
                    op_type = en
                    break

            # Skip the value-date line (same date repeated)
            j = i + 1
            desc_lines = []
            while j < len(all_lines):
                dl = all_lines[j].strip()
                # Stop at next transaction
                if TX_RE.match(dl):
                    break
                # Stop at page footer
                if 'Saldo do przeniesienia' in dl or 'Saldo końcowe' in dl:
                    break
                if 'Niniejszy dokument' in dl or 'Powszechna Kasa' in dl:
                    j += 1
                    continue
                if dl:
                    desc_lines.append(dl)
                j += 1

            full_desc = ' '.join(desc_lines)

            # Extract beneficiary
            benef = ''
            b_m = re.search(r'Benef\.:\s*(.+?)(?:Rach\. benef\.|tyt\.|$)', full_desc)
            if b_m:
                benef = b_m.group(1).strip()

            # Extract title
            title = ''
            t_m = re.search(r'tyt\.:\s*(.+?)(?:Kwota oryg|$)', full_desc)
            if t_m:
                title = t_m.group(1).strip()

            # If no benef, use first desc line
            if not benef and desc_lines:
                benef = desc_lines[0][:80]

            is_comm = op_type in ('Commission', 'Account fee', 'Card fee', 'Interest')
            is_fx   = op_type in ('FX debit', 'FX credit') or 'FX' in tx_id

            transactions.append(PKOWyciagTransaction(
                date=date, tx_id=tx_id, op_type=op_type,
                amount=amount, currency=currency,
                beneficiary=benef[:120],
                title=title[:200],
                is_commission=is_comm,
                is_fx=is_fx,
            ))
            i = j
        else:
            i += 1

    return transactions, metadata
