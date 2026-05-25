import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.zepter_parser import parse_zepter_rtf
from utils.clients import CLIENTS, SELLERS, find_best_client_match, load_clients_from_export, merge_clients
from utils.csv_builder import generate_csv


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
    matched_buyer = find_best_client_match(
        transaction.counterparty,
        clients,
        transaction.counterparty_tax_id,
    )
    buyer = matched_buyer or transaction.counterparty
    client = clients.get(matched_buyer, {})
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
        "Buyer": st.column_config.TextColumn(
            "Buyer",
            help="You can type any buyer name manually or paste the exact InvoiceOcean client name.",
        ),
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
output_rows = []
skipped = 0

for output_index, (_, row) in enumerate(edited_frame.iterrows(), start=1):
    buyer = str(row.get("Buyer", "")).strip()
    if not buyer:
        skipped += 1
        continue

    source_tax_id = str(row.get("Source tax ID", "")).strip()
    client_key = buyer if buyer in clients else find_best_client_match(buyer, clients, source_tax_id)
    client = clients.get(client_key, {})
    amount = float(row.get("Total gross price", 0) or 0)
    amount_eur = float(row.get("Total gross price EUR", 0) or 0)

    output_rows.append(
        [
            output_index,
            str(row.get("No. (invoice)", "")),
            str(row.get("Kind", "Invoice")),
            str(row.get("Seller", "")),
            str(row.get("Department short name", "")),
            str(row.get("Seller's TAX ID", "")),
            str(row.get("Status", "Issued")),
            str(row.get("Issue date", "")),
            str(row.get("Sale date", "")),
            str(row.get("Due date", "")),
            buyer,
            str(row.get("VAT ID", "") or client.get("vat_id", "")),
            str(row.get("Street", "") or client.get("street", "")),
            str(row.get("Postcode", "") or client.get("postcode", "")),
            str(row.get("City", "") or client.get("city", "")),
            str(row.get("Country", "") or client.get("country", "")),
            str(row.get("Client e-mail", "") or client.get("email", "")),
            str(row.get("Client's phone", "") or client.get("phone", "")),
            str(row.get("Mobile phone", "")),
            amount,
            float(row.get("TAX", 0) or 0),
            amount,
            amount_eur,
            float(row.get("TAX EUR", 0) or 0),
            amount_eur,
            str(row.get("Payment type", "Transfer")),
            str(row.get("Payment date", "")),
            float(row.get("Paid", 0) or 0),
            str(row.get("Currency", "EUR")),
            str(row.get("PO number", "")),
            "",
            "",
            "",
            "",
            "",
            "",
            str(row.get("Product / Service", "")),
            float(row.get("Qty", 1) or 1),
            amount,
            amount,
            "disabled",
            0.0,
            amount,
            amount,
            "",
            str(row.get("Quantity unit", "pc")),
            "",
        ]
    )

if skipped:
    st.info(f"Skipped {skipped} rows without Buyer.")

if not output_rows:
    st.warning("No rows are ready for export. Fill Buyer or add valid rows first.")
else:
    filename = f"InvoiceOcean_FMCGOODS_{datetime.now().strftime('%Y%m%d')}.csv"
    st.caption(f"Ready rows: {len(output_rows)}")
    st.download_button(
        "Download CSV for InvoiceOcean",
        generate_csv(output_rows),
        filename,
        "text/csv",
        use_container_width=True,
    )
