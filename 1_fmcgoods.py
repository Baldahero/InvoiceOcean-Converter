import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from parsers.zepter_parser import parse_zepter_rtf
from utils.csv_builder import build_row, generate_csv, add_days
from utils.clients import CLIENTS, SELLERS

st.set_page_config(page_title="FMCGOODS OÜ — Конвертер", page_icon="🇪🇪", layout="wide")
st.title("🇪🇪 FMCGOODS OÜ — Цептер Банк → InvoiceOcean")

# ── Sidebar settings ──────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Настройки")

    filter_type = st.selectbox(
        "Тип операций",
        ["Все", "Только поступления (+)", "Только списания (-)"],
    )

    due_days = st.number_input(
        "Срок оплаты (дней от даты выписки)", min_value=0, max_value=90, value=7
    )

    invoice_kind = st.selectbox(
        "Вид документа",
        ["Invoice", "Proforma Invoice", "Receipt"],
    )

    skip_commissions = st.checkbox("Пропускать банковские комиссии", value=True)
    skip_internal = st.checkbox("Пропускать внутренние переводы (конверсия)", value=True)

    st.divider()
    st.subheader("📋 Клиенты")
    st.caption("Клиенты из базы данных:")
    for name, info in CLIENTS.items():
        st.markdown(f"• **{name[:25]}…**  \n  {info['country']} · VAT: {info['vat_id']}")


# ── File upload ───────────────────────────────────────────────────────────────
uploaded = st.file_uploader(
    "Загрузите RTF-выписку из Цептер Банка",
    type=["rtf", "txt"],
    accept_multiple_files=True,
    help="Файлы: Выписка_*.rtf",
)

if not uploaded:
    st.info("👆 Загрузите RTF файл(ы) выписки из Цептер Банка")
    st.stop()

# ── Parse ─────────────────────────────────────────────────────────────────────
all_transactions = []
all_metadata = []

for f in uploaded:
    raw = f.read()
    try:
        txs, meta = parse_zepter_rtf(raw)
        all_transactions.extend(txs)
        all_metadata.append(meta)
        st.success(f"✅ {f.name}: найдено {len(txs)} операций · {meta.get('currency','?')} · {meta.get('date_from','?')} – {meta.get('date_to','?')}")
    except Exception as e:
        st.error(f"❌ Ошибка при разборе {f.name}: {e}")

if not all_transactions:
    st.warning("Не удалось распознать транзакции. Проверьте формат файла.")
    st.stop()

# ── Filter ────────────────────────────────────────────────────────────────────
txs = all_transactions

if skip_commissions:
    txs = [t for t in txs if not t.is_commission]

if skip_internal:
    txs = [t for t in txs if "конверс" not in t.description.lower()]

if filter_type == "Только поступления (+)":
    txs = [t for t in txs if t.amount > 0]
elif filter_type == "Только списания (-)":
    txs = [t for t in txs if t.amount < 0]

# ── Preview table ─────────────────────────────────────────────────────────────
st.subheader(f"📊 Транзакции ({len(txs)} шт.)")

if txs:
    df_data = []
    for t in txs:
        df_data.append({
            "Дата": t.date,
            "Описание": t.description[:80],
            "Контрагент": t.counterparty[:40] if t.counterparty else "—",
            "Сумма": t.amount,
            "Валюта": t.currency,
        })

    df = pd.DataFrame(df_data)

    col1, col2, col3 = st.columns(3)
    incoming = sum(t.amount for t in txs if t.amount > 0)
    outgoing = sum(t.amount for t in txs if t.amount < 0)
    col1.metric("Поступления", f"+{incoming:,.2f}")
    col2.metric("Списания", f"{outgoing:,.2f}")
    col3.metric("Итого операций", len(txs))

    st.dataframe(
        df.style.applymap(
            lambda v: "color: green" if isinstance(v, float) and v > 0
            else ("color: red" if isinstance(v, float) and v < 0 else ""),
            subset=["Сумма"],
        ),
        use_container_width=True,
        hide_index=True,
    )

# ── Client mapping ────────────────────────────────────────────────────────────
st.subheader("🔗 Сопоставление контрагентов с клиентами")
st.caption("Укажите, какому клиенту InvoiceOcean соответствует каждый контрагент из выписки.")

client_names = list(CLIENTS.keys()) + ["⚠️ Пропустить / не создавать счёт"]

counterparties = list({t.counterparty for t in txs if t.counterparty})
mapping = {}
for cp in counterparties:
    default_idx = 0
    for i, cname in enumerate(client_names):
        if any(word.lower() in cp.lower() for word in cname.lower().split()[:2]):
            default_idx = i
            break
    mapping[cp] = st.selectbox(
        f"**{cp[:60]}**",
        client_names,
        index=default_idx,
        key=f"map_{cp}",
    )

# ── Generate CSV ──────────────────────────────────────────────────────────────
st.subheader("📥 Экспорт CSV для InvoiceOcean")

if st.button("🔄 Сгенерировать CSV", type="primary", use_container_width=True):
    rows = []
    row_num = 1
    skipped = 0

    for t in txs:
        buyer = mapping.get(t.counterparty, "⚠️ Пропустить / не создавать счёт")
        if "Пропустить" in buyer:
            skipped += 1
            continue

        # For EUR account: amount = EUR, amount_eur = same
        # For RUB account: amount = RUB, amount_eur = 0 (unknown without rate)
        if t.currency == "EUR":
            amount_eur = abs(t.amount)
        else:
            amount_eur = 0.0

        due_date = add_days(t.date, due_days)
        status = "Paid" if t.amount > 0 else "Issued"
        paid_amount = abs(t.amount) if t.amount > 0 else 0.0

        row = build_row(
            row_num=row_num,
            invoice_no=t.doc_num or f"ZEPT-{t.date.replace('-','')}-{row_num:03d}",
            kind=invoice_kind,
            seller_key="FMCGOODS OÜ",
            status=status,
            issue_date=t.date,
            due_date=due_date,
            buyer_name=buyer,
            amount=abs(t.amount),
            amount_eur=amount_eur,
            currency=t.currency,
            payment_date=t.date if t.amount > 0 else "",
            paid=paid_amount,
            description=t.description[:200],
            po_number=t.doc_num,
        )
        rows.append(row)
        row_num += 1

    if rows:
        csv_bytes = generate_csv(rows)
        date_str = datetime.now().strftime("%Y%m%d")
        filename = f"InvoiceOcean_FMCGOODS_{date_str}.csv"

        st.download_button(
            label=f"⬇️ Скачать {filename} ({len(rows)} строк)",
            data=csv_bytes,
            file_name=filename,
            mime="text/csv",
            use_container_width=True,
        )
        if skipped:
            st.info(f"ℹ️ Пропущено {skipped} транзакций (не сопоставлены с клиентом)")
        st.success(f"✅ Готово! {len(rows)} записей экспортировано.")
    else:
        st.warning("Нет записей для экспорта — все транзакции пропущены.")

st.divider()
st.caption("📌 Загрузите CSV в InvoiceOcean: Settings → Import → New Import")
