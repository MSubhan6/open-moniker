"""Mock Excel adapter for demos and testing.

Simulates Excel file data for mortgages and other Excel-backed sources.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
import random


# =============================================================================
# Sample Data Configuration
# =============================================================================

AGENCIES = ["FNMA", "FHLMC", "GNMA"]
COUPONS = ["15Y", "20Y", "30Y"]

POOL_IDS = {
    "FNMA": ["31417EQ38", "31418ABC1", "31418DEF2", "31418GHI3", "31418JKL4"],
    "FHLMC": ["31283KLM5", "31283NOP6", "31283QRS7", "31283TUV8", "31283WXY9"],
    "GNMA": ["36179ABC0", "36179DEF1", "36179GHI2", "36179JKL3", "36179MNO4"],
}


# =============================================================================
# Mock Excel Adapter
# =============================================================================

class MockExcelAdapter:
    """
    Mock Excel adapter for demos.

    Simulates MBS pool data that would typically come from Excel spreadsheets.
    """

    def __init__(self, seed: int = 42):
        random.seed(seed)

    def get_pool_data(self, agency: str = "ALL", coupon: str = "ALL") -> list[dict[str, Any]]:
        """Generate sample MBS pool data."""
        agencies = [agency] if agency != "ALL" else AGENCIES
        coupons = [coupon] if coupon != "ALL" else COUPONS

        results = []
        base_date = date(2026, 1, 15)

        for ag in agencies:
            pool_ids = POOL_IDS.get(ag, [])
            for pool_id in pool_ids:
                for cp in coupons:
                    original_term = 360 if cp == "30Y" else (240 if cp == "20Y" else 180)
                    wala = random.randint(6, 60)
                    wam = original_term - wala

                    base_wac = 0.065 if cp == "30Y" else (0.055 if cp == "20Y" else 0.045)
                    wac = base_wac + random.uniform(-0.01, 0.01)

                    pool_factor = max(0.5, 1.0 - (wala / original_term) - random.uniform(0, 0.1))

                    cpr_1m = 8 + random.uniform(-3, 5)
                    cpr_3m = cpr_1m + random.uniform(-1, 2)

                    oas = random.uniform(30, 80)
                    price = 100 + random.uniform(-3, 5)

                    for month_offset in range(6):
                        asof = base_date - timedelta(days=month_offset * 30)

                        results.append({
                            "ASOF_DATE": asof.strftime("%Y-%m-%d"),
                            "POOL_ID": pool_id,
                            "AGENCY": ag,
                            "COUPON": cp,
                            "WAC": round(wac, 4),
                            "WAM": wam - month_offset,
                            "WALA": wala + month_offset,
                            "ORIGINAL_BALANCE": random.randint(50000000, 500000000),
                            "CURRENT_BALANCE": random.randint(40000000, 480000000),
                            "POOL_FACTOR": round(pool_factor - (month_offset * 0.01), 4),
                            "CPR_1M": round(cpr_1m + random.uniform(-2, 2), 1),
                            "CPR_3M": round(cpr_3m + random.uniform(-1, 1), 1),
                            "CPR_LIFE": round(cpr_1m * 0.8, 1),
                            "OAS": round(oas + random.uniform(-5, 5), 1),
                            "PRICE": round(price + random.uniform(-0.5, 0.5), 3),
                            "SPREAD_TO_TBA": round(random.uniform(-20, 40), 1),
                            "DURATION": round(random.uniform(3, 8), 2),
                            "CONVEXITY": round(random.uniform(-2, -0.5), 3),
                            "AVG_LOAN_SIZE": random.randint(150000, 500000),
                            "NUM_LOANS": random.randint(100, 5000),
                            "GEO_CONCENTRATION": random.choice(["CA", "TX", "FL", "NY", "Diversified"]),
                        })

        return results

    def get_prepay_data(self, agency: str = "ALL", coupon: str = "ALL") -> list[dict[str, Any]]:
        """Generate sample prepayment projection data."""
        agencies = [agency] if agency != "ALL" else AGENCIES
        coupons = [coupon] if coupon != "ALL" else COUPONS

        results = []
        base_date = date(2026, 1, 15)
        scenarios = ["BASE", "UP100", "UP200", "DN100", "DN200"]

        for ag in agencies:
            pool_ids = POOL_IDS.get(ag, [])
            for pool_id in pool_ids[:3]:
                for cp in coupons:
                    for scenario in scenarios:
                        if scenario == "BASE":
                            base_cpr = 12
                        elif scenario.startswith("UP"):
                            base_cpr = 12 - int(scenario[2:]) / 50
                        else:
                            base_cpr = 12 + int(scenario[2:]) / 30

                        for month in range(1, 13):
                            proj_date = base_date + timedelta(days=month * 30)
                            cpr_proj = base_cpr + (month * 0.2) + random.uniform(-1, 1)
                            smm = cpr_proj / 100 / 12

                            results.append({
                                "ASOF_DATE": base_date.strftime("%Y-%m-%d"),
                                "PROJECTION_DATE": proj_date.strftime("%Y-%m-%d"),
                                "POOL_ID": pool_id,
                                "AGENCY": ag,
                                "COUPON": cp,
                                "SCENARIO": scenario,
                                "MONTH": month,
                                "CPR_PROJ": round(cpr_proj, 1),
                                "SMM": round(smm, 4),
                                "CUMULATIVE_PREPAY": round(smm * month * 100, 2),
                                "FACTOR_PROJ": round(1 - (smm * month), 4),
                            })

        return results

    def fetch(self, file_pattern: str) -> list[dict[str, Any]]:
        """Fetch data from mock Excel file."""
        parts = file_pattern.replace(".xlsx", "").split("_")

        agency = "ALL"
        coupon = "ALL"

        for part in parts:
            if part.upper() in AGENCIES:
                agency = part.upper()
            elif part.upper() in COUPONS:
                coupon = part.upper()

        if "prepay" in file_pattern.lower():
            return self.get_prepay_data(agency, coupon)
        else:
            return self.get_pool_data(agency, coupon)

    def list_files(self) -> list[str]:
        """List available Excel files."""
        files = []
        for agency in AGENCIES:
            for coupon in COUPONS:
                files.append(f"{agency}_{coupon}_pools.xlsx")
                files.append(f"{agency}_{coupon}_prepay.xlsx")
        return files
