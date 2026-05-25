# Imoji AI Agents 가이드

## 프로젝트 개요
**Imoji**는 사용자의 캐릭터 스케치로부터 카카오톡 이모티콘(320×320 GIF)을 자동 생성하는 Next.js 기반 웹서비스입니다.

### 핵심 특징
- **입력**: 캐릭터 스케치 이미지 1장 + 스타일 선택 + 원하는 상황 1~24개 선택
- **출력**: 선택한 개수만큼의 320×320 GIF + ZIP 다운로드
- **목표**: 원본 스케치의 캐릭터 정체성 100% 유지하며 상황별 표정/동작 생성

---

## 아키텍처 및 처리 흐름

### 전체 흐름
```
사용자 → 스케치 업로드 + 스타일 선택 → Job 생성 (POST /api/jobs)
       ↓
       백그라운드 Worker 실행
       ├─ 캐릭터 프로필 분석 (Vision API)
       ├─ 상황별 GIF 1~24종 생성 (Image Generation API)
       └─ 후처리: 정렬, 라벨 오버레이, GIF 변환
       ↓
사용자 → 상태 조회 (GET /api/jobs/:id) → 결과 다운로드
```

### 주요 처리 단계

#### 1단계: 작업 생성
- **파일**: [app/page.tsx](app/page.tsx), [app/api/jobs/route.ts](app/api/jobs/route.ts)
- **역할**: 사용자 입력 검증 → Job 저장 → 상태 `queued` 설정
- **중요**: 원본 이미지가 `uploadPath`에 저장됨

#### 2단계: 캐릭터 프로필 분석
- **파일**: [lib/characterProfile.ts](lib/characterProfile.ts), [lib/worker.ts](lib/worker.ts)
- **역할**: Vision 모델이 스케치 분석 → 캐릭터 시각적 특징을 텍스트로 추출
- **목적**: 이후 모든 생성에서 같은 캐릭터 유지의 기준점

#### 3단계: 상황별 GIF 생성
- **파일**: [lib/prompts.ts](lib/prompts.ts), [lib/generator.ts](lib/generator.ts)
- **역할**: 각 상황마다 다음을 입력으로 전달
  - 원본 이미지 (reference image)
  - 캐릭터 프로필
  - 스타일 프롬프트
  - 상황별 프롬프트
  - 16프레임 액션 지시
- **결과**: 4×4 스프라이트 시트 생성
- **후처리**: 프레임 정렬 → 한글 라벨 오버레이 → 320×320 GIF 변환

#### 4단계: 결과 제공
- **파일**: [app/api/jobs/[jobId]/download/route.ts](app/api/jobs/[jobId]/download/route.ts)
- **역할**: 생성된 GIF 조회 및 ZIP 다운로드 제공

---

## 주요 데이터 및 상수

### 상황별 설정
- **파일**: [data/situations.json](data/situations.json)
- **구조**: `{ id, label, koreanLabel, actionPrompts }`
- **중요**: 한글 라벨은 모델 출력이 아니라 후처리 오버레이로 적용

### 스타일 설정
- **파일**: [lib/constants.ts](lib/constants.ts)
- **역할**: 스타일별 프롬프트 템플릿 관리
- **6가지 스타일**: 말랑 2D, 깔끔한 라인, 귀여운 SD, 수채화, 클레이, 픽셀아트

### 타입 정의
- **파일**: [lib/types.ts](lib/types.ts)
- **주요**: `GenerationJob`, `Situation`, `Style` 타입

---

## Agent 작업 범위 및 주의사항

### ✅ Agent가 할 수 있는 작업
1. **UI/기능 개선**: 업로드 → 선택 → 다운로드 흐름 개선
2. **프롬프트 튜닝**: [lib/prompts.ts](lib/prompts.ts)의 프롬프트 수정/개선
3. **상황 추가/수정**: [data/situations.json](data/situations.json)에 상황 추가
4. **스타일 추가**: [lib/constants.ts](lib/constants.ts)에 새 스타일 추가
5. **후처리 로직**: [lib/generator.ts](lib/generator.ts)의 프레임 정렬, 라벨 오버레이 개선
6. **API 엔드포인트**: 새로운 조회/관리 기능 추가
7. **에러 처리/로깅**: 작업 실패 시 에러 메시지/로깅 개선

### ⚠️ 주의사항
1. **절대 유지할 사항**:
   - 원본 이미지를 `inlineData` reference로 전달 (캐릭터 정체성 유지)
   - 16프레임 스프라이트 시트 구조 (4×4)
   - 320×320 GIF 포맷 고정
   - 한글 라벨은 모델 출력이 아닌 후처리 오버레이 적용

2. **테스트 시**:
   - `GENERATION_MODE=source_motion` 설정 시 preview 모드 (원본 이미지 변형)
   - 실제 생성은 `image_reference_sprite` 모드 사용
   - API 키 확인 후 테스트 실행

3. **문서 업데이트**:
   - 주요 구조 변경 시 [docs/design.md](docs/design.md) 업데이트
   - 요구사항 변경 시 [docs/requirements.md](docs/requirements.md) 업데이트

---

## 주요 파일 맵

| 파일 | 역할 |
|------|------|
| [app/page.tsx](app/page.tsx) | 메인 UI (업로드/선택/결과) |
| [app/api/jobs/route.ts](app/api/jobs/route.ts) | Job 생성 API |
| [app/api/jobs/[jobId]/route.ts](app/api/jobs/[jobId]/route.ts) | Job 상태 조회 API |
| [lib/worker.ts](lib/worker.ts) | 백그라운드 워커 (비동기 처리) |
| [lib/characterProfile.ts](lib/characterProfile.ts) | 캐릭터 분석 (Vision API) |
| [lib/generator.ts](lib/generator.ts) | GIF 생성 + 후처리 |
| [lib/prompts.ts](lib/prompts.ts) | 프롬프트 템플릿 |
| [lib/constants.ts](lib/constants.ts) | 스타일, 생성 모드 상수 |
| [data/situations.json](data/situations.json) | 24개 상황 정의 |

---

## 참고 링크
- [요구사항 문서](docs/requirements.md)
- [설계 문서](docs/design.md)
- [프로젝트 README](README.md)
