# core-api REST API

Base URL: `http://localhost:8080`

현재 구현된 범위: **User / Consultation / Attachment** CRUD.
`AI_ANALYSIS`는 `contracts/ai_analysis_mock.json` 계약서가 확정된 뒤 필드명을 그대로 맞춰서 추가 예정 (대기 중). 인증(로그인/비밀번호)은 아직 미구현.

모든 요청/응답 Body는 `application/json` (파일 업로드만 `multipart/form-data`).

---

## 공통 에러 응답

리소스가 없을 때 등은 Spring Boot 기본 에러 포맷으로 내려갑니다.

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

## 파일 저장 방식

로컬 디스크, 기본 경로 `./uploads` (환경변수 `UPLOAD_DIR`로 변경 가능). `uploads/{consultationId}/{uuid}_{원본파일명}` 구조로 저장. Git에는 포함 안 됨(gitignore).

---

## 아직 없는 것

- `AI_ANALYSIS` — 계약서(`contracts/README_ai_analysis_contract.md`) 확정 대기 중
- 인증/로그인 (`SESSION`, `OAUTH`), `User` 수정/삭제, 비밀번호 처리
- `GENERATED_DOCUMENT`, `LEGAL_TEMPLATE`, `CONSULTATION_LOG`
- 자동화 테스트, 헬스체크 엔드포인트
