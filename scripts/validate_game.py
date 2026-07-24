"""Static and data-integrity checks for the offline game build."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
HTML_PATH = ROOT / "trade-risk-sim.html"
JSON_PATH = ROOT / "market-data.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    markets = data["markets"]

    require(data["isSampleData"] is False, "Joined source data must not be marked sample")
    require(len(markets) == 1041, "Unexpected joined market count")
    require(len({market["id"] for market in markets}) == len(markets), "Duplicate IDs")
    require(
        len({(market["country"], market["sector"]) for market in markets}) == len(markets),
        "Duplicate country-sector key",
    )
    require(all(1 <= market["ri"] <= 5 for market in markets), "RI out of range")
    require(
        all(1 <= market["countryGrade"] <= 7 for market in markets),
        "Country grade out of range",
    )
    require(
        all(market["creditRisk"] in {"낮음", "중간", "높음"} for market in markets),
        "Credit-risk label out of range",
    )
    require(
        min(sum(market["ri"] <= 2 for market in markets),
            sum(market["ri"] == 3 for market in markets),
            sum(market["ri"] >= 4 for market in markets)) >= 3,
        "A stratified market pool is undersized",
    )

    forbidden_patterns = {
        "browser storage": r"\b(?:localStorage|sessionStorage)\b",
        "external image/style/script URL": r"(?:src|href)\s*=\s*[\"']https?://",
        "unresolved build placeholder": r"__(?:MARKET_DATA|ISO3_TO_ALPHA2|KSURE_LOGO_DATA_URI)__",
    }
    for label, pattern in forbidden_patterns.items():
        require(not re.search(pattern, html, re.IGNORECASE), f"Found forbidden {label}")

    for required in (
        "RI_TABLE",
        "CREDIT_TABLE",
        "GRADE_TABLE",
        "PAYMENT_TERMS",
        "INSURANCE",
        "drawMarketsForTurn",
        "deriveStats",
        "EMERGENCY",
        "ACCIDENT",
        "SUCCESS",
        "FRAUD",
        "한국무역보험공사 공공데이터",
        "본 시뮬레이션은 교육용이며 실제 거래 판단의 근거가 아닙니다",
        "@media (max-width: 680px)",
        "prefers-reduced-motion",
        'class="ksure-logo"',
        'src="data:image/png;base64,',
        "display: block;\n      width: 100%;\n      position: relative;",
        ".controls-panel > * { min-width: 0; }",
        "flex: 0 0 19px;",
        "padding-bottom: 6px;",
        "line-height: 1.45;",
    ):
        require(required in html, f"Missing required implementation marker: {required}")

    require(html.count('<img class="ksure-logo"') == 1, "Expected one embedded K-SURE logo")

    emergency_position = html.index("const emergencyRoll")
    accident_position = html.index("const accidentProb", emergency_position)
    require(
        emergency_position < accident_position,
        "Emergency risk must be resolved before ordinary accident risk",
    )

    script_match = re.search(r"<script>([\s\S]*)</script>\s*</body>", html)
    require(script_match is not None, "Inline game script was not found")
    script_text = script_match.group(1)
    node = (
        r"C:\Users\kjoun\.cache\codex-runtimes\codex-primary-runtime"
        r"\dependencies\node\bin\node.exe"
    )
    completed = subprocess.run(
        [node, "-e", "new Function(require('fs').readFileSync(0,'utf8')); console.log('syntax ok')"],
        input=script_text,
        text=True,
        capture_output=True,
        encoding="utf-8",
    )
    require(completed.returncode == 0, f"JavaScript syntax error:\n{completed.stderr}")

    print(
        json.dumps(
            {
                "status": "ok",
                "markets": len(markets),
                "countries": len({market["country"] for market in markets}),
                "sectors": len({market["sector"] for market in markets}),
                "htmlBytes": HTML_PATH.stat().st_size,
                "javascript": completed.stdout.strip(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
