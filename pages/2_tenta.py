import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.pko_parser import parse_pko_pdf
from utils.clients import CLIENTS, SELLERS

st.set_page_config(page_title="TENTA TRADE", page_icon="🇵🇱", layout="wide")
st.title("🇵🇱 TENTA TRADE SP. Z O.O. — PKO Bank → InvoiceOcean")

with st.sidebar:
    st.header("⚙️ Настройки")
    due_days = st.number_input("Срок оплаты (дней)", min_value=0, max_value=90, value=7)
    invoice_kind = st.selectbox("Вид документа", ["Invoice", "Proforma Invoice", "Receipt"])
    filter_type = st.selectbox("Показать операции", ["Все", "Только поступления (+)", "Только списания (-)"])
    skip_commissions = st.checkbox("Скрыть комиссии банка", value=True)
    skip_tax = st.checkbox("Скрыть налоги/ZUS", value=True)
    skip_fx = st.checkbox("Скрыть FX-конверсию", value=True)

uploaded = st.file_uploader(
    "Загрузите PDF-выписку из PKO Bank Polski",
    type=["pdf"],
    accept_multiple_files=True,
    help="ACCOUNTS-HISTORY_*.pdf",
)

if not uploaded:
    st.info("👆 Загрузите PDF файл(ы) выписки из PKO Bank Polski")
    st.stop()

all_txs = []
for f in uploaded:
    try:
        txs, meta = parse_pko_pdf(f.read())
        all_txs.extend(txs)
        st.success(f"✅ {f.name}: {len(txs)} операций · {meta.get('currency','?')} · {meta.get('date_from','?')} – {meta.get('date_to','?')}")
    except Exception as e:
        st.error(f"❌ {f.name}: {e}")

if not all_txs:
    st.warning("Транзакции не найдены.")
    st.stop()

txs = all_txs
if skip_commissions:
    txs = [t for t in txs if t.op_type != "Commission"]
if skip_tax:
    txs = [t for t in txs if t.op_type not in ["VAT transfer to Tax Office","Transfer to Social Security Institution"]]
if skip_fx:
    txs = [t for t in txs if "FX" not in t.title]
if filter_type == "Только поступления (+)":
    txs = [t for t in txs if t.amount > 0]
elif filter_type == "Только списания (-)":
    txs = [t for t in txs if t.amount < 0]

if not txs:
    st.warning("После фильтрации нет транзакций.")
    st.stop()

def find_client(name: str) -> str:
    nl = name.lower()
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

seller = SELLERS["TENTA TRADE SP. Z O.O."]
client_list = list(CLIENTS.keys())

rows = []
for i, t in enumerate(txs, 1):
    buyer = find_client(t.counterparty_name)
    client = CLIENTS.get(buyer, {})
    amt = abs(t.amount)
    amt_eur = amt if t.currency == "EUR" else 0.0
    due = make_due(t.date, due_days)
    status = "Paid" if t.amount > 0 else "Issued"
    paid = amt if t.amount > 0 else 0.0

    rows.append({
        "No.":                       i,
        "No. (invoice)":             t.tx_id or f"PKO-{t.date.replace('-','')}-{i:03d}",
        "Kind":                      invoice_kind,
        "Seller":                    seller["name"],
        "Department short name":     seller["name"],
        "Seller's TAX ID":           seller["tax_id"],
        "Status":                    status,
        "Issue date":                t.date,
        "Sale date":                 "",
        "Due date":                  due,
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
        "Paid":                      paid,
        "Currency":                  t.currency,
        "PO number":                 t.tx_id,
        "Addressee":                 "",
        "Category":                  "",
        "Notes":                     "",
        "Additional invoice field":  "",
        "Original document":         "",
        "Reason for the correction": "",
        "Product / Service":         t.title[:200],
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
    })

df = pd.DataFrame(rows)

st.subheader(f"📊 {len(txs)} операций")
c1, c2, c3 = st.columns(3)
c1.metric("Поступления", f"+{sum(t.amount for t in txs if t.amount>0):,.2f}")
c2.metric("Списания", f"{sum(t.amount for t in txs if t.amount<0):,.2f}")
c3.metric("Записей", len(txs))

st.subheader("✏️ Редактирование — изменяйте любые поля прямо в таблице")
st.caption("Самые важные колонки: **No. (invoice)**, **Buyer**, **Product / Service**, **Total gross price**, **Currency**, **Status**")

column_config = {
    "No.":               st.column_config.NumberColumn("№", width="small"),
    "No. (invoice)":     st.column_config.TextColumn("Номер счёта", width="medium"),
    "Kind":              st.column_config.SelectboxColumn("Вид", options=["Invoice","Proforma Invoice","Receipt"], width="small"),
    "Seller":            st.column_config.TextColumn("Продавец", width="medium"),
    "Department short name": st.column_config.TextColumn("Отдел", width="small"),
    "Seller's TAX ID":   st.column_config.TextColumn("TAX ID продавца", width="small"),
    "Status":            st.column_config.SelectboxColumn("Статус", options=["Paid","Partially paid","Issued","Rejected"], width="small"),
    "Issue date":        st.column_config.TextColumn("Дата выставления", width="small"),
    "Sale date":         st.column_config.TextColumn("Дата продажи", width="small"),
    "Due date":          st.column_config.TextColumn("Срок оплаты", width="small"),
    "Buyer":             st.column_config.SelectboxColumn("Покупатель", options=client_list + [""], width="large"),
    "VAT ID":            st.column_config.TextColumn("VAT ID", width="small"),
    "Street":            st.column_config.TextColumn("Улица", width="medium"),
    "Postcode":          st.column_config.TextColumn("Индекс", width="small"),
    "City":              st.column_config.TextColumn("Город", width="small"),
    "Country":           st.column_config.TextColumn("Страна", width="small"),
    "Client e-mail":     st.column_config.TextColumn("Email", width="medium"),
    "Client's phone":    st.column_config.TextColumn("Телефон", width="small"),
    "Mobile phone":      st.column_config.TextColumn("Мобильный", width="small"),
    "Total net price":   st.column_config.NumberColumn("Сумма нетто", format="%.2f", width="medium"),
    "TAX":               st.column_config.NumberColumn("НДС", format="%.2f", width="small"),
    "Total gross price": st.column_config.NumberColumn("Сумма брутто", format="%.2f", width="medium"),
    "Total net price EUR":   st.column_config.NumberColumn("Нетто EUR", format="%.2f", width="medium"),
    "TAX EUR":           st.column_config.NumberColumn("НДС EUR", format="%.2f", width="small"),
    "Total gross price EUR": st.column_config.NumberColumn("Брутто EUR", format="%.2f", width="medium"),
    "Payment type":      st.column_config.SelectboxColumn("Тип оплаты", options=["Transfer","Cash","Card"], width="small"),
    "Payment date":      st.column_config.TextColumn("Дата оплаты", width="small"),
    "Paid":              st.column_config.NumberColumn("Оплачено", format="%.2f", width="medium"),
    "Currency":          st.column_config.SelectboxColumn("Валюта", options=["EUR","RUB","PLN","USD"], width="small"),
    "PO number":         st.column_config.TextColumn("PO номер", width="medium"),
    "Product / Service": st.column_config.TextColumn("Товар / Услуга", width="large"),
    "Qty":               st.column_config.NumberColumn("Кол-во", format="%.2f", width="small"),
    "Unit net price":    st.column_config.NumberColumn("Цена нетто", format="%.2f", width="medium"),
    "Unit gross price":  st.column_config.NumberColumn("Цена брутто", format="%.2f", width="medium"),
    "TAX (position)":    st.column_config.TextColumn("НДС поз.", width="small"),
    "VAT amount":        st.column_config.NumberColumn("Сумма НДС", format="%.2f", width="small"),
    "Total net":         st.column_config.NumberColumn("Итого нетто", format="%.2f", width="medium"),
    "Total gross":       st.column_config.NumberColumn("Итого брутто", format="%.2f", width="medium"),
    "Position kind":     st.column_config.TextColumn("Тип позиции", width="small"),
    "Quantity unit":     st.column_config.SelectboxColumn("Ед. изм.", options=["cases","pc","kg","l","pcs"], width="small"),
    "Additional information": st.column_config.TextColumn("Доп. инфо", width="medium"),
}

edited_df = st.data_editor(
    df,
    column_config=column_config,
    use_container_width=True,
    num_rows="dynamic",
    hide_index=True,
    key="tenta_editor",
)

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

    import csv, io
    out_rows = []
    for _, row in edited_df.iterrows():
        client = CLIENTS.get(str(row.get("Buyer", "")), {})
        amt = float(row.get("Total gross price", 0) or 0)
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
            str(row.get("VAT ID", "") or client.get("vat_id", "")),
            str(row.get("Street", "") or client.get("street", "")),
            str(row.get("Postcode", "") or client.get("postcode", "")),
            str(row.get("City", "") or client.get("city", "")),
            str(row.get("Country", "") or client.get("country", "")),
            str(row.get("Client e-mail", "") or client.get("email", "")),
            str(row.get("Client's phone", "") or client.get("phone", "")),
            "",
            amt, 0.0, amt, amt_eur, 0.0, amt_eur,
            str(row.get("Payment type", "Transfer")),
            str(row.get("Payment date", "")),
            float(row.get("Paid", 0) or 0),
            str(row.get("Currency", "PLN")),
            str(row.get("PO number", "")),
            "", "", "", "", "", "",
            str(row.get("Product / Service", "")),
            float(row.get("Qty", 1) or 1),
            amt, amt,
            "disabled", 0.0, amt, amt,
            "", str(row.get("Quantity unit", "pc")), "",
        ])

    output = io.StringIO()
    csv.writer(output).writerow(final_cols)
    for r in out_rows:
        csv.writer(output).writerow(r)
    csv_bytes = ("\ufeff" + output.getvalue()).encode("utf-8")

    filename = f"InvoiceOcean_TENTA_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    st.download_button(f"⬇️ Скачать {filename}", csv_bytes, filename, "text/csv", use_container_width=True)
    st.success(f"✅ {len(out_rows)} строк готово.")

st.caption("📌 InvoiceOcean: Settings → Import → New Import → выбрать CSV")
