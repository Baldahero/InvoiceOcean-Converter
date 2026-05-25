import os
import sys
from datetime import datetime

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.zepter_parser import parse_zepter_rtf
from utils.clients import CLIENTS, find_best_client_match, load_clients_from_export, merge_clients
from utils.csv_builder import add_days, build_row, generate_csv


st.set_page_config(page_title="FMCGOODS OÜ", page_icon="🇪🇪", layout="wide")
st.title("🇪🇪 FMCGOODS OÜ -> Zepter Bank -> InvoiceOcean")

with st.sidebar:
    st.header("Settings")
    filter_type = st.selectbox("Transaction type", ["All", "Incoming only (+)", "Outgoing only (-)"])
    due_days = st.number_input("Due days", min_value=0, max_value=90, value=7)
    invoice_kind = st.selectbox("Document kind", ["Invoice", "Proforma Invoice", "Receipt"])
    skip_commissions = st.checkbox("Skip bank commissions", value=True)
    skip_internal = st.checkbox("Skip internal conversion", value=True)
    clients_file = st.file_uploader(
        "InvoiceOcean clients export",
        type=["xls", "xlsx", "csv"],
        help="Optional but recommended for better matching.",
    )

clients = CLIENTS
if clients_file is not None:
    try:
        uploaded_clients = load_clients_from_export(clients_file.read(), clients_file.name)
        clients = merge_clients(CLIENTS, uploaded_clients)
        st.sidebar.success(f"Loaded {len(uploaded_clients)} clients from export.")
    except Exception as exc:
        st.sidebar.error(f"Could not read clients export: {exc}")

with st.sidebar:
    st.divider()
    st.subheader("Known clients")
    st.caption(f"Available: {len(clients)}")
    for name in list(clients.keys())[:8]:
        st.caption(f"- {name[:35]}")
    if len(clients) > 8:
        st.caption(f"- ... and {len(clients) - 8} more")

uploaded_files = st.file_uploader(
    "Upload Zepter Bank RTF statements",
    type=["rtf", "txt"],
    accept_multiple_files=True,
    help="Files like Выписка_*.rtf",
)

if not uploaded_files:
    st.info("Upload one or more Zepter Bank RTF files to continue.")
    st.stop()

all_transactions = []
for uploaded_file in uploaded_files:
    raw_bytes = uploaded_file.read()
    try:
        transactions, metadata = parse_zepter_rtf(raw_bytes)
        all_transactions.extend(transactions)
        st.success(
            f"Loaded {uploaded_file.name}: {len(transactions)} transactions, "
            f"{metadata.get('currency', '?')} {metadata.get('date_from', '?')} -> {metadata.get('date_to', '?')}"
        )
    except Exception as exc:
        st.error(f"{uploaded_file.name}: {exc}")

if not all_transactions:
    st.warning("No transactions were parsed.")
    st.stop()

transactions = all_transactions
if skip_commissions:
    transactions = [transaction for transaction in transactions if not transaction.is_commission]
if skip_internal:
    transactions = [transaction for transaction in transactions if not transaction.is_conversion]
if filter_type == "Incoming only (+)":
    transactions = [transaction for transaction in transactions if transaction.amount > 0]
elif filter_type == "Outgoing only (-)":
    transactions = [transaction for transaction in transactions if transaction.amount < 0]

if not transactions:
    st.warning("No transactions left after filtering.")
    st.stop()

st.subheader(f"Parsed transactions: {len(transactions)}")
col1, col2, col3 = st.columns(3)
col1.metric("Incoming", f"+{sum(tx.amount for tx in transactions if tx.amount > 0):,.2f}")
col2.metric("Outgoing", f"{sum(tx.amount for tx in transactions if tx.amount < 0):,.2f}")
col3.metric("Rows", len(transactions))

preview_frame = pd.DataFrame(
    [
        {
            "Date": transaction.date,
            "Amount": transaction.amount,
            "Currency": transaction.currency,
            "Counterparty": transaction.counterparty[:50] if transaction.counterparty else "—",
            "Tax ID": transaction.counterparty_tax_id,
            "Description": transaction.description[:90],
        }
        for transaction in transactions
    ]
)
st.dataframe(preview_frame, use_container_width=True, hide_index=True)

st.subheader("Counterparty matching")
client_names = list(clients.keys()) + ["Skip"]
counterparties = sorted({transaction.counterparty for transaction in transactions if transaction.counterparty})
mapping: dict[str, str] = {}

for counterparty in counterparties:
    sample_transaction = next(
        transaction for transaction in transactions if transaction.counterparty == counterparty
    )
    default_client = find_best_client_match(
        counterparty,
        clients,
        sample_transaction.counterparty_tax_id,
    )
    default_index = client_names.index(default_client) if default_client in client_names else len(client_names) - 1
    mapping[counterparty] = st.selectbox(
        f"**{counterparty[:70]}**",
        client_names,
        index=default_index,
        key=f"map_{counterparty}",
    )

st.subheader("Export CSV for InvoiceOcean")
if st.button("Generate CSV", type="primary", use_container_width=True):
    rows = []
    row_num = 1
    skipped = 0

    for transaction in transactions:
        buyer = mapping.get(transaction.counterparty, "Skip")
        if buyer == "Skip":
            skipped += 1
            continue

        amount_eur = abs(transaction.amount) if transaction.currency == "EUR" else 0.0
        due_date = add_days(transaction.date, due_days)
        rows.append(
            build_row(
                row_num=row_num,
                invoice_no=transaction.doc_num or f"ZEPT-{transaction.date.replace('-', '')}-{row_num:03d}",
                kind=invoice_kind,
                seller_key="FMCGOODS OÜ",
                status="Paid" if transaction.amount > 0 else "Issued",
                issue_date=transaction.date,
                due_date=due_date,
                buyer_name=buyer,
                amount=abs(transaction.amount),
                amount_eur=amount_eur,
                currency=transaction.currency,
                payment_date=transaction.date if transaction.amount > 0 else "",
                paid=abs(transaction.amount) if transaction.amount > 0 else 0.0,
                description=transaction.description[:200],
                po_number=transaction.doc_num,
                clients=clients,
            )
        )
        row_num += 1

    if not rows:
        st.warning("No rows were prepared for export.")
    else:
        csv_bytes = generate_csv(rows)
        filename = f"InvoiceOcean_FMCGOODS_{datetime.now().strftime('%Y%m%d')}.csv"
        st.download_button(
            f"Download {filename}",
            csv_bytes,
            filename,
            "text/csv",
            use_container_width=True,
        )
        if skipped:
            st.info(f"Skipped {skipped} transactions without a mapped client.")
        st.success(f"Prepared {len(rows)} CSV rows.")
