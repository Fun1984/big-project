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

### 3. Spring Boot
IntelliJ에서 `backend/core-api` 폴더 열면 자동 세팅

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
`.env.example`을 복사해 `.env` 생성 후 값 입력