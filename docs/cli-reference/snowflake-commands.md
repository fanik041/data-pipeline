# Snowflake CLI Reference — CMIA Data Pipeline
# Everything done via the Snowflake web UI in this project, expressed as CLI commands.
# DO NOT RUN THIS FILE — it is a reference document only.
# Prerequisites: pip install snowflake-cli-labs
#                or: brew install snowflake-cli
# Authenticate: snow connection add

---

## 0. Setup — Snowflake CLI connection

```bash
# Install Snowflake CLI
pip install snowflake-cli-labs

# Add connection (interactive — prompts for account, user, password)
snow connection add \
  --connection-name cmia \
  --account jdfguoa-po34021 \
  --user fsanik041 \
  --password Ottawa300208836@ \
  --database CMIA_DW \
  --warehouse CMIA_ETL_WH \
  --role ACCOUNTADMIN

# Test the connection
snow connection test --connection cmia
```

### Alternative: SnowSQL (older CLI, still widely used)
```bash
# Install
brew install snowflake-snowsql

# Connect
snowsql \
  -a jdfguoa-po34021 \
  -u fsanik041 \
  --password Ottawa300208836@ \
  -d CMIA_DW \
  -w CMIA_ETL_WH \
  -r ACCOUNTADMIN
```

---

## 1. Run DDL files via CLI

### Run all Snowflake SQL files in order (SnowSQL)
```bash
for f in $(ls db/snowflake/*.sql | sort); do
  echo "Running $f..."
  snowsql \
    -a jdfguoa-po34021 \
    -u fsanik041 \
    --password Ottawa300208836@ \
    -f "$f"
done
```

### Run a single file
```bash
snowsql \
  -a jdfguoa-po34021 \
  -u fsanik041 \
  --password Ottawa300208836@ \
  -f db/snowflake/01_setup.sql
```

### Run an inline query
```bash
snowsql \
  -a jdfguoa-po34021 \
  -u fsanik041 \
  --password Ottawa300208836@ \
  -q "SELECT COUNT(*) FROM CMIA_DW.MARTS.FACT_PRICES"
```

### Using snow CLI (newer)
```bash
snow sql \
  --connection cmia \
  --query "SELECT COUNT(*) FROM CMIA_DW.MARTS.DIM_DATE"

snow sql \
  --connection cmia \
  --filename db/snowflake/02_dimensions.sql
```

---

## 2. Warehouse management

```bash
# Create warehouses (equivalent to 01_setup.sql)
snow sql --connection cmia --query "
  CREATE WAREHOUSE IF NOT EXISTS CMIA_WH
    WAREHOUSE_SIZE = 'X-SMALL'
    AUTO_SUSPEND   = 60
    AUTO_RESUME    = TRUE
    INITIALLY_SUSPENDED = TRUE;

  CREATE WAREHOUSE IF NOT EXISTS CMIA_ETL_WH
    WAREHOUSE_SIZE = 'SMALL'
    AUTO_SUSPEND   = 120
    AUTO_RESUME    = TRUE
    INITIALLY_SUSPENDED = TRUE;
"

# Resume a suspended warehouse manually
snow sql --connection cmia --query "ALTER WAREHOUSE CMIA_WH RESUME"

# Suspend a warehouse to stop billing
snow sql --connection cmia --query "ALTER WAREHOUSE CMIA_WH SUSPEND"

# Check warehouse status
snow sql --connection cmia --query "SHOW WAREHOUSES LIKE 'CMIA%'"
```

---

## 3. Database + schema setup

```bash
# Create database (equivalent to 01_setup.sql)
snow sql --connection cmia --query "
  CREATE DATABASE IF NOT EXISTS CMIA_DW
    DATA_RETENTION_TIME_IN_DAYS = 1;
"

# Create all schemas
snow sql --connection cmia --query "
  USE DATABASE CMIA_DW;
  CREATE SCHEMA IF NOT EXISTS RAW             DATA_RETENTION_TIME_IN_DAYS = 1;
  CREATE SCHEMA IF NOT EXISTS STAGING         DATA_RETENTION_TIME_IN_DAYS = 1;
  CREATE SCHEMA IF NOT EXISTS MARTS           DATA_RETENTION_TIME_IN_DAYS = 1;
  CREATE SCHEMA IF NOT EXISTS ACCESS_CONTROL  DATA_RETENTION_TIME_IN_DAYS = 1;
  CREATE SCHEMA IF NOT EXISTS AUDIT           DATA_RETENTION_TIME_IN_DAYS = 1;
"

# List schemas
snow sql --connection cmia --query "SHOW SCHEMAS IN DATABASE CMIA_DW"
```

---

## 4. Role + grant management

```bash
# Create roles
snow sql --connection cmia --query "
  CREATE ROLE IF NOT EXISTS CMIA_ADMIN;
  CREATE ROLE IF NOT EXISTS CMIA_ANALYST;
  CREATE ROLE IF NOT EXISTS CMIA_ETL;
  CREATE ROLE IF NOT EXISTS CMIA_API;
  GRANT ROLE CMIA_ADMIN TO ROLE SYSADMIN;
"

# List roles
snow sql --connection cmia --query "SHOW ROLES LIKE 'CMIA%'"
```

---

## 5. Validation queries

```bash
# Row counts across all tables
snow sql --connection cmia --query "
  SELECT 'DIM_SECTOR'       AS tbl, COUNT(*) AS rows FROM CMIA_DW.MARTS.DIM_SECTOR    UNION ALL
  SELECT 'DIM_SYMBOL'       AS tbl, COUNT(*) AS rows FROM CMIA_DW.MARTS.DIM_SYMBOL    UNION ALL
  SELECT 'DIM_DATE'         AS tbl, COUNT(*) AS rows FROM CMIA_DW.MARTS.DIM_DATE      UNION ALL
  SELECT 'FACT_PRICES'      AS tbl, COUNT(*) AS rows FROM CMIA_DW.MARTS.FACT_PRICES   UNION ALL
  SELECT 'FACT_FEATURES'    AS tbl, COUNT(*) AS rows FROM CMIA_DW.MARTS.FACT_FEATURES UNION ALL
  SELECT 'FACT_BENCHMARKS'  AS tbl, COUNT(*) AS rows FROM CMIA_DW.MARTS.FACT_BENCHMARKS;
"

# Checksum validation — compare against Azure SQL v_sector_summary view
snow sql --connection cmia --query "
  SELECT PRICE_DATE, SECTOR_CODE, CLOSE_CHECKSUM
  FROM CMIA_DW.MARTS.V_SECTOR_DAILY_SUMMARY
  ORDER BY PRICE_DATE DESC
  LIMIT 10;
"

# Check latest features per symbol
snow sql --connection cmia --query "
  SELECT SYMBOL_CODE, PRICE_DATE, RSI_14, MACD, BB_POSITION
  FROM CMIA_DW.MARTS.V_LATEST_FEATURES
  ORDER BY SYMBOL_CODE;
"
```

---

## 6. Task management (Snowflake scheduled jobs)

```bash
# Resume the rolling returns refresh task
snow sql --connection cmia --query "
  ALTER TASK CMIA_DW.AUDIT.TASK_REFRESH_ROLLING_RETURNS RESUME;
"

# Check task status
snow sql --connection cmia --query "
  SHOW TASKS IN SCHEMA CMIA_DW.AUDIT;
"

# Run task manually (for testing)
snow sql --connection cmia --query "
  EXECUTE TASK CMIA_DW.AUDIT.TASK_REFRESH_ROLLING_RETURNS;
"

# Suspend task (stop scheduled runs)
snow sql --connection cmia --query "
  ALTER TASK CMIA_DW.AUDIT.TASK_REFRESH_ROLLING_RETURNS SUSPEND;
"
```

---

## 7. Time Travel (Snowflake-specific — good interview talking point)

```bash
# Query FACT_PRICES as it was 1 hour ago
snow sql --connection cmia --query "
  SELECT COUNT(*) FROM CMIA_DW.MARTS.FACT_PRICES
  AT (OFFSET => -3600);
"

# Restore a dropped table within retention window
snow sql --connection cmia --query "
  UNDROP TABLE CMIA_DW.MARTS.FACT_PRICES;
"
```

---

## 8. Useful diagnostics

```bash
# Check account identifier (needed for .env)
snow sql --connection cmia --query "SELECT CURRENT_ACCOUNT(), CURRENT_REGION()"

# List all tables in MARTS
snow sql --connection cmia --query "SHOW TABLES IN SCHEMA CMIA_DW.MARTS"

# Check running queries
snow sql --connection cmia --query "SELECT * FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY()) LIMIT 10"

# Check credit usage
snow sql --connection cmia --query "
  SELECT DATE_TRUNC('day', START_TIME) AS day,
         SUM(CREDITS_USED) AS credits
  FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
  WHERE START_TIME >= DATEADD('day', -7, CURRENT_DATE())
  GROUP BY 1 ORDER BY 1 DESC;
"
```
