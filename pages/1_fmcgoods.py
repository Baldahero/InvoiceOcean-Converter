import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.zepter_pdf_parser import parse_zepter_pdf_auto
from parsers.pko_wyciag_parser import parse_pko_wyciag
from parsers.zepter_parser import parse_zepter_rtf
from utils.clients import CLIENTS, SELLERS

st.set_page_config(page_title="FMCGOODS OÜ", page_icon="🇪🇪", layout="wide")
st.title("🇪🇪 FMCGOODS OÜ → InvoiceOcean")

with st.sidebar:
    st.header("⚙️ Настройки")
    due_days     = st.number_input("Срок оплаты (дней)", min_value=0, max_value=90, value=7)
    invoice_kind = st.selectbox("Вид документа", ["Invoice", "Proforma Invoice", "Receipt"])
    filter_type  = st.selectbox("Показать", ["Все", "Только поступления (+)", "Только списания (-)"])
    skip_comm    = st.checkbox("Скрыть комиссии банка", value=True)
    skip_conv    = st.checkbox("Скрыть конверсию валют", value=True)
    skip_fx      = st.checkbox("Скрыть FX-операции", value=True)
    skip_loans   = st.checkbox("Скрыть займы (LOAN)", value=False)

st.info("📂 Поддерживаемые форматы:\n"
        "- **Цептер Банк**: PDF (EUR/RUB) или RTF\n"
        "- **PKO Bank Polski**: PDF (WYCIĄG — польская выписка)")

uploaded = st.file_uploader(
    "Загрузите выписки (PDF или RTF)",
    type=["pdf", "rtf", "txt"],
    accept_multiple_files=True,
)
if not uploaded:
    st.stop()

# ── Parse all files ────────────────────────────────────────────────────────────
class UnifiedTx:
    def __init__(self, date, doc_num, amount, currency, counterparty,
                 description, is_commission, is_conversion, is_fx, source):
        self.date          = date
        self.doc_num       = doc_num
        self.amount        = amount
        self.currency      = currency
        self.counterparty  = counterparty
        self.description   = description
        self.is_commission = is_commission
        self.is_conversion = is_conversion
        self.is_fx         = is_fx
        self.source        = source   # "Zepter EUR", "Zepter RUB", "PKO EUR", etc.

all_txs = []
for f in uploaded:
    raw = f.read()
    name = f.name.lower()
    try:
        if name.endswith('.rtf') or name.endswith('.txt'):
            txs, meta = parse_zepter_rtf(raw)
            cur = meta.get('currency', 'EUR')
            src = f"Zepter {cur} (RTF)"
            for t in txs:
                all_txs.append(UnifiedTx(
                    t.date, t.doc_num, t.amount, t.currency,
                    t.counterparty, t.description,
                    t.is_commission, t.is_conversion, False, src
                ))
        elif name.endswith('.pdf'):
            # Detect bank by content
            import pdfplumber, io
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                first = pdf.pages[0].extract_text() or ''

            if 'ЦЕПТЕР БАНК' in first or 'ZEPTBY2X' in first:
                txs, meta = parse_zepter_pdf_auto(raw)
                cur = meta.get('currency', 'EUR')
                src = f"Zepter {cur} (PDF)"
                for t in txs:
                    all_txs.append(UnifiedTx(
                        t.date, t.doc_num, t.amount, t.currency,
                        t.counterparty, t.description,
                        t.is_commission, t.is_conversion, False, src
                    ))
            elif 'WYCIĄG' in first or 'PKO' in first or 'Waluta rachunku' in first:
                txs, meta = parse_pko_wyciag(raw)
                cur = meta.get('currency', 'EUR')
                src = f"PKO {cur} (PDF)"
                for t in txs:
                    all_txs.append(UnifiedTx(
                        t.date, t.tx_id, t.amount, t.currency,
                        t.beneficiary, t.title,
                        t.is_commission, False, t.is_fx, src
                    ))
            else:
                st.warning(f"⚠️ {f.name}: не удалось определить банк")
                continue

        real = [t for t in all_txs if t.source == src]
        st.success(f"✅ {f.name} → **{src}**: {len(txs)} операций · {meta.get('date_from','')} – {meta.get('date_to','')}")
    except Exception as e:
        st.error(f"❌ {f.name}: {e}")
        import traceback; st.code(traceback.format_exc())

if not all_txs:
    st.warning("Транзакции не найдены.")
    st.stop()

# ── Filter ─────────────────────────────────────────────────────────────────────
txs = all_txs
if skip_comm:  txs = [t for t in txs if not t.is_commission]
if skip_conv:  txs = [t for t in txs if not t.is_conversion]
if skip_fx:    txs = [t for t in txs if not t.is_fx]
if skip_loans: txs = [t for t in txs if 'LOAN' not in (t.description or '').upper()]
if filter_type == "Только поступления (+)": txs = [t for t in txs if t.amount > 0]
elif filter_type == "Только списания (-)":  txs = [t for t in txs if t.amount < 0]

if not txs:
    st.warning("После фильтрации нет транзакций.")
    st.stop()

# ── Build table ────────────────────────────────────────────────────────────────
def find_client(name: str) -> str:
    nl = (name or '').lower()
    for cname in CLIENTS:
        words = [w for w in cname.lower().split() if len(w) > 3]
        if any(w in nl for w in words[:3]):
            return cname
    return ""

def make_due(issue: str, days: int) -> str:
    try:
        return (datetime.strptime(issue, "%Y-%m-%d") + timedelta(days=days)).strftime("%Y-%m-%d")
    except:
        return ""

seller      = SELLERS["FMCGOODS OÜ"]
client_list = [""] + list(CLIENTS.keys())

def build_rows(txs, kind, days):
    rows = []
    for i, t in enumerate(txs, 1):
        buyer  = find_client(t.counterparty)
        client = CLIENTS.get(buyer, {})
        amt    = abs(t.amount)
        amt_eur = amt if t.currency == "EUR" else 0.0
        rows.append({
            "No.":                       i,
            "No. (invoice)":             t.doc_num or f"FMC-{t.date.replace('-','')}-{i:03d}",
            "Kind":                      kind,
            "Seller":                    seller["name"],
            "Department short name":     seller["name"],
            "Seller's TAX ID":           seller["tax_id"],
            "Status":                    "Paid" if t.amount > 0 else "Issued",
            "Issue date":                t.date,
            "Sale date":                 "",
            "Due date":                  make_due(t.date, days),
            "Buyer":                     buyer,
            "VAT ID":                    client.get("vat_id", ""),
            "Street":                    client.get("street", ""),
            "Postcode":                  client.get("postcode", ""),
            "City":                      client.get("city", ""),
            "Country":                   client.get("country", ""),
            "Client e-mail":             client.get("email", ""),
            "Client's phone":            client.get("phone", ""),
            "Mobile phone":              "",
            "Total net price":           amt,
            "TAX":                       0.0,
            "Total gross price":         amt,
            "Total net price EUR":       amt_eur,
            "TAX EUR":                   0.0,
            "Total gross price EUR":     amt_eur,
            "Payment type":              "Transfer",
            "Payment date":              t.date if t.amount > 0 else "",
            "Paid":                      amt if t.amount > 0 else 0.0,
            "Currency":                  t.currency,
            "PO number":                 t.doc_num or "",
            "Addressee":                 "",
            "Category":                  "",
            "Notes":                     "",
            "Additional invoice field":  "",
            "Original document":         "",
            "Reason for the correction": "",
            "Product / Service":         (t.description or "")[:200],
            "Qty":                       1.0,
            "Unit net price":            amt,
            "Unit gross price":          amt,
            "TAX (position)":            "disabled",
            "VAT amount":                0.0,
            "Total net":                 amt,
            "Total gross":               amt,
            "Position kind":             "",
            "Quantity unit":             "pc",
            "Additional information":    "",
            "_source":                   t.source,
        })
    return rows

if "fmc_df" not in st.session_state or st.button("🔃 Перезагрузить из выписок", key="reload_fmc"):
    st.session_state.fmc_df = pd.DataFrame(build_rows(txs, invoice_kind, due_days))

# ── Stats ──────────────────────────────────────────────────────────────────────
st.subheader(f"📊 {len(txs)} операций")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Поступления",  f"+{sum(t.amount for t in txs if t.amount>0):,.2f}")
c2.metric("Списания",     f"{sum(t.amount for t in txs if t.amount<0):,.2f}")
c3.metric("Записей",      len(txs))
sources = list({t.source for t in txs})
c4.metric("Источников",   len(sources))
if sources:
    st.caption("Источники: " + " · ".join(sources))

# ── Editable table ─────────────────────────────────────────────────────────────
st.subheader("✏️ Редактирование")
st.caption("Выберите **Покупателя ▼** — адрес и VAT заполнятся автоматически.")

display_cols = [c for c in st.session_state.fmc_df.columns if c != "_source"]

col_cfg = {
    "No.":               st.column_config.NumberColumn("№", width="small", disabled=True),
    "No. (invoice)":     st.column_config.TextColumn("Номер счёта", width="medium"),
    "Kind":              st.column_config.SelectboxColumn("Вид", options=["Invoice","Proforma Invoice","Receipt"], width="small"),
    "Seller":            st.column_config.TextColumn("Продавец", width="medium"),
    "Department short name": st.column_config.TextColumn("Отдел", width="small"),
    "Seller's TAX ID":   st.column_config.TextColumn("TAX ID", width="small"),
    "Status":            st.column_config.SelectboxColumn("Статус", options=["Paid","Partially paid","Issued","Rejected"], width="small"),
    "Issue date":        st.column_config.TextColumn("Дата", width="small"),
    "Sale date":         st.column_config.TextColumn("Дата продажи", width="small"),
    "Due date":          st.column_config.TextColumn("Срок оплаты", width="small"),
    "Buyer":             st.column_config.SelectboxColumn("Покупатель ▼", options=client_list, width="large"),
    "VAT ID":            st.column_config.TextColumn("VAT ID", width="medium"),
    "Street":            st.column_config.TextColumn("Улица", width="medium"),
    "Postcode":          st.column_config.TextColumn("Индекс", width="small"),
    "City":              st.column_config.TextColumn("Город", width="small"),
    "Country":           st.column_config.TextColumn("Страна", width="small"),
    "Client e-mail":     st.column_config.TextColumn("Email", width="medium"),
    "Client's phone":    st.column_config.TextColumn("Телефон", width="small"),
    "Total net price":   st.column_config.NumberColumn("Нетто",    format="%.2f", width="medium"),
    "TAX":               st.column_config.NumberColumn("НДС",      format="%.2f", width="small"),
    "Total gross price": st.column_config.NumberColumn("Брутто",   format="%.2f", width="medium"),
    "Total net price EUR":   st.column_config.NumberColumn("Нетто EUR",  format="%.2f", width="medium"),
    "TAX EUR":               st.column_config.NumberColumn("НДС EUR",    format="%.2f", width="small"),
    "Total gross price EUR": st.column_config.NumberColumn("Брутто EUR", format="%.2f", width="medium"),
    "Payment type":      st.column_config.SelectboxColumn("Оплата", options=["Transfer","Cash","Card"], width="small"),
    "Payment date":      st.column_config.TextColumn("Дата оплаты", width="small"),
    "Paid":              st.column_config.NumberColumn("Оплачено",   format="%.2f", width="medium"),
    "Currency":          st.column_config.SelectboxColumn("Валюта", options=["EUR","RUB","PLN","USD"], width="small"),
    "PO number":         st.column_config.TextColumn("PO", width="medium"),
    "Product / Service": st.column_config.TextColumn("Товар / Услуга", width="large"),
    "Qty":               st.column_config.NumberColumn("Кол-во", format="%.2f", width="small"),
    "Unit net price":    st.column_config.NumberColumn("Цена нетто",  format="%.2f", width="medium"),
    "Unit gross price":  st.column_config.NumberColumn("Цена брутто", format="%.2f", width="medium"),
    "TAX (position)":    st.column_config.TextColumn("НДС поз.", width="small"),
    "VAT amount":        st.column_config.NumberColumn("Сумма НДС", format="%.2f", width="small"),
    "Total net":         st.column_config.NumberColumn("Итого нетто",  format="%.2f", width="medium"),
    "Total gross":       st.column_config.NumberColumn("Итого брутто", format="%.2f", width="medium"),
    "Quantity unit":     st.column_config.SelectboxColumn("Ед. изм.", options=["cases","pc","kg","l","pcs"], width="small"),
    "Additional information": st.column_config.TextColumn("Доп. инфо", width="medium"),
}

edited = st.data_editor(
    st.session_state.fmc_df[display_cols],
    column_config=col_cfg,
    use_container_width=True,
    num_rows="dynamic",
    hide_index=True,
    key="fmc_editor",
)

# Auto-fill client data
changed = False
for idx in range(len(edited)):
    if idx >= len(st.session_state.fmc_df):
        changed = True
        break
    buyer_new = edited.at[idx, "Buyer"]
    buyer_old = st.session_state.fmc_df.at[idx, "Buyer"]
    if buyer_new != buyer_old and buyer_new in CLIENTS:
        c = CLIENTS[buyer_new]
        for col, key in [("VAT ID","vat_id"),("Street","street"),("Postcode","postcode"),
                         ("City","city"),("Country","country"),
                         ("Client e-mail","email"),("Client's phone","phone")]:
            edited.at[idx, col] = c.get(key, "")
        changed = True

# Merge edited back with _source column
merged = edited.copy()
if "_source" in st.session_state.fmc_df.columns:
    merged["_source"] = st.session_state.fmc_df["_source"].values[:len(merged)] if len(merged) <= len(st.session_state.fmc_df) else ""

if changed:
    st.session_state.fmc_df = merged
    st.rerun()
else:
    st.session_state.fmc_df = merged

# ── Export ─────────────────────────────────────────────────────────────────────
st.divider()
st.subheader("📥 Экспорт")

if st.button("🔄 Сгенерировать CSV для InvoiceOcean", type="primary", use_container_width=True):
    final_cols = [
        "No.", "No.", "Kind", "Seller", "Department short name",
        "Seller's TAX ID", "Status", "Issue date", "Sale date", "Due date",
        "Buyer", "VAT ID", "Street", "Postcode", "City", "Country",
        "Client e-mail", "Client's phone", "Mobile phone",
        "Total net price", "TAX", "Total gross price",
        "Total net price EUR", "TAX EUR", "Total gross price EUR",
        "Payment type", "Payment date", "Paid", "Currency",
        "PO number", "Addressee", "Category", "Notes",
        "Additional invoice field ", "Original document", "Reason for the correction",
        "Product / Service", "Qty", "Unit net price", "Unit gross price", "TAX",
        "VAT amount", "Total net", "Total gross",
        "Position kind", "Quantity unit", "Additional information field",
    ]
    import csv, io as sio
    out_rows = []
    df_exp = st.session_state.fmc_df
    for _, row in df_exp.iterrows():
        amt     = float(row.get("Total gross price", 0) or 0)
        amt_eur = float(row.get("Total gross price EUR", 0) or 0)
        out_rows.append([
            int(row.get("No.", 0)),
            str(row.get("No. (invoice)", "")),
            str(row.get("Kind", "Invoice")),
            str(row.get("Seller", "")),
            str(row.get("Department short name", "")),
            str(row.get("Seller's TAX ID", "")),
            str(row.get("Status", "Issued")),
            str(row.get("Issue date", "")),
            str(row.get("Sale date", "")),
            str(row.get("Due date", "")),
            str(row.get("Buyer", "")),
            str(row.get("VAT ID", "")),
            str(row.get("Street", "")),
            str(row.get("Postcode", "")),
            str(row.get("City", "")),
            str(row.get("Country", "")),
            str(row.get("Client e-mail", "")),
            str(row.get("Client's phone", "")),
            "",
            amt, 0.0, amt, amt_eur, 0.0, amt_eur,
            str(row.get("Payment type", "Transfer")),
            str(row.get("Payment date", "")),
            float(row.get("Paid", 0) or 0),
            str(row.get("Currency", "EUR")),
            str(row.get("PO number", "")),
            "", "", "", "", "", "",
            str(row.get("Product / Service", "")),
            float(row.get("Qty", 1) or 1),
            amt, amt, "disabled", 0.0, amt, amt,
            "", str(row.get("Quantity unit", "pc")), "",
        ])
    buf = sio.StringIO()
    w = csv.writer(buf)
    w.writerow(final_cols)
    w.writerows(out_rows)
    csv_bytes = ("\ufeff" + buf.getvalue()).encode("utf-8")
    filename = f"InvoiceOcean_FMCGOODS_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    st.download_button(f"⬇️ Скачать {filename}", csv_bytes, filename, "text/csv", use_container_width=True)
    st.success(f"✅ {len(out_rows)} строк экспортировано.")

st.caption("📌 InvoiceOcean: Settings → Import → New Import → выбрать CSV")
