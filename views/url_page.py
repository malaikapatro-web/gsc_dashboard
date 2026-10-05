from datetime import timedelta

import altair as alt
import pandas as pd
import streamlit as st

from db import AC_EXPR, URL_TABLE, fmt_int, in_clause, materialize, pct_delta, run_query
from ui import paged_table

st.title("GSC SEO Dashboard - URL")

bounds = run_query(f"SELECT MIN(data_date) AS mn, MAX(data_date) AS mx FROM {URL_TABLE}").iloc[0]
min_d, max_d = bounds["mn"], bounds["mx"]
buckets_all = run_query(f"SELECT DISTINCT bucket FROM {URL_TABLE} ORDER BY 1")["bucket"].tolist()
ac_all = run_query(f"SELECT DISTINCT {AC_EXPR} AS ac FROM {URL_TABLE} ORDER BY 1")["ac"].tolist()

with st.sidebar:
    st.header("Filters")
    date_range = st.date_input("Date", (min_d, max_d), min_value=min_d, max_value=max_d, key="url_date")
    buckets = st.multiselect("Bucket", buckets_all, placeholder="All buckets", key="url_bucket")
    acute = st.multiselect("Acute / Chronic", ac_all, placeholder="All", key="url_ac")
    st.caption(f"Data available {min_d} to {max_d}")

if len(date_range) != 2:
    st.info("Pick an end date.")
    st.stop()
start, end = date_range
span = (end - start).days + 1
prev_start, prev_end = start - timedelta(days=span), start - timedelta(days=1)


def filters(params: dict) -> str:
    sql = ""
    if buckets:
        sql += " AND " + in_clause("bucket", buckets, params, "b")
    if acute:
        sql += " AND " + in_clause(AC_EXPR, acute, params, "a")
    return sql


# One daily query covers the KPI cards, the previous-period deltas and both trend charts.
params = {"ps": prev_start, "e": end}
daily = run_query(
    f"""SELECT data_date, SUM(clicks) AS clicks, SUM(impressions) AS impressions, SUM(sum_position) AS sp
        FROM {URL_TABLE}
        WHERE data_date BETWEEN %(ps)s AND %(e)s {filters(params)}
        GROUP BY data_date ORDER BY data_date""",
    params,
)
daily["data_date"] = pd.to_datetime(daily["data_date"])
cur = daily[(daily["data_date"].dt.date >= start)]
prv = daily[(daily["data_date"].dt.date <= prev_end)]


def totals(df):
    c, i = df["clicks"].sum(), df["impressions"].sum()
    return c, i, (c / i if i else None), (df["sp"].sum() / i + 1 if i else None)


c, i, ctr, pos = totals(cur)
pc, pi, pctr, ppos = totals(prv)


def delta(a, b):
    d = pct_delta(a, b)
    return None if d is None else f"{d:+.1%}"


k1, k2, k3, k4 = st.columns(4)
k1.metric("Clicks", fmt_int(c), delta(c, pc))
k2.metric("Impressions", fmt_int(i), delta(i, pi))
k3.metric("CTR %", "-" if ctr is None else f"{ctr:.2%}", delta(ctr, pctr))
k4.metric("Avg Position", "-" if pos is None else f"{pos:.2f}", delta(pos, ppos), delta_color="inverse")
st.caption(f"Change vs previous {span} day(s): {prev_start} to {prev_end}")

st.subheader("URL Level Data Table")
search = st.text_input("URL contains", placeholder="e.g. paracetamol", key="url_search")
tparams = {"s": start, "e": end}
extra = filters(tparams)
if search:
    tparams["q"] = f"%{search.strip()}%"
    extra += " AND url ILIKE %(q)s"
url_tbl = materialize(
    "URL",
    f"""SELECT url, bucket, SUM(clicks) AS clicks, SUM(impressions) AS impressions,
               SUM(sum_position) AS sum_position
        FROM {URL_TABLE}
        WHERE data_date BETWEEN %(s)s AND %(e)s {extra}
        GROUP BY url, bucket""",
    tparams,
)
paged_table(
    url_tbl,
    cols_sql="""url, bucket, clicks, impressions,
                DIV0NULL(clicks, impressions) AS ctr,
                DIV0NULL(sum_position, impressions) + 1 AS avg_position""",
    sort_options={
        "Clicks (high to low)": "clicks DESC",
        "Impressions (high to low)": "impressions DESC",
        "CTR (high to low)": "ctr DESC NULLS LAST",
        "Avg Position (best first)": "avg_position ASC NULLS LAST",
        "URL (A to Z)": "url ASC",
    },
    tiebreak="url",
    col_config={
        "url": st.column_config.LinkColumn("URL", width="large"),
        "bucket": "Bucket",
        "clicks": st.column_config.NumberColumn("Clicks", format="%d"),
        "impressions": st.column_config.NumberColumn("Impressions", format="%d"),
        "ctr": st.column_config.NumberColumn("CTR", format="percent"),
        "avg_position": st.column_config.NumberColumn("Avg Position", format="%.2f"),
    },
    key="url",
    export_name="gsc_urls",
    height=560,
)


def trend(df, y, title):
    chart = (
        alt.Chart(df)
        .mark_line(point=True)
        .encode(
            x=alt.X("data_date:T", title="Date"),
            y=alt.Y(f"{y}:Q", title=title),
            tooltip=["data_date:T", alt.Tooltip(f"{y}:Q", format=",")],
        )
        .properties(height=320)
    )
    st.altair_chart(chart, use_container_width=True)


st.subheader("Clicks wrt Date")
trend(cur, "clicks", "Clicks")
st.subheader("Impressions wrt Date")
trend(cur, "impressions", "Impressions")
