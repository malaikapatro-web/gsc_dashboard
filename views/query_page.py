import altair as alt
import pandas as pd
import streamlit as st

from db import QUERY_TABLE, SCHEMA, in_clause, materialize, run_query
from ui import paged_table

DETAIL_TABLE = f"{SCHEMA}.GSC_DB_TABLE"  # query-level detail: no long-tail collapsing, so no query is lost

st.title("GSC SEO Dashboard - Query")

bounds = run_query(f"SELECT MIN(data_date) AS mn, MAX(data_date) AS mx FROM {QUERY_TABLE}").iloc[0]
min_d, max_d = bounds["mn"], bounds["mx"]
buckets_all = run_query(f"SELECT DISTINCT bucket FROM {QUERY_TABLE} ORDER BY 1")["bucket"].tolist()

with st.sidebar:
    st.header("Filters")
    date_range = st.date_input("Date", (min_d, max_d), min_value=min_d, max_value=max_d, key="q_date")
    buckets = st.multiselect("Bucket", buckets_all, placeholder="All buckets", key="q_bucket")
    search = st.text_input("Query contains", placeholder="e.g. dolo 650", key="q_search")
    hide_short = st.checkbox("Hide queries shorter than 4 characters", value=False,
                             help="The original Power BI table hid these. Off here so no query is dropped.")
    st.caption(f"Data available {min_d} to {max_d}")

if len(date_range) != 2:
    st.info("Pick an end date.")
    st.stop()
start, end = date_range


def where(params: dict) -> str:
    sql = ""
    if buckets:
        sql += " AND " + in_clause("bucket", buckets, params, "b")
    if search:
        params["q"] = f"%{search.strip()}%"
        sql += " AND query ILIKE %(q)s"
    return sql


# Base: one row per (query, bucket). Anonymized queries (no text in GSC) are kept as one labelled row.
bp = {"s": start, "e": end}
base = materialize(
    "QBASE",
    f"""SELECT COALESCE(query, '(anonymized queries)') AS query, bucket, brand_non_brand,
               SUM(clicks) AS clicks, SUM(impressions) AS impressions, SUM(sum_position) AS sum_position
        FROM {DETAIL_TABLE}
        WHERE data_date BETWEEN %(s)s AND %(e)s {where(bp)}
        GROUP BY 1, 2, 3""",
    bp,
)

CFG = {
    "query": st.column_config.TextColumn("Query", width="large"),
    "bucket": "Bucket",
    "clicks": st.column_config.NumberColumn("Clicks", format="%d"),
    "impressions": st.column_config.NumberColumn("Impressions", format="%d"),
    "ctr": st.column_config.NumberColumn("CTR", format="percent"),
    "avg_position": st.column_config.NumberColumn("Avg Position", format="%.2f"),
}
SORTS = {
    "Clicks (high to low)": "clicks DESC",
    "Impressions (high to low)": "impressions DESC",
    "CTR (high to low)": "ctr DESC NULLS LAST",
    "Query (A to Z)": "query ASC",
}
SORTS_POS = {**SORTS, "Avg Position (best first)": "avg_position ASC NULLS LAST"}

view = st.radio("Table", ["Query Wise Bucketing", "BRAND", "NON-BRAND"], horizontal=True, key="q_view")
st.subheader(view)

if view == "Query Wise Bucketing":
    tbl = base
    if hide_short:
        tbl = materialize("QSHORT", f"SELECT * FROM {base} WHERE LEN(TRIM(query)) >= 4")
    paged_table(
        tbl,
        cols_sql="query, bucket, clicks, impressions, DIV0NULL(clicks, impressions) AS ctr",
        sort_options=SORTS, tiebreak="query, bucket", col_config=CFG,
        key="qb", export_name="gsc_queries_bucketing",
    )
else:
    tbl = materialize(
        "QBR",
        f"""SELECT query, SUM(clicks) AS clicks, SUM(impressions) AS impressions,
                   SUM(sum_position) AS sum_position
            FROM {base} WHERE brand_non_brand = '{view}' GROUP BY query""",
    )
    paged_table(
        tbl,
        cols_sql="""query, clicks, impressions, DIV0NULL(clicks, impressions) AS ctr,
                    DIV0NULL(sum_position, impressions) + 1 AS avg_position""",
        sort_options=SORTS_POS, tiebreak="query", col_config=CFG,
        key=f"qbr_{view}", export_name=f"gsc_queries_{view.lower()}",
    )

# Trends: the daily agg table is fine unless a query search is active (it collapses low-volume queries).
dp = {"s": start, "e": end}
src = DETAIL_TABLE if search else QUERY_TABLE
daily = run_query(
    f"""SELECT data_date, brand_non_brand, SUM(clicks) AS clicks, SUM(impressions) AS impressions
        FROM {src}
        WHERE data_date BETWEEN %(s)s AND %(e)s {where(dp)}
        GROUP BY data_date, brand_non_brand ORDER BY data_date""",
    dp,
)
daily["data_date"] = pd.to_datetime(daily["data_date"])
for c in ("clicks", "impressions"):
    daily[c] = pd.to_numeric(daily[c])


def trend(label, y, title):
    d = daily[daily["brand_non_brand"] == label]
    chart = (
        alt.Chart(d)
        .mark_line(point=True)
        .encode(
            x=alt.X("data_date:T", title="Date"),
            y=alt.Y(f"{y}:Q", title=title),
            tooltip=["data_date:T", alt.Tooltip(f"{y}:Q", format=",")],
        )
        .properties(height=300)
    )
    st.altair_chart(chart, use_container_width=True)


left, right = st.columns(2)
with left:
    st.subheader("Clicks wrt Date (Branded)")
    trend("BRAND", "clicks", "Clicks")
    st.subheader("Impressions wrt Date (Branded)")
    trend("BRAND", "impressions", "Impressions")
with right:
    st.subheader("Clicks wrt Date (Non-Branded)")
    trend("NON-BRAND", "clicks", "Clicks")
    st.subheader("Impressions wrt Date (Non-Branded)")
    trend("NON-BRAND", "impressions", "Impressions")
