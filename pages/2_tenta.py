import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.pko_parser import parse_pko_pdf
from utils.clients import CLIENTS, SELLERS, find_best_client_match, load_clients_from_export, merge_clients
from utils.csv_builder import EXPENSE_HEADERS, generate_csv
from utils.learning import find_learning_match, learning_examples_count, remember_learning_rows


TENTA_NAME = "TENTA TRADE SP. Z O.O."
TENTA_PROFILE = SELLERS[TENTA_NAME]


st.set_page_config(page_title="TENTA TRADE", page_icon="🇵🇱", layout="wide")
st.title("🇵🇱 TENTA TRADE SP. Z O.O. -> PKO Bank -> InvoiceOcean")


def make_due(issue_date: str, days: int) -> str:
    try:
        return (datetime.strptime(issue_date, "%Y-%m-%d") + timedelta(days=days)).strftime("%Y-%m-%d")
    except ValueError:
        return ""


def detect_document_side(amount: float) -> str:
    return "Income" if amount > 0 else "Expenses"


with st.sidebar:
    st.header("Settings")
    due_days = st.number_input("Due days", min_value=0, max_value=90, value=7)
    default_kind = st.selectbox("Default document kind", ["Invoice", "Proforma Invoice", "Receipt"])
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

with st.sidebar:
    st.divider()
    st.caption(f"Learning memory: {learning_examples_count()} saved examples")

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

st.subheader(f"Parsed transactions: {len(transactions)}")
col1, col2, col3 = st.columns(3)
col1.metric("Incoming", f"+{sum(tx.amount for tx in transactions if tx.amount > 0):,.2f}")
col2.metric("Outgoing", f"{sum(tx.amount for tx in transactions if tx.amount < 0):,.2f}")
col3.metric("Rows", len(transactions))

rows = []
for row_index, transaction in enumerate(transactions, start=1):
    matched_party = find_best_client_match(transaction.counterparty_name, clients)
    partner_name = matched_party or transaction.counterparty_name
    partner_client = clients.get(matched_party, {})

    document_side = detect_document_side(transaction.amount)
    amount = abs(transaction.amount)
    amount_eur = amount if transaction.currency == "EUR" else 0.0
    due_date = make_due(transaction.date, due_days)

    if document_side == "Income":
        buyer_name = partner_name
        seller_name = TENTA_PROFILE["name"]
    else:
        buyer_name = TENTA_PROFILE["name"]
        seller_name = partner_name

    row = {
        "No.": row_index,
        "Document side": document_side,
        "No. (invoice)": transaction.tx_id or f"PKO-{transaction.date.replace('-', '')}-{row_index:03d}",
        "Kind": default_kind,
        "Status": "Paid" if transaction.amount > 0 else "Issued",
        "Issue date": transaction.date,
        "Sale date": "",
        "Due date": due_date,
        "Buyer": buyer_name,
        "Seller": seller_name,
        "VAT ID": partner_client.get("vat_id", ""),
        "Street": partner_client.get("street", ""),
        "Postcode": partner_client.get("postcode", ""),
        "City": partner_client.get("city", ""),
        "Country": partner_client.get("country", ""),
        "Client e-mail": partner_client.get("email", ""),
        "Client's phone": partner_client.get("phone", ""),
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
        "PO number": transaction.tx_id,
        "Product / Service": transaction.title[:200],
        "Qty": 1.0,
        "Quantity unit": "pc",
        "Source counterparty": transaction.counterparty_name,
        "Source description": transaction.title,
        "Source tax ID": "",
        "Source bank doc": transaction.tx_id,
    }

    learned = find_learning_match(
        TENTA_NAME,
        transaction.counterparty_name,
        "",
        transaction.title,
    )
    if learned:
        row.update({key: value for key, value in learned.items() if value not in (None, "")})

    rows.append(row)

frame = pd.DataFrame(rows)

st.subheader("Edit rows before export")
st.caption("You can change document side, buyer, seller, product text, dates, and delete rows directly in the table.")

edited_frame = st.data_editor(
    frame,
    use_container_width=True,
    num_rows="dynamic",
    hide_index=True,
    column_config={
        "Document side": st.column_config.SelectboxColumn("Document side", options=["Income", "Expenses"]),
        "Buyer": st.column_config.TextColumn(
            "Buyer",
            help="For Income this is the customer. For Expenses this should usually stay TENTA TRADE SP. Z O.O.",
        ),
        "Seller": st.column_config.TextColumn(
            "Seller",
            help="For Income this should usually stay TENTA TRADE SP. Z O.O. For Expenses this is the supplier.",
        ),
        "Kind": st.column_config.SelectboxColumn("Kind", options=["Invoice", "Proforma Invoice", "Receipt"]),
        "Status": st.column_config.SelectboxColumn(
            "Status", options=["Paid", "Partially paid", "Issued", "Rejected"]
        ),
        "Currency": st.column_config.SelectboxColumn("Currency", options=["EUR", "PLN", "USD", "RUB"]),
        "Payment type": st.column_config.SelectboxColumn("Payment type", options=["Transfer", "Cash", "Card"]),
        "Quantity unit": st.column_config.SelectboxColumn("Quantity unit", options=["pc", "pcs", "case", "kg", "l"]),
    },
)

st.divider()
st.subheader("Export")

income_rows = []
expense_rows = []
skipped = 0

for _, row in edited_frame.iterrows():
    document_side = str(row.get("Document side", "Income")).strip() or "Income"
    buyer_name = str(row.get("Buyer", "")).strip()
    seller_name = str(row.get("Seller", "")).strip()
    partner_name = buyer_name if document_side == "Income" else seller_name

    if not partner_name:
        skipped += 1
        continue

    client_key = partner_name if partner_name in clients else find_best_client_match(partner_name, clients)
    partner_client = clients.get(client_key, {})
    amount = float(row.get("Total gross price", 0) or 0)
    amount_eur = float(row.get("Total gross price EUR", 0) or 0)
    invoice_no = str(row.get("No. (invoice)", ""))
    po_number = str(row.get("PO number", "")) or invoice_no

    common_tail = [
        amount,
        float(row.get("TAX", 0) or 0),
        amount,
        amount_eur,
        float(row.get("TAX EUR", 0) or 0),
        amount_eur,
        str(row.get("Payment type", "Transfer")),
        str(row.get("Payment date", "")),
        float(row.get("Paid", 0) or 0),
        str(row.get("Currency", "PLN")),
        po_number,
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

    if document_side == "Income":
        income_rows.append(
            [
                len(income_rows) + 1,
                invoice_no,
                str(row.get("Kind", default_kind)),
                seller_name or TENTA_PROFILE["name"],
                TENTA_PROFILE["name"],
                TENTA_PROFILE["tax_id"],
                str(row.get("Status", "Issued")),
                str(row.get("Issue date", "")),
                str(row.get("Sale date", "")),
                str(row.get("Due date", "")),
                buyer_name,
                str(row.get("VAT ID", "") or partner_client.get("vat_id", "")),
                str(row.get("Street", "") or partner_client.get("street", "")),
                str(row.get("Postcode", "") or partner_client.get("postcode", "")),
                str(row.get("City", "") or partner_client.get("city", "")),
                str(row.get("Country", "") or partner_client.get("country", "")),
                str(row.get("Client e-mail", "") or partner_client.get("email", "")),
                str(row.get("Client's phone", "") or partner_client.get("phone", "")),
                str(row.get("Mobile phone", "")),
                *common_tail,
            ]
        )
    else:
        expense_rows.append(
            [
                len(expense_rows) + 1,
                invoice_no,
                str(row.get("Kind", default_kind)),
                buyer_name or TENTA_PROFILE["name"],
                TENTA_PROFILE["name"],
                TENTA_PROFILE["tax_id"],
                str(row.get("Status", "Issued")),
                str(row.get("Issue date", "")),
                str(row.get("Sale date", "")),
                str(row.get("Due date", "")),
                seller_name,
                str(row.get("VAT ID", "") or partner_client.get("vat_id", "")),
                str(row.get("Street", "") or partner_client.get("street", "")),
                str(row.get("Postcode", "") or partner_client.get("postcode", "")),
                str(row.get("City", "") or partner_client.get("city", "")),
                str(row.get("Country", "") or partner_client.get("country", "")),
                str(row.get("Client e-mail", "") or partner_client.get("email", "")),
                str(row.get("Client's phone", "") or partner_client.get("phone", "")),
                str(row.get("Mobile phone", "")),
                *common_tail,
            ]
        )

if skipped:
    st.info(f"Skipped {skipped} rows without a filled buyer/seller.")

downloaded = False

if not income_rows and not expense_rows:
    st.warning("No rows are ready for export. Fill buyer/seller or add valid rows first.")
else:
    st.caption(f"Ready rows: Income {len(income_rows)} | Expenses {len(expense_rows)}")

    if income_rows:
        income_name = f"InvoiceOcean_TENTA_Income_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        downloaded = st.download_button(
            "Download Income CSV",
            generate_csv(income_rows),
            income_name,
            "text/csv",
            use_container_width=True,
        ) or downloaded

    if expense_rows:
        expense_name = f"InvoiceOcean_TENTA_Expenses_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        downloaded = st.download_button(
            "Download Expenses CSV",
            generate_csv(expense_rows, headers=EXPENSE_HEADERS),
            expense_name,
            "text/csv",
            use_container_width=True,
        ) or downloaded

if downloaded:
    learned_count = remember_learning_rows(TENTA_NAME, edited_frame.to_dict("records"))
    if learned_count:
        st.success(f"Learning memory updated from {learned_count} row(s).")
