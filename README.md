# 이클래스 크롤러

대학교 이클래스에서 수강 과목의 모든 데이터를 자동 추출하여 JSON으로 저장하는 프로그램.

## 개요

- **대상 사이트**: Moodle 기반 LMS
- **인증 방식**: Playwright 브라우저 자동화로 SSO 로그인 처리
- **동작 방식**: 스캔(구조 분석) → 추출(데이터 수집) 2단계 파이프라인
- **출력 형식**: JSON (통합 + 과목별 개별 파일)

## 추출 가능한 데이터

| 데이터 | 설명 |
|--------|------|
| **강의계획서** (syllabus) | 과목명, 교수정보, 강의개요/목표, 주차별 계획, 평가비율, 교재 |
| **성적** (grades) | 카테고리별 성적 (출석, 중간, 기말, 과제 등) |
| **출석** (attendance) | 주차별 교시별 출결 기록 (출석/결석/지각/조퇴) |
| **게시판** (boards) | 과목공지, 질의응답, 학습자료실 등 게시판 글 목록 |
| **활동/과제** (activities) | 과목 페이지의 섹션별 활동 모듈 구조 |
| **캘린더** | 전체 일정/이벤트 (AJAX API) |
| **수업자료** (materials) | 업로드된 파일 다운로드 (PDF, PPT 등) |

## 작동 구조

```
[로그인]  Playwright → SSO 인증 → 세션 확보
    │
[Phase 1: 구조 분석]  각 과목 페이지 스캔
    │   ├─ 네비게이션 메뉴에서 기능 탐색 (강의계획서, 성적, 출석 등)
    │   ├─ 활동 모듈 타입 분석 (게시판, 과제, 폴더, 퀴즈 등)
    │   ├─ 게시판 목록 수집
    │   └─ 다운로드 가능 리소스 수집
    │
[스캔 결과 요약 출력]  무엇을 추출할지 미리 보여줌
    │
[Phase 2: 데이터 추출]  스캔 결과 기반으로 존재하는 것만 추출
    │   ├─ 각 추출기가 해당 페이지를 방문하여 HTML 파싱
    │   ├─ 캘린더는 AJAX API 호출
    │   └─ 수업자료는 Playwright API로 파일 다운로드
    │
[저장]  JSON 파일 출력
```

## 프로젝트 구조

```
eclass_crawler/
├── main.py              # CLI 진입점, 전체 파이프라인 오케스트레이션
├── config.py            # 설정 (URL, 학기, 딜레이 등)
├── browser.py           # Playwright 브라우저 세션 매니저
├── scanner.py           # 과목별 동적 구조 분석기
├── auth.py              # SSO 인증 모듈 (독립 실행용)
├── probe.py             # Moodle API 가용 범위 탐색 도구
├── requirements.txt     # Python 의존성
├── .env                 # 로그인 자격증명 (git 제외)
├── extractors/
│   ├── courses.py       # 수강 과목 목록
│   ├── syllabus.py      # 강의 계획서
│   ├── grades.py        # 성적
│   ├── attendance.py    # 출석 기록
│   ├── notices.py       # 게시판 (공지/자료실)
│   ├── assignments.py   # 활동/과제
│   ├── calendar.py      # 캘린더 이벤트 (AJAX API)
│   └── materials.py     # 수업자료 파일 다운로드
└── output/              # 출력 디렉토리 (git 제외)
    ├── 2026-1_semester.json        # 통합 JSON
    ├── scan_result.json            # 스캔 결과
    ├── courses/                    # 과목별 개별 JSON
    │   ├── 자료구조_-_2분반_[컴퓨터·AI학부]_(1학기).json
    │   ├── 데이터베이스_-_2분반_[컴퓨터·AI학부]_(1학기).json
    │   └── ...
    └── downloads/                  # 다운로드한 수업자료
        ├── 객체지향설계와패턴/
        │   └── (배포)2026-01-...강의 소개.pdf
        └── ...
```

## 설치

```bash
# 의존성 설치
pip install -r requirements.txt

# Playwright 브라우저 설치
python -m playwright install chromium
```

## 설정

`.env` 파일에 이클래스 로그인 정보 입력:

```
ECLASS_USERNAME=학번
ECLASS_PASSWORD=비밀번호
```

## 사용법

```bash
# 전체 과목 전체 데이터 추출
python main.py

# 수강 과목 목록 확인
python main.py --list

# 과목별 구조 분석만 (추출 없이 무엇이 있는지 확인)
python main.py --scan

# 특정 과목만 추출 (번호 또는 이름)
python main.py --course 1 3
python main.py --course 자료구조

# 특정 데이터만 추출
python main.py --only syllabus grades

# 수업자료 파일 다운로드 포함
python main.py --download
python main.py --course 5 --download

# 조합
python main.py --course 2 --only syllabus attendance --download

# 테스트 (첫 과목만)
python main.py --test
```

## 출력 JSON 형식

### 통합 JSON (`output/2026-1_semester.json`)

```json
{
  "semester": "2026-1",
  "extracted_at": "2026-03-03T16:00:00",
  "course_count": 6,
  "calendar_events": [...],
  "courses": [
    {
      "id": 51011,
      "name": "자료구조 - 2분반",
      "professor": "선석규",
      "syllabus": { "교과목명": "...", "강의목표": "...", ... },
      "grades": [...],
      "attendance": { "records": [...] },
      "boards": { "과목공지": { "posts": [...] }, ... },
      "activities": { "sections": [...], "activities": [...] }
    },
    ...
  ]
}
```

### 과목별 JSON (`output/courses/과목명.json`)

통합 JSON의 단일 과목 데이터와 동일한 구조. 각 과목을 개별적으로 활용할 때 사용.

## 기술 스택

- **Python 3.11+**
- **Playwright** - 브라우저 자동화 (SSO 로그인, 페이지 탐색, 파일 다운로드)
- **httpx** - AJAX API 호출 (캘린더 이벤트)
- **pydantic** - 데이터 모델링 (확장용)
- **python-dotenv** - 환경변수 관리
