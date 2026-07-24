# K-SURE 무역 리스크 대응 시뮬레이션

한국무역보험공사 공공데이터를 활용해 국가·업종별 무역 위험을 비교하고,
결제조건과 무역보험으로 자금을 관리하는 교육용 웹 게임입니다.

## 실행

별도 설치 없이 `trade-risk-sim.html`을 웹 브라우저에서 열면 실행됩니다.

공개 버전: https://ksure-trade-risk-sim.kjoun031108.chatgpt.site

## 데이터

다음 CSV 3개를 `scripts/build_market_data.py`로 결합해
`market-data.json`을 생성합니다.

- 국가별 업종별 위험지수
- 주요 업종별 신용위험지수
- 국가신용등급

## 주요 파일

- `trade-risk-sim.template.html`: 게임 원본 템플릿
- `trade-risk-sim.html`: 실행 가능한 단일 HTML
- `market-data.json`: 결합된 게임 데이터
- `scripts/build_market_data.py`: CSV 결합 스크립트
- `scripts/build_game.py`: 데이터와 로고를 HTML에 포함하는 빌드 스크립트
- `scripts/validate_game.py`: 데이터·게임 구조 검증 스크립트
- `trade-sim-dev-spec.md`: 개발 명세

## 검증

```powershell
python scripts/build_market_data.py
python scripts/build_game.py
python scripts/validate_game.py
```

본 시뮬레이션은 교육용이며 실제 거래 판단의 근거가 아닙니다.
