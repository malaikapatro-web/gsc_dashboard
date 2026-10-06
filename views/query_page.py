import altair as alt
import pandas as pd
import streamlit as st

from db import GB_EXPR, QUERY_TABLE, SCHEMA, in_clause, materialize, run_query
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
    group_tail = st.checkbox(
        "Group queries under 10 impressions as Long-tail", value=False, key="q_tail",
        help="Same rule as the Power BI report: a query with fewer than 10 total impressions across all loaded "
             "days is shown as 'Long-tail (low volume)' (one row per bucket). Totals do not change.",
    )
    st.caption(f"Data available {min_d} to {max_d}")

if len(date_range) != 2:
    st.info("Pick an end date.")
    st.stop()
start, end = date_range


def where(params: dict, p: str = "") -> str:
    """Filter clauses; p is a table alias prefix such as 'd.' so column names never clash with SELECT aliases."""
    sql = ""
    if buckets:
        sql += " AND " + in_clause(f"{p}bucket", buckets, params, "b")
    if search:
        params["q"] = f"%{search.strip()}%"
        sql += f" AND {p}query ILIKE %(q)s"
    return sql


TAIL_LABEL = "Long-tail (low volume)"
if group_tail:
    # Same rule as the pipeline: total impressions per query over every loaded day, threshold 10.
    qvol = materialize(
        "QVOL",
        f"""SELECT query AS vq, SUM(impressions) AS total_impressions
            FROM {DETAIL_TABLE} WHERE query IS NOT NULL GROUP BY query""",
    )
    QUERY_EXPR = (f"CASE WHEN d.query IS NULL THEN '(anonymized queries)' "
                  f"WHEN v.total_impressions >= 10 THEN d.query ELSE '{TAIL_LABEL}' END")
    SOURCE = f"{DETAIL_TABLE} d LEFT JOIN {qvol} v ON d.query = v.vq"
else:
    QUERY_EXPR = "COALESCE(d.query, '(anonymized queries)')"
    SOURCE = f"{DETAIL_TABLE} d"

# Base: one row per (query, bucket). Anonymized queries (no text in GSC) are kept as one labelled row.
bp = {"s": start, "e": end}
base = materialize(
    "QBASE",
    f"""SELECT {QUERY_EXPR} AS query, d.bucket AS bucket, d.brand_non_brand AS brand_non_brand,
               SUM(d.clicks) AS clicks, SUM(d.impressions) AS impressions, SUM(d.sum_position) AS sum_position
        FROM {SOURCE}
        WHERE d.data_date BETWEEN %(s)s AND %(e)s {where(bp, "d.")}
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

# BRAND / NON-BRAND = does the search query mention TrueMeds. Generic / Branded = the medicine type of the
# page that earned the impression (from MEDICINE_MASTER); "Other pages" are URLs with no medicine match.
GB_VIEWS = {"GENERIC medicines": "GENERIC", "BRANDED medicines": "BRANDED", "OTHER pages (no medicine)": "(BLANK)"}
view = st.radio("Table", ["Query Wise Bucketing", "BRAND", "NON-BRAND", *GB_VIEWS], horizontal=True, key="q_view")
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
    if view in GB_VIEWS:
        gp = {"s": start, "e": end}
        gbase = materialize(
            "QGB",
            f"""SELECT {QUERY_EXPR} AS query, {GB_EXPR} AS gb,
                       SUM(d.clicks) AS clicks, SUM(d.impressions) AS impressions,
                       SUM(d.sum_position) AS sum_position
                FROM {SOURCE}
                WHERE d.data_date BETWEEN %(s)s AND %(e)s {where(gp, "d.")}
                GROUP BY 1, 2""",
            gp,
        )
        tbl = materialize("QGBV", f"SELECT query, clicks, impressions, sum_position FROM {gbase} "
                                  f"WHERE gb = '{GB_VIEWS[view]}'")
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
        key=f"qbr_{view}", export_name="gsc_queries_" + view.split()[0].lower(),
    )

# Trends: the daily agg table is fine unless a query search is active (it collapses low-volume queries).
dp = {"s": start, "e": end}
src = DETAIL_TABLE if search else QUERY_TABLE
daily = run_query(
    f"""SELECT data_date, brand_non_brand, {GB_EXPR} AS gb, SUM(clicks) AS clicks,
               SUM(impressions) AS impressions, SUM(sum_position) AS sp
        FROM {src}
        WHERE data_date BETWEEN %(s)s AND %(e)s {where(dp)}
        GROUP BY data_date, brand_non_brand, {GB_EXPR} ORDER BY data_date""",
    dp,
)
daily["data_date"] = pd.to_datetime(daily["data_date"])
for c in ("clicks", "impressions", "sp"):
    daily[c] = pd.to_numeric(daily[c])


def series(col, label):
    d = daily[daily[col] == label].groupby("data_date", as_index=False)[["clicks", "impressions", "sp"]].sum()
    d["avg_position"] = d["sp"] / d["impressions"].where(d["impressions"] > 0) + 1  # same formula as the tables
    return d


def trend(d, y, title, zero=True):
    chart = (
        alt.Chart(d)
        .mark_line(point=True)
        .encode(
            x=alt.X("data_date:T", title="Date"),
            y=alt.Y(f"{y}:Q", title=title, scale=alt.Scale(zero=zero)),
            tooltip=["data_date:T", alt.Tooltip(f"{y}:Q", format=",.2f" if y == "avg_position" else ",")],
        )
        .properties(height=300)
    )
    st.altair_chart(chart, use_container_width=True)


def trend_section(heading, col, left, right):
    """left/right are (value in `col`, label shown in chart titles)."""
    st.header(heading)
    for column, (value, name) in zip(st.columns(2), (left, right)):
        d = series(col, value)
        with column:
            st.subheader(f"Clicks wrt Date ({name})")
            trend(d, "clicks", "Clicks")
            st.subheader(f"Impressions wrt Date ({name})")
            trend(d, "impressions", "Impressions")
            st.subheader(f"Avg Position wrt Date ({name})")
            trend(d, "avg_position", "Avg Position", zero=False)


trend_section("Brand vs Non-Brand queries", "brand_non_brand", ("BRAND", "Branded"), ("NON-BRAND", "Non-Branded"))
trend_section("Generic vs Branded medicines", "gb", ("GENERIC", "Generic"), ("BRANDED", "Branded medicines"))
