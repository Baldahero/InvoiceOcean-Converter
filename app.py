import streamlit as st

st.set_page_config(
    page_title="Bank → InvoiceOcean",
    page_icon="🏦",
    layout="wide",
)

st.title("🏦 Bank Statement → InvoiceOcean CSV")
st.markdown("Конвертер банковских выписок в формат InvoiceOcean")

st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.info("### 🇪🇪 FMCGOODS OÜ\nЦептер Банк (RTF) — EUR / RUB счета")
    if st.button("Открыть конвертер FMCGOODS", use_container_width=True):
        st.switch_page("pages/1_fmcgoods.py")

with col2:
    st.info("### 🇵🇱 TENTA TRADE SP. Z O.O.\nPKO Bank Polski (PDF) — PLN / EUR счета")
    if st.button("Открыть конвертер TENTA TRADE", use_container_width=True):
        st.switch_page("pages/2_tenta.py")

st.markdown("---")
st.markdown("""
**Как пользоваться:**
1. Выберите компанию
2. Загрузите файл выписки из банка (RTF или PDF)
3. Проверьте распознанные транзакции
4. Нажмите «Скачать CSV»
5. Загрузите CSV в InvoiceOcean: Settings → Import → New Import
""")
