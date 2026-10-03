from collector.sec import parse_financials


def _entry(end, val, form="10-K", accn="a1", filed="2023-11-01", start=None):
    entry = {"end": end, "val": val, "form": form, "accn": accn, "filed": filed, "fy": 2023, "fp": "FY"}
    if start:
        entry["start"] = start
    return entry


def _facts(**concepts):
    return {"facts": {"us-gaap": {name: {"units": {"USD": entries}} for name, entries in concepts.items()}}}


def test_parse_financials_builds_fy_and_q_records():
    facts = _facts(
        Assets=[
            _entry("2023-09-30", 1000),
            _entry("2023-06-30", 900, form="10-Q", accn="a2"),
        ],
        NetIncomeLoss=[_entry("2023-09-30", 100, start="2022-10-01")],
    )

    rows = parse_financials("TEST", facts)
    by_key = {(r["period"], r["period_type"]): r for r in rows}

    assert by_key[("2023-09-30", "FY")]["assets"] == 1000
    assert by_key[("2023-09-30", "FY")]["net_income"] == 100
    assert by_key[("2023-06-30", "Q")]["assets"] == 900
    assert by_key[("2023-06-30", "Q")]["net_income"] is None


def test_ytd_durations_are_excluded_from_quarterly_rows():
    facts = _facts(
        NetIncomeLoss=[
            _entry("2023-06-30", 30, form="10-Q", start="2023-04-01"),
            _entry("2023-06-30", 70, form="10-Q", start="2023-01-01"),
        ],
    )

    rows = parse_financials("TEST", facts)

    assert [r["net_income"] for r in rows] == [30]


def test_restatements_are_kept_as_separate_filings():
    facts = _facts(
        Assets=[
            _entry("2023-09-30", 1000, accn="orig", filed="2023-11-01"),
            _entry("2023-09-30", 990, form="10-K", accn="restated", filed="2024-02-01"),
        ],
    )

    rows = parse_financials("TEST", facts)

    assert {(r["accn"], r["filed"], r["assets"]) for r in rows} == {
        ("orig", "2023-11-01", 1000),
        ("restated", "2024-02-01", 990),
    }


def test_free_cash_flow_uses_absolute_capex():
    facts = _facts(
        NetCashProvidedByUsedInOperatingActivities=[_entry("2023-09-30", 500, start="2022-10-01")],
        PaymentsToAcquirePropertyPlantAndEquipment=[_entry("2023-09-30", -120, start="2022-10-01")],
    )

    rows = parse_financials("TEST", facts)

    assert rows[0]["free_cash_flow"] == 380


def test_first_concept_in_precedence_order_wins():
    facts = _facts(
        RevenueFromContractWithCustomerExcludingAssessedTax=[_entry("2023-09-30", 111, start="2022-10-01")],
        Revenues=[_entry("2023-09-30", 222, start="2022-10-01")],
    )

    rows = parse_financials("TEST", facts)

    assert rows[0]["revenue"] == 222
