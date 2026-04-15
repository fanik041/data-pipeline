# =============================================================================
# FILE: app/db.py
# What this file does: Connection factory — returns a live DB connection for
#                      Azure SQL (pymssql) or Snowflake based on the backend param.
# Which services: Azure SQL (cmia-source-db), Snowflake (CMIA_DW)
# Tech layer: API infrastructure — all FastAPI routes call get_connection()
# Project goal: Single API hits both DBs so we can compare response times
#               pre- and post-migration (OLTP vs OLAP query performance).
# =============================================================================

import os
import time
import logging

import pymssql
import snowflake.connector
from typing import Literal
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

Backend = Literal["azure", "snowflake"]


def get_azure_connection() -> pymssql.Connection:
    """Open pymssql connection to Azure SQL using .env credentials; raises on failure."""
    return pymssql.connect(
        server=os.getenv("AZURE_SQL_SERVER"),
        user=os.getenv("AZURE_SQL_USERNAME"),
        password=os.getenv("AZURE_SQL_PASSWORD"),
        database=os.getenv("AZURE_SQL_DATABASE"),
        port=1433,
        tds_version="7.4",   # required for Azure SQL (SQL Server 2012+)
        login_timeout=30,
    )


def get_snowflake_connection() -> snowflake.connector.SnowflakeConnection:
    """Open Snowflake connection using .env credentials; raises on failure."""
    return snowflake.connector.connect(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "CMIA_ETL_WH"),
        database=os.getenv("SNOWFLAKE_DATABASE", "CMIA_DW"),
        schema="MARTS",
        role=os.getenv("SNOWFLAKE_ROLE", "CMIA_ETL"),
    )


def get_connection(backend: Backend):
    """
    Dispatch to Azure SQL or Snowflake based on backend param; logs connect latency.
    Called once per request — connection is closed after the query completes.
    """
    t0 = time.perf_counter()
    if backend == "azure":
        conn = get_azure_connection()
    else:
        conn = get_snowflake_connection()
    elapsed_ms = (time.perf_counter() - t0) * 1000
    log.info("DB connect [%s]: %.1f ms", backend, elapsed_ms)
    return conn


def is_snowflake(conn) -> bool:
    """Check if the connection is a Snowflake connection (vs pymssql)."""
    return isinstance(conn, snowflake.connector.connection.SnowflakeConnection)
