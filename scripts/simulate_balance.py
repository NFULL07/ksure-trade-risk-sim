"""Monte Carlo regression test for the game balance.

The simulator mirrors the browser game's event order and evaluates a player who
always selects the low-RI candidate. Stage 2 is replayed with each fixed
payment/insurance policy so that one policy cannot silently become dominant.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MARKET_DATA = ROOT / "market-data.json"
BALANCE_CONFIG = ROOT / "balance-config.json"
DEFAULT_REPORT = ROOT / "balance-report.md"

CONFIG = json.loads(BALANCE_CONFIG.read_text(encoding="utf-8"))
START_FUND = CONFIG["START_FUND"]
BANKRUPTCY_FUND = CONFIG["BANKRUPTCY_FUND"]
DEAL_AMOUNT = CONFIG["DEAL_AMOUNT"]
STAGE1_TURNS = CONFIG["STAGE1_TURNS"]
STAGE2_TURNS = CONFIG["STAGE2_TURNS"]
EMERGENCY_LOSS = CONFIG["EMERGENCY_LOSS"]
STAGE2_TARGET_GAIN = CONFIG["STAGE2_TARGET_GAIN"]
PREMIUM_RATE = CONFIG["INSURANCE"]["premiumRate"]
MIN_PREMIUM = CONFIG["INSURANCE"]["minPremium"]
MAX_PREMIUM = CONFIG["INSURANCE"]["maxPremium"]

RI_TABLE = {
    int(key): {
        "accident_prob": value["accidentProb"],
        "return_rate": value["returnRate"],
    }
    for key, value in CONFIG["RI_TABLE"].items()
}
CREDIT_TABLE = CONFIG["CREDIT_TABLE"]
GRADE_TABLE = {int(key): value for key, value in CONFIG["GRADE_TABLE"].items()}


@dataclass(frozen=True)
class PaymentTerm:
    label: str
    prob_mult: float
    return_mult: float
    loss: int


PAYMENT_TERMS = {
    key: PaymentTerm(
        f"{value['label']}·무보험",
        value["probMult"],
        value["returnMult"],
        value["loss"],
    )
    for key, value in CONFIG["PAYMENT_TERMS"].items()
}


def round_to_ten(value: float) -> int:
    return int(round(value / 10) * 10)


def insurance_premium(gross_profit: float) -> int:
    return min(MAX_PREMIUM, max(MIN_PREMIUM, round_to_ten(gross_profit * PREMIUM_RATE)))


def derived(market: dict) -> dict:
    ri = RI_TABLE[market["ri"]]
    return {
        **market,
        "accident_prob": ri["accident_prob"],
        "return_rate": ri["return_rate"],
        "credit_weight": CREDIT_TABLE[market["creditRisk"]],
        "emergency_prob": GRADE_TABLE[market["countryGrade"]],
    }


def resolve_turn(rng: random.Random, market: dict, term: PaymentTerm, insured: bool) -> int:
    gross_profit = DEAL_AMOUNT * market["return_rate"] * term.return_mult
    premium = insurance_premium(gross_profit) if insured else 0

    if rng.random() < market["emergency_prob"]:
        coverage = CONFIG["INSURANCE"]["emergencyCoverage"]
        covered_loss = EMERGENCY_LOSS * ((1 - coverage) if insured else 1.0)
        return -round(covered_loss + premium)

    accident_prob = min(1.0, (market["accident_prob"] + market["credit_weight"]) * term.prob_mult)
    if rng.random() >= accident_prob:
        return round(gross_profit - premium)

    coverage = CONFIG["INSURANCE"]["accidentCoverage"]
    covered_loss = term.loss * ((1 - coverage) if insured else 1.0)
    return -round(covered_loss + premium)


def run_policy(
    markets: list[dict],
    term_key: str,
    insured: bool,
    runs: int,
    seed: int,
) -> dict:
    rng = random.Random(seed)
    low_markets = [derived(market) for market in markets if market["ri"] <= 2]
    term = PAYMENT_TERMS[term_key]
    finals: list[int] = []
    stage1_at_or_above_start = 0
    bankruptcies = 0
    successes = 0
    stage2_gains: list[int] = []

    for _ in range(runs):
        selected = rng.sample(low_markets, STAGE1_TURNS + STAGE2_TURNS)
        fund = START_FUND

        for market in selected[:STAGE1_TURNS]:
            fund += resolve_turn(rng, market, PAYMENT_TERMS["postpaid"], False)
            if fund < BANKRUPTCY_FUND:
                break

        if fund < BANKRUPTCY_FUND:
            bankruptcies += 1
            finals.append(fund)
            stage2_gains.append(0)
            continue

        if fund >= START_FUND:
            stage1_at_or_above_start += 1

        stage2_start = fund
        for market in selected[STAGE1_TURNS:]:
            fund += resolve_turn(rng, market, term, insured)
            if fund < BANKRUPTCY_FUND:
                break

        stage2_gain = fund - stage2_start
        stage2_gains.append(stage2_gain)
        finals.append(fund)
        if fund < BANKRUPTCY_FUND:
            bankruptcies += 1
        elif stage2_gain >= STAGE2_TARGET_GAIN:
            successes += 1

    policy_label = term.label.replace("무보험", "보험" if insured else "무보험")
    return {
        "policy": policy_label,
        "finalMean": round(statistics.fmean(finals)),
        "bankruptcyRate": bankruptcies / runs,
        "successRate": successes / runs,
        "stage1AtOrAboveStartRate": stage1_at_or_above_start / runs,
        "stage2MeanGain": round(statistics.fmean(stage2_gains)),
    }


def render_report(results: list[dict], runs: int, seed: int) -> str:
    rows = "\n".join(
        "| {policy} | {finalMean:,} | {stage2MeanGain:+,} | {bankruptcyRate:.1%} | {successRate:.1%} |".format(
            **result
        )
        for result in results
    )
    return f"""# 게임 밸런스 몬테카를로 검증

## 검증 조건

- 반복 횟수: 정책별 **{runs:,}회**
- 난수 시드: **{seed}**
- 플레이 방식: 매 턴 낮은 RI 후보 선택
- 턴 구성: 스테이지 1 **{STAGE1_TURNS}턴** + 스테이지 2 **{STAGE2_TURNS}턴**
- 스테이지 1: 후불·무보험 고정
- 스테이지 2 성공: 시작 시점 자금보다 **{STAGE2_TARGET_GAIN:,} 크레딧 이상 증가**
- 선불 사고 손실: **{PAYMENT_TERMS['prepaid'].loss:,} 크레딧**
- 보험료: 성공 예상수익의 **{PREMIUM_RATE:.0%}**, 최소 {MIN_PREMIUM}·최대 {MAX_PREMIUM}
- 보험료는 성공·일반사고·비상위험 모든 경로에서 차감

## 결과

| 스테이지 2 정책 | 최종 평균 | 2단계 평균 증감 | 파산율 | 성공률 |
|---|---:|---:|---:|---:|
{rows}

스테이지 1 종료 시 시작 자금 이상 비율은 정책별 표본 오차 범위에서
{statistics.fmean(result['stage1AtOrAboveStartRate'] for result in results):.1%}였다.
최종 성공은 절대 자금이 아니라 스테이지 2의 성과로 판정하므로,
선택지가 없는 스테이지 1의 운이 최종 성공을 선점하지 않는다.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=20_000)
    parser.add_argument("--seed", type=int, default=20260724)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    data = json.loads(MARKET_DATA.read_text(encoding="utf-8"))
    policies = [
        ("postpaid", False),
        ("postpaid", True),
        ("partial", False),
        ("partial", True),
        ("prepaid", False),
        ("prepaid", True),
    ]
    results = [
        run_policy(data["markets"], term, insured, args.runs, args.seed + index)
        for index, (term, insured) in enumerate(policies)
    ]
    args.report.write_text(render_report(results, args.runs, args.seed), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
