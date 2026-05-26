import csv
import io
import os
import re
import sys
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.zepter_parser import parse_zepter_rtf
from utils import clients as client_utils

try:
    from utils.learning import find_learning_match, learning_examples_count, remember_learning_rows
except ImportError:
    def find_learning_match(*args, **kwargs):
        return {}

    def learning_examples_count():
        return 0

    def remember_learning_rows(*args, **kwargs):
        return 0


FMC_NAME = "FMCGOODS OÜ"
CLIENTS = client_utils.CLIENTS
SELLERS = client_utils.SELLERS
find_best_client_match = client_utils.find_best_client_match
load_clients_from_export = client_utils.load_clients_from_export
merge_clients = client_utils.merge_clients

FMC_PROFILE = SELLERS.get("FMCGOODS OÜ") or SELLERS.get("FMCGOODS OU") or {
    "name": FMC_NAME,
    "tax_id": "EE102627019",
    "currency_default": "EUR",
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

EXPENSE_HEADERS = [
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
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def make_due(date_value, days):
    try:
        return (datetime.strptime(date_value, "%Y-%m-%d") + timedelta(days=days)).strftime("%Y-%m-%d")
    except ValueError:
        return date_value


def parse_slash_date(date_text):
    try:
        return datetime.strptime(date_text, "%d/%m/%Y").strftime("%Y-%m-%d")
    except ValueError:
        return ""


def normalize_invoice_ref(value):
    cleaned = re.sub(r"\s+", " ", str(value or "")).strip(" ,.;:")
    cleaned = re.sub(r"\s+/\s+", "/", cleaned)
    return cleaned


def extract_invoice_ref(description, fallback_value):
    upper = description.upper()
    kind = "Proforma Invoice" if "PROFORMA INVOICE" in upper else "Invoice"

    match = re.search(
        r"(?:PROFORMA\s+INVOICE|INVOICE)\s*(?:NO\.?|:)\s*([^()]+?)(?:\(|CN code|$)",
        description,
        re.IGNORECASE,
    )
    invoice_ref = normalize_invoice_ref(match.group(1)) if match else fallback_value

    issue_match = re.search(r"\bDD\s*(\d{2}/\d{2}/\d{4})\b", invoice_ref, re.IGNORECASE)
    if not issue_match:
        issue_match = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", invoice_ref)

    issue_date = parse_slash_date(issue_match.group(1)) if issue_match else ""
    return invoice_ref or fallback_value, issue_date, kind


def detect_document_side(transaction):
    role = getattr(transaction, "counterparty_role", "")
    description = getattr(transaction, "description", "")
    if role == "beneficiary" or "Бенефициар:" in description:
        return "Expenses"
    if role == "payer" or "Плательщик:" in description:
        return "Income"
    return "Expenses" if transaction.amount < 0 else "Income"


st.set_page_config(page_title=FMC_NAME, page_icon="EE", layout="wide")
st.title("EE FMCGOODS OÜ -> Zepter Bank -> InvoiceOcean")

with st.sidebar:
    st.header("Settings")
    filter_type = st.selectbox("Transaction type", ["All", "Incoming only (+)", "Outgoing only (-)"])
    due_days = st.number_input("Due days", min_value=0, max_value=90, value=7)
    default_kind = st.selectbox("Default document kind", ["Invoice", "Proforma Invoice", "Receipt"])
    skip_commissions = st.checkbox("Skip bank commissions", value=True)
    skip_internal = st.checkbox("Skip internal conversion", value=True)
    clients_file = st.file_uploader("InvoiceOcean clients export", type=["xls", "xlsx", "csv"])

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
    transactions = [transaction for transaction in transactions if not transaction.is_commission]
if skip_internal:
    transactions = [transaction for transaction in transactions if not transaction.is_conversion]
if filter_type == "Incoming only (+)":
    transactions = [transaction for transaction in transactions if transaction.amount > 0]
elif filter_type == "Outgoing only (-)":
    transactions = [transaction for transaction in transactions if transaction.amount < 0]

if not transactions:
    st.warning("No transactions left after filtering.")
