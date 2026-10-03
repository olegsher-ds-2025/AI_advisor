-- Sher Stock Advisor AI - V1.0 schema (Data phase only)
-- Later phases (metrics, scores, research, watchlist) are added in their own
-- migrations once the quant/ai phases start.

CREATE TABLE IF NOT EXISTS companies (
    ticker      TEXT PRIMARY KEY,
    cik         TEXT UNIQUE,
    name        TEXT NOT NULL,
    sector      TEXT,
    industry    TEXT,
    exchange    TEXT,
    country     TEXT,
    market_cap  NUMERIC,
    active      BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS prices (
    ticker      TEXT NOT NULL REFERENCES companies(ticker),
    date        DATE NOT NULL,
    open        NUMERIC,
    high        NUMERIC,
    low         NUMERIC,
    close       NUMERIC,
    adj_close   NUMERIC,
    volume      BIGINT,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS financials (
    ticker           TEXT NOT NULL REFERENCES companies(ticker),
    period           DATE NOT NULL,       -- fiscal period end date
    period_type      TEXT NOT NULL,       -- 'Q' or 'FY'
    revenue          NUMERIC,
    gross_profit     NUMERIC,
    operating_income NUMERIC,
    net_income       NUMERIC,
    ebitda           NUMERIC,
    eps              NUMERIC,
    assets           NUMERIC,
    liabilities      NUMERIC,
    cash             NUMERIC,
    debt             NUMERIC,
    equity           NUMERIC,
    operating_cf     NUMERIC,
    capex            NUMERIC,
    free_cash_flow   NUMERIC,
    shares           NUMERIC,
    PRIMARY KEY (ticker, period, period_type)
);

CREATE INDEX IF NOT EXISTS idx_prices_date ON prices(date);
CREATE INDEX IF NOT EXISTS idx_financials_period ON financials(period);
