import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.pko_parser import parse_pko_pdf
from utils.clients import CLIENTS, SELLERS, find_best_client_match, load_clients_from_export, merge_clients


st.set_page_config(page_title="TENTA TRADE", page_icon="🇵🇱", layout="wide")
st.title("🇵🇱 TENTA TRADE SP. Z O.O. -> PKO Bank -> InvoiceOcean")

with st.sidebar:
    st.header("Settings")
    due_days = st.number_input("Due days", min_value=0, max_value=90, value=7)
    invoice_kind = st.selectbox("Document kind", ["Invoice", "Proforma Invoice", "Receipt"])
    filter_type = st.selectbox("Show transactions", ["All", "Incoming only (+)", "Outgoing only (-)"])
    skip_commissions = st.checkbox("Hide bank commissions", value=True)
    skip_tax = st.checkbox("Hide tax and social transfers", value=True)
    skip_fx = st.checkbox("Hide FX conversion", value=True)
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

uploaded_files = st.file_uploader(
    "Upload PKO Bank Polski PDF statements",
    type=["pdf"],
    accept_multiple_files=True,
    help="Files like ACCOUNTS-HISTORY_*.pdf",
)

if not uploaded_files:
    st.info("Upload one or more PKO PDF statements to continue.")
    st.stop()

all_transactions = []
for uploaded_file in uploaded_files:
    try:
        transactions, metadata = parse_pko_pdf(uploaded_file.read())
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
    transactions = [tx for tx in transactions if tx.op_type != "Commission"]
if skip_tax:
    transactions = [
        tx
        for tx in transactions
        if tx.op_type not in ["VAT transfer to Tax Office", "Transfer to Social Security Institution"]
    ]
if skip_fx:
    transactions = [tx for tx in transactions if "FX" not in tx.title]
if filter_type == "Incoming only (+)":
    transactions = [tx for tx in transactions if tx.amount > 0]
elif filter_type == "Outgoing only (-)":
    transactions = [tx for tx in transactions if tx.amount < 0]

if not transactions:
    st.warning("No transactions left after filtering.")
    st.stop()


def make_due(issue_date: str, days: int) -> str:
    try:
        return (datetime.strptime(issue_date, "%Y-%m-%d") + timedelta(days=days)).strftime("%Y-%m-%d")
    except ValueError:
        return ""


seller = SELLERS["TENTA TRADE SP. Z O.O."]
client_list = list(clients.keys())

rows = []
for row_index, transaction in enumerate(transactions, start=1):
    buyer = find_best_client_match(transaction.counterparty_name, clients)
    client = clients.get(buyer, {})
    amount = abs(transaction.amount)
    amount_eur = amount if transaction.currency == "EUR" else 0.0
    due_date = make_due(transaction.date, due_days)
    status = "Paid" if transaction.amount > 0 else "Issued"
    paid = amount if transaction.amount > 0 else 0.0

    rows.append(
        {
            "No.": row_index,
            "No. (invoice)": transaction.tx_id or f"PKO-{transaction.date.replace('-', '')}-{row_index:03d}",
            "Kind": invoice_kind,
            "Seller": seller["name"],
            "Department short name": seller["name"],
            "Seller's TAX ID": seller["tax_id"],
            "Status": status,
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
            "Paid": paid,
            "Currency": transaction.currency,
            "PO number": transaction.tx_id,
            "Product / Service": transaction.title[:200],
            "Qty": 1.0,
            "Quantity unit": "pc",
        }
    )

frame = pd.DataFrame(rows)

st.subheader(f"Parsed transactions: {len(transactions)}")
col1, col2, col3 = st.columns(3)
col1.metric("Incoming", f"+{sum(tx.amount for tx in transactions if tx.amount > 0):,.2f}")
col2.metric("Outgoing", f"{sum(tx.amount for tx in transactions if tx.amount < 0):,.2f}")
col3.metric("Rows", len(transactions))

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
        "Currency": st.column_config.SelectboxColumn("Currency", options=["EUR", "PLN", "USD", "RUB"]),
        "Payment type": st.column_config.SelectboxColumn("Payment type", options=["Transfer", "Cash", "Card"]),
    },
)

st.divider()
st.subheader("Export")

if st.button("Generate CSV for InvoiceOcean", type="primary", use_container_width=True):
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
        "Product / Service", "Qty", "Unit net price", "
