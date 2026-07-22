# Big Project

법률상담 AI 지원 시스템

## 구조

```
backend/
├── core-api/     Spring Boot (인증, 상담 CRUD, DB)
└── ai-api/       FastAPI (AI 파이프라인 + HWPX 서식 처리)
frontend/         React + Vite
contracts/        팀 공용 JSON 계약서
```

## 설치 방법

### 사전 요구사항
- **Python 3.12** (3.13/3.14는 일부 패키지 설치 실패)
- Node.js (frontend용)
- JDK 17+ (core-api용)

### 1. 프론트엔드
```
cd frontend
npm install
npm run dev
```

### 2. AI API (FastAPI)
```
cd backend/ai-api

py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

실행:
```
uvicorn app.main:app --reload --port 8001
```
API 문서: http://localhost:8001/docs

**PowerShell에서 스크립트 실행이 막히는 경우**
```powershell
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```
또는 cmd에서 실행

### 3. Spring Boot (core-api)

**사전 준비: 로컬 Postgres에 DB 생성**
```
createdb bigproject
```
(이미 `bigproject` DB가 있으면 생략)

**pgvector는 아직 필요 없음** — `database/postgres/init.sql`(`CREATE EXTENSION vector`)은 유사사건 검색 등
임베딩 기능이 실제로 코드에 붙기 전까지는 안 돌려도 지금 core-api는 정상 동작합니다. 관련 기능 브랜치가
머지되면 이 섹션 업데이트 예정.

**실행**

IntelliJ에서 `backend/core-api` 폴더 열면 자동 세팅되고, 터미널로는:
```
cd backend/core-api
gradlew bootRun        # cmd
.\gradlew bootRun       # PowerShell
./gradlew bootRun       # Git Bash
```
`http://localhost:8080`에서 실행됨. API 문서: [`docs/api.md`](docs/api.md)

**⚠️ `.env`는 core-api엔 안 먹힘**
`ai-api`는 python-dotenv로 `.env`를 직접 읽지만, Spring Boot는 `.env` 파일을 자동으로 읽지 않습니다.
`application.yaml`이 `${DB_URL:...}` 형태로 **OS 환경변수**를 참조하는 구조라서, DB 접속 정보를 기본값(`localhost:5432`, `postgres`/`postgres`)과 다르게 쓰려면 `.env` 대신 실제 환경변수를 설정하거나 IntelliJ 실행 설정(Run Configuration)에 넣어야 합니다. 기본값 그대로 쓸 거면 아무것도 안 해도 됩니다.

## 법률서식 데이터 (HWPX)

서식은 **HWPX 형식**으로 `backend/ai-api/서식_hwpx/`에 배치
(대분류/소분류 폴더 구조, 출처: [helplaw24](https://www.helplaw24.go.kr/)).
용량 문제로 git 미포함 — 팀 드라이브에서 받아서 배치.

> **왜 HWPX인가**: 원본 HWP는 한컴 비공개 바이너리라 오픈소스로는
> 표 안에 값을 넣을 수 없음. HWPX는 공개 표준(KS X 6101)이라
> python-hwpx로 표 안까지 자유롭게 채울 수 있어 서식을 HWPX로 표준화함.

**신규 서식 추가 시**: 한컴오피스 설치된 PC에서
`tools/convert_all_hwpx.py`로 HWP→HWPX 일괄 변환 (1회성 작업)

## 서식 추천·초안 생성 (ai-api/services/)

```
services/form_recommender.py   분석 JSON → 추천 서식 목록 + 근거
services/form_drafter.py       서식명 + 추출정보 → 초안 HWPX 생성
```

- 추천: case_subtype으로 서식 후보를 좁힌 뒤 GPT가 상담 내용 기반으로
  우선순위와 근거를 제시
- 초안: 추출정보에 있는 값만 서식에 채우고(환각 차단), 없는 값은
  missing_info로 반환하여 상담원이 추가 확인
- 서식 선택은 상담원이 결정 (AI는 추천·초안 보조만 수행, HITL)

테스트:
```
cd backend/ai-api
python test_flow.py    # 추천→초안 전체 흐름 (목업 3건)
```

## 환경 변수
`.env.example`을 복사해 `.env` 생성 후 값 입력 (ai-api용 — core-api는 `.env`를 안 읽음, 위 3번 참고)