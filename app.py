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
    st.info("""### 🇪🇪 FMCGOODS OÜ
**Цептер Банк** — PDF или RTF (EUR / RUB)
**PKO Bank Polski** — PDF (EUR / PLN)""")
    if st.button("Открыть конвертер FMCGOODS", use_container_width=True):
        st.switch_page("pages/1_fmcgoods.py")

with col2:
    st.info("""### 🇵🇱 TENTA TRADE SP. Z O.O.
**PKO Bank Polski** — PDF (PLN / EUR)""")
    if st.button("Открыть конвертер TENTA TRADE", use_container_width=True):
        st.switch_page("pages/2_tenta.py")

st.markdown("---")
st.markdown("""
**Как пользоваться:**
1. Выберите компанию
2. Загрузите файл(ы) выписки из банка — PDF или RTF, можно несколько сразу
3. Проверьте и отредактируйте распознанные транзакции прямо в таблице
4. Выберите покупателя — адрес и VAT заполнятся автоматически
5. Нажмите «Сгенерировать CSV» → скачайте файл
6. Загрузите CSV в InvoiceOcean: **Settings → Import → New Import**
""")
