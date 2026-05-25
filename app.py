import streamlit as st


st.set_page_config(
    page_title="Bank -> InvoiceOcean",
    page_icon="🏦",
    layout="wide",
)

st.title("🏦 Bank Statement -> InvoiceOcean CSV")
st.markdown("Convert bank statements into InvoiceOcean import files.")

st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.info("### FMCGOODS OÜ\nZepter Bank statements in RTF (EUR / RUB).")
    if st.button("Open FMCGOODS converter", use_container_width=True):
        st.switch_page("pages/1_fmcgoods.py")

with col2:
    st.info("### TENTA TRADE SP. Z O.O.\nPKO Bank Polski statements in PDF (PLN / EUR).")
    if st.button("Open TENTA TRADE converter", use_container_width=True):
        st.switch_page("pages/2_tenta.py")

st.markdown("---")
st.markdown(
    """
**How it works**

1. Choose the company.
2. Upload one or more bank statement files.
3. Optionally upload a fresh InvoiceOcean client export.
4. Review matched transactions.
5. Download the CSV and import it into InvoiceOcean.
"""
)
