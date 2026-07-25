"""Portable semantic and data-integrity checks for the offline game build."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
HTML_PATH = ROOT / "trade-risk-sim.html"
JSON_PATH = ROOT / "market-data.json"
BALANCE_PATH = ROOT / "balance-config.json"
ISO_PATH = ROOT / "data" / "iso-country-codes.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def premium(config: dict, ri: int, term: dict) -> int:
    gross = (
        config["DEAL_AMOUNT"]
        * config["RI_TABLE"][str(ri)]["returnRate"]
        * term["returnMult"]
    )
    rounded = round(gross * config["INSURANCE"]["premiumRate"] / 10) * 10
    return min(
        config["INSURANCE"]["maxPremium"],
        max(config["INSURANCE"]["minPremium"], rounded),
    )


def find_node() -> str:
    configured = os.environ.get("NODE_BINARY")
    node = configured or shutil.which("node") or shutil.which("node.exe")
    require(bool(node), "Node.js not found. Install Node or set NODE_BINARY.")
    return str(node)


def main() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    config = json.loads(BALANCE_PATH.read_text(encoding="utf-8"))
    iso = json.loads(ISO_PATH.read_text(encoding="utf-8"))
    markets = data["markets"]

    require(data["isSampleData"] is False, "Joined source data must not be marked sample")
    require(bool(markets), "Joined market data is empty")
    require(data.get("creditRiskScope") == "업종 단위", "Credit-risk scope is not explicit")
    require(
        {"riskIndex", "sectorCreditRisk", "countryGrade", "countryGradeMethod"}
        <= data.get("dataVintages", {}).keys(),
        "Data-vintage metadata is incomplete",
    )
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
        min(
            sum(market["ri"] <= 2 for market in markets),
            sum(market["ri"] == 3 for market in markets),
            sum(market["ri"] >= 4 for market in markets),
        )
        >= 3,
        "A stratified market pool is undersized",
    )
    require(
        all(
            iso["countryNameToAlpha3"].get(market["country"]) == market["countryCode"]
            and market["countryCode"] in iso["alpha3ToAlpha2"]
            for market in markets
        ),
        "Static ISO mapping does not cover every joined market",
    )

    require(config["PAYMENT_TERMS"]["prepaid"]["loss"] > 0, "Prepaid must retain loss exposure")
    require(config["STAGE1_TURNS"] == 2, "Stage 1 must contain two presentation-friendly turns")
    require(config["STAGE2_TURNS"] == 4, "Stage 2 must retain four decision turns")
    require(config["STAGE2_TARGET_GAIN"] > 0, "Stage 2 target gain must be positive")
    require(0 < config["FRAUD_EVENT_PROB"] <= 0.10, "Fraud event must remain low probability")
    for ri in range(1, 6):
        for term in config["PAYMENT_TERMS"].values():
            gross = (
                config["DEAL_AMOUNT"]
                * config["RI_TABLE"][str(ri)]["returnRate"]
                * term["returnMult"]
            )
            require(
                gross > premium(config, ri, term),
                f"Successful insured trade is non-positive: RI{ri} {term['label']}",
            )

    forbidden_patterns = {
        "browser storage": r"\b(?:localStorage|sessionStorage)\b",
        "external image/style/script URL": r"(?:src|href)\s*=\s*[\"']https?://",
        "unresolved build placeholder": r"__(?:BALANCE_CONFIG|MARKET_DATA|ISO3_TO_ALPHA2|KSURE_LOGO_DATA_URI)__",
    }
    for label, pattern in forbidden_patterns.items():
        require(not re.search(pattern, html, re.IGNORECASE), f"Found forbidden {label}")
    repository_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            ROOT / "README.md",
            ROOT / "trade-sim-dev-spec.md",
            ROOT / "trade-risk-sim.template.html",
            *sorted((ROOT / "scripts").glob("*.py")),
        )
    )
    require(
        not re.search(r"[A-Za-z]:\\Users\\[^\\]+\\", repository_text),
        "Found a personal Windows home path in public source files",
    )
    require(
        not re.search(r"CONFIG\.INSURANCE\.premium\b", html),
        "Legacy fixed insurance premium remains in the game build",
    )

    for required in (
        "drawMarketsForTurn",
        "deriveStats",
        "insurancePremium",
        "currentTarget",
        "stageTwoStartFund",
        "stageTurnLimit",
        "STAGE1_TURNS",
        "STAGE2_TURNS",
        "EMERGENCY",
        "ACCIDENT",
        "SUCCESS",
        "FRAUD",
        "VERIFIED",
        "송금 확인증이 도착했습니다",
        "계좌 변경 메일이 도착했습니다",
        "pendingTradeAfterSpecial",
        "원래 거래 결과 확인",
        "업종 신용위험",
        "데이터 기준시점",
        "판정 후 공개",
        "한국무역보험공사 공공데이터",
        "본 시뮬레이션은 교육용이며 실제 거래 판단의 근거가 아닙니다",
        "@media (max-width: 680px)",
        "prefers-reduced-motion",
        'class="ksure-logo"',
        'src="data:image/png;base64,',
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
    completed = subprocess.run(
        [
            find_node(),
            "-e",
            "new Function(require('fs').readFileSync(0,'utf8')); console.log('syntax ok')",
        ],
        input=script_match.group(1),
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
