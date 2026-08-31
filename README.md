# 주택청약지도

대한민국 행정구역 지도와 청약 공고 수집 백엔드를 결합한 프로젝트입니다. 프런트엔드는 시·도 → 시·군 → 구 단위로 탐색하고, 백엔드는 청약홈·LH 공식 API를 우선 수집한 뒤 PDF 원문과 정정 이력을 별도로 보관합니다.

> 청약 조건과 일정은 바뀔 수 있습니다. 서비스의 데이터는 탐색 보조용이며, 최종 판단 전 반드시 원문 공고문을 확인해야 합니다.

## 구성

```text
.
├── index.html, app.js, styles.css  # 지도 프런트엔드
├── assets/                         # 행정경계 데이터
├── backend/
│   ├── src/housing_backend/
│   │   ├── domain/                 # 공급자와 무관한 공고/주택형/경쟁률 모델
│   │   ├── application/            # 수집 유스케이스와 포트
│   │   ├── infrastructure/         # PostgreSQL, 청약홈, LH, PDF 저장 어댑터
│   │   └── api/                    # FastAPI 라우트와 응답 모델
│   ├── migrations/                 # Alembic DB 마이그레이션
│   └── tests/
└── docker-compose.yml              # PostgreSQL + API + 일회성 수집 작업
```

상세 설계는 [backend/README.md](backend/README.md)를 참고하세요.

## API 키 입력 예시

루트의 `.env.example`을 `.env.local`로 복사한 다음 아래 값을 채웁니다.

```bash
cp .env.example .env.local
```

```dotenv
DATA_GO_KR_SERVICE_KEY=공공데이터포털에서_발급받은_Decoding_인증키
ADMIN_API_TOKEN=충분히_긴_임의의_관리자_토큰
```

실제 키가 들어간 `.env.local`은 Git에서 제외됩니다. 현재 1차 수집에는 다음 활용신청이 필요합니다.

- [청약홈 분양정보 조회 서비스](https://www.data.go.kr/data/15098547/openapi.do)
- [청약홈 경쟁률·특별공급 신청현황 서비스](https://www.data.go.kr/data/15098905/openapi.do)
- LH 분양·임대 공고 목록 (`lhLeaseNoticeInfo1`)
- LH 공고별 공급·첨부 정보 (`lhLeaseNoticeSplInfo1`, `lhLeaseNoticeDtlInfo1`)

## 가장 간단한 실행

Python 3.11 이상이 필요합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install './backend[dev]'
uvicorn housing_backend.main:app --reload --port 8000
```

다른 터미널에서 프런트엔드를 실행합니다.

```bash
python3 -m http.server 4173
```

- 지도: `http://localhost:4173`
- API 문서: `http://localhost:8000/docs`
- 준비 상태: `http://localhost:8000/api/v1/health/ready`

SQLite는 로컬 개발 기본값입니다. 실제 PostgreSQL 환경은 다음으로 실행합니다.

```bash
docker compose up --build db api
docker compose --profile jobs run --rm collector
```

## 데이터 적재

지도 행정구역 시드:

```bash
cd backend
python -m housing_backend.cli seed-regions --geojson ../assets/sgg.json
```

청약홈과 LH 신규·변경 공고 수집:

```bash
cd backend
python -m housing_backend.cli collect --sources applyhome,lh
```

운영에서는 이 CLI를 Cloud Scheduler, Kubernetes CronJob, systemd timer 등 외부 스케줄러에서 10~30분마다 실행하세요. 워커를 API 프로세스 안에 넣지 않아 API 재시작이나 다중 인스턴스에서 중복 스케줄이 생기지 않게 했습니다.

## 프런트엔드 기능

- 17개 시·도 단위 벡터 지도와 시·군·구 드릴다운
- 확대 비율을 유지하는 순수 SVG 점 패턴
- 호버/선택/키보드/모바일 터치 지원
- Helvetica 중심 글꼴과 황금비 기반의 타이포·헤더·지도 비율
- `assets/api-client.js`를 통한 지역별 공고 수 표시(백엔드가 꺼져 있어도 지도는 동작)

## 프런트엔드 성능

- 원본 GeoJSON은 빌드 시 SVG 경로로 변환해 브라우저의 좌표 투영 연산을 제거했습니다.
- 전국 화면은 시·군·구 조각을 시·도별 단일 경로로 합쳐 17개 SVG 경로만 렌더링합니다.
- 지도 이벤트는 위임 방식으로 처리하고 포인터·리사이즈·점 패턴 갱신을 프레임 단위로 제한합니다.
- 기존 점묘 표현, 호버 강조, 선택 색상, 680ms 확대 모션은 그대로 유지합니다.

행정경계 원본을 갱신한 뒤 브라우저용 경로를 다시 생성하려면 다음을 실행합니다.

```bash
node scripts/build-map-data.js
```

경계 데이터 출처와 라이선스는 `assets/BOUNDARY-DATA-NOTICE.md`에 있습니다.
