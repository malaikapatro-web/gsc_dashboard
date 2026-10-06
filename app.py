import streamlit as st

from auth import require_password
from db import require_config

st.set_page_config(page_title="GSC SEO Dashboard", page_icon="🔎", layout="wide")
require_password()  # nothing below (including any Snowflake query) runs until the password is entered
require_config()

pages = [
    st.Page("views/url_page.py", title="URL", icon="🔗", default=True),
    st.Page("views/query_page.py", title="Query", icon="🔎"),
]
st.navigation(pages).run()
