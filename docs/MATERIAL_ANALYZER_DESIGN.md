# 수업자료 분석/요약 기능 설계

> 상태: 설계 단계
> 위치: `extensions/material_analyzer.py` (예정)

## 개요

이클래스에서 다운로드한 수업자료(PDF, PPT, HWP 등)를 자동으로 텍스트 추출 → LLM 요약 → 옵시디언 마크다운 노트로 변환하는 확장 모듈.

```
output/downloads/자료구조/*.pdf
        │
        ▼
  [텍스트 추출] PyMuPDF, python-pptx, python-hwp
        │
        ▼
  [LLM 요약] OpenAI / Anthropic / Ollama (로컬)
        │
        ▼
  The Record/3_Areas/School/자료구조/notes/
        ├── 01주차_강의소개.md
        ├── 02주차_배열과연결리스트.md
        └── ...
```

## 핵심 결정 사항

### 1. LLM 선택

| 옵션 | 장점 | 단점 |
|------|------|------|
| **OpenAI (GPT-4o-mini)** | 저렴, 빠름, 긴 컨텍스트 | API 키 필요, 비용 발생 |
| **Anthropic (Claude)** | 긴 문서에 강함, 200K 컨텍스트 | API 키 필요, 비용 발생 |
| **Ollama (로컬)** | 무료, 오프라인, 프라이버시 | GPU 필요, 품질 상대적 저하 |
| **하이브리드** | 로컬 우선 → 실패 시 API 폴백 | 구현 복잡도 |

**결정 필요**: 기본값을 어떤 것으로 할지. `.env`에서 `LLM_PROVIDER` 설정으로 선택 가능하게 하되, 기본값은?

### 2. 텍스트 추출 라이브러리

| 파일 형식 | 라이브러리 | 비고 |
|-----------|-----------|------|
| PDF | `PyMuPDF` (fitz) | 텍스트 + 이미지 추출 가능 |
| PPTX | `python-pptx` | 슬라이드별 텍스트/노트 |
| HWP | `python-hwp` 또는 `olefile` | 한글 파일, 지원 불완전할 수 있음 |
| DOCX | `python-docx` | Word 문서 |
| 이미지 (스캔PDF) | `pytesseract` + `Pillow` | OCR, 선택적 |

### 3. 요약 프롬프트 설계

**목표**: 수업자료를 "복습용 노트"로 변환

```
## 프롬프트 구조

시스템: 당신은 대학교 수업자료를 학습 노트로 변환하는 도우미입니다.

사용자 입력:
- 과목명: {course_name}
- 자료 제목: {material_title}  
- 주차: {week} (추정 가능하면)
- 내용: {extracted_text}

요청:
1. 핵심 개념을 구조화된 마크다운으로 정리
2. 중요 정의/공식/알고리즘은 별도 블록으로 강조
3. 이해를 돕는 한 줄 설명 추가
4. 시험에 나올 법한 핵심 포인트 정리
```

### 4. 출력 노트 포맷

```markdown
---
type: lecture-note
course: "자료구조"
week: 3
source: "03-Linked_List.pdf"
generated: "2026-03-03"
tags:
  - school
  - lecture-note
  - 자료구조
---

# 3주차: 연결 리스트

> 원본: [[자료구조]] 수업자료 `03-Linked_List.pdf`

## 핵심 개념

### 단일 연결 리스트
- ...

### 이중 연결 리스트
- ...

## 주요 정의/공식

> **시간 복잡도**
> - 탐색: O(n)
> - 삽입 (head): O(1)
> - 삭제: O(n)

## 시험 대비 포인트
1. ...
2. ...
```

## 아키텍처

```
extensions/
├── material_analyzer.py     # 메인 오케스트레이션
├── text_extractor.py        # 파일 → 텍스트 변환
├── llm_summarizer.py        # 텍스트 → 요약 (LLM 호출)
└── note_generator.py        # 요약 → 옵시디언 마크다운

sync_config.py               # LLM_PROVIDER, API_KEY 등 설정 추가
```

### 데이터 흐름

```
1. material_analyzer.analyze(course_name, downloads_dir)
   │
   ├── 2. text_extractor.extract(file_path) → raw_text
   │       - PDF: PyMuPDF
   │       - PPTX: python-pptx  
   │       - 기타: 확장자별 분기
   │
   ├── 3. llm_summarizer.summarize(raw_text, context) → summary_dict
   │       - 프롬프트 조립
   │       - LLM API 호출 (provider별 분기)
   │       - JSON 파싱 또는 마크다운 파싱
   │
   └── 4. note_generator.generate(summary, metadata) → markdown_str
           - frontmatter 생성
           - 구조화된 마크다운 조립
           - The Record 볼트에 저장
```

## CLI 인터페이스

```bash
# 전체 과목 전체 자료 분석
python -m extensions.material_analyzer

# 특정 과목만
python -m extensions.material_analyzer --course 자료구조

# 특정 파일만
python -m extensions.material_analyzer --file "output/downloads/자료구조/03-Linked_List.pdf"

# main.py 통합
python main.py --download --analyze
```

## 비용 추정

- 수업자료 1개 (10~30페이지): 약 2,000~8,000 토큰
- GPT-4o-mini 기준: 약 $0.001~$0.004 / 자료
- 6과목 × 15주 × 평균 2개 = 180개 자료
- **학기 전체 예상 비용: ~$0.5 이내**

## 구현 우선순위

1. **Phase 1**: PDF 텍스트 추출 + GPT-4o-mini 요약 (최소 동작)
2. **Phase 2**: PPTX/HWP 지원 추가
3. **Phase 3**: Ollama 로컬 LLM 지원
4. **Phase 4**: 주차 자동 감지, 이전 요약과 연결
5. **Phase 5**: OCR 지원 (스캔 PDF)

## 미결 사항

- [ ] 기본 LLM provider 결정 (OpenAI vs Ollama)
- [ ] 주차 번호 자동 추정 로직 (파일명/순서 기반? 강의계획서 매칭?)
- [ ] 이미 요약한 파일의 재처리 방지 (해시 기반 캐시?)
- [ ] 요약 품질 검증 방법
- [ ] 수업자료 외 게시판 첨부파일도 대상에 포함할지
