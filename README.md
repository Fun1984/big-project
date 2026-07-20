# Big Project

법률상담 AI 지원 시스템

## 구조

```
backend/
├── core-api/     Spring Boot (인증, 상담 CRUD, DB)
└── ai-api/       FastAPI (STT, 구조화 분석, RAG, 서식 초안 생성)
                  └ kordoc(Node)로 hwp/hwpx 문서 처리
frontend/         React + Vite
contracts/        팀 공용 JSON 계약서
```

## 설치 방법

### 1. 프론트엔드

```
cd frontend
npm install
npm run dev
```

### 2. AI API (FastAPI + kordoc)

Python과 Node.js가 모두 필요합니다.

```
cd backend/ai-api

python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

npm install
```

실행:
```
uvicorn app.main:app --reload --port 8001
```

**PowerShell에서 npm이 실행되지 않는 경우**

`npm.ps1 파일을 로드할 수 없습니다` 오류가 나면 아래 중 하나로 해결합니다.

```powershell
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```
또는 cmd(명령 프롬프트)에서 실행합니다.

### 3. Spring Boot

IntelliJ에서 `backend/core-api` 폴더를 열면 자동 세팅됩니다.

## 법률서식 데이터

용량(약 101MB) 문제로 git에 포함하지 않습니다.
[helplaw24](https://www.helplaw24.go.kr/)에서 내려받아 아래 경로에 배치하세요.

```
backend/ai-api/data/templates/
```

## kordoc 사용 참고

문서 파싱 및 서식 초안 생성에 사용합니다. Node 서버 없이 CLI로 호출합니다.

```
# 파싱 (파일명에 공백이 있으면 따옴표 필수)
node_modules\.bin\kordoc.cmd "서식.hwp" -o 서식.md

# 서식 필드 확인
node_modules\.bin\kordoc.cmd fill "서식.hwp" --dry-run

# 초안 생성 (마크다운 편집 후 원본에 반영)
node_modules\.bin\kordoc.cmd patch "서식.hwp" 편집.md -o 결과.hwpx
```

- 초안 생성은 **patch 방식**을 사용합니다. `fill`은 표 구조 서식에서만 동작하며, 소장처럼 줄글 형태의 서식에서는 필드를 감지하지 못합니다.
- 파싱 시 `images/` 폴더에 이미지가 자동 추출됩니다. (gitignore 대상)

## 환경 변수

`.env.example`을 복사해 `.env`를 만들고 값을 채웁니다.

```
copy .env.example .env
```