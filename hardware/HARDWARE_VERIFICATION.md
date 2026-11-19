# 검증 기록 (HARDWARE_VERIFICATION)

**원칙: 하지 않은 것은 하지 않았다고 적는다.** 아래 "검증한 것"은 이 저장소를 만든 환경에서 실제로 실행한
결과이고, 로그는 `docs/logs/`에 원문 그대로 있다. "검증하지 못한 것"은 실물 없이는 확인할 수 없는 항목이다.

- 작성 시각: 2026-11-19 (UTC 기준 로그)
- 작업 환경: Linux 컨테이너, GPU·프린터·실물 부품 없음. **호스트 C 컴파일러(gcc/clang)와 OpenSCAD가
  설치되어 있지 않아** Zig(clang)와 pip 패키지로 도구를 직접 구성했다(아래 §1).

---

## 1. 도구 구성 (환경에 없어서 직접 설치)

| 필요한 것 | 환경 기본 상태 | 이번에 쓴 것 |
|---|---|---|
| ARM 크로스 컴파일러 | 없음 (PlatformIO 동봉 9.2.1은 `as` 실행 실패) | ARM GNU Toolchain **12.3.rel1** 직접 다운로드 |
| pico-sdk | 없음 | **1.5.1** tarball + tinyusb 0.15.0 (git clone은 정책상 차단 → codeload tarball) |
| CMake / Ninja | 없음 | pip wheel (`cmake 4.4.5`, `ninja`) |
| 호스트 C 컴파일러 | 없음 | **Zig 0.13.0** (`zig cc` = clang 18.1.6) |
| OpenSCAD | 없음 | 사용하지 않음. Python CSG(trimesh + manifold3d)로 STL 생성 |
| 브라우저 | 없음 (Playwright/Chromium 라이브러리 일부 누락) | Chrome for Testing headless shell + at-spi 라이브러리 수동 배치 |

이 구성은 검증용이며, 사용자가 재현할 때는 일반적인 `gcc`, `openscad`, 최신 브라우저로 충분하다.

## 2. 펌웨어 — 실제 크로스 컴파일

로그: [`docs/logs/firmware_build.log`](docs/logs/firmware_build.log)

```
cmake -S firmware -B firmware/build -G Ninja -DPICO_BOARD=pico -DPICO_TOOLCHAIN_PATH=<12.3.rel1>
cmake --build firmware/build
[89/89] Linking CXX executable takedeck.elf
-rwxr-xr-x  51312  takedeck.bin
-rwxr-xr-x 101020  takedeck.elf
-rw-r--r-- 102912  takedeck.uf2
```

- 우리 소스(`firmware/src/*.c`)에서 **경고 0** (빌드 로그에 남은 경고 2건은 pico-sdk의 `flash.c`).
- 산출물: `.elf`, `.bin`, `.uf2` 모두 생성. `.uf2`는 그대로 `RPI-RP2` 드라이브에 복사하는 파일이다.
- **검증된 것**: ARM Cortex-M0+ 대상 컴파일·링크 성공, 링크 단계에서 미정의 심볼 없음, 플래시 이미지 크기
  (51 KB)가 RP2040의 2 MB에 여유 있게 들어감.
- **검증되지 않은 것**: 실기에서의 부팅·USB enumerating·I2C 통신·타이밍. 보드가 없어 실행하지 않았다.

## 3. 펌웨어 로직 — 호스트 단위 테스트

로그: [`docs/logs/firmware_host_tests.log`](docs/logs/firmware_host_tests.log)

`firmware/test/test_logic.c`가 **펌웨어와 같은 소스**(app.c, keys.c, protocol.c, ui.c)를 PC용으로
컴파일해 검사한다. 결과: **130 checks, 0 failures**.

| 영역 | 검사한 내용 |
|---|---|
| 프로토콜 파싱 | 정상 라인, 따옴표 안 공백, 이스케이프된 따옴표, 빈 값, 닫히지 않은 따옴표, 잘못된 방향 태그 |
| 라인 프레이밍 | 분할 수신, CRLF, 빈 줄, 192자 초과 시 라인 폐기 및 카운트 |
| 포맷 | HELLO/CMD/PING/NOTE 문자열, 세션 ID 16진 표기 |
| 디바운스 | 8 ms 채터 무시, 15 ms 안정 후 1회, 홀드 중 반복 없음, 릴리스 후 재입력 |
| 앱: 핸드셰이크 | 부팅 시 HELLO, 2초 재전송, HELLO 수신 후 링크 UP |
| 앱: 명령 | 4종 명령 발행, seq 증가, 30 ms 내 중복 이벤트 무시, ACK 후 큐 제거 |
| 앱: 재전송 | 700 ms 무응답 시 같은 seq로 재전송, 3회 실패 시 폐기 + `NO ACK` |
| 앱: 링크 단절 | 3초 침묵 → LOST, REC 상태 불명, LED 점멸, 키 입력 무시(`NO LINK`) |
| 앱: 재연결 | HELLO 수신 → 큐 초기화 + 재동기화, STATE 수신 후 정상화 |
| 앱: 큐 | 4개 적재, 순서대로 ACK, 초과 시 `BUSY` |
| 앱: 상태/시간 | STATE 파싱(장면·인덱스·음소거), 경과 시간 로컬 보간 |
| UI | 시간 포맷(99시간 클램프), 상태별 프레임 변화, REC 칩 실제 픽셀 점등, 긴 장면 이름 절단 |

**검증되지 않은 것**: 실제 GPIO 읽기, I2C 타이밍, USB CDC 스택 동작 — 모두 하드웨어 의존 코드(`main.c`,
`ssd1306.c`)이며 호스트에서 실행할 수 없다. `ssd1306.c`는 컴파일만 확인했다.

## 4. PC 브리지 — pytest 37개

로그: [`docs/logs/host_bridge_tests.log`](docs/logs/host_bridge_tests.log)

```
37 passed in 8.82s
```

| 파일 | 개수 | 성격 |
|---|---|---|
| `tests/test_protocol.py` | 8 | 라인 코덱, 따옴표/이스케이프, 왕복 |
| `tests/test_bridge.py` | 15 | 핸드셰이크, 4종 명령, 중복 차단(파일 캐시 포함), 재전송, OBS 다운/복구, 주기 푸시 |
| `tests/test_obs_ws.py` | 10 | **실제 simpleobsws 클라이언트 ↔ 모의 obs-websocket v5 서버**(msgpack subprotocol, 비밀번호 인증, 오류 코드) |
| `tests/test_integration.py` | 4 | **실제 펌웨어 로직(host_sim) ↔ 실제 브리지 ↔ 모의 OBS** end-to-end |

end-to-end 테스트가 실제로 확인한 것:

1. 키 입력(`PRESS REC`) → 펌웨어가 `D CMD seq=1 id=REC_TOGGLE` 발행 → 브리지가 OBS에서 녹화 시작 →
   `H STATE rec=1` → 펌웨어 LED 점등(`#LED 1`)까지 한 줄로 이어진다.
2. 경과 시간은 OBS의 `outputDuration`에서 온다(1초 후 `t=1` 확인).
3. 장면 ▶/◀가 OBS의 장면 순서를 따라 순환하고, 음소거 토글이 동작한다.
4. **OBS를 끄면** 펌웨어가 `ERR OBS_DOWN`을 받아 표시하고, **다시 켜면** 사람 개입 없이 상태가 복구된다.
5. 같은 `seq`의 명령이 두 번 도착해도(ACK 유실 시나리오) 토글이 두 번 실행되지 않는다.
6. 기기(=시뮬레이터)를 끄면 브리지가 정상 종료된다(좀비 스레드·행 없음).

**검증되지 않은 것**: 실제 OBS Studio(30.x) 인스턴스와의 연동, 실제 USB 시리얼 포트(`/dev/ttyACM*`),
Windows/macOS에서의 포트명·권한. 모의 서버는 이 제품이 쓰는 요청만 구현했다.

## 5. 케이스 CAD — 생성 + 수치 검사

로그: [`docs/logs/cad_checks.log`](docs/logs/cad_checks.log), 상세: [`enclosure/verification.json`](enclosure/verification.json)

```
bottom_case   137.0 kB  tri=  2804  watertight=True  bbox=[96. 74. 21.]
top_case      231.0 kB  tri=  4730  watertight=True  bbox=[96. 74.  6.6]
keycap         22.7 kB  tri=   464  watertight=True  bbox=[18. 18.  8.]
22 interference checks, 0 failure(s)
scad consistency: {'ok': True, 'compared': 76, 'mismatches': []}
```

- 세 STL 모두 **수밀(watertight) 단일 메시**이며 법선 방향이 일관된다(manifold3d CSG 커널).
- **간섭 검사 22건 통과**: 케이스 ↔ 보드·OLED·스위치 4개·키캡 4개·LED·나사 4개·USB 플러그 코리도
  교차 체적 0 mm³. 스위치 14 mm 홀과 OLED 창이 실제로 뚫려 있는지(막대가 통과) 확인.
- **긍정 대조군**: 일부러 상판을 뚫는 블록을 넣어 검사가 간섭을 "검출"하는지 확인(검사 자체의 신뢰성).
- **키 눌림**: 키캡을 4 mm 내렸을 때 상판과 간섭 0.
- **파라메트릭 일관성**: `params.json` ↔ `takedeck_case.scad`의 수치 76개를 비교해 불일치 0.

**검증되지 않은 것**: 실제 프린트 출력, 수축·공차, 나사 체결력, USB-C 케이블 삽입. 치수 가정은
[`docs/DIMENSION_SOURCES.md`](docs/DIMENSION_SOURCES.md) §2에 정리했다.

## 6. 프리뷰 — 실제 브라우저에서 실행

로그: [`docs/logs/preview_browser.log`](docs/logs/preview_browser.log), [`docs/logs/preview_checks.log`](docs/logs/preview_checks.log)

```
0 problem(s), 0 console error(s)
page state: {'led': '꺼짐', 'rec': '꺼짐', 'link': '정상', 'time': '00:00:02',
             'fps': '11 fps', 'logLines': 16, 'canvas': True}
```

- 헤드리스 Chromium(Chrome for Testing 159)에서 페이지를 열고 7단계로 조작하며 스크린샷 8장을 남겼다.
  Three.js CDN 로딩, WebGL 컨텍스트 생성, 조작(버튼·슬라이더·시점) 모두 콘솔 에러 없이 동작.
- 스크린샷: `docs/preview_assembled.png`, `preview_recording.png`, `preview_obs_side.png`,
  `preview_link_lost.png`, `preview_case_open.png`, `preview_exploded.png`, `preview_top.png`,
  `preview_oled_closeup.png`
- 정적 검사 5건: 두 사본 동일, 필수 UI 요소 존재, JS 파싱 성공, 임베디드 치수 = `params.json`,
  CDN 3개 URL 200.
- **fps 10–11은 소프트웨어 렌더링(SwiftShader) 결과이며 성능 주장이 아니다.**

**검증되지 않은 것**: 실제 GPU에서의 부드러움, 모바일 레이아웃, 접근성(스크린 리더).

## 7. 회로도

- `schematic/controller.svg`는 XML로 파싱되고 브라우저에서 정상 렌더링된다(`docs/schematic_view4.png`).
- `schematic/netlist.net`의 넷 10개가 `WIRING.md`의 표와 1:1로 대응한다(수작업 대조).
- **검증되지 않은 것**: ERC(전기 규칙 검사) 도구를 돌리지 않았다. 실물 연속성 시험도 하지 않았다.

## 8. 실기 인수 테스트 (조립 후 반드시 수행)

부품이 도착하면 아래를 순서대로 확인하고 결과를 이 문서에 덧붙인다. 각 항목은 실패 시 되돌아갈 지점을
함께 적었다.

| # | 시험 | 합격 기준 | 실패 시 |
|---|---|---|---|
| T1 | 프린트 치수 | 상판이 하판에 0.2–0.4 mm 유격으로 들어가고 흔들리지 않음 | `case.lid_clearance` 조정 |
| T2 | 스위치 장착 | 14 mm 홀에 스위치가 "끼워져" 클립이 걸리고 빠지지 않음 | `keys.cutout` ±0.1 |
| T3 | 키캡 결합 | 스템에 키캡이 손으로 눌러 들어가고, 흔들리지 않으며, 4 mm 눌림에서 상판에 닿지 않음 | `keycap.stem_cross_*`, `rim_z` |
| T4 | OLED 장착 | 링에 모듈이 들어가고 창과 액티브 영역이 정렬됨(±0.5 mm) | `oled.window_*`, `module_clearance` |
| T5 | USB-C 삽입 | 케이블이 컷아웃을 통과해 완전히 삽입되고 헐거움 없음 | `xiao.usb_cut_z / h` |
| T6 | 나사 체결 | 4개 모두 끝까지 조여지고 헛돌지 않음, 상판이 들뜨지 않음 | `screws.pilot_d` |
| T7 | 전원·전류 | 5 V에서 100 mA 미만, 3V3 레일 3.25–3.35 V | 전원 예산 재계산 |
| T8 | OLED 표시 | 부팅 3초 내 `WAIT FOR OBS` 표시, 깜빡임/찌꺼기 없음 | I2C 속도 400k→100k, 풀업 확인 |
| T9 | 키 인식 | 4키 모두 1회 누름 = 1회 명령, 채터 없음 (브리지 로그로 확인) | `KEY_DEBOUNCE_MS` 조정 |
| T10 | LED | 녹화 중 고정 점등, 중지 시 소등, 링크 단절 시 점멸. 어두운 방에서 눈부시지 않음 | 저항 220→330 Ω |
| T11 | OBS 연동 | 실 OBS 30.x에서 REC/장면/MUTE 동작, 지연 체감 즉시 | 브리지 로그의 요청/응답 확인 |
| T12 | 중복 방지 | REC를 빠르게 두 번 눌러도 두 번 토글되지 않음, 브리지 재시작 후에도 유지 | `--ack-cache` 확인 |
| T13 | 재연결 | 케이블 재삽입·OBS 재시작 후 5초 내 자동 복구 | `LINK_STALE_MS`, 백오프 |
| T14 | 발열 | 30분 연속 사용 시 케이스 표면 40 °C 미만 | 내부 환기·LDO 확인 |
| T15 | 장시간 | 2시간 연속 녹화에서 표시 시간과 OBS 시간 오차 < 1초 | 시간 보간 로직 확인 |

## 9. 재현 명령 모음

```bash
# 1) 펌웨어 빌드
export PICO_SDK_PATH=/path/to/pico-sdk-1.5.1
cmake -S firmware -B build -G Ninja -DPICO_BOARD=pico -DPICO_TOOLCHAIN_PATH=/path/to/arm-gnu-toolchain
cmake --build build

# 2) 펌웨어 로직 호스트 테스트 (CC=gcc 또는 CC="zig cc")
cd firmware/test && CC=gcc ./run_host_tests.sh

# 3) 브리지 테스트 (펌웨어 시뮬레이터가 먼저 빌드되어 있어야 함)
cd host && python3 -m pip install -r requirements.txt && python3 -m pytest tests -v

# 4) 케이스 STL + 간섭 검사
cd enclosure && python3 generate.py --render

# 5) 프리뷰 정적 검사 + 브라우저 실행
cd preview && python3 build_preview.py && python3 check_preview.py && python3 screenshot.py
```

## 10. 요약

| 영역 | 상태 |
|---|---|
| 펌웨어 컴파일 (RP2040) | ✅ 실제 빌드, .uf2 생성 |
| 펌웨어 로직 | ✅ 130 검사 통과 (호스트) |
| 브리지 ↔ OBS 프로토콜 | ✅ 37 테스트 통과 (모의 OBS 포함) |
| 펌웨어 ↔ 브리지 end-to-end | ✅ 4 시나리오 통과 (실제 펌웨어 로직 사용) |
| 케이스 STL 생성·간섭 | ✅ 22 검사 통과, 워터타이트 |
| 프리뷰 브라우저 실행 | ✅ 콘솔 에러 0, 스크린샷 8장 |
| 실물 조립·프린트·OBS 실연동 | ❌ **하지 않음** (§8 목록으로 남김) |
| 전류 실측 | ❌ 하지 않음 (계산값만) |
