# TakeDeck TD-01 — 아키텍처

```
┌──────────────────────────┐   USB CDC (텍스트 라인)   ┌───────────────────────┐   obs-websocket v5   ┌──────────────┐
│  TakeDeck TD-01          │  D HELLO / D CMD / D PING │  takedeck (Python)    │  GetRecordStatus ... │  OBS Studio  │
│  XIAO RP2040 + SSD1306   │ ────────────────────────▶ │  host/takedeck        │ ───────────────────▶ │  28 이상     │
│  + MX 키 4개 + 적색 LED   │ ◀──────────────────────── │  asyncio + pyserial   │ ◀─────────────────── │              │
│                          │  H HELLO / H ACK / STATE  │                       │  WebSocket(JSON/msgpack)│          │
└──────────────────────────┘                           └───────────────────────┘                      └──────────────┘
        펌웨어 (C, pico-sdk)                                 PC에서 상주 실행
```

---

## 1. 구성 요소

| 계층 | 위치 | 역할 | 하드웨어 의존 |
|---|---|---|---|
| 펌웨어 앱 | `firmware/src/app.c` | 링크 감시, 명령 큐·재전송, OBS 상태 사본, 알림 | 없음 (호스트 테스트) |
| 펌웨어 프로토콜 | `firmware/src/protocol.c` | 라인 프레이밍·파싱·포맷 | 없음 |
| 펌웨어 키 | `firmware/src/keys.c` | 4키 디바운스, 에지 검출 | 없음 |
| 펌웨어 UI | `firmware/src/ui.c` | 128×64 프레임버퍼 렌더 | 없음 |
| 펌웨어 하드웨어 | `firmware/src/main.c`, `ssd1306.c` | GPIO·I2C·USB CDC | 있음 |
| 브리지 | `host/takedeck/` | 시리얼 ↔ OBS 중계, 중복 차단, 재연결 | 없음 (전송·OBS 인터페이스 주입) |
| 모의 OBS | `host/mock_obs.py` | obs-websocket v5 서버 (테스트·개발용) | 없음 |
| CAD | `enclosure/` | 파라메트릭 케이스 → STL | 없음 |
| 프리뷰 | `preview/` | Three.js 조립/동작 시뮬레이션 | 브라우저 |

## 2. OBS를 제어하는 방식 — 왜 HID 키보드 주입이 아닌가

선택지 세 가지를 검토했다.

1. **USB HID 키보드로 OBS 단축키 주입** — 드라이버가 필요 없고 가장 단순하다. 그러나
   (a) OBS의 실제 녹화 상태를 되읽을 수 없어 "표시등이 OBS의 실제 상태를 반영" 요구를 만족할 수 없고,
   (b) 사용자의 다른 앱에 키가 들어갈 수 있으며, (c) 단축키 설정에 의존한다. → **탈락**
2. **OBS WebSocket 플러그인(구 v4)** — OBS 28부터 내장 기능이 v5로 교체되고 v4 플러그인은 유지보수가
   중단됐다. → **탈락**
3. **obs-websocket v5 (OBS 28+ 내장)** — 상태 조회(`GetRecordStatus`)와 제어(`StartRecord`,
   `StopRecord`, `SetCurrentProgramScene`, `ToggleInputMute`)를 모두 제공한다. 인증은 선택.
   → **채택**

USB 장치는 상태를 스스로 알 수 없으므로 PC 쪽 **브리지 앱**이 필요하다. 브리지는 USB CDC(시리얼)로
장치와 대화하고, WebSocket으로 OBS와 대화한다. 두 프로토콜 사이의 번역기이며, 중복 명령 차단과
상태 동기화의 책임을 진다.

## 3. USB 장치 식별

- pico-sdk의 `stdio_usb` CDC-ACM. VID/PID는 SDK 기본값 **2E8A:000A**(Raspberry Pi)를 그대로 쓴다.
  자체 VID/PID를 쓰려면 USB-IF 할당이 필요하므로, 판매용 제품이 아닌 프로토타입에서는 SDK 값을 유지하고
  **제품 문자열만** `TakeDeck TD-01`로 바꿨다(CMake `USBD_PRODUCT`).
- 1200 baud로 포트를 닫을 때 보드가 리셋되는 동작은 껐다(`PICO_STDIO_USB_ENABLE_RESET_VIA_BAUD_RATE=0`).
  브리지가 포트를 다시 열 때 장치가 재부팅되면 세션 ID가 바뀌어 중복 차단 캐시가 무효화되기 때문이다.
- 브리지는 VID/PID로 포트를 찾고, `H HELLO`를 보내 `D HELLO` 응답이 오는지로 한 번 더 확인한다
  (`--probe`). 다른 CDC 장치를 잘못 잡는 것을 막기 위해서다.

## 4. 프로토콜 (v1)

한 줄에 한 메시지, `\n` 종료, ASCII. 값은 공백 없는 토큰 또는 큰따옴표 문자열. 방향 태그는 `D`(장치→호스트),
`H`(호스트→장치)다.

| 방향 | 메시지 | 의미 |
|---|---|---|
| D | `HELLO v=1 fw=1.0.0 sid=0A1B2C3D` | 부팅/재연결 시 2 s 간격으로 반복. `sid`는 부팅마다 새로 생성 |
| D | `CMD seq=12 id=REC_TOGGLE` | 사용자 조작. ACK 필요. `id ∈ {REC_TOGGLE, SCENE_PREV, SCENE_NEXT, MUTE_TOGGLE}` |
| D | `PING t=12345` | 1 s마다. 호스트 생존 확인용 |
| D | `NOTE code=LINK_LOST` | 진단(응답 없음) |
| H | `HELLO v=1` | 호스트 존재 알림. 장치는 이걸 받아야 `LINK_UP` |
| H | `ACK seq=12 ok=1` / `ok=0 err=OBS_DOWN` | 명령 결과 |
| H | `STATE rec=0 t=42 scene="Wide Shot" idx=1 cnt=3 mute=0` | 4 Hz + 변화 시 즉시 |
| H | `PONG t=12345` | PING 응답 |
| H | `ERR code=OBS_DOWN text="..."` | 호스트/OBS 문제 |

예시 세션:

```
D HELLO v=1 fw=1.0.0 sid=0A1B2C3D
H HELLO v=1
H STATE rec=0 t=0 scene="Standby" idx=0 cnt=3 mute=0
D PING t=1000
H PONG t=1000
D CMD seq=1 id=REC_TOGGLE          ← REC 버튼
H ACK seq=1 ok=1
H STATE rec=1 t=0 scene="Standby" idx=0 cnt=3 mute=0
```

설계 근거:
- **텍스트 라인**을 쓴 이유: `picocom`/`screen`으로 사람이 직접 열어 보고, 문제를 재현할 수 있다.
  바이너리 프레이밍보다 디버깅 비용이 훨씬 낮고, 이 규모(초당 ~10줄)에서는 대역폭 이슈가 없다.
- 장면 이름은 큰따옴표로 감싸고 `"`·`\`를 이스케이프한다(OBS 장면 이름에 공백·따옴표가 들어갈 수 있다).
  장치 쪽 버퍼(20자)를 넘으면 잘라서 표시한다.
- 장치가 `t`를 스스로 세지 않고 호스트 값을 쓰는 이유: OBS가 실제로 기록한 시간과 어긋나지 않게 하기 위해서다.
  장치는 마지막 STATE 이후 경과분만 더해 1초 단위로 보간한다.

## 5. 상태 기계

### 5.1 링크

| 상태 | 진입 조건 | 표시 | 탈출 |
|---|---|---|---|
| `BOOT` | 전원 인가 | `BOOT` | 첫 HELLO 전송 후 → `WAIT` |
| `WAIT` | HELLO 반복 중 | `WAIT FOR OBS` | `H HELLO` 수신 → `UP` |
| `UP` | 호스트와 핸드셰이크 완료 | `USB LINK OK` (STATE 전에는 `SYNCING`) | 3 s 무응답 → `LOST` |
| `LOST` | 마지막 수신 후 3 s 초과 | `LINK LOST`, REC 상태 불명 | `H HELLO` 수신 → `UP` |

### 5.2 표시등 (빨간 LED)

| OBS 상태 | LED | 의미 |
|---|---|---|
| 녹화 중 (확인됨) | **점등** | OBS가 실제로 녹화 중 |
| 녹화 아님 (확인됨) | 소등 | OBS가 실제로 멈춰 있음 |
| 링크 끊김 / STATE 없음 | **1 Hz 점멸** (120 ms on) | 상태를 모른다 |

"빨강 = 녹화 중"이라는 관례를 지키기 위해, 상태를 모를 때는 켜 두지 않고 점멸로 구분한다.
OLED에는 `LINK LOST`와 `REC ?`가 함께 표시된다.

### 5.3 명령 생애주기

```
키 눌림(디바운스 통과)
   │  링크가 UP 아니면: 표시 "NO LINK", 명령 폐기 (큐에 쌓지 않음)
   ▼
큐에 등록 (seq 발급, 최대 4개)
   ▼  한 번에 하나만 전송
D CMD ──▶ ACK(ok=1) 수신 → 큐에서 제거, 다음 명령
   │
   ├─ 700 ms 동안 ACK 없음 → 같은 seq로 재전송 (최대 3회 시도)
   │        └─ 3회 모두 실패 → 큐에서 제거, "NO ACK"
   └─ ACK(ok=0) 수신 → 큐에서 제거, 에러 코드 표시
```

## 6. 중복 명령 차단 (3중)

1. **디바운스** — 15 ms 안정화, 누름 에지에서 1회만 이벤트. 홀드 반복 없음.
2. **시퀀스 + ACK 캐시** — 브리지는 `(sid, seq)` 키로 실행 결과를 기억한다. 같은 키가 다시 오면
   **실행하지 않고 저장된 ACK만 재전송**한다. 파일 캐시(`--ack-cache`)를 쓰면 **브리지 재시작** 후에도
   유지되어, ACK 유실 + 브리지 재시작이 겹쳐도 토글이 두 번 실행되지 않는다.
3. **의미 기반 실행** — `REC_TOGGLE`은 실행 직전에 OBS에 현재 상태를 다시 물어보고 시작/중지를 결정한다.
   캐시가 비어 있는 극단적 상황(기기·브리지 동시 재부팅)에서도 "녹화 중인데 또 시작" 같은 오류를 줄인다.

## 7. OBS API 매핑

| 기능 | obs-websocket v5 요청 | 비고 |
|---|---|---|
| 녹화 상태·경과 | `GetRecordStatus` | `outputActive`, `outputDuration`(ms) |
| 녹화 시작/중지 | `StartRecord` / `StopRecord` | `REC_TOGGLE`은 위에서 상태를 먼저 확인 |
| 장면 목록 | `GetSceneList` | **OBS는 최신 장면을 앞에 준다** → 브리지에서 뒤집어 UI 순서로 사용 |
| 현재 장면 | `GetCurrentProgramScene` | `currentProgramSceneName` (신버전은 `sceneName`도) |
| 장면 전환 | `SetCurrentProgramScene` | `SCENE_NEXT/PREV`는 브리지가 인덱스를 계산 (obs-websocket에 "다음 장면" 요청은 없다) |
| 음소거 | `GetInputMute` / `ToggleInputMute` | `--mute-input`으로 지정한 입력 |

상태는 **이벤트 구독 없이 250 ms 폴링**한다. obs-websocket 이벤트를 쓰면 지연을 줄일 수 있지만,
모의 서버·실서버 양쪽에서 이벤트 스키마 차이를 다뤄야 하고, 4 Hz 폴링이면 0.96" 화면에서는 충분히
즉각적이다. (개선 여지로 남김)

## 8. 실패 처리

| 상황 | 브리지 | 기기 표시 |
|---|---|---|
| OBS 미실행/종료 | 1→2→4…15 s 백오프로 재접속, 1 s마다 `ERR OBS_DOWN` | OLED에 `ERR OBS_DOWN` (1.5 s), 링크 자체는 유지 |
| OBS가 응답 없음(타임아웃) | `OBS_TIMEOUT` → 연결 재수립 | 위와 동일 |
| USB 케이블 분리 | 링크 종료 → 포트 재탐색 (2 s 간격) | 전원이 없으므로 표시 없음 |
| 브리지 종료 | — | 3 s 후 `LINK LOST`, LED 점멸 |
| 기기 재부팅 | `D HELLO`(새 sid) 수신 → 새 세션으로 처리 | 정상 부팅 화면 |
| 명령 실패 | `ACK ok=0 err=CODE` | `CMD REJECTED` / `ERR CODE` 표시 |
| 알 수 없는 명령 | `ACK ok=0 err=UNKNOWN_CMD` | `ERR UNKNOWN_CMD` |

## 9. 보안·개인정보

- OBS 비밀번호는 **파일에 저장하지 않는다**. `--obs-password` 인자 또는 `TAKEDECK_OBS_PASSWORD`
  환경변수로만 받고, 로그에도 남기지 않는다.
- 연결은 기본적으로 로컬 OBS(`127.0.0.1:4455`)만 향한다. 원격 OBS를 쓰려면 사용자가 명시적으로
  `--obs-host`를 지정해야 한다(이때 평문 WebSocket이므로 신뢰할 수 있는 네트워크에서만).
- 기기는 인증 정보를 갖지 않는다. USB로 연결된 PC만 제어할 수 있다.
- 브리지는 OBS의 녹화 파일 경로나 내용을 읽지 않는다. 상태 값(rec/시간/장면 이름/음소거)만 주고받는다.

## 10. 실행 구조

- **펌웨어**: 인터럽트 없이 단일 루프. 1 ms 주기로 (1) USB 수신 바이트 처리, (2) 2 ms마다 키 스캔,
  (3) 앱 틱(타임아웃·LED·알림), (4) 화면이 더러우면 128바이트 페이지 하나씩 I2C 전송.
  페이지 단위 전송(약 1.3 ms @400 kHz)으로 화면 갱신이 키 처리를 막지 않는다.
- **브리지**: 단일 asyncio 이벤트 루프 + 시리얼 수신 스레드 1개(큐로 전달). 명령 실행은 락으로 직렬화해
  ACK 순서가 뒤집히지 않게 한다.

## 11. 저장소 구조

```
hardware/
  REQUIREMENTS.md  ARCHITECTURE.md  HARDWARE_README.md  HARDWARE_VERIFICATION.md
  BOM.csv  WIRING.md  HARDWARE_SOURCES.md
  schematic/controller.svg  schematic/netlist.net
  firmware/   (pico-sdk CMake 프로젝트, 앱 로직 + 호스트 테스트 + 시뮬레이터)
  host/       (Python 브리지, 모의 OBS, pytest)
  enclosure/  (params.json, takedeck_case.scad, generate.py, stl/*.stl, verification.json)
  preview/    (Three.js 프리뷰 원본 템플릿·빌드 스크립트·스크린샷 도구)
  docs/       (치수 출처, CAD/프리뷰 이미지)
```

## 12. 채택하지 않은 대안

| 대안 | 왜 채택하지 않았나 |
|---|---|
| Raspberry Pi Pico (micro-USB) | 동작은 같지만 케이스 후면에 micro-USB 노출이 요즘 기준 어색하고, XIAO가 더 작아 배선이 짧다 |
| Adafruit SSD1306 라이브러리 | 의존성을 줄이고 페이지 단위 flush 타이밍을 직접 제어하려고 최소 드라이버를 직접 작성 (약 120줄) |
| 커스텀 PCB | 이번 범위는 "조립 가능한 프로토타입". PCB를 만들면 4주 이상 리드타임과 최소 주문 수량이 발생 |
| Cherry MX 대신 택트 스위치 | 키캡·플레이트 규격이 명확한 MX가 케이스 설계·검증에 유리. 가격은 비싸지만 4개면 충분 |
| OBS 이벤트 구독 | 위 §7 참조 |
| 밝기 자동 조절(조도센서) | 요구에 없음. OLED 대비는 설정 상수로만 노출 |
