import csv
import io
import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.zepter_parser import parse_zepter_rtf
from utils.clients import CLIENTS, SELLERS, find_best_client_match, load_clients_from_export, merge_clients


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

seller = SELLERS["FMCGOODS OÜ"]
client_list = list(clients.keys())


def make_due(date_value: str, days: int) -> str:
    try:
        return (datetime.strptime(date_value, "%Y-%m-%d") + timedelta(days=days)).strftime("%Y-%m-%d")
    except ValueError:
        return date_value


rows = []
for row_index, transaction in enumerate(transactions, start=1):
    buyer = find_best_client_match(
        transaction.counterparty,
        clients,
        transaction.counterparty_tax_id,
    )
    client = clients.get(buyer, {})
    amount = abs(transaction.amount)
    amount_eur = amount if transaction.currency == "EUR" else 0.0

    due_date = make_due(transaction.date, due_days)

    rows.append(
        {
            "No.": row_index,
            "No. (invoice)": transaction.doc_num or f"ZEPT-{transaction.date.replace('-', '')}-{row_index:03d}",
            "Kind": invoice_kind,
            "Seller": seller["name"],
            "Department short name": seller["name"],
            "Seller's TAX ID": seller["tax_id"],
            "Status": "Paid" if transaction.amount > 0 else "Issued",
            "Issue date": transaction.date,
            "Sale date": "",
            "Due date": due_date,
            "Buyer": buyer,
            "VAT ID": client.get("vat_id", ""),
            "Street": client.get("street", ""),
            "Postcode": client.get("postcode", ""),
            "City": client.get("city", ""),
            "Country": client.get("country", ""),
            "Client e-mail": client.get("email", ""),
            "Client's phone": client.get("phone", ""),
            "Mobile phone": "",
            "Total net price": amount,
            "TAX": 0.0,
            "Total gross price": amount,
            "Total net price EUR": amount_eur,
            "TAX EUR": 0.0,
            "Total gross price EUR": amount_eur,
            "Payment type": "Transfer",
            "Payment date": transaction.date if transaction.amount > 0 else "",
            "Paid": amount if transaction.amount > 0 else 0.0,
            "Currency": transaction.currency,
            "PO number": transaction.doc_num,
            "Product / Service": transaction.description[:200],
            "Qty": 1.0,
            "Quantity unit": "pc",
            "Source counterparty": transaction.counterparty,
            "Source tax ID": transaction.counterparty_tax_id,
        }
    )

frame = pd.DataFrame(rows)

st.subheader("Edit rows before export")
st.caption("You can edit any field here and delete rows directly in the table.")

edited_frame = st.data_editor(
    frame,
    use_container_width=True,
    num_rows="dynamic",
    hide_index=True,
    column_config={
        "Buyer": st.column_config.SelectboxColumn("Buyer", options=client_list + [""]),
        "Kind": st.column_config.SelectboxColumn("Kind", options=["Invoice", "Proforma Invoice", "Receipt"]),
        "Status": st.column_config.SelectboxColumn(
            "Status", options=["Paid", "Partially paid", "Issued", "Rejected"]
        ),
        "Currency": st.column_config.SelectboxColumn("Currency", options=["EUR", "RUB", "USD", "BYN"]),
        "Payment type": st.column_config.SelectboxColumn("Payment type", options=["Transfer", "Cash", "Card"]),
        "Quantity unit": st.column_config.SelectboxColumn("Quantity unit", options=["pc", "pcs", "case", "kg", "l"]),
    },
)

st.subheader("Export CSV for InvoiceOcean")
if st.button("Generate CSV", type="primary", use_container_width=True):
    final_columns = [
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
