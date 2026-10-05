import streamlit as st

from db import require_config

st.set_page_config(page_title="GSC SEO Dashboard", page_icon="🔎", layout="wide")
require_config()

pages = [
    st.Page("views/url_page.py", title="URL", icon="🔗", default=True),
    st.Page("views/query_page.py", title="Query", icon="🔎"),
]
st.navigation(pages).run()
