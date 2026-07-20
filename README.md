# Big Project

법률상담 AI 지원 시스템

## 구조

```
backend/
├── core-api/     Spring Boot (인증, 상담 CRUD, DB)
└── ai-api/       FastAPI (AI 파이프라인 + kordoc 문서 처리)
frontend/         React + Vite
contracts/        팀 공용 JSON 계약서
```

## 설치 방법

### 사전 요구사항
- **Python 3.12** (3.13/3.14는 일부 패키지 설치 실패)
- Node.js
- JDK 17+

### 1. 프론트엔드
```
cd frontend
npm install
npm run dev
```

### 2. AI API (FastAPI + kordoc)
```
cd backend/ai-api

py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

npm install
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

## 법률서식 데이터
용량(약 101MB) 문제로 git 미포함.
[helplaw24](https://www.helplaw24.go.kr/)에서 받아 `backend/ai-api/data/templates/`에 배치.

## kordoc 사용 참고
```
# 파싱 (파일명에 공백 있으면 따옴표 필수)
node_modules\.bin\kordoc.cmd "서식.hwp" -o 서식.md

# 서식 필드 확인
node_modules\.bin\kordoc.cmd fill "서식.hwp" --dry-run

# 초안 생성 (편집한 마크다운을 원본에 반영)
node_modules\.bin\kordoc.cmd patch "서식.hwp" 편집.md -o 결과.hwpx
```
- 초안 생성은 **patch 방식** 사용. `fill`은 표 구조 서식에서만 동작
- 파싱 시 `images/` 폴더에 이미지 자동 추출 (gitignore 대상)

## 환경 변수
`.env.example`을 복사해 `.env` 생성 후 값 입력 (ai-api용 — core-api는 `.env`를 안 읽음, 위 3번 참고)