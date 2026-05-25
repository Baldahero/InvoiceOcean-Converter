import streamlit as st
import pandas as pd
from datetime import datetime
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from parsers.pko_parser import parse_pko_pdf
from utils.csv_builder import build_row, generate_csv, add_days
from utils.clients import CLIENTS, SELLERS

st.set_page_config(page_title="TENTA TRADE — Конвертер", page_icon="🇵🇱", layout="wide")
st.title("🇵🇱 TENTA TRADE SP. Z O.O. — PKO Bank → InvoiceOcean")

with st.sidebar:
    st.header("⚙️ Настройки")

    filter_type = st.selectbox(
        "Тип операций",
        ["Все", "Только поступления (+)", "Только списания (-)"],
    )

    due_days = st.number_input(
        "Срок оплаты (дней)", min_value=0, max_value=90, value=7
    )

    invoice_kind = st.selectbox(
        "Вид документа",
        ["Invoice", "Proforma Invoice", "Receipt"],
    )

    skip_commissions = st.checkbox("Пропускать комиссии", value=True)
    skip_tax = st.checkbox("Пропускать налоги/ZUS", value=True)
    skip_fx = st.checkbox("Пропускать FX-конверсию", value=True)

    st.divider()
    st.subheader("📋 Клиенты")
    for name, info in CLIENTS.items():
        st.markdown(f"• **{name[:25]}**  \n  {info['country']} · VAT: {info['vat_id']}")


uploaded = st.file_uploader(
    "Загрузите PDF-выписку из PKO Bank Polski",
    type=["pdf"],
    accept_multiple_files=True,
    help="Файлы: ACCOUNTS-HISTORY_*.pdf",
)

if not uploaded:
    st.info("👆 Загрузите PDF файл(ы) выписки из PKO Bank Polski")
    st.stop()

all_transactions = []

for f in uploaded:
    raw = f.read()
    try:
        txs, meta = parse_pko_pdf(raw)
        all_transactions.extend(txs)
        st.success(f"✅ {f.name}: {len(txs)} операций · {meta.get('currency','?')} · {meta.get('date_from','?')} – {meta.get('date_to','?')}")
    except ImportError:
        st.error("❌ Не установлен pdfplumber. Выполните: pip install pdfplumber")
        st.stop()
    except Exception as e:
        st.error(f"❌ Ошибка: {e}")

if not all_transactions:
    st.warning("Транзакции не найдены.")
    st.stop()

txs = all_transactions

if skip_commissions:
    txs = [t for t in txs if t.op_type != "Commission"]
if skip_tax:
    txs = [t for t in txs if t.op_type not in ["VAT transfer to Tax Office", "Transfer to Social Security Institution"]]
if skip_fx:
    txs = [t for t in txs if "FX" not in t.title]

if filter_type == "Только поступления (+)":
    txs = [t for t in txs if t.amount > 0]
elif filter_type == "Только списания (-)":
    txs = [t for t in txs if t.amount < 0]

st.subheader(f"📊 Транзакции ({len(txs)} шт.)")

if txs:
    col1, col2, col3 = st.columns(3)
    incoming = sum(t.amount for t in txs if t.amount > 0)
    outgoing = sum(t.amount for t in txs if t.amount < 0)
    col1.metric("Поступления", f"+{incoming:,.2f}")
    col2.metric("Списания", f"{outgoing:,.2f}")
    col3.metric("Итого", len(txs))

    df = pd.DataFrame([{
        "Дата": t.date,
        "Тип": t.op_type,
        "Контрагент": t.counterparty_name[:40] if t.counterparty_name else "—",
        "Описание": t.title[:60],
        "Сумма": t.amount,
        "Валюта": t.currency,
    } for t in txs])

    st.dataframe(df, use_container_width=True, hide_index=True)

st.subheader("🔗 Сопоставление контрагентов с клиентами")
client_names = list(CLIENTS.keys()) + ["⚠️ Пропустить"]

counterparties = list({t.counterparty_name for t in txs if t.counterparty_name})
mapping = {}
for cp in counterparties:
    default_idx = len(client_names) - 1
    for i, cname in enumerate(client_names):
        if any(w.lower() in cp.lower() for w in cname.lower().split()[:2] if len(w) > 3):
            default_idx = i
            break
    mapping[cp] = st.selectbox(f"**{cp[:70]}**", client_names, index=default_idx, key=f"tenta_{cp}")

st.subheader("📥 Экспорт")

if st.button("🔄 Сгенерировать CSV", type="primary", use_container_width=True):
    rows = []
    row_num = 1
    skipped = 0

    for t in txs:
        buyer = mapping.get(t.counterparty_name, "⚠️ Пропустить")
        if "Пропустить" in buyer:
            skipped += 1
            continue

        if t.currency == "EUR":
            amount_eur = abs(t.amount)
        else:
            amount_eur = 0.0

        due_date = add_days(t.date, due_days)
        status = "Paid" if t.amount > 0 else "Issued"
        paid = abs(t.amount) if t.amount > 0 else 0.0

        row = build_row(
            row_num=row_num,
            invoice_no=t.tx_id or f"PKO-{t.date.replace('-','')}-{row_num:03d}",
            kind=invoice_kind,
            seller_key="TENTA TRADE SP. Z O.O.",
            status=status,
            issue_date=t.date,
            due_date=due_date,
            buyer_name=buyer,
            amount=abs(t.amount),
            amount_eur=amount_eur,
            currency=t.currency,
            payment_date=t.date if t.amount > 0 else "",
            paid=paid,
            description=t.title[:200],
            po_number=t.tx_id,
        )
        rows.append(row)
        row_num += 1

    if rows:
        csv_bytes = generate_csv(rows)
        date_str = datetime.now().strftime("%Y%m%d")
        filename = f"InvoiceOcean_TENTA_{date_str}.csv"
        st.download_button(
            label=f"⬇️ Скачать {filename} ({len(rows)} строк)",
            data=csv_bytes,
            file_name=filename,
            mime="text/csv",
            use_container_width=True,
        )
        if skipped:
            st.info(f"ℹ️ Пропущено {skipped} транзакций")
        st.success(f"✅ {len(rows)} записей готово.")
    else:
        st.warning("Нет записей для экспорта.")

st.divider()
st.caption("📌 Загрузите CSV в InvoiceOcean: Settings → Import → New Import")
