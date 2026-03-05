"""
Stress catalog generator.

Generates a YAML-dumpable catalog dict with n paths weighted to reflect
realistic production usage:

  oracle      60%  (heavy, complex 40-60 line SQL)
  snowflake   20%  (heavier, 60-80 line SQL with Snowflake-specific syntax)
  rest         5%
  mssql        5%
  static       4%
  excel        4%
  opensearch   2%

Paths vary in depth (2-4 segments) to exercise catalog prefix matching.

Usage:
    from tests.stress.gen_catalog import gen_stress_catalog, write_stress_catalog
    catalog = gen_stress_catalog(n=10_000)
    paths = write_stress_catalog("stress_catalog.yaml", n=10_000)
"""

from __future__ import annotations

import math
import yaml


# ── Oracle query bank (8 templates, 40-60 lines each) ──────────────────────

_ORACLE_QUERIES: list[str] = [

    # 1. CVaR tail-risk aggregation with hierarchy and PFE roll-up
    """\
WITH
  date_spine AS (
    SELECT
      TRUNC(SYSDATE) - LEVEL + 1 AS biz_date
    FROM DUAL
    CONNECT BY LEVEL <= 252
  ),
  raw_positions AS (
    SELECT
      p.port_no, p.port_type, p.ssm_id, p.base_currency,
      p.cvar_coeff, p.cvar,
      p.asof_date,
      ph.market_value, ph.delta, ph.vega,
      ROW_NUMBER() OVER (
        PARTITION BY p.port_no, p.ssm_id
        ORDER BY p.asof_date DESC
      ) AS rn
    FROM proteus_2_own.te_stress_tail_risk_pnl p
    JOIN holdings_own.position_header ph
      ON ph.port_no   = p.port_no
     AND ph.ssm_id    = p.ssm_id
     AND ph.asof_date = p.asof_date
    WHERE p.asof_date >= TRUNC(SYSDATE) - 30
      AND ('{segments[0]}' = 'ALL' OR p.port_no || '-' || p.port_type = '{segments[0]}')
      AND ('{segments[1]}' = 'ALL' OR p.base_currency = '{segments[1]}')
      AND ('{segments[2]}' = 'ALL' OR p.ssm_id = '{segments[2]}')
  ),
  latest_positions AS (
    SELECT * FROM raw_positions WHERE rn = 1
  ),
  cvar_bands AS (
    SELECT
      port_no, port_type, base_currency,
      SUM(cvar)         AS total_cvar,
      SUM(market_value) AS total_market_value,
      STDDEV(cvar)      AS cvar_stddev,
      PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY cvar) AS cvar_p99
    FROM latest_positions
    GROUP BY port_no, port_type, base_currency
  )
SELECT
  lp.asof_date, lp.port_no, lp.port_type, lp.ssm_id,
  lp.base_currency, lp.cvar_coeff, lp.cvar,
  lp.market_value, lp.delta, lp.vega,
  cb.total_cvar, cb.total_market_value, cb.cvar_stddev, cb.cvar_p99,
  lp.cvar / NULLIF(cb.total_market_value, 0) AS cvar_contribution_pct
FROM latest_positions lp
JOIN cvar_bands cb
  ON cb.port_no      = lp.port_no
 AND cb.port_type    = lp.port_type
 AND cb.base_currency = lp.base_currency
ORDER BY lp.asof_date DESC, lp.port_no, lp.ssm_id
""",

    # 2. Counterparty credit exposure with PFE, CVA and limit utilisation
    """\
WITH
  exposure_base AS (
    SELECT
      e.asof_date,
      e.counterparty_id,
      e.counterparty_name,
      e.sector,
      e.rating,
      e.country,
      e.exposure_type,
      e.notional,
      e.mark_to_market,
      e.pfe,
      e.cva,
      e.lgd,
      e.pd,
      e.expected_loss,
      e.currency,
      ROW_NUMBER() OVER (
        PARTITION BY e.counterparty_id, e.exposure_type
        ORDER BY e.asof_date DESC
      ) AS rn
    FROM credit_risk_own.credit_exposures e
    WHERE e.asof_date >= ADD_MONTHS(TRUNC(SYSDATE), -3)
      AND ('{segments[0]}' = 'ALL' OR e.counterparty_id = '{segments[0]}')
      AND ('{segments[1]}' = 'ALL' OR e.sector = '{segments[1]}')
  ),
  latest_exposure AS (
    SELECT * FROM exposure_base WHERE rn = 1
  ),
  limits AS (
    SELECT
      counterparty_id,
      limit_type,
      limit_amount,
      utilized,
      available,
      expiry_date
    FROM credit_risk_own.credit_limits
    WHERE expiry_date > SYSDATE
  ),
  combined AS (
    SELECT
      le.*,
      l.limit_type,
      l.limit_amount,
      l.utilized       AS limit_utilized,
      l.available      AS limit_available,
      CASE
        WHEN l.limit_amount > 0
        THEN ROUND(le.notional / l.limit_amount * 100, 2)
        ELSE NULL
      END AS utilization_pct
    FROM latest_exposure le
    LEFT JOIN limits l
      ON l.counterparty_id = le.counterparty_id
     AND l.limit_type = le.exposure_type
  )
SELECT
  asof_date, counterparty_id, counterparty_name,
  sector, rating, country, exposure_type, currency,
  notional, mark_to_market, pfe, cva,
  lgd, pd, expected_loss,
  limit_type, limit_amount, limit_utilized, limit_available,
  utilization_pct,
  SUM(notional)  OVER (PARTITION BY sector)  AS sector_notional_total,
  SUM(cva)       OVER (PARTITION BY country) AS country_cva_total
FROM combined
ORDER BY asof_date DESC, sector, counterparty_id
""",

    # 3. Portfolio performance attribution with Brinson factor decomposition
    """\
WITH
  bm_weights AS (
    SELECT
      bc.benchmark_id,
      bc.security_id,
      bc.weight        AS bm_weight,
      bc.sector,
      bc.country,
      bc.as_of_date
    FROM benchmark_own.benchmark_constituents bc
    WHERE bc.as_of_date = (
      SELECT MAX(as_of_date) FROM benchmark_own.benchmark_constituents
      WHERE as_of_date <= TO_DATE('{segments[1]}', 'YYYYMMDD')
    )
  ),
  port_weights AS (
    SELECT
      ph.portfolio_id,
      ph.security_id,
      ph.market_value / SUM(ph.market_value) OVER (
        PARTITION BY ph.portfolio_id, ph.as_of_date
      )                AS port_weight,
      ph.as_of_date
    FROM holdings_own.daily_positions ph
    WHERE ph.portfolio_id = '{segments[0]}'
      AND ph.as_of_date = TO_DATE('{segments[1]}', 'YYYYMMDD')
  ),
  security_returns AS (
    SELECT
      security_id,
      return_1d,
      return_mtd,
      return_ytd
    FROM prices_own.security_returns
    WHERE as_of_date = TO_DATE('{segments[1]}', 'YYYYMMDD')
  ),
  brinson AS (
    SELECT
      pw.portfolio_id,
      bw.sector,
      bw.country,
      pw.port_weight,
      bw.bm_weight,
      pw.port_weight - bw.bm_weight              AS active_weight,
      (pw.port_weight - bw.bm_weight) * sr.return_1d AS selection_effect,
      bw.bm_weight * (sr.return_1d - AVG(sr.return_1d) OVER ())
                                                  AS allocation_effect,
      pw.port_weight * sr.return_1d               AS port_contribution,
      bw.bm_weight   * sr.return_1d               AS bm_contribution
    FROM port_weights pw
    JOIN bm_weights bw   ON bw.security_id = pw.security_id
    JOIN security_returns sr ON sr.security_id = pw.security_id
  )
SELECT
  portfolio_id,
  sector, country,
  SUM(port_weight)        AS total_port_weight,
  SUM(bm_weight)          AS total_bm_weight,
  SUM(active_weight)      AS total_active_weight,
  SUM(selection_effect)   AS total_selection_effect,
  SUM(allocation_effect)  AS total_allocation_effect,
  SUM(port_contribution)  AS total_port_contribution,
  SUM(bm_contribution)    AS total_bm_contribution,
  SUM(selection_effect) + SUM(allocation_effect) AS total_active_return
FROM brinson
GROUP BY portfolio_id, sector, country
ORDER BY ABS(SUM(selection_effect) + SUM(allocation_effect)) DESC
""",

    # 4. Yield curve construction with zero rates and discount factors
    """\
WITH
  raw_bonds AS (
    SELECT
      ts.cusip, ts.tenor, ts.coupon, ts.yield,
      ts.price, ts.duration, ts.convexity,
      ts.asof_date,
      CASE ts.tenor
        WHEN '3M'  THEN  0.25
        WHEN '6M'  THEN  0.50
        WHEN '1Y'  THEN  1.00
        WHEN '2Y'  THEN  2.00
        WHEN '3Y'  THEN  3.00
        WHEN '5Y'  THEN  5.00
        WHEN '7Y'  THEN  7.00
        WHEN '10Y' THEN 10.00
        WHEN '20Y' THEN 20.00
        WHEN '30Y' THEN 30.00
        ELSE NULL
      END AS tenor_years
    FROM fixed_income_own.treasury_securities ts
    WHERE ts.asof_date = (
      SELECT MAX(asof_date) FROM fixed_income_own.treasury_securities
      WHERE asof_date <= TRUNC(SYSDATE)
    )
      AND ('{segments[0]}' = 'ALL' OR ts.tenor = '{segments[0]}')
  ),
  stripped AS (
    SELECT
      cusip, tenor, tenor_years,
      yield, coupon, price, duration, convexity, asof_date,
      EXP(- yield * tenor_years)      AS discount_factor,
      LN(1 + yield)                    AS zero_rate,
      yield - LAG(yield) OVER (ORDER BY tenor_years) AS yield_change_1t
    FROM raw_bonds
    WHERE tenor_years IS NOT NULL
  ),
  curve AS (
    SELECT
      s.*,
      yield - (
        SELECT yield FROM stripped WHERE tenor = '10Y'
      )                               AS spread_vs_10y,
      REGR_SLOPE(yield, tenor_years) OVER (
        ORDER BY tenor_years ROWS BETWEEN 2 PRECEDING AND 2 FOLLOWING
      )                               AS local_slope,
      AVG(yield) OVER (
        ORDER BY tenor_years ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING
      )                               AS smoothed_yield
    FROM stripped s
  )
SELECT
  asof_date, tenor, tenor_years,
  yield, zero_rate, coupon, price,
  duration, convexity,
  discount_factor,
  spread_vs_10y,
  local_slope,
  smoothed_yield,
  yield_change_1t
FROM curve
ORDER BY tenor_years
""",

    # 5. Intraday position P&L with Greeks and scenario shocks
    """\
WITH
  positions AS (
    SELECT
      ph.portfolio_id,
      ph.security_id,
      ph.quantity,
      ph.market_value,
      ph.cost_basis,
      ph.unrealized_pnl,
      ph.currency,
      pg.delta, pg.gamma, pg.vega, pg.theta, pg.rho,
      sm.security_type, sm.issuer_name, sm.country_code
    FROM holdings_own.daily_positions ph
    JOIN risk_own.position_greeks pg
      ON pg.portfolio_id = ph.portfolio_id
     AND pg.security_id  = ph.security_id
     AND pg.as_of_date   = ph.as_of_date
    JOIN ref_own.security_master sm
      ON sm.security_id  = ph.security_id
    WHERE ph.portfolio_id = '{segments[0]}'
      AND ph.as_of_date   = TO_DATE('{segments[1]}', 'YYYYMMDD')
  ),
  shocks AS (
    SELECT 'rates_up_100'  AS scenario, 0.01  AS rate_shock, 0.00  AS vol_shock FROM DUAL UNION ALL
    SELECT 'rates_dn_100',              -0.01,               0.00              FROM DUAL UNION ALL
    SELECT 'vol_up_25',                  0.00,               0.25              FROM DUAL UNION ALL
    SELECT 'vol_dn_25',                  0.00,              -0.25              FROM DUAL UNION ALL
    SELECT 'combined_stress',            0.02,               0.50              FROM DUAL
  ),
  scenario_pnl AS (
    SELECT
      p.portfolio_id, p.security_id, p.security_type,
      p.quantity, p.market_value, p.currency,
      s.scenario,
      p.delta * s.rate_shock * p.market_value +
      0.5 * p.gamma * POWER(s.rate_shock, 2) * p.market_value +
      p.vega  * s.vol_shock  * p.market_value AS scenario_pnl,
      p.theta * (1.0/252.0) * p.market_value  AS daily_theta_pnl
    FROM positions p
    CROSS JOIN shocks s
  )
SELECT
  portfolio_id, security_id, security_type, currency,
  quantity, market_value,
  scenario,
  ROUND(scenario_pnl, 2)    AS scenario_pnl,
  ROUND(daily_theta_pnl, 2) AS daily_theta_pnl,
  SUM(scenario_pnl) OVER (
    PARTITION BY portfolio_id, scenario
  )                          AS portfolio_scenario_total,
  RANK() OVER (
    PARTITION BY portfolio_id, scenario
    ORDER BY ABS(scenario_pnl) DESC
  )                          AS pnl_rank
FROM scenario_pnl
ORDER BY portfolio_id, scenario, ABS(scenario_pnl) DESC
""",

    # 6. VaR back-test with breach detection and traffic-light RAG
    """\
WITH
  var_history AS (
    SELECT
      vd.portfolio_id,
      vd.asof_date,
      vd.var_1d_99,
      vd.var_1d_95,
      vd.var_10d_99,
      vd.model_type,
      pp.twr_1d          AS actual_pnl_1d,
      pp.excess_return   AS excess_return,
      pp.tracking_error
    FROM risk_own.daily_var vd
    JOIN portfolios_own.portfolio_performance pp
      ON pp.portfolio_id = vd.portfolio_id
     AND pp.as_of_date   = vd.asof_date
    WHERE vd.portfolio_id = '{segments[0]}'
      AND vd.asof_date BETWEEN
          TO_DATE('{segments[1]}', 'YYYYMMDD') - 252
          AND TO_DATE('{segments[1]}', 'YYYYMMDD')
  ),
  breach_flags AS (
    SELECT
      vh.*,
      CASE WHEN actual_pnl_1d < -var_1d_99 THEN 1 ELSE 0 END AS breach_99,
      CASE WHEN actual_pnl_1d < -var_1d_95 THEN 1 ELSE 0 END AS breach_95,
      actual_pnl_1d + var_1d_99                               AS shortfall_99
    FROM var_history vh
  ),
  rolling_breaches AS (
    SELECT
      bf.*,
      SUM(breach_99) OVER (
        ORDER BY asof_date ROWS BETWEEN 249 PRECEDING AND CURRENT ROW
      ) AS breaches_1yr_99,
      SUM(breach_95) OVER (
        ORDER BY asof_date ROWS BETWEEN 249 PRECEDING AND CURRENT ROW
      ) AS breaches_1yr_95,
      AVG(actual_pnl_1d) OVER (
        ORDER BY asof_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW
      ) AS avg_pnl_10d,
      STDDEV(actual_pnl_1d) OVER (
        ORDER BY asof_date ROWS BETWEEN 249 PRECEDING AND CURRENT ROW
      ) AS realised_vol_1yr
    FROM breach_flags bf
  )
SELECT
  portfolio_id, asof_date, model_type,
  var_1d_99, var_1d_95, var_10d_99,
  actual_pnl_1d, excess_return, tracking_error,
  breach_99, breach_95, shortfall_99,
  breaches_1yr_99, breaches_1yr_95,
  avg_pnl_10d, realised_vol_1yr,
  CASE
    WHEN breaches_1yr_99 <= 4  THEN 'GREEN'
    WHEN breaches_1yr_99 <= 9  THEN 'AMBER'
    ELSE                            'RED'
  END AS traffic_light_rag
FROM rolling_breaches
ORDER BY asof_date DESC
""",

    # 7. Swap rate curve with DV01 and convexity adjustment
    """\
WITH
  sofr_base AS (
    SELECT
      asof_date,
      rate_type,
      rate AS sofr_rate,
      LAG(rate) OVER (PARTITION BY rate_type ORDER BY asof_date) AS prev_rate
    FROM rates_own.sofr_rates
    WHERE asof_date >= TRUNC(SYSDATE) - 90
      AND ('{segments[0]}' = 'ALL' OR rate_type = '{segments[0]}')
  ),
  swap_rates AS (
    SELECT
      sr.asof_date, sr.currency, sr.tenor,
      sr.par_rate, sr.spread_vs_govt, sr.dv01,
      CASE sr.tenor
        WHEN '1Y'  THEN  1 WHEN '2Y'  THEN  2 WHEN '3Y'  THEN  3
        WHEN '5Y'  THEN  5 WHEN '7Y'  THEN  7 WHEN '10Y' THEN 10
        WHEN '15Y' THEN 15 WHEN '20Y' THEN 20 WHEN '30Y' THEN 30
        ELSE NULL
      END AS tenor_years
    FROM rates_own.swap_rates sr
    WHERE sr.asof_date = (
      SELECT MAX(asof_date) FROM rates_own.swap_rates
      WHERE asof_date <= TRUNC(SYSDATE)
        AND currency = CASE WHEN '{segments[0]}' = 'ALL' THEN currency ELSE '{segments[0]}' END
    )
      AND ('{segments[0]}' = 'ALL' OR sr.currency = '{segments[0]}')
      AND ('{segments[1]}' = 'ALL' OR sr.tenor    = '{segments[1]}')
  ),
  enriched AS (
    SELECT
      sw.*,
      sb.sofr_rate,
      sw.par_rate - sb.sofr_rate                           AS swap_sofr_spread,
      sw.dv01 * 10000                                      AS pv01_per_100k,
      0.5 * POWER(sw.dv01, 2) / NULLIF(sw.par_rate, 0)    AS approx_convexity,
      sw.par_rate - LAG(sw.par_rate) OVER (
        PARTITION BY sw.currency ORDER BY sw.tenor_years
      )                                                     AS tenor_roll_change
    FROM swap_rates sw
    LEFT JOIN sofr_base sb
      ON sb.asof_date = sw.asof_date
     AND sb.rate_type = 'ON'
  )
SELECT
  asof_date, currency, tenor, tenor_years,
  par_rate, spread_vs_govt, dv01,
  sofr_rate, swap_sofr_spread,
  pv01_per_100k, approx_convexity,
  tenor_roll_change,
  AVG(par_rate) OVER (PARTITION BY currency)                  AS curve_avg_rate,
  par_rate - AVG(par_rate) OVER (PARTITION BY currency)       AS spread_vs_avg
FROM enriched
ORDER BY currency, tenor_years
""",

    # 8. Regulatory capital charge with SA-CCR netting and CCP adjustment
    """\
WITH
  netting_sets AS (
    SELECT
      e.counterparty_id,
      e.counterparty_name,
      e.netting_set_id,
      e.exposure_type,
      e.notional,
      e.mark_to_market,
      e.pfe,
      e.maturity_date,
      e.asset_class,
      GREATEST(e.mark_to_market, 0)                      AS rc_floored,
      e.pfe * DECODE(e.exposure_type,
        'CCP_CLEARED', 0.02,
        'BILATERAL',   1.00,
                       0.50)                              AS adjusted_pfe
    FROM credit_risk_own.credit_exposures e
    WHERE e.asof_date = (
      SELECT MAX(asof_date) FROM credit_risk_own.credit_exposures
      WHERE asof_date <= TRUNC(SYSDATE)
    )
      AND ('{segments[0]}' = 'ALL' OR e.counterparty_id = '{segments[0]}')
  ),
  ead_calc AS (
    SELECT
      ns.*,
      ns.rc_floored + ns.adjusted_pfe                    AS ead,
      (ns.rc_floored + ns.adjusted_pfe) * 1.4            AS ead_alpha_adj,
      DECODE(ns.asset_class,
        'IR',         0.005,
        'FX',         0.040,
        'EQUITY',     0.320,
        'COMMODITY',  0.400,
        'CREDIT',     0.500,
                      0.050)                              AS supervisory_factor
    FROM netting_sets ns
  ),
  capital AS (
    SELECT
      counterparty_id, counterparty_name,
      netting_set_id, asset_class,
      SUM(notional)       AS total_notional,
      SUM(mark_to_market) AS total_mtm,
      SUM(ead)            AS total_ead,
      SUM(ead_alpha_adj)  AS total_ead_alpha,
      AVG(supervisory_factor) AS avg_sf,
      SUM(ead_alpha_adj * supervisory_factor) * 0.08 AS rwa_capital_charge
    FROM ead_calc
    GROUP BY counterparty_id, counterparty_name, netting_set_id, asset_class
  )
SELECT
  counterparty_id, counterparty_name,
  netting_set_id, asset_class,
  total_notional, total_mtm, total_ead, total_ead_alpha,
  avg_sf, rwa_capital_charge,
  rwa_capital_charge / NULLIF(total_notional, 0) * 100 AS capital_pct_of_notional,
  SUM(rwa_capital_charge) OVER (PARTITION BY counterparty_id) AS counterparty_total_rwa,
  RANK() OVER (ORDER BY rwa_capital_charge DESC)               AS rwa_rank
FROM capital
ORDER BY rwa_capital_charge DESC
""",
]


# ── Snowflake query bank (8 templates, 60-80 lines each) ───────────────────

_SNOWFLAKE_QUERIES: list[str] = [

    # 1. Portfolio factor attribution with Qualify and lateral flatten
    """\
WITH
  factor_exposures AS (
    SELECT
      fe.portfolio_id,
      fe.as_of_date,
      fe.factor_name,
      fe.exposure,
      fe.t_stat,
      fe.r_squared,
      fe.residual_return
    FROM ANALYTICS.FACTOR_MODEL.FACTOR_EXPOSURES fe
    WHERE fe.portfolio_id = '{segments[0]}'
      AND fe.as_of_date BETWEEN
            TO_DATE('{segments[1]}', 'YYYYMMDD') - 90
            AND TO_DATE('{segments[1]}', 'YYYYMMDD')
  ),
  factor_returns AS (
    SELECT
      fr.as_of_date,
      fr.factor_name,
      fr.return_1d,
      fr.return_mtd,
      fr.return_ytd,
      fr.volatility_30d
    FROM ANALYTICS.FACTOR_MODEL.FACTOR_RETURNS fr
  ),
  attribution_raw AS (
    SELECT
      fe.portfolio_id,
      fe.as_of_date,
      fe.factor_name,
      fe.exposure,
      fe.t_stat,
      fe.r_squared,
      fr.return_1d   AS factor_return_1d,
      fr.volatility_30d,
      fe.exposure * fr.return_1d              AS attributed_return_1d,
      fe.exposure * fr.volatility_30d         AS factor_risk_contribution,
      fe.residual_return
    FROM factor_exposures fe
    JOIN factor_returns fr
      ON fr.as_of_date  = fe.as_of_date
     AND fr.factor_name = fe.factor_name
  ),
  cumulative_attribution AS (
    SELECT
      *,
      SUM(attributed_return_1d) OVER (
        PARTITION BY portfolio_id, factor_name
        ORDER BY as_of_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
      )                                       AS cum_attributed_return,
      SUM(factor_risk_contribution) OVER (
        PARTITION BY portfolio_id
        ORDER BY as_of_date
        ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
      )                                       AS rolling_30d_risk,
      AVG(attributed_return_1d) OVER (
        PARTITION BY portfolio_id, factor_name
        ORDER BY as_of_date
        ROWS BETWEEN 59 PRECEDING AND CURRENT ROW
      )                                       AS rolling_60d_avg_attribution
    FROM attribution_raw
  ),
  ranked AS (
    SELECT
      *,
      RANK() OVER (
        PARTITION BY portfolio_id, as_of_date
        ORDER BY ABS(attributed_return_1d) DESC
      )                                       AS attribution_rank,
      RATIO_TO_REPORT(ABS(factor_risk_contribution)) OVER (
        PARTITION BY portfolio_id, as_of_date
      )                                       AS risk_share
    FROM cumulative_attribution
  )
SELECT
  portfolio_id, as_of_date, factor_name,
  exposure, t_stat, r_squared,
  factor_return_1d, volatility_30d,
  attributed_return_1d, factor_risk_contribution,
  cum_attributed_return, rolling_30d_risk,
  rolling_60d_avg_attribution, attribution_rank, risk_share,
  residual_return,
  SUM(attributed_return_1d + residual_return) OVER (
    PARTITION BY portfolio_id, as_of_date
  )                                           AS total_portfolio_return
FROM ranked
QUALIFY attribution_rank <= 20
ORDER BY as_of_date DESC, attribution_rank
""",

    # 2. Benchmark constituent ASOF join and weight drift tracking
    """\
WITH
  date_spine AS (
    SELECT DATEADD('day', SEQ4(), TO_DATE('{segments[1]}', 'YYYYMMDD') - 90) AS dt
    FROM TABLE(GENERATOR(ROWCOUNT => 91))
  ),
  constituents AS (
    SELECT
      bc.benchmark_id,
      bc.security_id,
      bc.weight,
      bc.sector,
      bc.country,
      bc.as_of_date,
      bc.duration_contribution,
      bc.spread_contribution,
      bc.yield_contribution
    FROM BENCHMARKS.CONSTITUENTS.BENCHMARK_CONSTITUENTS bc
    WHERE bc.benchmark_id = '{segments[0]}'
      AND bc.as_of_date BETWEEN
            TO_DATE('{segments[1]}', 'YYYYMMDD') - 90
            AND TO_DATE('{segments[1]}', 'YYYYMMDD')
  ),
  security_meta AS (
    SELECT DISTINCT
      sm.security_id,
      sm.ticker,
      sm.issuer_name,
      sm.security_type,
      sm.currency,
      sm.rating_sp,
      sm.rating_mdy
    FROM REFERENCE.INSTRUMENTS.SECURITY_MASTER sm
  ),
  joined AS (
    SELECT
      c.*,
      sm.ticker, sm.issuer_name, sm.security_type,
      sm.currency, sm.rating_sp, sm.rating_mdy,
      c.weight - LAG(c.weight) OVER (
        PARTITION BY c.benchmark_id, c.security_id
        ORDER BY c.as_of_date
      )                                           AS weight_delta_1d,
      c.weight - FIRST_VALUE(c.weight) OVER (
        PARTITION BY c.benchmark_id, c.security_id
        ORDER BY c.as_of_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
      )                                           AS weight_drift_since_start,
      AVG(c.weight) OVER (
        PARTITION BY c.benchmark_id, c.security_id
        ORDER BY c.as_of_date
        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
      )                                           AS avg_weight_20d,
      STDDEV(c.weight) OVER (
        PARTITION BY c.benchmark_id, c.security_id
        ORDER BY c.as_of_date
        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
      )                                           AS weight_vol_20d,
      SUM(c.weight) OVER (
        PARTITION BY c.benchmark_id, c.sector, c.as_of_date
      )                                           AS sector_weight_total,
      ZEROIFNULL(c.duration_contribution) +
      ZEROIFNULL(c.spread_contribution)           AS total_risk_contribution
    FROM constituents c
    LEFT JOIN security_meta sm ON sm.security_id = c.security_id
  ),
  final AS (
    SELECT
      *,
      IFF(ABS(weight_delta_1d) > 0.005, TRUE, FALSE) AS significant_rebalance,
      NTILE(10) OVER (
        PARTITION BY benchmark_id, as_of_date
        ORDER BY weight DESC
      )                                               AS weight_decile
    FROM joined
  )
SELECT
  benchmark_id, as_of_date, security_id, ticker,
  issuer_name, security_type, sector, country,
  currency, rating_sp, rating_mdy,
  weight, weight_delta_1d, weight_drift_since_start,
  avg_weight_20d, weight_vol_20d,
  duration_contribution, spread_contribution,
  yield_contribution, total_risk_contribution,
  sector_weight_total, significant_rebalance, weight_decile
FROM final
ORDER BY as_of_date DESC, weight DESC
""",

    # 3. Rates curve volatility surface and term structure
    """\
WITH
  raw_sofr AS (
    SELECT
      asof_date,
      rate_type,
      rate,
      LAG(rate, 1)  OVER (PARTITION BY rate_type ORDER BY asof_date) AS rate_prev_1d,
      LAG(rate, 5)  OVER (PARTITION BY rate_type ORDER BY asof_date) AS rate_prev_5d,
      LAG(rate, 21) OVER (PARTITION BY rate_type ORDER BY asof_date) AS rate_prev_21d
    FROM RATES.BENCHMARKS.SOFR_RATES
    WHERE asof_date >= DATEADD('day', -252, CURRENT_DATE())
      AND ('{segments[0]}' = 'ALL' OR rate_type = '{segments[0]}')
  ),
  changes AS (
    SELECT
      *,
      rate - rate_prev_1d                        AS chg_1d,
      rate - rate_prev_5d                        AS chg_5d,
      rate - rate_prev_21d                       AS chg_21d,
      LN(rate / NULLIF(rate_prev_1d, 0)) * 10000 AS log_chg_1d_bps
    FROM raw_sofr
    WHERE rate_prev_1d IS NOT NULL
  ),
  vol_surface AS (
    SELECT
      *,
      STDDEV(chg_1d) OVER (
        PARTITION BY rate_type
        ORDER BY asof_date
        ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
      ) * SQRT(252) * 10000                      AS ann_vol_5d_bps,
      STDDEV(chg_1d) OVER (
        PARTITION BY rate_type
        ORDER BY asof_date
        ROWS BETWEEN 20 PRECEDING AND CURRENT ROW
      ) * SQRT(252) * 10000                      AS ann_vol_21d_bps,
      STDDEV(chg_1d) OVER (
        PARTITION BY rate_type
        ORDER BY asof_date
        ROWS BETWEEN 62 PRECEDING AND CURRENT ROW
      ) * SQRT(252) * 10000                      AS ann_vol_63d_bps,
      AVG(rate) OVER (
        PARTITION BY rate_type
        ORDER BY asof_date
        ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
      )                                          AS avg_rate_5d,
      AVG(rate) OVER (
        PARTITION BY rate_type
        ORDER BY asof_date
        ROWS BETWEEN 20 PRECEDING AND CURRENT ROW
      )                                          AS avg_rate_21d,
      PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY rate)
        OVER (PARTITION BY rate_type)            AS rate_p5,
      PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY rate)
        OVER (PARTITION BY rate_type)            AS rate_p95
    FROM changes
  ),
  z_scores AS (
    SELECT
      *,
      (rate - avg_rate_21d) / NULLIF(ann_vol_21d_bps / SQRT(252) / 10000, 0)
                                                  AS z_score_21d,
      IFF(ann_vol_5d_bps > ann_vol_21d_bps, 'ELEVATED', 'NORMAL')
                                                  AS vol_regime
    FROM vol_surface
  )
SELECT
  asof_date, rate_type, rate,
  chg_1d, chg_5d, chg_21d, log_chg_1d_bps,
  ann_vol_5d_bps, ann_vol_21d_bps, ann_vol_63d_bps,
  avg_rate_5d, avg_rate_21d,
  rate_p5, rate_p95,
  z_score_21d, vol_regime
FROM z_scores
ORDER BY asof_date DESC, rate_type
""",

    # 4. NAV reconciliation with fund-of-fund rollup
    """\
WITH
  fund_hierarchy AS (
    SELECT
      f.fund_id,
      f.fund_name,
      f.parent_fund_id,
      f.fund_type,
      f.currency,
      f.inception_date,
      CONNECT_BY_ISLEAF                                AS is_leaf,
      LEVEL                                            AS hierarchy_depth,
      SYS_CONNECT_BY_PATH(f.fund_id, ' > ')           AS fund_path
    FROM fund_master_own.funds f
    START WITH f.parent_fund_id IS NULL
    CONNECT BY PRIOR f.fund_id = f.parent_fund_id
  ),
  official_nav AS (
    SELECT
      on2.fund_id,
      on2.as_of_date,
      on2.nav_per_share,
      on2.total_nav,
      on2.shares_outstanding,
      LAG(on2.total_nav) OVER (
        PARTITION BY on2.fund_id ORDER BY on2.as_of_date
      )                                               AS prev_total_nav,
      LAG(on2.nav_per_share) OVER (
        PARTITION BY on2.fund_id ORDER BY on2.as_of_date
      )                                               AS prev_nav_per_share
    FROM nav_own.official_nav on2
    WHERE on2.as_of_date >= TRUNC(SYSDATE) - 30
      AND ('{segments[0]}' = 'ALL' OR on2.fund_id = '{segments[0]}')
  ),
  nav_returns AS (
    SELECT
      on2.*,
      on2.total_nav - on2.prev_total_nav              AS nav_change_1d,
      (on2.total_nav - on2.prev_total_nav)
        / NULLIF(on2.prev_total_nav, 0)               AS nav_return_1d,
      (on2.nav_per_share - on2.prev_nav_per_share)
        / NULLIF(on2.prev_nav_per_share, 0)           AS per_share_return_1d,
      AVG((on2.total_nav - on2.prev_total_nav)
        / NULLIF(on2.prev_total_nav, 0)) OVER (
        PARTITION BY on2.fund_id
        ORDER BY on2.as_of_date
        ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
      )                                               AS avg_return_5d
    FROM official_nav on2
    WHERE on2.prev_total_nav IS NOT NULL
  )
SELECT
  nr.fund_id, nr.as_of_date,
  fh.fund_name, fh.fund_type, fh.currency,
  fh.hierarchy_depth, fh.fund_path, fh.is_leaf,
  nr.nav_per_share, nr.total_nav, nr.shares_outstanding,
  nr.nav_change_1d, nr.nav_return_1d, nr.per_share_return_1d,
  nr.avg_return_5d,
  SUM(nr.total_nav) OVER (
    PARTITION BY fh.parent_fund_id, nr.as_of_date
  )                                                   AS parent_aum,
  nr.total_nav / NULLIF(
    SUM(nr.total_nav) OVER (PARTITION BY nr.as_of_date), 0
  ) * 100                                             AS pct_of_total_aum
FROM nav_returns nr
JOIN fund_hierarchy fh ON fh.fund_id = nr.fund_id
ORDER BY nr.as_of_date DESC, nr.total_nav DESC
""",

    # 5. Equity price momentum and mean-reversion signal construction
    """\
WITH
  price_history AS (
    SELECT
      symbol,
      trade_date,
      open_price, high_price, low_price, close_price,
      volume, vwap,
      close_price - LAG(close_price, 1)  OVER (PARTITION BY symbol ORDER BY trade_date)
                                                            AS chg_1d,
      close_price - LAG(close_price, 5)  OVER (PARTITION BY symbol ORDER BY trade_date)
                                                            AS chg_5d,
      close_price - LAG(close_price, 21) OVER (PARTITION BY symbol ORDER BY trade_date)
                                                            AS chg_21d,
      close_price - LAG(close_price, 63) OVER (PARTITION BY symbol ORDER BY trade_date)
                                                            AS chg_63d
    FROM PRICES.EQUITY.EQUITY_EOD
    WHERE trade_date >= DATEADD('day', -252, CURRENT_DATE())
      AND ('{segments[0]}' = 'ALL' OR symbol = '{segments[0]}')
  ),
  tech_indicators AS (
    SELECT
      *,
      AVG(close_price) OVER (
        PARTITION BY symbol ORDER BY trade_date
        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
      )                                                     AS sma_20,
      AVG(close_price) OVER (
        PARTITION BY symbol ORDER BY trade_date
        ROWS BETWEEN 49 PRECEDING AND CURRENT ROW
      )                                                     AS sma_50,
      AVG(close_price) OVER (
        PARTITION BY symbol ORDER BY trade_date
        ROWS BETWEEN 199 PRECEDING AND CURRENT ROW
      )                                                     AS sma_200,
      STDDEV(chg_1d) OVER (
        PARTITION BY symbol ORDER BY trade_date
        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
      ) * SQRT(252)                                         AS ann_vol_20d,
      STDDEV(chg_1d) OVER (
        PARTITION BY symbol ORDER BY trade_date
        ROWS BETWEEN 62 PRECEDING AND CURRENT ROW
      ) * SQRT(252)                                         AS ann_vol_63d,
      MAX(close_price) OVER (
        PARTITION BY symbol ORDER BY trade_date
        ROWS BETWEEN 51 PRECEDING AND CURRENT ROW
      )                                                     AS high_52w,
      MIN(close_price) OVER (
        PARTITION BY symbol ORDER BY trade_date
        ROWS BETWEEN 251 PRECEDING AND CURRENT ROW
      )                                                     AS low_52w,
      AVG(volume) OVER (
        PARTITION BY symbol ORDER BY trade_date
        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
      )                                                     AS avg_volume_20d
    FROM price_history
    WHERE chg_1d IS NOT NULL
  ),
  signals AS (
    SELECT
      *,
      close_price / NULLIF(sma_20,  0) - 1                 AS pct_above_sma20,
      close_price / NULLIF(sma_50,  0) - 1                 AS pct_above_sma50,
      close_price / NULLIF(sma_200, 0) - 1                 AS pct_above_sma200,
      (close_price - low_52w) / NULLIF(high_52w - low_52w, 0)
                                                            AS position_in_52w_range,
      volume / NULLIF(avg_volume_20d, 0)                    AS volume_ratio,
      IFF(sma_20 > sma_50, 'BULLISH', 'BEARISH')           AS trend_signal,
      chg_21d / NULLIF(ann_vol_20d / SQRT(252) * 21, 0)    AS momentum_z_21d
    FROM tech_indicators
  )
SELECT
  symbol, trade_date,
  open_price, high_price, low_price, close_price, vwap,
  volume, avg_volume_20d, volume_ratio,
  chg_1d, chg_5d, chg_21d, chg_63d,
  sma_20, sma_50, sma_200,
  ann_vol_20d, ann_vol_63d,
  high_52w, low_52w, position_in_52w_range,
  pct_above_sma20, pct_above_sma50, pct_above_sma200,
  trend_signal, momentum_z_21d
FROM signals
QUALIFY ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY trade_date DESC) = 1
ORDER BY momentum_z_21d DESC NULLS LAST
""",

    # 6. Cross-asset risk aggregation with FX translation
    """\
WITH
  fx_rates AS (
    SELECT
      from_currency, to_currency,
      rate AS fx_rate,
      1.0 / rate AS inverse_rate
    FROM PRICES.FX.FX_RATES_EOD
    WHERE as_of_date = (SELECT MAX(as_of_date) FROM PRICES.FX.FX_RATES_EOD)
      AND to_currency = 'USD'
  ),
  positions AS (
    SELECT
      dp.portfolio_id, dp.security_id,
      dp.quantity, dp.market_value, dp.currency,
      dp.cost_basis, dp.unrealized_pnl,
      sm.security_type, sm.asset_class, sm.sector, sm.country_code,
      sm.rating_sp,
      COALESCE(fx.fx_rate, 1.0) AS fx_to_usd
    FROM PORTFOLIOS.HOLDINGS.DAILY_POSITIONS dp
    JOIN REFERENCE.INSTRUMENTS.SECURITY_MASTER sm
      ON sm.security_id = dp.security_id
    LEFT JOIN fx_rates fx
      ON fx.from_currency = dp.currency
    WHERE dp.portfolio_id = '{segments[0]}'
      AND dp.as_of_date   = TO_DATE('{segments[1]}', 'YYYYMMDD')
  ),
  usd_positions AS (
    SELECT
      *,
      market_value * fx_to_usd     AS market_value_usd,
      unrealized_pnl * fx_to_usd   AS unrealized_pnl_usd,
      cost_basis * fx_to_usd       AS cost_basis_usd
    FROM positions
  ),
  risk_metrics AS (
    SELECT
      up.*,
      SUM(market_value_usd) OVER (PARTITION BY portfolio_id) AS total_aum_usd,
      market_value_usd / NULLIF(
        SUM(market_value_usd) OVER (PARTITION BY portfolio_id), 0
      )                                                        AS weight,
      SUM(market_value_usd) OVER (
        PARTITION BY portfolio_id, asset_class
      )                                                        AS asset_class_total_usd,
      SUM(market_value_usd) OVER (
        PARTITION BY portfolio_id, sector
      )                                                        AS sector_total_usd,
      SUM(market_value_usd) OVER (
        PARTITION BY portfolio_id, country_code
      )                                                        AS country_total_usd,
      NTILE(5) OVER (
        PARTITION BY portfolio_id
        ORDER BY market_value_usd DESC
      )                                                        AS concentration_quintile
    FROM usd_positions
  )
SELECT
  portfolio_id, security_id, security_type, asset_class,
  sector, country_code, currency, rating_sp, fx_to_usd,
  quantity, market_value, market_value_usd,
  cost_basis_usd, unrealized_pnl_usd,
  weight, total_aum_usd,
  asset_class_total_usd / NULLIF(total_aum_usd, 0) * 100 AS asset_class_pct,
  sector_total_usd      / NULLIF(total_aum_usd, 0) * 100 AS sector_pct,
  country_total_usd     / NULLIF(total_aum_usd, 0) * 100 AS country_pct,
  concentration_quintile
FROM risk_metrics
ORDER BY market_value_usd DESC
""",

    # 7. Fund flow attribution with cohort analysis and investor segmentation
    """\
WITH
  subscription_history AS (
    SELECT
      fund_id, trade_date, settle_date,
      amount, shares, investor_type,
      'SUB' AS flow_type,
      amount                          AS inflow,
      0                               AS outflow
    FROM FLOWS.TRANSACTIONS.SUBSCRIPTIONS
    WHERE fund_id = '{segments[0]}'
      AND trade_date BETWEEN
            TO_DATE('{segments[1]}', 'YYYYMMDD') - 90
            AND TO_DATE('{segments[1]}', 'YYYYMMDD')
    UNION ALL
    SELECT
      fund_id, trade_date, settle_date,
      amount, shares, investor_type,
      'RED',
      0,
      amount
    FROM FLOWS.TRANSACTIONS.REDEMPTIONS
    WHERE fund_id = '{segments[0]}'
      AND trade_date BETWEEN
            TO_DATE('{segments[1]}', 'YYYYMMDD') - 90
            AND TO_DATE('{segments[1]}', 'YYYYMMDD')
  ),
  daily_flows AS (
    SELECT
      fund_id, trade_date, investor_type, flow_type,
      SUM(inflow)  AS daily_inflow,
      SUM(outflow) AS daily_outflow,
      SUM(inflow) - SUM(outflow) AS net_flow,
      SUM(shares)  AS flow_shares,
      COUNT(*)     AS trade_count
    FROM subscription_history
    GROUP BY fund_id, trade_date, investor_type, flow_type
  ),
  rolling_flows AS (
    SELECT
      *,
      SUM(net_flow) OVER (
        PARTITION BY fund_id, investor_type
        ORDER BY trade_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
      )                                           AS net_flow_7d,
      SUM(net_flow) OVER (
        PARTITION BY fund_id, investor_type
        ORDER BY trade_date
        ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
      )                                           AS net_flow_30d,
      SUM(daily_inflow) OVER (
        PARTITION BY fund_id
        ORDER BY trade_date
        ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
      )                                           AS total_inflow_30d,
      SUM(daily_outflow) OVER (
        PARTITION BY fund_id
        ORDER BY trade_date
        ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
      )                                           AS total_outflow_30d,
      AVG(net_flow) OVER (
        PARTITION BY fund_id, investor_type
        ORDER BY trade_date
        ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
      )                                           AS avg_daily_net_flow_30d,
      RATIO_TO_REPORT(ABS(net_flow)) OVER (
        PARTITION BY fund_id, trade_date
      )                                           AS flow_share_of_daily_total
    FROM daily_flows
  )
SELECT
  fund_id, trade_date, investor_type, flow_type,
  daily_inflow, daily_outflow, net_flow, flow_shares, trade_count,
  net_flow_7d, net_flow_30d,
  total_inflow_30d, total_outflow_30d,
  total_inflow_30d - total_outflow_30d            AS net_flow_30d_total,
  avg_daily_net_flow_30d, flow_share_of_daily_total,
  IFF(net_flow_30d < 0, 'OUTFLOW_TREND', 'INFLOW_TREND') AS flow_trend_label
FROM rolling_flows
ORDER BY trade_date DESC, investor_type, flow_type
""",

    # 8. Credit migration matrix with Markov transition probabilities
    """\
WITH
  rating_history AS (
    SELECT
      cr.counterparty_id,
      cr.rating_date,
      cr.rating_agency,
      cr.rating,
      cr.rating_action,
      CASE cr.rating
        WHEN 'AAA' THEN 1 WHEN 'AA+' THEN 2 WHEN 'AA'  THEN 3 WHEN 'AA-' THEN 4
        WHEN 'A+'  THEN 5 WHEN 'A'   THEN 6 WHEN 'A-'  THEN 7
        WHEN 'BBB+'THEN 8 WHEN 'BBB' THEN 9 WHEN 'BBB-'THEN 10
        WHEN 'BB+' THEN 11WHEN 'BB'  THEN 12WHEN 'BB-' THEN 13
        WHEN 'B+'  THEN 14WHEN 'B'   THEN 15WHEN 'B-'  THEN 16
        WHEN 'CCC' THEN 17WHEN 'D'   THEN 18
        ELSE 99
      END                                               AS rating_numeric,
      LEAD(cr.rating) OVER (
        PARTITION BY cr.counterparty_id, cr.rating_agency
        ORDER BY cr.rating_date
      )                                                 AS next_rating,
      LEAD(cr.rating_date) OVER (
        PARTITION BY cr.counterparty_id, cr.rating_agency
        ORDER BY cr.rating_date
      )                                                 AS next_rating_date
    FROM credit_risk_own.counterparty_ratings cr
    WHERE ('{segments[0]}' = 'ALL' OR cr.counterparty_id = '{segments[0]}')
      AND cr.rating_date >= TRUNC(SYSDATE) - 365 * 5
      AND cr.rating_agency = CASE
            WHEN '{segments[1]}' = 'ALL' THEN cr.rating_agency
            ELSE '{segments[1]}'
          END
  ),
  transitions AS (
    SELECT
      rh.*,
      CASE
        WHEN next_rating IS NULL             THEN 'WITHDRAWN'
        WHEN next_rating = rating            THEN 'STABLE'
        WHEN rating_numeric < CASE next_rating
               WHEN 'AAA' THEN 1 WHEN 'AA+' THEN 2 WHEN 'AA' THEN 3
               ELSE 99 END                   THEN 'DOWNGRADE'
        ELSE                                      'UPGRADE'
      END                                        AS transition_type,
      MONTHS_BETWEEN(next_rating_date, rating_date) AS months_in_rating
    FROM rating_history
    WHERE next_rating IS NOT NULL
  ),
  migration_matrix AS (
    SELECT
      rating          AS from_rating,
      next_rating     AS to_rating,
      COUNT(*)        AS transition_count,
      AVG(months_in_rating) AS avg_months_held,
      COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY rating)
                              AS transition_probability
    FROM transitions
    GROUP BY rating, next_rating
  )
SELECT
  from_rating, to_rating, transition_count,
  ROUND(avg_months_held, 1)          AS avg_months_held,
  ROUND(transition_probability, 4)   AS transition_probability,
  ROUND(transition_probability * 100, 2) AS pct,
  RANK() OVER (
    PARTITION BY from_rating ORDER BY transition_probability DESC
  )                                  AS probability_rank,
  SUM(transition_count) OVER (PARTITION BY from_rating) AS from_rating_total,
  CASE
    WHEN transition_probability >= 0.90 THEN 'VERY_STABLE'
    WHEN transition_probability >= 0.70 THEN 'STABLE'
    WHEN transition_probability >= 0.40 THEN 'MODERATE'
    ELSE 'VOLATILE'
  END                                AS stability_label
FROM migration_matrix
ORDER BY from_rating, transition_probability DESC
""",
]


# ── Simple bindings for minor source types ─────────────────────────────────

def _rest_binding(i: int) -> dict:
    return {
        "type": "rest",
        "config": {
            "base_url": "https://stress-api.firm.com",
            "path_template": f"/api/v1/items/{i:04d}",
            "method": "GET",
        },
    }


def _mssql_binding(i: int) -> dict:
    return {
        "type": "mssql",
        "config": {
            "server": "stress-mssql.firm.com",
            "port": 1433,
            "database": "StressDB",
            "driver": "ODBC Driver 17 for SQL Server",
            "query": (
                f"SELECT TOP 1000 s.stress_id, s.item_{i % 10} AS item_val,\n"
                f"  s.metric_a, s.metric_b, s.metric_c, s.created_at\n"
                f"FROM dbo.stress_items_{i % 4} s WITH (NOLOCK)\n"
                f"WHERE s.stress_id = {i}\n"
                f"ORDER BY s.created_at DESC"
            ),
        },
    }


def _static_binding(i: int) -> dict:
    return {
        "type": "static",
        "config": {
            "data": {"value": i, "category": f"stress-{i % 5}"},
            "format": "json",
        },
    }


def _excel_binding(i: int) -> dict:
    return {
        "type": "excel",
        "config": {
            "base_path": "/data/stress/excel",
            "file_pattern": f"stress_data_{i % 8:02d}.xlsx",
            "sheet": f"Sheet{(i % 4) + 1}",
            "header_row": 1,
        },
    }


def _opensearch_binding(i: int) -> dict:
    return {
        "type": "opensearch",
        "config": {
            "hosts": ["https://stress-search.firm.com:9200"],
            "index": f"stress-instruments-v{(i % 3) + 1}",
            "query": (
                f'{{"query": {{"bool": {{"must": [{{"term": '
                f'{{"stress_id": "{i:06d}"}}}}]}}}}}}'
            ),
        },
    }


# ── Path depth helpers ─────────────────────────────────────────────────────

# Intermediate sub-categories for depth-3 and depth-4 paths
_SUBCATEGORIES = [
    "portfolio", "risk", "analytics", "credit", "market",
    "rates", "equity", "fixed_income", "derivatives", "collateral",
]
_SUBSUBCATEGORIES = [
    "attribution", "exposure", "limits", "greeks", "scenarios",
    "var", "cvar", "stress", "performance", "flows",
]


def _leaf_path(domain: str, i: int, depth: int) -> str:
    """Return a catalog key at the requested depth (2, 3, or 4 segments)."""
    item = f"item-{i:04d}"
    if depth == 2:
        return f"{domain}/{item}"
    sub = _SUBCATEGORIES[i % len(_SUBCATEGORIES)]
    if depth == 3:
        return f"{domain}/{sub}/{item}"
    subsub = _SUBSUBCATEGORIES[i % len(_SUBSUBCATEGORIES)]
    return f"{domain}/{sub}/{subsub}/{item}"


def _depth_for(i: int, total: int) -> int:
    """Return depth 2/3/4 based on position: ~50% / ~35% / ~15%."""
    bucket = i % 20
    if bucket < 10:
        return 2
    if bucket < 17:
        return 3
    return 4


# ── Per-domain generators ──────────────────────────────────────────────────

def _oracle_binding(i: int) -> dict:
    query = _ORACLE_QUERIES[i % len(_ORACLE_QUERIES)]
    return {
        "type": "oracle",
        "config": {
            "dsn": "stress-oracle.firm.com:1521/STRESSDB",
            "user": "stress_ro",
            "query": query,
        },
    }


def _snowflake_binding(i: int) -> dict:
    query = _SNOWFLAKE_QUERIES[i % len(_SNOWFLAKE_QUERIES)]
    return {
        "type": "snowflake",
        "config": {
            "account": "stress-test.us-east-1",
            "warehouse": "STRESS_WH",
            "database": "STRESS_DB",
            "schema": "ITEMS",
            "query": query,
        },
    }


# ── Domain spec: (prefix, count_fraction, binding_fn) ─────────────────────

_DOMAIN_SPEC: list[tuple[str, float, object]] = [
    ("stress.oracle",      0.60, _oracle_binding),
    ("stress.snowflake",   0.20, _snowflake_binding),
    ("stress.rest",        0.05, _rest_binding),
    ("stress.mssql",       0.05, _mssql_binding),
    ("stress.static",      0.04, _static_binding),
    ("stress.excel",       0.04, _excel_binding),
    ("stress.opensearch",  0.02, _opensearch_binding),
]


# ── Ownership / parent node ────────────────────────────────────────────────

def _parent_node(domain_key: str, source_label: str) -> dict:
    return {
        "display_name": f"Stress {source_label.replace('_', ' ').title()}",
        "description": (
            f"Stress-test domain for {source_label} source type — "
            "auto-generated, do not use in production."
        ),
        "ownership": {
            "accountable_owner": "stress-test@firm.com",
            "data_specialist": "stress-tech@firm.com",
            "support_channel": "#stress-test",
        },
    }


def _intermediate_node(path: str) -> dict:
    """Thin parent node for intermediate depth-3/4 path segments."""
    return {
        "display_name": path.split("/")[-1].replace("_", " ").title(),
        "description": "Stress test intermediate node — auto-generated.",
        "ownership": {
            "accountable_owner": "stress-test@firm.com",
            "data_specialist": "stress-tech@firm.com",
            "support_channel": "#stress-test",
        },
    }


# ── Public API ─────────────────────────────────────────────────────────────

def gen_stress_catalog(n: int = 10_000) -> dict:
    """
    Generate a YAML-dumpable catalog dict with *n* leaf paths.

    Distribution (by count):
      oracle       60%   heavy 40-60 line SQL, 8-query bank
      snowflake    20%   heavier 60-80 line SQL, 8-query bank
      rest          5%
      mssql         5%
      static        4%
      excel         4%
      opensearch    2%

    Path depth: ~50% depth-2, ~35% depth-3, ~15% depth-4.
    """
    catalog: dict = {}
    registered_intermediates: set[str] = set()

    for domain_key, fraction, binding_fn in _DOMAIN_SPEC:
        source_label = domain_key.split(".")[-1]
        count = max(1, round(n * fraction))

        # Domain parent node
        catalog[domain_key] = _parent_node(domain_key, source_label)

        for i in range(count):
            depth = _depth_for(i, count)
            leaf_key = _leaf_path(domain_key, i, depth)

            # Register intermediate parent nodes (depth-3 and depth-4)
            parts = leaf_key.split("/")
            for end in range(2, len(parts)):
                parent_key = "/".join(parts[:end])
                if parent_key not in registered_intermediates and parent_key not in catalog:
                    catalog[parent_key] = _intermediate_node(parent_key)
                    registered_intermediates.add(parent_key)

            catalog[leaf_key] = {
                "display_name": (
                    f"Stress {source_label.title()} Item {i:04d}"
                ),
                "source_binding": binding_fn(i),
            }

    return catalog


def write_stress_catalog(path: str, n: int = 10_000) -> list[str]:
    """
    Write the stress catalog YAML to *path*.
    Returns the list of resolvable leaf path keys (those with source_binding).
    """
    catalog = gen_stress_catalog(n)

    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(
            catalog, fh,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=True,
            width=120,
        )

    return [k for k, v in catalog.items() if "source_binding" in v]


if __name__ == "__main__":
    import sys

    out = sys.argv[1] if len(sys.argv) > 1 else "stress_catalog.yaml"
    n   = int(sys.argv[2]) if len(sys.argv) > 2 else 10_000
    paths = write_stress_catalog(out, n)
    print(f"Wrote {len(paths):,} resolvable paths to {out}")
