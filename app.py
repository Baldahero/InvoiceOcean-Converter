import streamlit as st
import pandas as pd
import pdfplumber
import re
import csv
import io
from datetime import datetime, timedelta

st.set_page_config(page_title="Bank → InvoiceOcean", page_icon="🏦", layout="wide")

# ══════════════════════════════════════════════════════════════════════
# КЛИЕНТЫ
# ══════════════════════════════════════════════════════════════════════
CLIENTS = {
    "Brandshandel Limited Liability Company": {"vat_id": "193674952", "street": 'Damashevski zavulak, 11 "A", room 712', "postcode": "220036", "city": "Minsk", "country": "BY", "email": ""},
    "Tenta Trade sp z o.o.": {"vat_id": "PL5423456230", "street": "Ludwika Zamenhofa 29", "postcode": "15435", "city": "Białystok", "country": "PL", "email": "purchase@tentatrade.com"},
    'LLC "Interopt"': {"vat_id": "9718077310", "street": "Beregovaya pass, h. 5A, b.1", "postcode": "127282", "city": "Moscow", "country": "RU", "email": ""},
    "PILOT D S SP. Z.O.O.": {"vat_id": "5242950541", "street": "UL.STANIEWICKA 5", "postcode": "03-310", "city": "Warszawa", "country": "PL", "email": ""},
    "GHS CLASSIC DRINKS LTD": {"vat_id": "", "street": "UNIT 5, OC COMMERCIAL PARK, LITTLE ISLAND", "postcode": "", "city": "Cork", "country": "IE", "email": ""},
    "DLG UAB": {"vat_id": "", "street": "PERKUNKIEMIO G. 5", "postcode": "LT-12129", "city": "Vilnius", "country": "LT", "email": ""},
    "SIA PRODIMPEKSS LOGISTIKAS GRUPA": {"vat_id": "", "street": "", "postcode": "", "city": "Riga", "country": "LV", "email": ""},
    "GREENRISE OU": {"vat_id": "", "street": "LAKI 16-411", "postcode": "", "city": "Tallinn", "country": "EE", "email": ""},
    "BV PROVISIONS": {"vat_id": "", "street": "SCHEEPSDALELAAN 18", "postcode": "8000", "city": "Brugge", "country": "BE", "email": ""},
    "GLOBAL TRADE SERVICES SARL": {"vat_id": "", "street": "", "postcode": "", "city": "", "country": "ES", "email": ""},
    "DIOS LOGISTIC SIA": {"vat_id": "", "street": "LATGALES IELA 240, K. 3", "postcode": "LV-1063", "city": "Riga", "country": "LV", "email": ""},
    "SANDERA MB": {"vat_id": "", "street": "VISAGINO STR. 16A", "postcode": "31117", "city": "Visaginas", "country": "LT", "email": ""},
    "KREGERLORNA UAB": {"vat_id": "", "street": "", "postcode": "", "city": "", "country": "LT", "email": ""},
    "Casovnikova Liudmila": {"vat_id": "", "street": "", "postcode": "", "city": "", "country": "FR", "email": ""},
    "MULTI-FRUIT SP. Z O.O.": {"vat_id": "", "street": "UL. CECYLII ŚNIEGOCKIEJ 10/49", "postcode": "00-430", "city": "Warszawa", "country": "PL", "email": ""},
    "CONSULT CORPORATION SP. Z O.O.": {"vat_id": "", "street": "UL. BOBROWIECKA 10/67", "postcode": "00-728", "city": "Warszawa", "country": "PL", "email": ""},
    "SANBAKS KONSULT": {"vat_id": "", "street": "", "postcode": "", "city": "", "country": "PL", "email": ""},
    "LLC CELERITAS": {"vat_id": "193902397", "street": "Pr-t Gazety Zvyazda, 16-29", "postcode": "", "city": "Minsk", "country": "BY", "email": ""},
    "W.CONSULTANCY B.V.": {"vat_id": "", "street": "TUINBOUWVEILINGWEG 5 B34", "postcode": "4814RP", "city": "Breda", "country": "NL", "email": ""},
    "CHIC N BASIC 2010 SL": {"vat_id": "B65316093", "street": "AV. CASTELL DE BARBERA, 27-29", "postcode": "08210", "city": "Barcelona", "country": "ES", "email": ""},
    "SEZEN ANNA": {"vat_id": "", "street": "", "postcode": "", "city": "", "country": "ES", "email": ""},
    "ASSTRA FORWARDING AG": {"vat_id": "CHE-115.138.470", "street": "Staubstrasse 15", "postcode": "8038", "city": "Zurich", "country": "CH", "email": "office@asstra.com"},
    "LLC UNISTORE GROUP": {"vat_id": "", "street": "SLOBODSKAYA 131", "postcode": "", "city": "Minsk", "country": "BY", "email": ""},
    "OOO GROALLS": {"vat_id": "193766800", "street": "G.MINSK, UL.TIMIRYAZEVA, DOM 67-222", "postcode": "", "city": "Minsk", "country": "BY", "email": ""},
}

SELLERS = {
    "FMCGOODS OÜ": {"name": "FMCGOODS OÜ", "tax_id": "EE102627019"},
    "TENTA TRADE SP. Z O.O.": {"name": "TENTA TRADE SP. Z O.O.", "tax_id": "PL5423456230"},
}

# ══════════════════════════════════════════════════════════════════════
# ПАРСЕРЫ
# ══════════════════════════════════════════════════════════════════════

def _amt(s):
    try: return float(str(s).replace('\xa0','').replace(' ','').replace(',','.'))
    except: return 0.0

def _fdate(d):
    p = str(d).strip().split('.')
    return f"{p[2]}-{p[1]}-{p[0]}" if len(p)==3 else d

def _pdf_lines(path_or_bytes):
    src = io.BytesIO(path_or_bytes) if isinstance(path_or_bytes, bytes) else path_or_bytes
    lines = []
    with pdfplumber.open(src) as pdf:
        for page in pdf.pages:
            lines.extend((page.extract_text() or '').split('\n'))
    return lines

def detect_bank(pdf_bytes):
    lines = _pdf_lines(pdf_bytes)[:20]
    text = ' '.join(lines)
    if 'ЦЕПТЕР БАНК' in text or 'ZEPTBY2X' in text: return 'zepter'
    if 'PKO' in text or 'CURRENT HISTORY' in text or 'WYCIĄG' in text: return 'pko'
    return 'unknown'

def parse_zepter(pdf_bytes):
    lines = _pdf_lines(pdf_bytes)
    currency, date_from, date_to = 'EUR', '', ''
    for line in lines:
        m = re.search(r'Счет клиента:\s*\S+\s+(EUR|RUB)', line)
        if m: currency = m.group(1)
        m = re.search(r'с\s+(\d{2}\.\d{2}\.\d{4})\s+по\s+(\d{2}\.\d{2}\.\d{4})', line)
        if m: date_from, date_to = _fdate(m.group(1)), _fdate(m.group(2))

    TX = re.compile(r'^(\d+)\s+(\S+)\s+(\d{2}\.\d{2}\.\d{4})\s+([16])\s+(\S+)\s+([\d\s]+,\d{2})\s+([\d\s]+,\d{2})')
    txs = []
    i = 0
    while i < len(lines):
        m = TX.match(lines[i].strip())
        if m:
            seq, doc, date, op = m.group(1), m.group(2), _fdate(m.group(3)), m.group(4)
            v1 = _amt(m.group(6))
            amount = v1 if op == '1' else -v1
            j = i + 1
            parts = []
            while j < len(lines):
                dl = lines[j].strip()
                if TX.match(dl) or 'Итого оборотов' in dl or 'Исходящее сальдо' in dl: break
                if dl and 'КОПИЯ' not in dl and 'Наименование банка' not in dl and 'Подпись банка' not in dl:
                    parts.append(dl)
                j += 1
            full = ' '.join(parts)
            cp = ''
            for pat in [r'Бенефициар:\s*([^У]+?)(?:УНП:|$)', r'Плательщик:\s*([^У]+?)(?:УНП:|$)']:
                cm = re.search(pat, full)
                if cm: cp = re.sub(r'\s+', ' ', cm.group(1)).strip()[:120]; break
            is_c = 'омисси' in full.lower() or 'ом.возн' in full.lower() or 'ЦЕПТЕР БАНК' in full
            is_v = 'онверси' in full
            if not is_c and not is_v:
                txs.append({'seq': seq, 'doc': doc, 'date': date, 'amount': amount,
                            'currency': currency, 'counterparty': cp,
                            'description': re.sub(r'\s+', ' ', full).strip()[:250]})
            i = j
        else:
            i += 1
    return txs, {'currency': currency, 'date_from': date_from, 'date_to': date_to}

def parse_pko(pdf_bytes):
    lines = _pdf_lines(pdf_bytes)
    currency, date_from, date_to, company = 'PLN', '', '', ''
    for line in lines:
        if 'RACHUNEK EUR' in line: currency = 'EUR'
        elif 'BIZNES PARTNER' in line: currency = 'PLN'
        m = re.search(r'from:\s*(\d{4}-\d{2}-\d{2})', line)
        if m: date_from = m.group(1)
        m = re.search(r'to:\s*(\d{4}-\d{2}-\d{2})', line)
        if m: date_to = m.group(1)
        if 'Company name:' in line: company = line.split('Company name:')[-1].strip()

    OP_TYPES = ('Transfer from account|Foreign transfer|Commission|Crediting|Debit|'
                'VAT transfer to Tax Office|Transfer to Social Security Institution')
    TX_RE = re.compile(
        rf'^(\d{{4}}-\d{{2}}-\d{{2}})\s+(.+?)\s+({OP_TYPES})\s+(-?[\d\s]+,\d{{2}})\s+(EUR|PLN)'
    )
    txs = []
    i = 0
    while i < len(lines):
        m = TX_RE.match(lines[i].strip())
        if m:
            date, data, op = m.group(1), m.group(2), m.group(3)
            amount = _amt(m.group(4))
            cur    = m.group(5)
            j = i + 1
            extra = []
            while j < len(lines):
                nl = lines[j].strip()
                if re.match(r'^\d{4}-\d{2}-\d{2}\s+', nl): break
                if nl and 'Electronic document' not in nl and 'Powszechna' not in nl: extra.append(nl)
                j += 1
            full = data + ' ' + ' '.join(extra)
            cp = ''
            m2 = re.search(r'Counterparty name[^:]*:\s*(.+?)(?=Title:|Transaction|$)', full)
            if m2: cp = re.sub(r'\s+', ' ', m2.group(1)).strip()[:100]
            title = ''
            m2 = re.search(r'Title:\s*(.+?)(?=Transaction|Commission:|$)', full)
            if m2: title = re.sub(r'\s+', ' ', m2.group(1)).strip()[:200]
            tx_id = ''
            m2 = re.search(r'Transaction identifier:\s*(\d+)', full)
            if m2: tx_id = m2.group(1)
            is_comm = op == 'Commission' or 'OPŁATY' in full
            is_fx   = bool(re.search(r'FX\d+', title + full[:50])) and amount < 0
            is_tax  = op in ('VAT transfer to Tax Office', 'Transfer to Social Security Institution')
            if not is_comm and not is_fx:
                txs.append({'date': date, 'amount': amount, 'currency': cur,
                            'op_type': op, 'counterparty': cp,
                            'title': title, 'tx_id': tx_id, 'is_tax': is_tax})
            i = j
        else:
            i += 1
    return txs, {'currency': currency, 'date_from': date_from, 'date_to': date_to, 'company': company}

# ══════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════

def find_client(text):
    t = (text or '').lower()
    for name in CLIENTS:
        words = [w for w in name.lower().split() if len(w) > 3]
        if any(w in t for w in words[:3]):
            return name
    return ''

def make_due(date_str, days):
    try: return (datetime.strptime(date_str, '%Y-%m-%d') + timedelta(days=days)).strftime('%Y-%m-%d')
    except: return ''

def build_invoiceocean_csv(rows_df):
    headers = [
        'No.','No.','Kind','Seller','Department short name',"Seller's TAX ID",
        'Status','Issue date','Sale date','Due date',
        'Buyer','VAT ID','Street','Postcode','City','Country',
        'Client e-mail',"Client's phone",'Mobile phone',
        'Total net price','TAX','Total gross price',
        'Total net price EUR','TAX EUR','Total gross price EUR',
        'Payment type','Payment date','Paid','Currency',
        'PO number','Addressee','Category','Notes',
        'Additional invoice field ','Original document','Reason for the correction',
        'Product / Service','Qty','Unit net price','Unit gross price','TAX',
        'VAT amount','Total net','Total gross',
        'Position kind','Quantity unit','Additional information field',
    ]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    for _, r in rows_df.iterrows():
        amt     = float(r.get('Total gross price', 0) or 0)
        amt_eur = float(r.get('Total gross price EUR', 0) or 0)
        w.writerow([
            int(r.get('No.', 0)),
            str(r.get('No. (invoice)', '')),
            str(r.get('Kind', 'Invoice')),
            str(r.get('Seller', '')),
            str(r.get('Seller', '')),
            str(r.get("Seller's TAX ID", '')),
            str(r.get('Status', 'Issued')),
            str(r.get('Issue date', '')),
            '',
            str(r.get('Due date', '')),
            str(r.get('Buyer', '')),
            str(r.get('VAT ID', '')),
            str(r.get('Street', '')),
            str(r.get('Postcode', '')),
            str(r.get('City', '')),
            str(r.get('Country', '')),
            str(r.get('Client e-mail', '')),
            str(r.get("Client's phone", '')),
            '',
            amt, 0.0, amt, amt_eur, 0.0, amt_eur,
            str(r.get('Payment type', 'Transfer')),
            str(r.get('Payment date', '')),
            float(r.get('Paid', 0) or 0),
            str(r.get('Currency', '')),
            str(r.get('PO number', '')),
            '', '', '', '', '', '',
            str(r.get('Product / Service', '')),
            1.0, amt, amt, 'disabled', 0.0, amt, amt,
            '', str(r.get('Quantity unit', 'pc')), '',
        ])
    return ('\ufeff' + buf.getvalue()).encode('utf-8')

# ══════════════════════════════════════════════════════════════════════
# UI
# ══════════════════════════════════════════════════════════════════════

st.title('🏦 Bank → InvoiceOcean')

# Sidebar
with st.sidebar:
    st.header('⚙️ Настройки')
    seller_key   = st.selectbox('Компания (продавец)', list(SELLERS.keys()))
    st.divider()
    skip_tax   = st.checkbox('Скрыть налоги / ZUS', True)
    skip_loans = st.checkbox('Скрыть займы (LOAN)', False)
    skip_neg   = st.checkbox('Скрыть списания (−)', False)

# File upload
uploaded = st.file_uploader(
    'Загрузите выписки из банка (PDF)',
    type=['pdf'], accept_multiple_files=True
)

if not uploaded:
    st.info('👆 Загрузите один или несколько PDF файлов выписок из банка.\n\n'
            '**Поддерживается:** Цептер Банк (EUR / RUB) · PKO Bank Polski (EUR / PLN)')
    st.stop()

# Parse
all_rows = []
for f in uploaded:
    raw  = f.read()
    bank = detect_bank(raw)
    try:
        if bank == 'zepter':
            txs, meta = parse_zepter(raw)
            seller = SELLERS[seller_key]
            for i, t in enumerate(txs, len(all_rows) + 1):
                buyer  = find_client(t['counterparty'])
                client = CLIENTS.get(buyer, {})
                amt    = abs(t['amount'])
                amt_eur = amt if t['currency'] == 'EUR' else 0.0
                all_rows.append({
                    'No.': i,
                    'No. (invoice)': t['doc'] or f"Z-{t['date'].replace('-','')}-{i:03d}",
                    'Kind': 'Invoice',
                    'Seller': seller['name'],
                    "Seller's TAX ID": seller['tax_id'],
                    'Status': 'Paid' if t['amount'] > 0 else 'Issued',
                    'Issue date': t['date'],
                    'Due date': make_due(t['date'], 7),
                    'Buyer': buyer,
                    'VAT ID': client.get('vat_id', ''),
                    'Street': client.get('street', ''),
                    'Postcode': client.get('postcode', ''),
                    'City': client.get('city', ''),
                    'Country': client.get('country', ''),
                    'Client e-mail': client.get('email', ''),
                    "Client's phone": '',
                    'Total net price': amt,
                    'Total gross price': amt,
                    'Total net price EUR': amt_eur,
                    'Total gross price EUR': amt_eur,
                    'Payment type': 'Transfer',
                    'Payment date': t['date'] if t['amount'] > 0 else '',
                    'Paid': amt if t['amount'] > 0 else 0.0,
                    'Currency': t['currency'],
                    'PO number': t['doc'],
                    'Product / Service': t['description'][:200],
                    'Quantity unit': 'pc',
                    'Тип': 'Income' if t['amount'] >= 0 else 'Expense',
                    '_amount_raw': t['amount'],
                    '_source': f.name,
                    '_bank': 'Zepter',
                    '_is_tax': False,
                })
            st.success(f"✅ {f.name} → Цептер Банк {meta.get('currency')} · {len(txs)} операций · {meta.get('date_from')} – {meta.get('date_to')}")

        elif bank == 'pko':
            txs, meta = parse_pko(raw)
            seller = SELLERS[seller_key]
            for i, t in enumerate(txs, len(all_rows) + 1):
                buyer  = find_client(t['counterparty'])
                client = CLIENTS.get(buyer, {})
                amt    = abs(t['amount'])
                amt_eur = amt if t['currency'] == 'EUR' else 0.0
                all_rows.append({
                    'No.': i,
                    'No. (invoice)': t['tx_id'] or f"P-{t['date'].replace('-','')}-{i:03d}",
                    'Kind': 'Invoice',
                    'Seller': seller['name'],
                    "Seller's TAX ID": seller['tax_id'],
                    'Status': 'Paid' if t['amount'] > 0 else 'Issued',
                    'Issue date': t['date'],
                    'Due date': make_due(t['date'], 7),
                    'Buyer': buyer,
                    'VAT ID': client.get('vat_id', ''),
                    'Street': client.get('street', ''),
                    'Postcode': client.get('postcode', ''),
                    'City': client.get('city', ''),
                    'Country': client.get('country', ''),
                    'Client e-mail': client.get('email', ''),
                    "Client's phone": '',
                    'Total net price': amt,
                    'Total gross price': amt,
                    'Total net price EUR': amt_eur,
                    'Total gross price EUR': amt_eur,
                    'Payment type': 'Transfer',
                    'Payment date': t['date'] if t['amount'] > 0 else '',
                    'Paid': amt if t['amount'] > 0 else 0.0,
                    'Currency': t['currency'],
                    'PO number': t['tx_id'],
                    'Product / Service': t['title'][:200],
                    'Quantity unit': 'pc',
                    'Тип': 'Income' if t['amount'] >= 0 else 'Expense',
                    '_amount_raw': t['amount'],
                    '_source': f.name,
                    '_bank': 'PKO',
                    '_is_tax': t.get('is_tax', False),
                })
            st.success(f"✅ {f.name} → PKO Bank {meta.get('currency')} · {len(txs)} операций · {meta.get('date_from')} – {meta.get('date_to')}")
        else:
            st.warning(f"⚠️ {f.name}: не удалось определить банк")
    except Exception as e:
        import traceback
        st.error(f"❌ {f.name}: {e}")
        st.code(traceback.format_exc())

if not all_rows:
    st.warning('Транзакции не найдены.'); st.stop()

# Filters
df = pd.DataFrame(all_rows)
if skip_tax:  df = df[~df['_is_tax']]
if skip_loans: df = df[~df['Product / Service'].str.upper().str.contains('LOAN', na=False)]
if skip_neg:  df = df[df['_amount_raw'] >= 0]

# Renumber
df = df.reset_index(drop=True)
df['No.'] = df.index + 1

if df.empty:
    st.warning('После фильтрации нет транзакций.'); st.stop()

# Stats
st.subheader(f'📊 {len(df)} транзакций')
c1, c2, c3 = st.columns(3)
pos = df[df['_amount_raw'] > 0]['Total gross price'].sum()
neg = df[df['_amount_raw'] < 0]['Total gross price'].sum()
c1.metric('Поступления', f'+{pos:,.2f}')
c2.metric('Списания', f'-{neg:,.2f}')
c3.metric('Источников', df['_source'].nunique())

# Editable table
st.subheader('✏️ Редактирование')
st.caption('Выберите **Покупателя** → адрес и VAT заполнятся автоматически. Можно удалять строки через чекбокс + Delete.')

display_cols = [c for c in df.columns if not c.startswith('_')]
client_list  = [''] + list(CLIENTS.keys())

col_cfg = {
    'No.':             st.column_config.NumberColumn('№', width='small', disabled=True),
    'No. (invoice)':   st.column_config.TextColumn('Номер счёта', width='medium'),
    'Kind':            st.column_config.SelectboxColumn('Вид', options=['Invoice','Proforma Invoice','Receipt'], width='small'),
    'Seller':          st.column_config.TextColumn('Продавец', width='medium'),
    "Seller's TAX ID": st.column_config.TextColumn('TAX ID', width='small'),
    'Status':          st.column_config.SelectboxColumn('Статус', options=['Paid','Partially paid','Issued','Rejected'], width='small'),
    'Issue date':      st.column_config.TextColumn('Дата', width='small'),
    'Due date':        st.column_config.TextColumn('Срок оплаты', width='small'),
    'Buyer':           st.column_config.SelectboxColumn('Покупатель ▼', options=client_list, width='large'),
    'VAT ID':          st.column_config.TextColumn('VAT ID', width='medium'),
    'Street':          st.column_config.TextColumn('Улица', width='medium'),
    'Postcode':        st.column_config.TextColumn('Индекс', width='small'),
    'City':            st.column_config.TextColumn('Город', width='small'),
    'Country':         st.column_config.TextColumn('Страна', width='small'),
    'Client e-mail':   st.column_config.TextColumn('Email', width='medium'),
    "Client's phone":  st.column_config.TextColumn('Телефон', width='small'),
    'Total gross price':     st.column_config.NumberColumn('Сумма', format='%.2f', width='medium'),
    'Total gross price EUR': st.column_config.NumberColumn('Сумма EUR', format='%.2f', width='medium'),
    'Payment type':    st.column_config.SelectboxColumn('Оплата', options=['Transfer','Cash','Card'], width='small'),
    'Payment date':    st.column_config.TextColumn('Дата оплаты', width='small'),
    'Paid':            st.column_config.NumberColumn('Оплачено', format='%.2f', width='medium'),
    'Currency':        st.column_config.SelectboxColumn('Валюта', options=['EUR','RUB','PLN','USD'], width='small'),
    'Тип':             st.column_config.SelectboxColumn('Тип', options=['Income','Expense'], width='small'),
    'PO number':       st.column_config.TextColumn('Номер фактуры', width='medium'),
    'Product / Service': st.column_config.TextColumn('Описание', width='large'),
    'Quantity unit':   st.column_config.SelectboxColumn('Ед.', options=['pc','cases','kg','l'], width='small'),
}

# Session state for the dataframe
if 'main_df' not in st.session_state or st.button('🔃 Сбросить и перечитать файлы'):
    st.session_state.main_df = df[display_cols].reset_index(drop=True).copy()

edited = st.data_editor(
    st.session_state.main_df.reset_index(drop=True),
    column_config=col_cfg,
    use_container_width=True,
    num_rows='dynamic',
    hide_index=True,
    key='main_editor',
)

# Auto-fill client when Buyer changes
old_df  = st.session_state.main_df.reset_index(drop=True)
new_df  = edited.reset_index(drop=True)
changed = False
for idx in new_df.index:
    try:
        b_new = str(new_df.at[idx, 'Buyer'] or '')
        b_old = str(old_df.at[idx, 'Buyer'] if idx < len(old_df) else '') 
        if b_new != b_old and b_new in CLIENTS:
            c = CLIENTS[b_new]
            new_df.at[idx, 'VAT ID']         = c.get('vat_id', '')
            new_df.at[idx, 'Street']         = c.get('street', '')
            new_df.at[idx, 'Postcode']       = c.get('postcode', '')
            new_df.at[idx, 'City']           = c.get('city', '')
            new_df.at[idx, 'Country']        = c.get('country', '')
            new_df.at[idx, 'Client e-mail']  = c.get('email', '')
            changed = True
    except (KeyError, IndexError):
        pass

if changed:
    st.session_state.main_df = new_df
    st.rerun()
else:
    st.session_state.main_df = new_df

# Export
st.divider()
st.subheader('📥 Экспорт в InvoiceOcean')

# InvoiceOcean API settings
IO_DOMAIN = "tentatrade.invoiceocean.co.uk"
IO_TOKEN  = "Eq27xW22rlJdVjKm81S"

tab1, tab2 = st.tabs(["🚀 Отправить напрямую в InvoiceOcean", "📄 Скачать CSV"])

with tab1:
    st.info("Счета будут созданы прямо в InvoiceOcean — без CSV и без импорта!")
    
    col1, col2 = st.columns(2)
    with col1:
        send_email = st.checkbox("📧 Отправить PDF клиенту по email после создания", value=False)
    with col2:
        only_positive = st.checkbox("Только поступления (+ суммы)", value=True)

    if st.button("🚀 Создать счета в InvoiceOcean", type="primary", use_container_width=True):
        df_send = st.session_state.main_df.copy()
        if only_positive:
            if 'Тип' in df_send.columns:
                df_send = df_send[df_send['Тип'] == 'Income']
            else:
                df_send = df_send[df_send['Total gross price'] > 0]
        
        if df_send.empty:
            st.warning("Нет строк для отправки.")
        else:
            progress = st.progress(0)
            results = []
            errors  = []
            
            for idx, (_, row) in enumerate(df_send.iterrows()):
                buyer = str(row.get("Buyer", "") or "")
                client = CLIENTS.get(buyer, {})
                amt = float(row.get("Total gross price", 0) or 0)
                if amt == 0:
                    continue
                
                payload = {
                    "api_token": IO_TOKEN,
                    "invoice": {
                        "kind": "expense" if str(row.get("Тип","")) == "Expense" else "vat",
                        "number": None,
                        "issue_date": str(row.get("Issue date", "")),
                        "sell_date":  str(row.get("Issue date", "")),
                        "payment_to": str(row.get("Due date", "")),
                        "buyer_name":    buyer or "Unknown",
                        "buyer_tax_no":  client.get("vat_id", ""),
                        "buyer_street":  client.get("street", ""),
                        "buyer_post_code": client.get("postcode", ""),
                        "buyer_city":    client.get("city", ""),
                        "buyer_country": client.get("country", ""),
                        "buyer_email":   client.get("email", ""),
                        "currency": str(row.get("Currency", "EUR")),
                        "payment_type": "transfer",
                        "status": "paid" if str(row.get("Status","")) == "Paid" else "issued",
                        "paid": amt if str(row.get("Status","")) == "Paid" else 0,
                        "positions": [{
                            "name": (str(row.get("Product / Service", "") or "").strip() or "Payment")[:200],
                            "tax": "disabled",
                            "total_price_gross": amt,
                            "quantity": 1,
                        }]
                    }
                }
                
                try:
                    import requests as req_lib
                    resp = req_lib.post(
                        f"https://{IO_DOMAIN}/invoices.json",
                        json=payload,
                        timeout=10
                    )
                    if resp.status_code == 201:
                        inv = resp.json()
                        inv_id  = inv.get("id")
                        inv_num = inv.get("number", "")
                        results.append((inv_id, inv_num, buyer, amt, str(row.get("Currency",""))))
                        
                        # Send by email if requested
                        if send_email and client.get("email") and inv_id:
                            req_lib.post(
                                f"https://{IO_DOMAIN}/invoices/{inv_id}/send_by_email.json?api_token={IO_TOKEN}",
                                timeout=10
                            )
                    else:
                        errors.append(f"Row {idx+1}: {resp.status_code} — {resp.text[:100]}")
                except Exception as e:
                    errors.append(f"Row {idx+1}: {e}")
                
                progress.progress((idx + 1) / len(df_send))
            
            progress.empty()
            
            if results:
                st.success(f"✅ Создано {len(results)} счетов в InvoiceOcean!")
                result_df = pd.DataFrame(results, columns=["ID", "Номер", "Клиент", "Сумма", "Валюта"])
                st.dataframe(result_df, use_container_width=True, hide_index=True)
                if send_email:
                    st.info("📧 PDF отправлены клиентам по email")
            if errors:
                st.error(f"❌ Ошибки ({len(errors)}):")
                for e in errors:
                    st.caption(e)

with tab2:
    st.caption("Скачайте CSV и загрузите вручную через InvoiceOcean → Settings → Import")
    if st.button("📄 Скачать CSV", use_container_width=True):
        export_df = st.session_state.main_df.copy()
        for col in ['Total net price','Total gross price','Total net price EUR','Total gross price EUR']:
            if col not in export_df.columns:
                export_df[col] = export_df.get('Total gross price', 0)
        csv_bytes = build_invoiceocean_csv(export_df)
        fname = f"InvoiceOcean_{seller_key.replace(' ','_')[:20]}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        st.download_button(
            f'⬇️ Скачать {fname}',
            csv_bytes, fname, 'text/csv',
            use_container_width=True,
        )
