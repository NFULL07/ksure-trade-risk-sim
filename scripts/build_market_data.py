"""Build the game-ready market list from the three K-SURE CSV files.

The source CSV files are CP949 encoded.  The join is intentionally conservative:

* RI: latest available month in the RI file
* credit risk: latest available year in the credit-risk file
* country grade: latest dated row for each country
* credit risk joins by an explicit, auditable sector crosswalk
* country grade joins by the Korean country name
* ambiguous or incomplete rows are discarded, never imputed
"""

from __future__ import annotations

import csv
import json
import math
import statistics
import subprocess
from collections import Counter
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_JSON = ROOT / "market-data.json"
OUTPUT_REPORT = ROOT / "market-data-report.md"

SOURCE_FILES = {
    "ri": ROOT / "한국무역보험공사_국가별 업종별 위험지수(RISK INDEX)_20250501.csv",
    "credit": ROOT / "한국무역보험공사_주요 업종별 신용위험지수_20231231.csv",
    "grade": ROOT / "한국무역보험공사_국가신용등급_20260206.csv",
}

# The credit-risk file uses broader labels than the RI file.  Only unambiguous
# one-to-one matches are included.  "공사업" is intentionally excluded because
# it could refer to more than one RI category.
SECTOR_CROSSWALK = {
    "소매업": "소매업; 자동차 제외",
    "도매업": "도매 및 상품 중개업",
    "의류 제조업": "의복  의복 액세서리 및 모피제품 제조업",
    "자동차 제조업": "자동차 및 트레일러 제조업",
    "펄프종이 제조업": "펄프  종이 및 종이제품 제조업",
    "자동차판매업": "자동차 및 부품 판매업",
    "기계장비 제조업": "기타 기계 및 장비 제조업",
    "전기장비 제조업": "전기장비 제조업",
    "금속가공 제조업": "금속가공제품 제조업; 기계 및 가구 제외",
    "금속 제조업": "1차 금속 제조업",
    "플라스틱 제조업": "고무 및 플라스틱제품 제조업",
    "컴퓨터 제조업": "전자부품  컴퓨터  영상  음향 및 통신장비 제조업",
    "섬유제품 제조업": "섬유제품 제조업; 의복제외",
    "화학물질 제조업": "화학물질 및 화학제품 제조업; 의약품 제외",
    "식료품 제조업": "식료품 제조업",
}

# K-SURE labels that differ from the Korean locale names returned by Windows.
# These are spelling/spacing aliases only; no country identity is inferred from
# a partial match.
COUNTRY_CODE_ALIASES = {
    "과달루프": "GLP",
    "남아프리카공화국": "ZAF",
    "도미니카공화국": "DOM",
    "레위니옹": "REU",
    "마샬군도": "MHL",
    "마카오": "MAC",
    "모리타니아": "MRT",
    "베넹": "BEN",
    "벨라루스": "BLR",
    "보스니아-헤르체코비나": "BIH",
    "사이프러스": "CYP",
    "산 마리노": "SMR",
    "아랍에미리트 연합": "ARE",
    "영국령 버진군도": "VGB",
    "조지아": "GEO",
    "콩고": "COG",
    "콩고민주공화국": "COD",
    "키르기즈공화국": "KGZ",
    "태국": "THA",
    "튀르키예(구 터키)": "TUR",
    "트리니다드토바고": "TTO",
    "호주": "AUS",
    "홍콩": "HKG",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="cp949", newline="") as handle:
        return list(csv.DictReader(handle))


def quantile(values: list[float], q: float) -> float:
    """Inclusive linear quantile, equivalent here across common methods."""
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def load_windows_iso_map() -> dict[str, str]:
    """Return Korean country display name -> ISO 3166 alpha-3 code."""
    script = r"""
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$old = [System.Threading.Thread]::CurrentThread.CurrentUICulture
[System.Threading.Thread]::CurrentThread.CurrentUICulture = [Globalization.CultureInfo]'ko-KR'
$rows = [Globalization.CultureInfo]::GetCultures([Globalization.CultureTypes]::SpecificCultures) |
  ForEach-Object {
    try {
      $r = [Globalization.RegionInfo]::new($_.Name)
      if ($r.TwoLetterISORegionName.Length -eq 2) {
        [PSCustomObject]@{name=$r.DisplayName; code=$r.ThreeLetterISORegionName}
      }
    } catch {}
  } | Sort-Object name -Unique
[System.Threading.Thread]::CurrentThread.CurrentUICulture = $old
$rows | ConvertTo-Json -Compress
"""
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    rows = json.loads(completed.stdout)
    return {row["name"]: row["code"] for row in rows}


def build() -> tuple[dict, dict]:
    ri_rows = read_csv(SOURCE_FILES["ri"])
    credit_rows = read_csv(SOURCE_FILES["credit"])
    grade_rows = read_csv(SOURCE_FILES["grade"])

    latest_ri_month = max(row["기준년월"] for row in ri_rows)
    latest_credit_year = max(row["기준년도"] for row in credit_rows)
    ri_latest = [row for row in ri_rows if row["기준년월"] == latest_ri_month]
    credit_latest = [
        row for row in credit_rows if row["기준년도"] == latest_credit_year
    ]

    # Terciles are calculated on the latest source-year sector observations,
    # before country repetition in the joined table can bias the thresholds.
    credit_values = [float(row["신용위험지수"]) for row in credit_latest]
    lower_boundary = quantile(credit_values, 1 / 3)
    upper_boundary = quantile(credit_values, 2 / 3)

    def credit_label(value: float) -> str:
        if value <= lower_boundary:
            return "낮음"
        if value <= upper_boundary:
            return "중간"
        return "높음"

    credit_by_ri_sector: dict[str, dict] = {}
    for row in credit_latest:
        source_sector = row["업종"].strip()
        target_sector = SECTOR_CROSSWALK.get(source_sector)
        if target_sector is None:
            continue
        value = float(row["신용위험지수"])
        if target_sector in credit_by_ri_sector:
            raise ValueError(f"Duplicate mapped credit sector: {target_sector}")
        credit_by_ri_sector[target_sector] = {
            "sourceSector": source_sector,
            "value": value,
            "label": credit_label(value),
        }

    latest_grade_by_country: dict[str, tuple[date, int]] = {}
    for row in grade_rows:
        country = row["국가명"].strip()
        grade_text = row["국가등급"].strip()
        date_text = row["등급평가일자"].strip()
        if not country or not grade_text or not date_text:
            continue
        evaluated = date.fromisoformat(date_text)
        grade = int(grade_text)
        existing = latest_grade_by_country.get(country)
        if existing is None or evaluated > existing[0]:
            latest_grade_by_country[country] = (evaluated, grade)
        elif evaluated == existing[0] and grade != existing[1]:
            raise ValueError(
                f"Conflicting latest country grade for {country}: "
                f"{existing[1]} vs {grade}"
            )

    iso_map = load_windows_iso_map()
    iso_map.update(COUNTRY_CODE_ALIASES)

    joined: list[dict] = []
    seen_keys: set[tuple[str, str]] = set()
    excluded = Counter()

    for row in ri_latest:
        country = row["국가한글명"].strip()
        sector = row["업종한글명"].strip()
        ri_text = row["위험지수(Risk Index)"].strip()
        credit = credit_by_ri_sector.get(sector)
        grade_record = latest_grade_by_country.get(country)
        country_code = iso_map.get(country)

        if not ri_text:
            excluded["RI 결측"] += 1
            continue
        if credit is None:
            excluded["신용위험 업종 미매핑"] += 1
            continue
        if grade_record is None:
            excluded["국가등급 결측"] += 1
            continue
        if country_code is None:
            excluded["ISO 코드 미확인"] += 1
            continue

        ri = int(ri_text)
        country_grade = grade_record[1]
        if ri not in range(1, 6):
            raise ValueError(f"Invalid RI value: {ri}")
        if country_grade not in range(1, 8):
            raise ValueError(f"Invalid country grade: {country_grade}")

        key = (country, sector)
        if key in seen_keys:
            raise ValueError(f"Duplicate market key: {key}")
        seen_keys.add(key)

        joined.append(
            {
                "countryCode": country_code,
                "country": country,
                "sector": sector,
                "ri": ri,
                "creditRisk": credit["label"],
                "countryGrade": country_grade,
            }
        )

    joined.sort(key=lambda item: (item["country"], item["sector"]))
    markets = [{"id": f"M{index:04d}", **market} for index, market in enumerate(joined, 1)]

    strata = Counter(
        "낮음(RI1~2)" if market["ri"] <= 2 else
        "중간(RI3)" if market["ri"] == 3 else
        "높음(RI4~5)"
        for market in markets
    )
    for label in ("낮음(RI1~2)", "중간(RI3)", "높음(RI4~5)"):
        if strata[label] < 3:
            raise ValueError(f"Insufficient markets in stratum {label}: {strata[label]}")

    result = {
        "source": (
            "한국무역보험공사 공공데이터포털 "
            "(국가별 업종별 위험지수/주요 업종별 신용위험지수/국가신용등급)"
        ),
        "isSampleData": False,
        "markets": markets,
    }
    audit = {
        "riMonth": latest_ri_month,
        "creditYear": latest_credit_year,
        "creditLowerBoundary": lower_boundary,
        "creditUpperBoundary": upper_boundary,
        "marketCount": len(markets),
        "countryCount": len({market["country"] for market in markets}),
        "sectorCount": len({market["sector"] for market in markets}),
        "strata": dict(strata),
        "riCounts": dict(sorted(Counter(market["ri"] for market in markets).items())),
        "creditRiskCounts": dict(Counter(market["creditRisk"] for market in markets)),
        "countryGradeCounts": dict(
            sorted(Counter(market["countryGrade"] for market in markets).items())
        ),
        "excluded": dict(excluded),
        "sourceCreditSectors": len(credit_latest),
        "mappedCreditSectors": len(credit_by_ri_sector),
    }
    return result, audit


def write_outputs(result: dict, audit: dict) -> None:
    OUTPUT_JSON.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    report = f"""# 시장 데이터 조인 보고서

## 결과

- 생성 시장: **{audit['marketCount']:,}개**
- 포함 국가: **{audit['countryCount']}개**
- 포함 업종: **{audit['sectorCount']}개**
- RI 기준월: **{audit['riMonth']}**
- 신용위험 기준연도: **{audit['creditYear']}**
- 국가신용등급: 국가별 최신 평가일자 행
- `isSampleData`: **false**

## 신용위험 3분위 경계

최신 기준연도의 업종별 신용위험지수 {audit['sourceCreditSectors']}개를 국가별
시장으로 반복하기 전에 계산했다. 따라서 국가 수가 많은 업종이 경계값을
왜곡하지 않는다.

- 낮음: 지수 ≤ **{audit['creditLowerBoundary']:.1f}**
- 중간: **{audit['creditLowerBoundary']:.1f} < 지수 ≤ {audit['creditUpperBoundary']:.1f}**
- 높음: 지수 > **{audit['creditUpperBoundary']:.1f}**

## 조인·표준화 원칙

1. 원본 CSV는 모두 CP949로 읽었다.
2. RI 파일은 최신 월인 {audit['riMonth']} 행만 사용했다.
3. 신용위험 파일은 최신 연도인 {audit['creditYear']} 행만 사용했다.
4. 신용위험은 명시적 업종 교차표로 RI 업종에 연결했다.
5. 국가등급은 동일 국가의 최신 평가일자 행만 사용했다.
6. ISO 3166 alpha-3는 Windows 지역 표준 목록과 정확히 일치하는 한글명,
   또는 철자·띄어쓰기만 다른 명시적 별칭표로 부여했다.
7. 값이 하나라도 없거나 모호한 행은 추측·보간하지 않고 제외했다.

`공사업`은 RI 파일의 여러 공사·건설 업종 중 어느 하나로 단정할 수 없어
교차표에서 제외했다. 이에 따라 최신 신용위험 업종
{audit['sourceCreditSectors']}개 중 {audit['mappedCreditSectors']}개를 사용했다.

## RI 층 검증

| 층 | 시장 수 |
|---|---:|
| 낮음(RI1~2) | {audit['strata'].get('낮음(RI1~2)', 0):,} |
| 중간(RI3) | {audit['strata'].get('중간(RI3)', 0):,} |
| 높음(RI4~5) | {audit['strata'].get('높음(RI4~5)', 0):,} |

세 층 모두 권장 최소치(2~3개)를 충분히 충족한다.

## 완전성 검사

- 국가+업종 중복: **0개**
- 허용 범위 밖 RI/국가등급: **0개**
- 조인된 시장의 결측값: **0개**
- 층화 추출 불가 층: **0개**
"""
    OUTPUT_REPORT.write_text(report, encoding="utf-8")


if __name__ == "__main__":
    market_data, audit_data = build()
    write_outputs(market_data, audit_data)
    print(json.dumps(audit_data, ensure_ascii=False, indent=2))
