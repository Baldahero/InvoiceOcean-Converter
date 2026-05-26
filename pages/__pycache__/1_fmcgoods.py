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
    st.stop()

st.subheader("Parsed transactions: {0}".format(len(transactions)))
col1, col2, col3 = st.columns(3)
col1.metric("Incoming", "+{0:,.2f}".format(sum(tx.amount for tx in transactions if tx.amount > 0)))
col2.metric("Outgoing", "{0:,.2f}".format(sum(tx.amount for tx in transactions if tx.amount < 0)))
col3.metric("Rows", len(transactions))

rows = []
for row_index, transaction in enumerate(transactions, start=1):
    matched_party = find_best_client_match(transaction.counterparty, clients, transaction.counterparty_tax_id)
    partner_name = matched_party or transaction.counterparty
    partner_client = clients.get(matched_party, {})

    fallback_number = transaction.doc_num or "ZEPT-{0}-{1:03d}".format(transaction.date.replace("-", ""), row_index)
    invoice_ref, extracted_issue_date, detected_kind = extract_invoice_ref(transaction.description, fallback_number)
    document_side = detect_document_side(transaction)

    issue_date = extracted_issue_date or transaction.date
    due_date = transaction.date if detected_kind == "Proforma Invoice" else make_due(issue_date, due_days)
    amount = abs(transaction.amount)
    amount_eur = amount if transaction.currency == "EUR" else 0.0

    if document_side == "Expenses":
        buyer_name = FMC_PROFILE["name"]
        seller_name = partner_name
    else:
        buyer_name = partner_name
        seller_name = FMC_PROFILE["name"]

    row = {
        "No.": row_index,
        "Document side": document_side,
        "No. (invoice)": invoice_ref,
        "Kind": detected_kind or default_kind,
        "Status": "Paid",
        "Issue date": issue_date,
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
        "Payment date": transaction.date,
        "Paid": amount,
        "Currency": transaction.currency,
        "PO number": invoice_ref,
        "Product / Service": transaction.description[:200],
        "Qty": 1.0,
        "Quantity unit": "pc",
        "Source bank doc": transaction.doc_num,
        "Source counterparty": transaction.counterparty,
        "Source tax ID": transaction.counterparty_tax_id,
        "Source description": transaction.description,
    }

    learned = find_learning_match(FMC_NAME, transaction.counterparty, transaction.counterparty_tax_id, transaction.description)
    if learned:
        for key, value in learned.items():
            if value not in (None, ""):
                row[key] = value

    rows.append(row)

frame = pd.DataFrame(rows)

st.subheader("Edit rows before export")
st.caption("You can change document side, invoice number, buyer, seller, dates, and delete rows directly in the table.")

edited_frame = st.data_editor(
    frame,
    use_container_width=True,
    num_rows="dynamic",
    hide_index=True,
    column_config={
        "Document side": st.column_config.SelectboxColumn("Document side", options=["Income", "Expenses"]),
        "Buyer": st.column_config.TextColumn("Buyer"),
        "Seller": st.column_config.TextColumn("Seller"),
        "Kind": st.column_config.SelectboxColumn("Kind", options=["Invoice", "Proforma Invoice", "Receipt"]),
        "Status": st.column_config.SelectboxColumn("Status", options=["Paid", "Partially paid", "Issued", "Rejected"]),
        "Currency": st.column_config.SelectboxColumn("Currency", options=["EUR", "RUB", "USD", "BYN"]),
        "Payment type": st.column_config.SelectboxColumn("Payment type", options=["Transfer", "Cash", "Card"]),
        "Quantity unit": st.column_config.SelectboxColumn("Quantity unit", options=["pc", "pcs", "case", "kg", "l"]),
    },
)

st.subheader("Export CSV for InvoiceOcean")
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

    source_tax_id = str(row.get("Source tax ID", "")).strip()
    client_key = partner_name if partner_name in clients else find_best_client_match(partner_name, clients, source_tax_id)
    partner_client = clients.get(client_key, {})
    amount = float(row.get("Total gross price", 0) or 0)
    amount_eur = float(row.get("Total gross price EUR", 0) or 0)
    invoice_no = str(row.get("No. (invoice)", "")).strip()
    po_number = str(row.get("PO number", "")).strip() or invoice_no

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
        str(row.get("Currency", "EUR")),
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
        income_rows.append([
            len(income_rows) + 1,
            invoice_no,
            str(row.get("Kind", default_kind)),
            seller_name or FMC_PROFILE["name"],
            FMC_PROFILE["name"],
            FMC_PROFILE["tax_id"],
            str(row.get("Status", "Paid")),
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
            *common_tail
        ])
    else:
        expense_rows.append([
            len(expense_rows) + 1,
            invoice_no,
            str(row.get("Kind", default_kind)),
            buyer_name or FMC_PROFILE["name"],
            FMC_PROFILE["name"],
            FMC_PROFILE["tax_id"],
            str(row.get("Status", "Paid")),
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
            *common_tail
        ])

if skipped:
    st.info("Skipped {0} rows without a filled buyer/seller.".format(skipped))

downloaded = False

if not income_rows and not expense_rows:
    st.warning("No rows are ready for export. Fill buyer/seller or add valid rows first.")
else:
    st.caption("Ready rows: Income {0} | Expenses {1}".format(len(income_rows), len(expense_rows)))

    if income_rows:
        income_name = "InvoiceOcean_FMCGOODS_Income_{0}.csv".format(datetime.now().strftime("%Y%m%d"))
        downloaded = st.download_button(
            "Download Income CSV",
            build_csv_bytes(income_rows, INCOME_HEADERS),
            income_name,
            "text/csv",
            use_container_width=True,
        ) or downloaded

    if expense_rows:
        expense_name = "InvoiceOcean_FMCGOODS_Expenses_{0}.csv".format(datetime.now().strftime("%Y%m%d"))
        downloaded = st.download_button(
            "Download Expenses CSV",
            build_csv_bytes(expense_rows, EXPENSE_HEADERS),
            expense_name,
            "text/csv",
            use_container_width=True,
        ) or downloaded

if downloaded:
    learned_count = remember_learning_rows(FMC_NAME, edited_frame.to_dict("records"))
    if learned_count:
        st.success("Learning memory updated from {0} row(s).".format(learned_count))
