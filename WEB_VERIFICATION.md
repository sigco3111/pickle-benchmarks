# 검증 기록 (WEB_VERIFICATION)

**원칙: 하지 않은 검증은 하지 않았다고 적는다.** 아래의 "검증한 것"은 실제로 실행한 결과이고, "검증하지 못한 것"은
환경( GPU·프린터·실물 부품 없음) 때문에 확인할 수 없었던 항목이다. 과제별 상세 로그는 하드웨어의 경우 저장소 안
`hardware/docs/logs/`에 원문이 있고, 웹 과제의 실행 기록은 2026-11-19 통합 단계에서 다시 실행해 이 문서에 값으로 남겼다.

- 실행 주체: **Pickle** (세부 모델명·effort **미지정**)
- 과제 출처: 유튜버 코드팩토리의 메타프롬프트 ([ORIGINAL_PROMPTS.txt](ORIGINAL_PROMPTS.txt))
- 작성: 2026-11-19

---

## 1. 검증 환경

| 항목 | 실제 환경 |
|---|---|
| OS | Linux 컨테이너 |
| GPU | **없음** — Chromium은 SwiftShader(소프트웨어 래스터라이저)로 WebGL 실행 |
| 브라우저 | Chromium headless / Chrome for Testing (헤드리스), 버전 158–159 |
| 프린터·실물 부품 | **없음** |
| ARM 크로스 컴파일러 | ARM GNU Toolchain 12.3.rel1 (직접 내려받아 사용) |
| pico-sdk | 1.5.1 + tinyusb 0.15.0 |
| 빌드 도구 | CMake·Ninja(pip wheel), 호스트 C는 Zig 0.13(`zig cc` = clang 18.1.6) |
| CAD 커널 | OpenSCAD 없음 → Python CSG(trimesh 5.2.1 + manifold3d)로 STL 생성 |
| 네트워크 | three.js·GSAP는 CDN(unpkg/jsDelivr)에서 로드 |

이 구성은 **검증용**이다. 사용자가 재현할 때는 일반적인 GPU 있는 브라우저, `gcc`, OpenSCAD, 실물 부품이면 충분하다.

## 2. 요약

| # | 과제 | 정적 검사 | 헤드리스 브라우저 | 단위·통합 테스트 | 빌드/CAD |
|---|---|---|---|---|---|
| 01 | 궁전 브릭 모션 | ✅ 전체 통과 | ✅ 콘솔 오류 0 | ✅ 집계·재현성 스크립트 | — |
| 02 | 한강시 게임 | ✅ `node --check` | ⚠️ 로드·시뮬레이션 정상, **셰이더 콘솔 오류 1건** | ✅ 60 Hz 결정론 시뮬레이션 | — |
| 03 | 소개 페이지 | ✅ 태그·괄호 균형 | ✅ 콘솔 오류 0 (6구간·테마·모바일·폴백) | — | — |
| 04 | 단편 소설 | ✅ 파서·문자열 대조 | ✅ 로드·렌더 확인 | — | — |
| 05 | 촬영 컨트롤러 | ✅ SVG·넷리스트 대조 | ✅ 프리뷰 콘솔 오류 0 | ✅ 펌웨어 130검사 · 브리지 37테스트 | ✅ ARM 빌드 · STL 22검사 |
| — | 통합 문서·목차 | ✅ 태그 균형·내부 링크 200 | ✅ 콘솔 오류 0 | — | — |

---

## 3. 과제별 검증

### 3-1. 궁전 모션 그래픽 — `palace.html`

**정적 검사 (전체 통과)**

- 단일 HTML, importmap으로 `three@0.170.0`만 CDN 사용, 외부 3D 파일 0.
- esprima `parseModule`로 55 KB 모듈 구문 검사 통과.
- dukpy로 코어 로직을 실행해 화면 표시값과 집계 일치 확인: 브릭·파트·단계 합계, 에러 0, 경고 3→0, 치수.
- 시간 함수 경계: `t=-5 ≡ 0`, `t=40 ≡ 32`, 같은 `t` 재현, 모든 진행값 0..1, 인벤토리 5장·통계 6칸 경계.

**헤드리스 Chromium(SwiftShader)**

- 콘솔 에러 0, 페이지 예외 0.
- 같은 `t`를 두 번 그리면 인스턴스 컬러 버퍼가 동일(결정론).
- 구간 점프 `t=17.02`, 재생 진행, 슬라이더 `25.5`, 클램프 `[-5→0, 99→32]`, 820 px·1440 px 리사이즈 정상.

**통합 단계 재측정 (2026-11-19, 1440×900)**

| 항목 | 값 |
|---|---|
| 브릭 | **1,963** |
| 파트 | 월대 304 · 기둥 636 · 공포 308 · 지붕 475 · 마당 240 |
| 단계 | 21 |
| 겹침/에러 | 0 |
| 결합부 경고 | 3 → 보강 6개 → 0 |
| 바운딩 | 4,200 × 2,500 × 3,600 cm (몸체 3,000 × 2,100) |
| 콘솔 | 오류 0 |

**검증하지 못한 것**: 실제 GPU에서의 프레임 시간(모션은 32초 타임라인 기반이라 fps를 성능 주장으로 쓰지 않음), 색·형태의 미학적 평가.

### 3-2. 한강시 게임 — `hangang-city.html`

**정적 검사**

- `node --check`로 모듈 전체 추출 검사 → 문법 오류 0.
- 외부 3D/이미지 에셋 0, three.js 0.170.0만 CDN.

**헤드리스 Chrome(WebGL2/SwiftShader) 결정론 시뮬레이션**

| 시나리오 | 결과 |
|---|---|
| 강변도로 10초 주행 | 60 → 331 m, **122 km/h**, 충돌 0 |
| 고가 진입로(x=37) | 데크 **y=10** 진입, 난간에서 정지 |
| 주차빌딩 경사로 | **옥상 y=14** 주행 성공 |
| 드리프트 | 횡속도 −3.7 m/s(슬립 약 11°), 핸드브레이크 유무 비교 |
| 배달 미션 | 비콘 시작 → 목적지 판정 → `done=1` |
| 따돌리기 미션 | 30초 은신 → `done=1`, 수배·순찰차 해제 |
| 레이스 미션 | CP0 통과 → `index 0→1` |
| 도보 | 달리기 → 강변 둑 충돌 정지(물에 빠지지 않음) |
| 수배 | 상승 시 순찰차 3대 스폰 |

화면 캡처: [`screenshots/hangang-city-01-overview.png`](screenshots/hangang-city-01-overview.png) 외 3장(낮 스카이라인·주행 HUD·야간 조명·레이스 HUD).

**통합 단계 재검증에서 발견한 미해결 항목 (2026-11-19)**

- 증상: 로드 후 콘솔에 셰이더 컴파일 오류 1건.
  `THREE.WebGLProgram: Shader Error 0 — VALIDATE_STATUS false … MeshStandardMaterial … ERROR: 0:472: 'vColor' : undeclared identifier`,
  이어서 `WebGL: INVALID_OPERATION: useProgram: program not valid` 경고가 간헐 반복(관측 17초 동안 22회).
- 원인(코드 확인): `enableInstanceColor()`가 `#include <color_vertex>` 뒤에 `vInstColor = vColor;`를 조건 없이 붙인다.
  해당 재질이 처음 컴파일되는 시점에 인스턴스 색상 속성이 아직 없으면 `vColor`가 선언되지 않아 프로그램이 무효가 된다.
- 영향: 시작 후 장면·HUD·미니맵은 정상 렌더된다(상태값: 건물 764동, 네온 간판 170, 차량 61대, 램프 7). 다만 무효 프로그램을 쓰는 메시는 그려지지 않으므로 일부 요소가 보이지 않을 수 있다. 화면상 뚜렷한 누락은 확인하지 못했다.
- 상태: **원본은 고치지 않았다.** 벤치마크 결과물을 그대로 보존하기 위해서다. 복사본에 셰이더 가드
  (`#if defined(USE_COLOR) || defined(USE_INSTANCING_COLOR) || defined(USE_BATCHING_COLOR)` … `#else vInstColor = vec3(1.0)`)를
  적용해 시험한 결과 콘솔 오류 0, 상태값·화면 동일함을 확인했다. 적용 여부는 사용자 결정 사항으로 남긴다.

**검증하지 못한 것**: 실제 GPU에서의 **60 fps**(SwiftShader라 프레임 시간이 의미 없음), 오디오(넣지 않음), 터치 조작(데스크톱 키보드·마우스 기준).

### 3-3. 소개 페이지 — `model-intro.html`

**정적 검사**

- `html.parser` 태그 균형 오류 0, CSS 중괄호 172/172, JS 중괄호 233/233·괄호 967/967·대괄호 99/99.
- 외부 URL은 `three@0.170.0`, `gsap@3.12.5`(gsap·ScrollTrigger)뿐.
- 모델·제공사 이름 없음, 성능 수치는 `{{CONTEXT_WINDOW}}`·`{{BENCH_SCORE}}`·`{{TOKENS_PER_SEC}}`·`{{COST_PER_MTOK}}` 자리표시자.

**헤드리스 Chromium(SwiftShader)**

- 1440×900, 1920×1080, 1200×800, 390×844(모바일), reduced-motion 컨텍스트에서 로드 → 콘솔/페이지 오류 0.
- 6구간 전부 렌더, 다크 테마, 푸터, 리사이즈 재구축(6,900 → 4,600 파티클), GSAP 차단 폴백, WebGL 차단 안내 문구까지 확인.

**통합 단계 재확인 (1440×900)**

- `window.__pickle.ready=true`, 파티클 6,900, 테마 light, reduced=false, **fps 22(SwiftShader)**, 자리표시자 4개 검출, 콘솔 오류 0.

**검증하지 못한 것**: GPU 있는 실기기의 "모바일 60 fps"(여기서는 1440×900 10–27 fps, 480×320 17 fps에 그침), 실제 모바일 기기 레이아웃, 스크린 리더 접근성.

### 3-4. 단편 소설 — `novel.html` · `novel.md`

**정적 검사**

- `html.parser` 파싱: 닫히지 않은 태그 0, 여는/닫는 태그 불일치 0, CSS 중괄호 68/68.
- `novel.md`의 모든 문단·대사·날짜 표제가 `novel.html`에 존재하는지 문자열 대조 → 누락 0
  (장면 표제가 번호/제목 요소로 나뉜 5건 제외).
- 분량(Python 실측, 제목·구성 제외 본문): 공백 포함 **12,386자**, 공백 제외 **9,183자**, 원고지 **61.93매**(200자/매).
- 외부 폰트·스크립트·이미지 참조 0.

**통합 단계 재확인**

- HTTP 서버 + 헤드리스 Chromium: 상태 200, 콘솔 오류 0, `section` 6개(표지 포함), 화면 텍스트 13,208자(표지·머리말 포함), 버튼 4개(테마·글자 크기·목차).
- 원래 과제 작업에서는 이 환경의 브라우저가 `file://`·루프백을 거부해 렌더 스크린샷을 남기지 못했다. 통합 단계에서 로컬 서버로 열어 **로드와 콘솔까지는 확인**했으나, 테마·글자 크기·진행 바의 시각적 배치를 픽셀 단위로 검수하지는 않았다.

### 3-5. 촬영용 USB 컨트롤러 — `hardware/` · `1-controller-3d.html`

로그 원문: `hardware/docs/logs/` (6종).

**펌웨어 — 실제 크로스 컴파일**

```
[89/89] Linking CXX executable takedeck.elf
takedeck.bin  51,312 B · takedeck.elf 101,020 B · takedeck.uf2 102,912 B
```

- 우리 소스(`firmware/src/*.c`) 경고 **0** (로그의 경고 2건은 pico-sdk `flash.c`).
- 검증된 것: Cortex-M0+ 컴파일·링크, 미정의 심볼 없음, 플래시 이미지 51 KB가 RP2040 2 MB에 여유.
- 검증되지 않은 것: 실기 부팅·USB enumerating·I2C 통신·타이밍.

**펌웨어 로직 — 호스트 단위 테스트**

- 펌웨어와 같은 소스(app·keys·protocol·ui)를 PC용으로 컴파일해 **130 checks, 0 failures**.
- 영역: 프로토콜 파싱·프레이밍(192자 초과 폐기 포함), 디바운스(8 ms 채터 무시, 15 ms 안정), 핸드셰이크·재전송(700 ms, 3회),
  링크 단절 시 `REC ?`·LED 점멸·키 무시, 재연결 재동기화, 큐 4개·`BUSY`, 상태 파싱·시간 보간, UI 프레임.
- 검증되지 않은 것: 실제 GPIO·I2C·USB CDC(`main.c`·`ssd1306.c`는 컴파일만).

**PC 브리지 — pytest**

- **37 passed** — 프로토콜 8, 브리지 15, 실제 `simpleobsws` ↔ 모의 obs-websocket v5 10, end-to-end 4.
- end-to-end(실제 펌웨어 로직 `host_sim` ↔ 브리지 ↔ 모의 OBS): REC → OBS 녹화 → `H STATE rec=1` → `#LED 1`,
  경과 시간 `outputDuration`, 장면 순환·음소거, OBS 다운/복구, ACK 유실 시 중복 토글 차단, 기기 종료 시 정리.
- 검증되지 않은 것: 실제 OBS Studio 30.x, 실제 `/dev/ttyACM*`, Windows/macOS 포트·권한.

**케이스 CAD**

```
bottom_case  tri=2804 watertight=True bbox=[96,74,21]
top_case     tri=4730 watertight=True bbox=[96,74,6.6]
keycap       tri=464  watertight=True bbox=[18,18,8]
22 interference checks, 0 failure(s)
scad consistency: {'ok': True, 'compared': 76, 'mismatches': []}
```

- 세 STL 모두 수밀 단일 메시·법선 일관. 케이스↔보드·OLED·스위치 4·키캡 4·LED·나사 4·USB 코리도 교차 체적 0 mm³.
- 긍정 대조군(일부러 넣은 간섭 블록)이 실제로 검출되는지 확인. 키캡 4 mm 눌림 시 상판 간섭 0.
- 검증되지 않은 것: 실제 프린트, 수축·공차, 나사 체결력, USB-C 삽입.

**프리뷰 · 회로도**

- 헤드리스 Chromium에서 7단계 조작, 콘솔 에러 0, 스크린샷 8장, 정적 검사 5건, CDN 3개 URL 200. 관측 10–11 fps는 **SwiftShader 값이며 성능 주장이 아니다**.
- 회로도 SVG는 XML 파싱·브라우저 렌더 확인, 넷리스트 10넷이 `WIRING.md` 표와 1:1 대응(수작업 대조).
- 검증되지 않은 것: ERC 도구 미실행, 실물 연속성 시험 미실시.

**실물 인수 테스트**: T1–T15를 [`hardware/HARDWARE_VERIFICATION.md`](hardware/HARDWARE_VERIFICATION.md) §8에 남겼다. **하나도 수행하지 않았다.**

---

## 4. 환경적 한계 (공통)

1. **GPU 없음** — 모든 WebGL 검증은 SwiftShader 소프트웨어 렌더링이다. 02의 "60 fps", 03의 "모바일 60 fps"는 구조(인스턴싱·LOD·컬링·적응 해상도·파티클 예산)로 설계했을 뿐 **실측하지 못했다**. 화면의 fps 표시(SwiftShader 10–27)를 성능 근거로 읽으면 안 된다.
2. **실물 없음** — 05는 프린트·납땜·조립·USB 전류 측정·실제 OBS 연동을 하지 않았다. 계산·빌드·시뮬레이션까지만 검증이다.
3. **모바일 실기기 없음** — 03의 390×844 검증은 데스크톱 Chromium의 뷰포트 에뮬레이션이고, 실제 iOS/Android GPU·터치 스크롤은 확인하지 않았다.
4. **시각 품질의 주관 평가 없음** — 레이아웃·색·타이포그래피가 "보기 좋은지"는 자동 검사로 판정하지 않았다.
5. **CDN 의존** — 01·02·03·05는 three.js(03은 GSAP 포함)를 CDN에서 받는다. 오프라인이면 로드되지 않는다(과제 요구사항).

## 5. 재현 명령

```bash
# 웹: 로컬 서버로 열기
python3 -m http.server 8000 --bind 127.0.0.1     # → http://127.0.0.1:8000/

# 01 정적 검증 (과제 작업에서 사용한 스크립트는 결과물에 포함하지 않음)

# 02 문법 검사 (모듈 스크립트를 .mjs 파일로 추출한 뒤 Node 20으로)
node --check check.mjs

# 05 펌웨어 빌드
export PICO_SDK_PATH=/path/to/pico-sdk-1.5.1
cmake -S hardware/firmware -B hardware/firmware/build -G Ninja -DPICO_BOARD=pico \
      -DPICO_TOOLCHAIN_PATH=/path/to/arm-gnu-toolchain-12.3.rel1
cmake --build hardware/firmware/build

# 05 펌웨어 로직 호스트 테스트
cd hardware/firmware/test && CC=gcc ./run_host_tests.sh

# 05 브리지 테스트
cd hardware/host && python3 -m pip install -r requirements.txt && python3 -m pytest tests -v

# 05 케이스 STL + 간섭 검사
cd hardware/enclosure && python3 generate.py --render

# 05 프리뷰 정적 검사 + 스크린샷
cd hardware/preview && python3 build_preview.py && python3 check_preview.py && python3 screenshot.py
```

## 6. 이번 통합 단계에서 실행한 검사 (2026-11-19)

통합 문서를 쓰기 전에 저장소 전체를 대상으로 아래를 실제로 실행했다.

| 검사 | 방법 | 결과 |
|---|---|---|
| HTML 태그 균형 | `html.parser` 기반 검사기로 6개 HTML(index·palace·hangang·model-intro·novel·1-controller-3d) | 미닫힘 0, 불일치 0, 중복 id 0 |
| CSS 중괄호 | 동일 검사기로 `{`/`}` 개수 대조 | index 65/65 · palace 326/326 · hangang 768/768 · model-intro 413/413 · novel 98/98 · controller 183/183 |
| 내부 링크 | index.html의 모든 `href`를 로컬 서버에서 GET | 18개 중 로컬 링크 전부 **200**(작성 시점에 미작성 문서 1건 → 작성 후 재검사 200) |
| 문서 링크 | README·WEB_VERIFICATION·NOVEL_README·hardware 문서의 마크다운 링크 대상 존재 확인 | 깨진 링크 0 |
| 페이지 로드 | 헤드리스 Chromium 1440×900, 6개 페이지 | 전부 **200** |
| 콘솔/페이지 오류 | 위 로드에서 수집 | 01·03·04·05·index **0** · 02 **셰이더 오류 1건**(§3-2) |
| 01 수치 재측정 | 페이지 내 `PALACE_APP.model` | 브릭 1,963·단계 21·에러 0·경고 3→0·치수 4,200/2,500/3,600 cm |
| 02 상태 확인 | `HC.state()` | 건물 764·간판 170·차량 61·램프 7·수배 0 |
| 03 상태 확인 | `__pickle.stats()` | ready, 파티클 6,900, 테마 light, 자리표시자 4 |
| 04 렌더 확인 | DOM 확인 | 200, 콘솔 0, section 6, 텍스트 13,208자 |
| 05 프리뷰 확인 | DOM 확인 | 200, canvas 존재, 콘솔 0, 버튼 15 |

이 표의 값은 통합 단계에서 직접 측정한 것이고, 3장의 과제별 표는 각 과제 작업에서 실행해 기록된 결과와 통합 단계 재측정을 함께 적은 것이다.
