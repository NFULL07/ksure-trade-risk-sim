# K-SURE 무역 리스크 대응 시뮬레이션

한국무역보험공사 공공데이터를 활용해 국가·업종별 무역 위험을 비교하고,
결제조건과 무역보험으로 자금을 관리하는 교육용 웹 게임입니다.

## 실행

별도 설치 없이 `trade-risk-sim.html`을 웹 브라우저에서 열면 실행됩니다.

공개 버전: https://ksure-trade-risk-sim.kjoun031108.chatgpt.site

## 데이터

다음 CSV 3개를 `scripts/build_market_data.py`로 결합해
`market-data.json`을 생성합니다.

- 국가별 업종별 위험지수: 2025-04
- 주요 **업종별** 신용위험지수: 2023년
- 국가신용등급: 국가별 최신 평가일(전체 최신 2026-02-06)

신용위험 라벨은 업종 단위이므로 같은 업종은 국가가 달라도 같은 라벨을
사용합니다. 별도의 국가별 신용위험 데이터는 이 3개 파일 조인에 포함하지
않았습니다. ISO 국가는 운영체제 명령이 아니라
`data/iso-country-codes.json`의 명시적 대응표로 변환합니다.

## 밸런스

- 스테이지 1: 후불·무보험으로 지표를 읽는 연습
- 스테이지 2: 시작 자금보다 400 크레딧 이상 늘리면 성공
- 선불도 생산비 노출로 사고 시 1,200 크레딧 손실
- 보험료: 성공 예상수익의 35%, 최소 50·최대 250
- 보험료는 성공·일반사고·비상위험 모든 경로에서 납부

## 주요 파일

- `trade-risk-sim.template.html`: 게임 원본 템플릿
- `trade-risk-sim.html`: 실행 가능한 단일 HTML
- `market-data.json`: 결합된 게임 데이터
- `balance-config.json`: 공공데이터와 분리된 게임 밸런스 설정
- `balance-report.md`: 3만 회 몬테카를로 검증 결과
- `data/iso-country-codes.json`: 정적 ISO 국가 코드 대응표
- `scripts/build_market_data.py`: CSV 결합 스크립트
- `scripts/build_game.py`: 데이터와 로고를 HTML에 포함하는 빌드 스크립트
- `scripts/validate_game.py`: 데이터·게임 구조 검증 스크립트
- `scripts/simulate_balance.py`: 밸런스 몬테카를로 검증 스크립트
- `trade-sim-dev-spec.md`: 개발 명세

## 검증

Python 3과 Node.js가 필요하며 Windows, macOS, Linux에서 같은 명령으로
재현할 수 있습니다. Node가 PATH에 없다면 `NODE_BINARY` 환경변수로 실행
파일 경로를 지정합니다.

```sh
python scripts/build_market_data.py
python scripts/build_game.py
python scripts/validate_game.py
python scripts/simulate_balance.py --runs 30000 --seed 20260724
```

본 시뮬레이션은 교육용이며 실제 거래 판단의 근거가 아닙니다.
