import csv
import io
import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.pko_parser import parse_pko_pdf
from utils import clients as client_utils

try:
    from utils.csv_builder import EXPENSE_HEADERS as SHARED_EXPENSE_HEADERS
except ImportError:
    SHARED_EXPENSE_HEADERS = None

try:
    from utils.csv_builder import generate_csv as shared_generate_csv
except ImportError:
    shared_generate_csv = None

try:
    from utils.learning import find_learning_match, learning_examples_count, remember_learning_rows
except ImportError:
    def find_learning_match(*args, **kwargs):
        return {}

    def learning_examples_count():
        return 0

    def remember_learning_rows(*args, **kwargs):
        return 0


TENTA_NAME = "TENTA TRADE SP. Z O.O."
CLIENTS = client_utils.CLIENTS
SELLERS = client_utils.SELLERS
find_best_client_match = client_utils.find_best_client_match
load_clients_from_export = client_utils.load_clients_from_export
merge_clients = client_utils.merge_clients

TENTA_PROFILE = SELLERS.get(TENTA_NAME) or {
    "name": TENTA_NAME,
    "tax_id": "PL5423456230",
    "currency_default": "PLN",
}

INCOME_HEADERS = [
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

EXPENSE_HEADERS = SHARED_EXPENSE_HEADERS or [
    "No.", "No.", "Kind", "Buyer", "Department short name",
    "Buyer's TAX ID", "Status", "Issue date", "Sale date", "Due date",
    "Seller", "VAT ID", "Street", "Postcode", "City", "Country",
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


def build_csv_bytes(rows, headers):
    if shared_generate_csv is not None:
        try:
            return shared_generate_csv(rows, headers=headers)
        except TypeError:
            if headers == INCOME_HEADERS:
                return shared_generate_csv(rows)

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def make_due(issue_date, days):
    try:
        return (datetime.strptime(issue_date, "%Y-%m-%d") + timedelta(days=days)).strftime("%Y-%m-%d")
    except ValueError:
        return ""


def detect_document_side(amount):
    if amount > 0:
        return "Income"
    return "Expenses"


st.set_page_config(page_title="TENTA TRADE", page_icon="PL", layout="wide")
st.title("PL TENTA TRADE SP. Z O.O. -> PKO Bank -> InvoiceOcean")

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
        st.sidebar.success("Loaded {0} clients from export.".format(len(uploaded_clients)))
    except Exception as exc:
        st.sidebar.error("Could not read clients export: {0}".format(exc))

with st.sidebar:
    st.divider()
    st.caption("Learning memory: {0} saved examples".format(learning_examples_count()))

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
            "Loaded {0}: {1} transactions, {2} {3} -> {4}".format(
                uploaded_file.name,
                len(transactions),
                metadata.get("currency", "?"),
                metadata.get("date_from", "?"),
                metadata.get("date_to", "?"),
            )
        )
    except Exception as exc:
        st.error("{0}: {1}".format(uploaded_file.name, exc))

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

st.subheader("Parsed transactions: {0}".format(len(transactions)))
col1, col2, col3 = st.columns(3)
col1.metric("Incoming", "+{0:,.2f}".format(sum(tx.amount for tx in transactions if tx.amount > 0)))
col2.metric("Outgoing", "{0:,.2f}".format(sum(tx.amount for tx in transactions if tx.amount < 0)))
col3.metric("Rows", len(transactions))

rows = []
for row_index, transaction in enumerate(transactions, start=1):
