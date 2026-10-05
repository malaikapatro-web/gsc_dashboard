# GSC SEO Dashboard (Streamlit)

Streamlit rebuild of the "GSC SEO Dashboard" Power BI report. Reads the Google Search Console gold tables in
Snowflake (`STG_SILVER_DB.ANALYTICS`): `GSC_URL_DAILY_AGG`, `GSC_QUERY_DAILY_AGG` and `GSC_DB_TABLE`.

- **URL page**: KPIs, URL table (every URL, paged), clicks and impressions trends.
- **Query page**: Query Wise Bucketing, BRAND and NON-BRAND tables (every query, uncollapsed), branded and
  non-branded trends.
- Tables are paged server-side and can be downloaded in batches (CSV) or, up to 1M rows, as one zip.

## Run locally

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then fill in; this file is git-ignored
streamlit run app.py
```

## Deploy on Streamlit Community Cloud

1. share.streamlit.io > Create app > pick this repo, branch `main`, main file `app.py`.
2. Advanced settings: Python 3.12; paste your filled-in secrets (see `.streamlit/secrets.toml.example`) into **Secrets**.
3. After deploy, open the app's **Settings > Sharing** and restrict viewers to specific people. The data is internal.

Credentials live only in the Community Cloud Secrets box. They are never stored in this repo.

## Authentication: Snowflake key pair

The app logs in with an RSA key pair. The public key must be registered on the Snowflake user
(`ALTER USER <user> SET RSA_PUBLIC_KEY='...'`). Paste the private key (PEM text) into the app's Secrets as
`private_key` (add `private_key_passphrase` if it is encrypted). Locally you can use `private_key_path` instead.

- The key never expires on its own, so there is nothing to rotate daily.
- If you use a Snowflake network policy, Community Cloud has no fixed IPs, so the allow-list must cover it.

## Snowflake requirements

Use a dedicated service user and read-only role rather than a personal login. The role needs:

```sql
GRANT USAGE ON DATABASE STG_SILVER_DB TO ROLE GSC_DASH_RO;
GRANT USAGE ON SCHEMA STG_SILVER_DB.ANALYTICS TO ROLE GSC_DASH_RO;
GRANT SELECT ON ALL TABLES IN SCHEMA STG_SILVER_DB.ANALYTICS TO ROLE GSC_DASH_RO;
GRANT USAGE ON WAREHOUSE <warehouse> TO ROLE GSC_DASH_RO;
-- scratch schema for session-temporary tables (they vanish when the session ends)
GRANT USAGE ON DATABASE <DB> TO ROLE GSC_DASH_RO;
GRANT USAGE, CREATE TABLE ON SCHEMA <DB>.<SCHEMA> TO ROLE GSC_DASH_RO;
```

## Notes

- Free-tier apps have about 1 GB of RAM, hence the 1M-row cap on single-file downloads and the batch sizes.
- Query results are cached for 6 hours (the source refreshes daily).
