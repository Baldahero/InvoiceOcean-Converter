# Bank Statement -> InvoiceOcean CSV

Streamlit app for converting bank statements into InvoiceOcean-compatible CSV.

## Supported flows

- `FMCGOODS OÜ` + `Zepter Bank` statement in `.rtf`
- `TENTA TRADE SP. Z O.O.` + `PKO Bank Polski` statement in `.pdf`
- Optional InvoiceOcean client export in `.xls`, `.xlsx`, or `.csv`

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Workflow

1. Open the company page.
2. Upload one or more bank statement files.
3. Optionally upload a fresh InvoiceOcean client export.
4. Review matched counterparties.
5. Download the generated CSV and import it into InvoiceOcean.
