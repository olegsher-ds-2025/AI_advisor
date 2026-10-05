import pandas as pd

from collector.financials import build_financials


def facts(*rows):
    cols = ["concept", "value", "unit", "period_start", "period_end", "form", "filed_at", "accession_no"]
    return pd.DataFrame(rows, columns=cols)


def fact(concept, value, end, form="10-K", accn="a1", filed="2023-11-01", start=None, unit="USD"):
    return (concept, value, unit, start, end, form, filed, accn)


def test_builds_fy_and_q_rows():
    df = build_financials("TEST", facts(
        fact("Assets", 1000, "2023-09-30"),
        fact("Assets", 900, "2023-06-30", form="10-Q", accn="a2"),
        fact("NetIncomeLoss", 100, "2023-09-30", start="2022-10-01"),
    ))
    by_key = df.set_index([df["period"].dt.strftime("%Y-%m-%d"), "period_type"])

    assert by_key.loc[("2023-09-30", "FY"), "assets"] == 1000
    assert by_key.loc[("2023-09-30", "FY"), "net_income"] == 100
    assert by_key.loc[("2023-06-30", "Q"), "assets"] == 900
    assert pd.isna(by_key.loc[("2023-06-30", "Q"), "net_income"])


def test_ytd_durations_are_excluded_from_quarterly_rows():
    df = build_financials("TEST", facts(
        fact("NetIncomeLoss", 30, "2023-06-30", form="10-Q", start="2023-04-01"),
        fact("NetIncomeLoss", 70, "2023-06-30", form="10-Q", start="2023-01-01"),
    ))

    assert df["net_income"].tolist() == [30]


def test_restatements_are_kept_as_separate_filings():
    df = build_financials("TEST", facts(
        fact("Assets", 1000, "2023-09-30", accn="orig", filed="2023-11-01"),
        fact("Assets", 990, "2023-09-30", accn="restated", filed="2024-02-01"),
    ))

    assert set(zip(df["accn"], df["filed"].dt.strftime("%Y-%m-%d"), df["assets"])) == {
        ("orig", "2023-11-01", 1000),
        ("restated", "2024-02-01", 990),
    }


def test_free_cash_flow_uses_absolute_capex():
    df = build_financials("TEST", facts(
        fact("NetCashProvidedByUsedInOperatingActivities", 500, "2023-09-30", start="2022-10-01"),
        fact("PaymentsToAcquirePropertyPlantAndEquipment", -120, "2023-09-30", start="2022-10-01"),
    ))

    assert df["free_cash_flow"].tolist() == [380]


def test_first_concept_in_precedence_order_wins():
    df = build_financials("TEST", facts(
        fact("RevenueFromContractWithCustomerExcludingAssessedTax", 111, "2023-09-30", start="2022-10-01"),
        fact("Revenues", 222, "2023-09-30", start="2022-10-01"),
    ))

    assert df["revenue"].tolist() == [222]


def test_discrete_quarters_are_derived_from_cumulative_cash_flow():
    ocf = "NetCashProvidedByUsedInOperatingActivities"
    df = build_financials("TEST", facts(
        fact(ocf, 10, "2023-03-31", form="10-Q", accn="q1", filed="2023-05-01", start="2023-01-01"),
        fact(ocf, 25, "2023-06-30", form="10-Q", accn="q2", filed="2023-08-01", start="2023-01-01"),
        fact(ocf, 45, "2023-09-30", form="10-Q", accn="q3", filed="2023-11-01", start="2023-01-01"),
        fact(ocf, 80, "2023-12-31", form="10-K", accn="k", filed="2024-02-01", start="2023-01-01"),
    ))
    quarters = df[df["period_type"] == "Q"]
    quarters = quarters.set_index(quarters["period"].dt.strftime("%Y-%m-%d"))

    assert quarters["operating_cf"].to_dict() == {"2023-03-31": 10, "2023-06-30": 15, "2023-09-30": 20, "2023-12-31": 35}
    assert quarters.loc["2023-12-31", "filed"] == pd.Timestamp("2024-02-01")
