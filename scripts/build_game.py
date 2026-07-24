"""Embed the generated market JSON and flag lookup into one offline HTML file."""

from __future__ import annotations

import json
import base64
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "trade-risk-sim.template.html"
MARKET_DATA = ROOT / "market-data.json"
OUTPUT = ROOT / "trade-risk-sim.html"
KSURE_LOGO = ROOT / "assets" / "ksure-logo.png"


def iso3_to_alpha2() -> dict[str, str]:
    script = r"""
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$rows = [Globalization.CultureInfo]::GetCultures([Globalization.CultureTypes]::SpecificCultures) |
  ForEach-Object {
    try {
      $r = [Globalization.RegionInfo]::new($_.Name)
      if ($r.TwoLetterISORegionName.Length -eq 2) {
        [PSCustomObject]@{a3=$r.ThreeLetterISORegionName; a2=$r.TwoLetterISORegionName}
      }
    } catch {}
  } | Sort-Object a3 -Unique
$rows | ConvertTo-Json -Compress
"""
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return {row["a3"]: row["a2"] for row in json.loads(completed.stdout)}


def main() -> None:
    template = TEMPLATE.read_text(encoding="utf-8")
    market_data = json.loads(MARKET_DATA.read_text(encoding="utf-8"))
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
    if template.count("__ISO3_TO_ALPHA2__") != 1:
        raise ValueError("Template must contain exactly one flag-code placeholder")
    if template.count("__KSURE_LOGO_DATA_URI__") != 1:
        raise ValueError("Template must contain exactly one logo placeholder")

    output = template.replace(
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
