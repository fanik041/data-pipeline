-- =============================================================================
-- FILE: db/azure-sql/04_rls.sql
-- Layer: Source DB — Row-Level Security
-- Connects to: rls.user_sector_access (02_tables.sql), ref.symbols,
--              market.daily_prices, market.price_features
-- Goal: Analysts can only read price data for sectors they are granted access to.
--       Admins (db_owner, cmia_admin role) bypass all filters.
-- Ref: SQL Server Row-Level Security — filter + block predicates
-- Run order: 4th — after 03_indexes.sql
--
-- HOW IT WORKS:
--   1. Predicate function returns a 1-row table if access is allowed, empty if not
--   2. SQL Server joins this as a filter on every SELECT automatically
--   3. No application code change needed — enforced at engine level
--   4. Block predicates prevent INSERT/UPDATE into rows the user can't see
-- =============================================================================


-- =============================================================================
-- Step 1: DB roles
-- cmia_admin   : full access, bypasses RLS (Mark Segal, DBAs, migration service)
-- cmia_analyst : read-only, subject to sector-based RLS
-- =============================================================================
CREATE ROLE cmia_admin;
CREATE ROLE cmia_analyst;
GO

-- Analysts can SELECT from market and ref schemas
GRANT SELECT ON SCHEMA::market TO cmia_analyst;
GRANT SELECT ON SCHEMA::ref    TO cmia_analyst;
GRANT SELECT ON SCHEMA::reports TO cmia_analyst;
GO

-- Admins get full schema access
GRANT SELECT, INSERT, UPDATE, DELETE ON SCHEMA::market  TO cmia_admin;
GRANT SELECT, INSERT, UPDATE, DELETE ON SCHEMA::ref     TO cmia_admin;
GRANT SELECT, INSERT, UPDATE, DELETE ON SCHEMA::audit   TO cmia_admin;
GRANT SELECT, INSERT, UPDATE, DELETE ON SCHEMA::rls     TO cmia_admin;
GO


-- =============================================================================
-- Step 2: Predicate function — inline TVF (table-valued function)
-- MUST be inline TVF (not scalar function) — scalar UDFs in RLS kill performance
-- because SQL Server can't push them into the query plan properly.
--
-- Logic:
--   Allow if:  user is db_owner           (full admin)
--           OR user is in cmia_admin role  (app admin)
--           OR user has an active grant for this sector_id in rls.user_sector_access
-- =============================================================================
-- NOTE: RLS predicates cannot receive subqueries as arguments — SQL Server requires
-- scalar column references only. Fix: accept symbol_id directly, resolve sector
-- inside the function via a JOIN. This is the correct pattern for indirect RLS.
CREATE OR ALTER FUNCTION rls.fn_sector_access_predicate
(
    @symbol_id INT   -- changed from @sector_id: subqueries not allowed as predicate args
)
RETURNS TABLE
WITH SCHEMABINDING   -- required for RLS predicates; prevents accidental schema changes
AS
RETURN
(
    SELECT 1 AS fn_result
    WHERE
        -- DB owner bypasses everything
        IS_MEMBER('db_owner') = 1
        OR
        -- cmia_admin role bypasses RLS (migration service account uses this role)
        IS_MEMBER('cmia_admin') = 1
        OR
        -- Analyst has an active, non-revoked grant for the sector this symbol belongs to
        EXISTS (
            SELECT 1
            FROM   rls.user_sector_access usa
            JOIN   ref.symbols            s   ON s.sector_id = usa.sector_id
            WHERE  usa.login_name  = USER_NAME()
            AND    s.symbol_id     = @symbol_id
            AND    usa.is_active   = 1
            AND    usa.revoked_at  IS NULL
        )
);
GO


-- =============================================================================
-- Step 3: Security policies
-- Filter predicate  → silently hides rows the user can't see (SELECT returns nothing)
-- Block predicate   → prevents writes to rows outside user's sector
-- STATE = ON        → policy is active immediately
-- Pass symbol_id column directly — sector resolution happens inside the function
-- =============================================================================

-- Policy on market.daily_prices
CREATE SECURITY POLICY rls.policy_daily_prices
ADD FILTER PREDICATE rls.fn_sector_access_predicate(symbol_id) ON market.daily_prices,
ADD BLOCK PREDICATE  rls.fn_sector_access_predicate(symbol_id) ON market.daily_prices AFTER INSERT
WITH (STATE = ON, SCHEMABINDING = ON);
GO

-- Policy on market.price_features
CREATE SECURITY POLICY rls.policy_price_features
ADD FILTER PREDICATE rls.fn_sector_access_predicate(symbol_id) ON market.price_features,
ADD BLOCK PREDICATE  rls.fn_sector_access_predicate(symbol_id) ON market.price_features AFTER INSERT
WITH (STATE = ON, SCHEMABINDING = ON);
GO


-- =============================================================================
-- Step 4: Seed data — sectors and demo access grants
-- =============================================================================
INSERT INTO ref.sectors (sector_name, sector_code) VALUES
('Technology',              'TECH'),
('Financial Services',      'FIN'),
('Communication Services',  'COMM'),
('Consumer Cyclical',       'CONS');
GO

-- Demo: grant tech_analyst access to Technology and Communication sectors only
INSERT INTO rls.user_sector_access (login_name, sector_id, granted_by) VALUES
('tech_analyst',  1, 'cmia_admin'),   -- Technology
('tech_analyst',  3, 'cmia_admin'),   -- Communication Services
('fin_analyst',   2, 'cmia_admin'),   -- Financial Services
('full_analyst',  1, 'cmia_admin'),   -- all sectors
('full_analyst',  2, 'cmia_admin'),
('full_analyst',  3, 'cmia_admin'),
('full_analyst',  4, 'cmia_admin');
GO


-- =============================================================================
-- HOW TO TEST RLS:
--
--   EXECUTE AS USER = 'tech_analyst';
--   SELECT symbol_code, price_date, close_price
--   FROM market.daily_prices
--   ORDER BY price_date DESC;
--   -- Should return: AAPL, MSFT, GOOGL, etc. — NOT JPM, GS, MS (those are FIN)
--
--   REVERT;  -- switch back to your own login
--
-- =============================================================================
