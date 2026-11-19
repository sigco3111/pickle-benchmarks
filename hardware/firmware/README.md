# firmware/

TakeDeck TD-01 펌웨어 — RP2040 (Seeed XIAO RP2040), Pico SDK 1.5.1, 순수 C.

## 빌드

```bash
export PICO_SDK_PATH=/path/to/pico-sdk-1.5.1          # tinyusb 서브모듈 포함
cmake -S . -B build -G Ninja -DPICO_BOARD=pico \
      -DPICO_TOOLCHAIN_PATH=/path/to/arm-gnu-toolchain-12.3.rel1-x86_64-arm-none-eabi
cmake --build build
# → build/takedeck.uf2  (RPI-RP2 드라이브에 복사)
```

미리 빌드된 이미지: `prebuilt/takedeck.uf2` (이 저장소의 소스로 ARM GNU 12.3 + pico-sdk 1.5.1에서
빌드한 결과. `docs/logs/firmware_build.log` 참조). 도구 없이 바로 플래시할 수 있다.

## 구조

| 파일 | 역할 | 하드웨어 의존 |
|---|---|---|
| `src/main.c` | 핀 초기화, 1 ms 루프, USB CDC 입출력 | O |
| `src/app.c` | 링크 상태, 명령 큐·재전송, OBS 상태 사본, LED 결정 | X |
| `src/protocol.c` | 라인 프레이밍/파싱/포맷 | X |
| `src/keys.c` | 4키 디바운스·에지 검출 | X |
| `src/ui.c` | 128×64 프레임버퍼 렌더 | X |
| `src/ssd1306.c` | SSD1306 I2C 드라이버 (페이지 단위 flush) | O |
| `include/font5x7.h` | 5×7 폰트 (tools/gen_font.py로 생성) | X |
| `include/config.h` | 핀 맵, 타이밍 상수 | — |

하드웨어 의존 코드는 `main.c`와 `ssd1306.c` 두 파일뿐이다. 나머지는 PC에서 그대로 컴파일해
테스트할 수 있다.

## 테스트

```bash
cd test
CC=gcc ./run_host_tests.sh        # 또는 CC="zig cc"
```

- `test_logic.c` — 130개 검사 (프로토콜·디바운스·앱 상태 기계·UI)
- `host_sim.c` — 같은 앱 코드를 stdin/stdout으로 돌리는 시뮬레이터.
  `host/tests`가 이 바이너리를 실제 브리지와 연결해 end-to-end로 시험한다.

```bash
# 수동으로 만져 보기
./test/build/host_sim
HOST H HELLO v=1
HOST H STATE rec=1 t=61 scene="Main Cam" idx=1 cnt=3 mute=0
PRESS REC
LED
QUIT
```

## 폰트 재생성

```bash
python3 tools/gen_font.py            # include/font5x7.h 재작성
python3 tools/gen_font.py --png out.png
```

## USB identity

- VID/PID: `2E8A:000A` (pico-sdk 기본값, 프로토타입). 제품화하려면 USB-IF 할당이 필요하다.
- 제품 문자열: `TakeDeck TD-01` (CMake의 `USBD_MANUFACTURER`/`USBD_PRODUCT`).
- 1200 baud로 포트를 닫을 때의 리셋 동작은 껐다 — 브리지가 포트를 다시 열어도 세션이 유지된다.
