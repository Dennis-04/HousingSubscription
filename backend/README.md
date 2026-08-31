# 백엔드 설계

## 설계 원칙

- 공식 구조화 API로 공고를 발견하고 PDF는 원문 보관·상세 조건·정정 감지에 사용합니다.
- 청약홈/LH의 필드명은 `infrastructure/sources` 밖으로 새지 않습니다.
- 공고 현재값과 `notice_versions`를 분리해 조용한 수정도 설명할 수 있습니다.
- PDF는 SHA-256, ETag, Last-Modified, 파서 버전을 기록하고 동일 해시는 중복 저장하지 않습니다.
- API 프로세스와 수집 스케줄을 분리합니다. 여러 API 인스턴스로 확장해도 스케줄 중복이 생기지 않습니다.
- PostgreSQL 전문검색으로 시작할 수 있는 구조이며, 저장소/검색/파일 포트는 이후 S3·OpenSearch 어댑터로 교체할 수 있습니다.

## 데이터 흐름

```text
청약홈 API ─┐
LH API ─────┼─> Source adapters ─> CollectNotices ─> PostgreSQL ─> FastAPI ─> App
SH/GH(추가) ┘                         │
                                      └─> PDF download ─> hash/version ─> local/S3
```

## 핵심 테이블

| 테이블 | 역할 |
|---|---|
| `regions` | 지도와 API가 공유하는 시·도/시·군·구 코드 |
| `announcements` | 현재 공고 상태와 검색용 정규화 필드 |
| `notice_versions` | 변경 전후 스냅샷, 변경 필드, 정정 여부 |
| `housing_units` | 주택형, 전용면적, 세대수, 분양가/보증금/월세 |
| `competitions` | 주택형·공급구분·순위·거주지역별 경쟁률 |
| `documents` | 공고문/첨부파일의 해시, 저장 위치, 추출 텍스트 |
| `document_facts` | 추출 필드, PDF 페이지, 원문 근거, 신뢰도, 검수 상태 |
| `collection_runs` | 소스별 실행시간, 성공/실패, 발견/변경 건수 |
| `watch_rules` | 관심지역·유형·알림 이벤트 규칙 |
| `notification_deliveries` | 중복 방지 키가 포함된 알림 발송 이력 |

## API

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/v1/health/live` | 프로세스 생존 확인 |
| GET | `/api/v1/health/ready` | DB/키/소스별 마지막 수집 상태 |
| GET | `/api/v1/announcements` | 지역·상태·공급자·주택유형·검색어 필터 |
| GET | `/api/v1/announcements/{id}` | 버전·주택형·경쟁률·문서 포함 상세 |
| GET | `/api/v1/regions/summary` | 지도 표시용 지역별 공고 수 |
| GET | `/api/v1/documents/{id}/file` | 저장된 원문 파일 |
| POST | `/api/v1/admin/collections` | 관리 토큰으로 수집 실행 |

관리 API 예시:

```bash
curl -X POST http://localhost:8000/api/v1/admin/collections \
  -H 'Content-Type: application/json' \
  -H 'X-Admin-Token: .env.local에_설정한_값' \
  -d '{"sources":["applyhome","lh"]}'
```

## PDF 파싱과 검수

현재 파이프라인은 PDF 페이지 경계(`--- page:N ---`)를 보존해 텍스트를 추출합니다. 텍스트가 없는 스캔 PDF는 `needs_ocr`로 표시합니다. 다음 파서 단계는 `document_facts`에 다음 형태로 저장하도록 확장하면 됩니다.

```json
{
  "field_name": "income_limit",
  "value_text": "전년도 도시근로자 월평균소득 120% 이하",
  "source_page": 18,
  "evidence_quote": "신청자격은 ... 120% 이하인 자",
  "confidence": 0.86,
  "review_status": "pending"
}
```

신뢰도가 낮은 값은 앱에서 `원문 확인 필요`로 표시하고 운영 검수 대상으로 보냅니다.

## 다음 공급자 추가

`NoticeSource` 포트를 구현하고 `bootstrap.py`에 등록하면 됩니다. SH처럼 공개 목록 HTML을 사용하는 공급자는 robots 정책과 이용약관을 확인한 뒤 목록 발견만 자동화하고, 로그인·CAPTCHA가 필요한 화면은 수집하지 않습니다. GH/iH/부산도시공사도 각각 독립 어댑터로 추가해 한 기관의 HTML 변경이 전체 수집을 깨지 않게 합니다.

## 테스트

```bash
cd backend
pytest
ruff check .
```
