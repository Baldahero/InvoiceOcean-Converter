import streamlit as st
import pandas as pd
from datetime import datetime
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.zepter_parser import parse_zepter_rtf
from utils.csv_builder import build_row, generate_csv, add_days
from utils.clients import CLIENTS, SELLERS

st.set_page_config(page_title="FMCGOODS OÜ — Конвертер", page_icon="🇪🇪", layout="wide")
st.title("🇪🇪 FMCGOODS OÜ — Цептер Банк → InvoiceOcean")

with st.sidebar:
    st.header("⚙️ Настройки")
    filter_type = st.selectbox("Тип операций", ["Все", "Только поступления (+)", "Только списания (-)"])
    due_days = st.number_input("Срок оплаты (дней)", min_value=0, max_value=90, value=7)
    invoice_kind = st.selectbox("Вид документа", ["Invoice", "Proforma Invoice", "Receipt"])
    skip_commissions = st.checkbox("Пропускать банковские комиссии", value=True)
    skip_internal = st.checkbox("Пропускать конверсию", value=True)
    st.divider()
    st.subheader("📋 Клиенты в базе")
    st.caption(f"Всего: {len(CLIENTS)} клиентов")
    for name in list(CLIENTS.keys())[:8]:
        st.caption(f"• {name[:35]}")
    if len(CLIENTS) > 8:
        st.caption(f"• ... и ещё {len(CLIENTS)-8}")

uploaded = st.file_uploader(
    "Загрузите RTF-выписку из Цептер Банка",
    type=["rtf", "txt"],
    accept_multiple_files=True,
    help="Файлы: Выписка_*.rtf",
)

if not uploaded:
    st.info("👆 Загрузите RTF файл(ы) выписки из Цептер Банка")
    st.stop()

all_transactions = []
for f in uploaded:
    raw = f.read()
    try:
        txs, meta = parse_zepter_rtf(raw)
        all_transactions.extend(txs)
        st.success(f"✅ {f.name}: {len(txs)} операций · {meta.get('currency','?')} · {meta.get('date_from','?')} – {meta.get('date_to','?')}")
    except Exception as e:
        st.error(f"❌ Ошибка {f.name}: {e}")

if not all_transactions:
    st.warning("Транзакции не найдены.")
    st.stop()

txs = all_transactions
if skip_commissions:
    txs = [t for t in txs if not t.is_commission]
if skip_internal:
    txs = [t for t in txs if not t.is_conversion]
if filter_type == "Только поступления (+)":
    txs = [t for t in txs if t.amount > 0]
elif filter_type == "Только списания (-)":
    txs = [t for t in txs if t.amount < 0]

st.subheader(f"📊 Транзакции ({len(txs)} шт.)")
if txs:
    col1, col2, col3 = st.columns(3)
    col1.metric("Поступления", f"+{sum(t.amount for t in txs if t.amount>0):,.2f}")
    col2.metric("Списания", f"{sum(t.amount for t in txs if t.amount<0):,.2f}")
    col3.metric("Итого", len(txs))

    df = pd.DataFrame([{
        "Дата": t.date,
        "Сумма": t.amount,
        "Валюта": t.currency,
        "Контрагент": t.counterparty[:40] if t.counterparty else "—",
        "Описание": t.description[:70],
    } for t in txs])
    st.dataframe(df, use_container_width=True, hide_index=True)

st.subheader("🔗 Сопоставление контрагентов с клиентами")
client_names = list(CLIENTS.keys()) + ["⚠️ Пропустить"]
counterparties = list({t.counterparty for t in txs if t.counterparty})
mapping = {}
for cp in counterparties:
    default_idx = len(client_names) - 1
    for i, cname in enumerate(client_names):
        words = [w for w in cname.lower().split() if len(w) > 3]
        if any(w in cp.lower() for w in words[:3]):
            default_idx = i
            break
    mapping[cp] = st.selectbox(f"**{cp[:70]}**", client_names, index=default_idx, key=f"map_{cp}")

st.subheader("📥 Экспорт CSV для InvoiceOcean")
if st.button("🔄 Сгенерировать CSV", type="primary", use_container_width=True):
    rows = []
    row_num = 1
    skipped = 0
    for t in txs:
        buyer = mapping.get(t.counterparty, "⚠️ Пропустить")
        if "Пропустить" in buyer:
            skipped += 1
            continue
        amount_eur = abs(t.amount) if t.currency == "EUR" else 0.0
        due_date = add_days(t.date, due_days)
        row = build_row(
            row_num=row_num,
            invoice_no=t.doc_num or f"ZEPT-{t.date.replace('-','')}-{row_num:03d}",
            kind=invoice_kind,
            seller_key="FMCGOODS OÜ",
            status="Paid" if t.amount > 0 else "Issued",
            issue_date=t.date,
            due_date=due_date,
            buyer_name=buyer,
            amount=abs(t.amount),
            amount_eur=amount_eur,
            currency=t.currency,
            payment_date=t.date if t.amount > 0 else "",
            paid=abs(t.amount) if t.amount > 0 else 0.0,
            description=t.description[:200],
            po_number=t.doc_num,
        )
        rows.append(row)
        row_num += 1

    if rows:
        csv_bytes = generate_csv(rows)
        filename = f"InvoiceOcean_FMCGOODS_{datetime.now().strftime('%Y%m%d')}.csv"
        st.download_button(f"⬇️ Скачать {filename} ({len(rows)} строк)", csv_bytes, filename, "text/csv", use_container_width=True)
        if skipped:
            st.info(f"ℹ️ Пропущено {skipped} транзакций")
        st.success(f"✅ {len(rows)} записей готово.")
    else:
        st.warning("Нет записей для экспорта.")

st.divider()
st.caption("📌 InvoiceOcean: Settings → Import → New Import → выбрать CSV")
