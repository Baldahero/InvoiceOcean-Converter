"""
Parser for Zepter Bank PDF statements (FMCGOODS OÜ).
Format per transaction block:
  Line A: "{seq} {doc} {date} {op_code} {BIC} {amount_debit} {amount_credit} {equiv_debit} {equiv_credit} {rate}"
           (account number split across lines)
  Line B: "OTHR Иной платеж" or "INTE CMCN ..."
  Line C+: description text
  Line D: "Бенефициар: ..." or "Плательщик: ..."
"""
import re
import pdfplumber
import io
from dataclasses import dataclass


@dataclass
class ZepterPDFTransaction:
    seq_num:      str   = ""
    doc_num:      str   = ""
    date:         str   = ""   # YYYY-MM-DD
    op_code:      str   = ""   # 1=credit, 6=debit
    bic:          str   = ""
    account:      str   = ""
    debit:        float = 0.0
    credit:       float = 0.0
    amount:       float = 0.0  # positive=incoming, negative=outgoing
    currency:     str   = "EUR"
    description:  str   = ""
    counterparty: str   = ""
    is_commission:  bool = False
    is_conversion:  bool = False


def _amt(s: str) -> float:
    try:
        return float(s.replace('\xa0', '').replace(' ', '').replace(',', '.'))
    except:
        return 0.0


def _fmt_date(d: str) -> str:
    """DD.MM.YYYY → YYYY-MM-DD"""
    p = d.strip().split('.')
    return f"{p[2]}-{p[1]}-{p[0]}" if len(p) == 3 else d


def parse_zepter_pdf(pdf_bytes: bytes) -> tuple[list[ZepterPDFTransaction], dict]:
    transactions = []
    metadata = {}

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        all_lines = []
        for page in pdf.pages:
            text = page.extract_text() or ''
            all_lines.extend(text.split('\n'))

    # Metadata
    for line in all_lines:
        if 'Счет клиента:' in line:
            m = re.search(r'Счет клиента:\s*(\S+)\s+(EUR|RUB|USD|BYN)', line)
            if m:
                metadata['account']  = m.group(1)
                metadata['currency'] = m.group(2)
        if 'с ' in line and 'по ' in line:
            m = re.search(r'с\s+(\d{2}\.\d{2}\.\d{4})\s+по\s+(\d{2}\.\d{2}\.\d{4})', line)
            if m:
                metadata['date_from'] = _fmt_date(m.group(1))
                metadata['date_to']   = _fmt_date(m.group(2))
        if 'Наименование клиента:' in line:
            metadata['client'] = line.split('Наименование клиента:')[-1].strip()

    currency = metadata.get('currency', 'EUR')

    # Transaction main line pattern:
    # "1 236 04.05.2026 1 BPKOPLPW 43 891,20 145 108,70 3,3061"
    # op_code 1 → credit column filled, op_code 6 → debit column filled
    TX_RE = re.compile(
        r'^(\d+)\s+(\S+)\s+(\d{2}\.\d{2}\.\d{4})\s+(\d)\s+(\S+)\s+'
        r'([\d\s]+,\d{2})\s+([\d\s]+,\d{2})\s+([\d\s,]+)$'
    )

    i = 0
    while i < len(all_lines):
        line = all_lines[i].strip()
        m = TX_RE.match(line)
        if m:
            seq      = m.group(1)
            doc      = m.group(2)
            date     = _fmt_date(m.group(3))
            op_code  = m.group(4)
            bic      = m.group(5)
            val1     = _amt(m.group(6))
            val2     = _amt(m.group(7))

            # op_code 1 = incoming (credit): val1=credit, val2=equiv_credit
            # op_code 6 = outgoing (debit):  val1=debit,  val2=equiv_debit
            if op_code == '1':
                debit, credit = 0.0, val1
            else:
                debit, credit = val1, 0.0

            amount = credit if credit > 0 else -debit

            # Collect account (next line if it looks like account fragment)
            account = ''
            if i + 1 < len(all_lines):
                next_l = all_lines[i + 1].strip()
                if re.match(r'^[A-Z0-9\s]+$', next_l) and len(next_l) < 30:
                    account = next_l
                    i += 1

            # Collect description lines until next transaction or end
            desc_lines = []
            j = i + 1
            while j < len(all_lines):
                dl = all_lines[j].strip()
                if TX_RE.match(dl):
                    break
                if dl in ('', 'КОПИЯ') or 'Наименование банка' in dl or 'Подпись банка' in dl:
                    j += 1
                    continue
                if 'Итого оборотов' in dl or 'Исходящее сальдо' in dl:
                    break
                desc_lines.append(dl)
                j += 1

            full_desc = ' '.join(desc_lines)

            # Counterparty
            counterparty = ''
            cp_m = re.search(r'(?:Бенефициар|Плательщик):\s*([^У]+?)(?:УНП:|$)', full_desc)
            if cp_m:
                counterparty = re.sub(r'\s+', ' ', cp_m.group(1)).strip()[:120]

            is_comm = ('комиссии' in full_desc.lower() or
                       'ЦЕПТЕР БАНК' in full_desc or
                       'ком.возн' in full_desc.lower() or
                       'ком.вознагр' in full_desc.lower())
            is_conv = 'конверсией' in full_desc.lower() or 'конверсия' in full_desc.lower()

            transactions.append(ZepterPDFTransaction(
                seq_num=seq, doc_num=doc, date=date,
                op_code=op_code, bic=bic, account=account,
                debit=debit, credit=credit, amount=amount,
                currency=currency,
                description=re.sub(r'\s+', ' ', full_desc).strip()[:300],
                counterparty=counterparty,
                is_commission=is_comm,
                is_conversion=is_conv,
            ))
            i = j
        else:
            i += 1

    return transactions, metadata


def parse_zepter_pdf_rub(pdf_bytes: bytes) -> tuple[list[ZepterPDFTransaction], dict]:
    """
    Parser for RUB account — different column layout in PDF.
    Transaction line: "{seq} {doc} {date} {op_code} [{BIC}] {debit} {credit} {rate}"
    But BIC and account are on separate lines before/after the main line.
    """
    transactions = []
    metadata = {}

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        all_lines = []
        for page in pdf.pages:
            text = page.extract_text() or ''
            all_lines.extend(text.split('\n'))

    # Metadata
    for line in all_lines:
        if 'Счет клиента:' in line:
            m = re.search(r'Счет клиента:\s*(\S+)\s+(EUR|RUB|USD|BYN)', line)
            if m:
                metadata['account']  = m.group(1)
                metadata['currency'] = m.group(2)
        m = re.search(r'с\s+(\d{2}\.\d{2}\.\d{4})\s+по\s+(\d{2}\.\d{2}\.\d{4})', line)
        if m:
            metadata['date_from'] = _fmt_date(m.group(1))
            metadata['date_to']   = _fmt_date(m.group(2))

    currency = metadata.get('currency', 'RUB')

    # RUB format: main line is like:
    # "1 000018 05.05.2026 6  6 056 267,75  228 284,96"  (no BIC on same line)
    # or "2 241 06.05.2026 6 ZEPTBY2X  6 300 000,00  237 680,10"
    TX_RE_RUB = re.compile(
        r'^(\d+)\s+(\S+)\s+(\d{2}\.\d{2}\.\d{4})\s+(\d)\s+'
        r'(?:(\S+)\s+)?([\d\s]+,\d{2})\s+([\d\s]+,\d{2})'
    )

    i = 0
    while i < len(all_lines):
        line = all_lines[i].strip()
        m = TX_RE_RUB.match(line)
        if m:
            seq     = m.group(1)
            doc     = m.group(2)
            date    = _fmt_date(m.group(3))
            op_code = m.group(4)
            bic     = m.group(5) or ''
            val1    = _amt(m.group(6))
            val2    = _amt(m.group(7))

            # For RUB: op_code 1=credit incoming, op_code 6=debit outgoing
            # val1 = amount in account currency (RUB), val2 = equiv EUR
            if op_code == '1':
                debit, credit = 0.0, val1
            else:
                debit, credit = val1, 0.0
            amount = credit if credit > 0 else -debit

            # Collect description
            desc_lines = []
            j = i + 1
            while j < len(all_lines):
                dl = all_lines[j].strip()
                if TX_RE_RUB.match(dl):
                    break
                if 'Итого оборотов' in dl or 'Исходящее сальдо' in dl:
                    break
                if dl and dl not in ('КОПИЯ',) and 'Наименование банка' not in dl:
                    desc_lines.append(dl)
                j += 1

            full_desc = ' '.join(desc_lines)

            counterparty = ''
            # For RUB: payer info
            cp_m = re.search(r'(?:Плательщик|Бенефициар):\s*([^У]+?)(?:УНП:|$)', full_desc)
            if cp_m:
                counterparty = re.sub(r'\s+', ' ', cp_m.group(1)).strip()[:120]
            # Also try company name from VO lines
            if not counterparty:
                vo_m = re.search(r'OOO\s+\w+|ООО\s+\S+', full_desc)
                if vo_m:
                    counterparty = vo_m.group(0)

            is_comm = ('ком.вознагр' in full_desc.lower() or
                       'ком.возн' in full_desc.lower() or
                       'ЦЕПТЕР БАНК' in full_desc)
            is_conv = 'конверсией' in full_desc.lower() or 'конверсия' in full_desc.lower()

            transactions.append(ZepterPDFTransaction(
                seq_num=seq, doc_num=doc, date=date,
                op_code=op_code, bic=bic, account='',
                debit=debit, credit=credit, amount=amount,
                currency=currency,
                description=re.sub(r'\s+', ' ', full_desc).strip()[:300],
                counterparty=counterparty,
                is_commission=is_comm,
                is_conversion=is_conv,
            ))
            i = j
        else:
            i += 1

    return transactions, metadata


def parse_zepter_pdf_auto(pdf_bytes: bytes) -> tuple[list[ZepterPDFTransaction], dict]:
    """Auto-detect EUR or RUB and use correct parser."""
    # Peek at currency
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        text = pdf.pages[0].extract_text() or ''
    if 'RUB' in text:
        return parse_zepter_pdf_rub(pdf_bytes)
    return parse_zepter_pdf(pdf_bytes)
