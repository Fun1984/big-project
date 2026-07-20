# core-api REST API

Base URL: `http://localhost:8080`

현재 구현된 범위: **User / Consultation / Attachment / AI_ANALYSIS** CRUD.
`AI_ANALYSIS`는 `contracts/ai_analysis_mock.json` 계약서 필드명과 1:1로 맞춰서 구현했으나,
`case_type` 카테고리 목록·`urgency_level`/`eligibility` 값 표기·`checklist_json` 항목은
아직 팀 회의로 확정 전이라 자유 문자열/JSON으로 열어둔 상태 (값이 나중에 바뀔 수 있음).
인증(로그인/비밀번호)은 아직 미구현.

모든 요청/응답 Body는 `application/json` (파일 업로드만 `multipart/form-data`).

---

## 공통 에러 응답

리소스가 없으면(`NotFoundException`) `GlobalExceptionHandler`(`common/exception/`)가 아래 형식으로 404를 내려줍니다.
(User/Consultation/Attachment/AiAnalysis 서비스가 각자 예외를 던지던 걸 여기 한 곳으로 모음)

```json
{
  "timestamp": "2026-07-20T05:00:18.393Z",
  "status": 404,
  "error": "Not Found",
  "message": "상담을 찾을 수 없습니다: 999",
  "path": "/api/consultations/999"
}
```

| status | 상황 |
|---|---|
| 400 | 요청 body 파싱 실패 (JSON 형식 오류 등) |
| 404 | 경로의 id에 해당하는 리소스 없음 |
| 405 | 해당 경로에 정의되지 않은 HTTP 메서드 호출 |

---

## User (`/api/users`)

상담원 계정. `Consultation`이 참조하는 최소 범위만 구현 — 수정/삭제, 비밀번호/인증은 아직 없음.

### POST /api/users
상담원 생성.

Request
```json
{
  "name": "김상담",
  "role": "CONSULTANT",
  "email": "consultant1@example.com"
}
```
- `role`: `"CONSULTANT"` | `"ADMIN"`

Response `201`
```json
{
  "id": 1,
  "name": "김상담",
  "role": "CONSULTANT",
  "email": "consultant1@example.com",
  "createdAt": "2026-07-20T13:55:25.338075",
  "updatedAt": "2026-07-20T13:55:25.338075"
}
```

### GET /api/users
전체 목록. Response `200` — `UserResponse[]`

### GET /api/users/{id}
단건 조회. Response `200` — `UserResponse`, 없으면 `404`

---

## Consultation (`/api/consultations`)

상담 1건. `userId`로 `User`를 반드시 참조.

### POST /api/consultations
Request
```json
{
  "userId": 1,
  "title": "임금체불 상담",
  "inputText": "3개월치 임금을 못 받았습니다",
  "opponentName": "OO상사"
}
```
- `userId`: 필수, 존재하지 않으면 `404`
- `title`: 필수
- `inputText`: 선택 (녹음파일만 있고 텍스트 없는 상담 가능)
- `opponentName`: 선택
- `status`는 생성 시 무시되고 항상 `RECEIVED`로 시작

Response `201` — `ConsultationResponse` (아래 GET 참고)

### GET /api/consultations
전체 목록, 각 항목에 `attachments` 포함. Response `200` — `ConsultationResponse[]`

### GET /api/consultations/{id}
단건 조회. 없으면 `404`.

Response `200`
```json
{
  "id": 1,
  "userId": 1,
  "title": "임금체불 상담",
  "inputText": "3개월치 임금을 못 받았습니다",
  "opponentName": "OO상사",
  "status": "RECEIVED",
  "createdAt": "2026-07-20T13:55:25.651",
  "updatedAt": "2026-07-20T13:55:25.651",
  "attachments": [
    {
      "id": 1,
      "fileName": "rec.txt",
      "fileType": "음성",
      "extractedText": null,
      "uploadedAt": "2026-07-20T13:55:36.486",
      "downloadUrl": "/api/consultations/1/attachments/1"
    }
  ]
}
```

### PUT /api/consultations/{id}
부분 수정 — body에 넣은 필드만 갱신됨 (넣지 않은 필드는 유지).

Request (예: 상태만 변경)
```json
{ "status": "ANALYZING" }
```
- `status`: `"RECEIVED"` | `"ANALYZING"` | `"COMPLETED"`
- `title`, `inputText`, `opponentName`도 같은 방식으로 부분 갱신 가능
- `userId`는 이 엔드포인트로 변경 불가 (상담 담당자 재배정은 아직 미구현)

Response `200` — `ConsultationResponse`, 없으면 `404`

### DELETE /api/consultations/{id}
상담 삭제. 딸린 `Attachment`와 디스크에 저장된 파일도 함께 삭제됨 (cascade). Response `204`

---

## Attachment (`/api/consultations/{consultationId}/attachments`)

상담 1건에 여러 개 첨부 가능 (녹음파일, 증빙서류 등).

### POST /api/consultations/{consultationId}/attachments
`multipart/form-data`
- `file`: 업로드할 파일
- `fileType`: 자유 문자열 (예: `"음성"`, `"계약서"`, `"이미지"`, `"PDF"` — 고정 enum 아님)

Response `201`
```json
{
  "id": 1,
  "fileName": "rec.txt",
  "fileType": "음성",
  "extractedText": null,
  "uploadedAt": "2026-07-20T13:55:36.486",
  "downloadUrl": "/api/consultations/1/attachments/1"
}
```
- `extractedText`: STT/OCR 결과. 지금은 업로드 시 항상 `null` — ai-api 연동 시 채워질 필드 (아직 채우는 로직 없음)

### GET /api/consultations/{consultationId}/attachments/{attachmentId}
파일 원본 다운로드 (`Content-Disposition: attachment`). 없으면 `404`.

### DELETE /api/consultations/{consultationId}/attachments/{attachmentId}
첨부파일 삭제 — DB row와 디스크 파일 모두 제거. Response `204`

---

## AI_ANALYSIS (`/api/consultations/{consultationId}/analyses`)

`contracts/ai_analysis_mock.json` 계약서 필드명과 **1:1로 매칭**됨 (요청/응답 JSON은 snake_case).
상담 1건에 여러 번 재분석이 가능하다고 보고 1:N으로 설계함 (재분석 이력 보존).

⚠️ **주의**: `case_type` 카테고리 목록, `urgency_level`/`eligibility` 값 표기, `checklist_json` 항목은
아직 팀 회의로 확정 전이라 자유 문자열/JSON으로 열어둔 상태. 확정되면 값이 바뀔 수 있음.
`case_subtype`은 계약서 v0.1엔 없던 필드로, `case_type` 세부유형 용도로 추가 결정됨.

### POST /api/consultations/{consultationId}/analyses
ai-api가 분석을 끝낸 뒤 결과를 저장할 엔드포인트.

Request
```json
{
  "summary": "2025년 4월부터 3개월분 임금 약 600만원을 지급받지 못한 임금체불 사건",
  "case_type": "임금체불",
  "case_subtype": "정기임금 미지급",
  "urgency_level": "중",
  "eligibility": "대상후보",
  "extracted_json": { "당사자": [...], "금액": 6000000, "날짜": {...}, "사건개요": "..." },
  "missing_info_json": ["근로계약서", "급여명세서", "통장 입금내역"],
  "checklist_json": [{ "항목": "관할 확인", "결과": "충족" }],
  "recommendation_json": { "법령": [...], "판례": [...], "유사사례": [] },
  "timeline_json": [{ "날짜": "2025-01", "내용": "입사" }],
  "cluster_result_json": [],
  "estimated_time": null
}
```
- `consultation_id`는 body에 넣지 않음 — URL 경로에서 받음 (Attachment 업로드와 같은 방식)
- `_json`으로 끝나는 필드는 구조가 자유로운 JSON (객체/배열 무엇이든 가능) — DB엔 Postgres `jsonb`로 저장됨

Response `201` — 계약서와 동일한 형태 + `analysis_id`, `consultation_id`, `created_at` 포함

### GET /api/consultations/{consultationId}/analyses
해당 상담의 분석 결과 전체 (재분석 이력 포함). 상담이 없으면 `404`.

### GET /api/consultations/{consultationId}/analyses/{analysisId}
단건 조회. 없으면 `404`.

### PUT /api/consultations/{consultationId}/analyses/{analysisId}
부분 수정 — body에 넣은 필드만 갱신 (Consultation의 PUT과 같은 방식).

### DELETE /api/consultations/{consultationId}/analyses/{analysisId}
분석 결과 삭제. Response `204`

상담(Consultation) 삭제 시 딸린 AI_ANALYSIS도 함께 삭제됨 (cascade).

---

## 파일 저장 방식

로컬 디스크, 기본 경로 `./uploads` (환경변수 `UPLOAD_DIR`로 변경 가능). `uploads/{consultationId}/{uuid}_{원본파일명}` 구조로 저장. Git에는 포함 안 됨(gitignore).

---

## 아직 없는 것

- `case_type`/`urgency_level`/`eligibility`/`checklist_json` 값 확정 (팀 회의 대기 중)
- 인증/로그인 (`SESSION`, `OAUTH`), `User` 수정/삭제, 비밀번호 처리
- `GENERATED_DOCUMENT`, `LEGAL_TEMPLATE`, `CONSULTATION_LOG`
- 자동화 테스트, 헬스체크 엔드포인트
