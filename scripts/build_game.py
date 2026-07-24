"""Embed the generated market JSON and flag lookup into one offline HTML file."""

from __future__ import annotations

import json
import base64
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "trade-risk-sim.template.html"
MARKET_DATA = ROOT / "market-data.json"
BALANCE_CONFIG = ROOT / "balance-config.json"
OUTPUT = ROOT / "trade-risk-sim.html"
KSURE_LOGO = ROOT / "assets" / "ksure-logo.png"
ISO_CODES = ROOT / "data" / "iso-country-codes.json"


def iso3_to_alpha2() -> dict[str, str]:
    data = json.loads(ISO_CODES.read_text(encoding="utf-8"))
    return data["alpha3ToAlpha2"]


def main() -> None:
    template = TEMPLATE.read_text(encoding="utf-8")
    market_data = json.loads(MARKET_DATA.read_text(encoding="utf-8"))
    balance_config = json.loads(BALANCE_CONFIG.read_text(encoding="utf-8"))
    logo_data_uri = "data:image/png;base64," + base64.b64encode(
        KSURE_LOGO.read_bytes()
    ).decode("ascii")
    used_codes = {market["countryCode"] for market in market_data["markets"]}
    all_codes = iso3_to_alpha2()
    missing = sorted(used_codes - all_codes.keys())
    if missing:
        raise ValueError(f"Missing alpha-2 flag codes: {missing}")
    flag_codes = {code: all_codes[code] for code in sorted(used_codes)}

    if template.count("__MARKET_DATA__") != 1:
        raise ValueError("Template must contain exactly one market-data placeholder")
    if template.count("__BALANCE_CONFIG__") != 1:
        raise ValueError("Template must contain exactly one balance-config placeholder")
    if template.count("__ISO3_TO_ALPHA2__") != 1:
        raise ValueError("Template must contain exactly one flag-code placeholder")
    if template.count("__KSURE_LOGO_DATA_URI__") != 1:
        raise ValueError("Template must contain exactly one logo placeholder")

    output = template.replace(
        "__BALANCE_CONFIG__",
        json.dumps(balance_config, ensure_ascii=False, separators=(",", ":")),
    ).replace(
        "__MARKET_DATA__",
        json.dumps(market_data, ensure_ascii=False, separators=(",", ":")),
    ).replace(
        "__ISO3_TO_ALPHA2__",
        json.dumps(flag_codes, ensure_ascii=False, separators=(",", ":")),
    ).replace(
        "__KSURE_LOGO_DATA_URI__",
        logo_data_uri,
    )
    OUTPUT.write_text(output, encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(OUTPUT),
                "bytes": OUTPUT.stat().st_size,
                "markets": len(market_data["markets"]),
                "flagCodes": len(flag_codes),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
