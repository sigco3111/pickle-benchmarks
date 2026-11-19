# 공식 출처와 근거

BOM·배선·CAD에 쓴 수치는 아래 문서에서 가져왔다. "확인한 것"과 "확인하지 못한 것"을 구분해 둔다.
링크는 2026-11-19에 접속을 확인했다(일부 제조사 사이트는 봇 차단으로 HEAD 요청이 403을 주지만,
같은 URL을 브라우저로 열면 정상 표시된다 — 그 경우 "(403 to script)"로 적었다).

## 1. MCU 보드 — Seeed Studio XIAO RP2040

| 항목 | 값 | 출처 |
|---|---|---|
| 치수 | 21.0 × 17.8 mm | https://wiki.seeedstudio.com/XIAO-RP2040/ (Specification 표) |
| 로직 전압 | 3.3 V (I/O에 5 V 인가 금지) | 같은 문서 "Hardware Overview" caution |
| 전원 | USB-C 5 V 입력, 온보드 DC-DC로 3.3 V 생성 | 같은 문서 |
| 핀맵 | D0=GPIO26, D1=GPIO27, D2=GPIO28, D3=GPIO29, D4=GPIO6(SDA0), D5=GPIO7(SCL0), D6=GPIO0(TX) | 같은 문서 "Pin Map" 표 |
| 온보드 RGB LED | GPIO16/17/25 사용 → 이 핀들은 회피 | 같은 문서 "USER_LED_R/G/B" |
| 제품 페이지 | SKU 102010428 (XIAO RP2040) | https://www.seeedstudio.com/XIAO-RP2040-p-5200.html (403 to script) |
| RP2040 데이터시트 | USB 1.1 Full Speed device, Cortex-M0+ 133 MHz | https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf |
| Pico SDK | 1.5.1 (`pico_enable_stdio_usb`) | https://github.com/raspberrypi/pico-sdk/tree/1.5.1 |

**확인하지 못한 것**: XIAO RP2040 보드에는 나사 장착홀이 없다(카스텔레이티드 패드와 2.54 mm 핀만 존재).
그래서 케이스는 나사 대신 **레일 + 전면 스톱 + 폼**으로 보드를 고정한다. 실제 보드의 USB-C 리셉터클이
기판 가장자리에서 얼마나 튀어나오는지는 데이터시트에 도면이 없어, 벽면 컷아웃을 여유 있게(9.6 × 3.6 mm) 잡았다.

## 2. OLED — SSD1306 0.96" I2C 모듈

| 항목 | 값 | 출처 |
|---|---|---|
| 모듈 치수 | 27.3 × 27.3 × 2.37 mm | https://www.winstar.com.tw/products/oled-module/graphic-oled-display/4-pin-oled.html (WEA012864D-03) |
| 액티브 영역 | 21.74 × 10.86 mm | 같은 페이지 |
| 해상도 | 128 × 64, 1/64 duty | 같은 페이지 |
| 공급 전압 | 2.8–5.2 V (모듈에 레벨 변환 내장) | 같은 페이지 |
| 핀 | 1 VCC, 2 GND, 3 SCL, 4 SDA | 같은 페이지 |
| 드라이버 IC | SSD1306 (Solomon Systech, Rev 1.1, 2008) | https://cdn-shop.adafruit.com/datasheets/SSD1306.pdf |
| I2C 주소 | 0x3C (SA0=0 모듈) | 드라이버 데이터시트 / 모듈 관례 |

**확인하지 못한 것**: 4핀 모듈의 **장착홀 피치**는 제조사마다 다르고(Ø2.2 4홀 등), Winstar 도면에는
피치 값이 명시돼 있지 않다. 그래서 케이스는 나사 대신 **모듈을 감싸는 링 + 하단 받침 ledge + 테이프**로
고정한다. 창 크기(24.4 × 13.6 mm)는 액티브 영역(21.74 × 10.86)과 글라스(26.7 × 19.26) 사이에서 잡았다.

## 3. 키 스위치 — CHERRY MX

| 항목 | 값 | 출처 |
|---|---|---|
| 플레이트 컷아웃 | 14.0 × 14.0 mm ±0.05, 코너 R ≤ 0.3 | Cherry MX 데이터시트(플레이트 도면), https://www.cherry.de/en-gb/product/mx-grey-tactile/downloads |
| 플레이트 두께 | 1.52 ± 0.10 mm (스위치 클립이 걸리는 두께) | 같은 데이터시트 |
| 플레이트 상면 ↔ PCB 상면 | 5.00 +0.30 mm | 같은 데이터시트 |
| 하우징 | 15.6 mm 폭, 11.6 mm 높이 | Cherry Keymodule MX 기술 자료 |
| 접점 정격 | 12 V / 10 mA, 바운스 5 ms 이하 | Cherry MX 기술 사양표 |
| 키 피치 | 19.05 mm (0.75 in) | 같은 자료 |
| 스템 십자 | 4.1 × 1.27 mm (키캡 소켓 여유 0.2 mm 권장) | Cherry 키캡 인터페이스 도면 |

케이스는 클립이 걸리는 구간만 1.5 mm가 되도록 **아래에서 16.2 × 16.2 mm 포켓을 1.5 mm 깊이로 파서**
플레이트 두께를 맞췄다(§4.4 간섭 검사).

## 4. 표시등 LED — Kingbright L-53SRD

| 항목 | 값 | 출처 |
|---|---|---|
| 패키지 | T-1¾ (5 mm), 적색 확산 | https://www.mouser.com/datasheet/2/239/L-53SRD-1145465.pdf |
| 순방향 전압 | 1.85 V typ, 2.5 V max @ 20 mA | 같은 데이터시트 |
| 최대 연속 전류 | 30 mA | 같은 데이터시트 |
| 저항 계산 | (3.3 − 1.85) / 220 Ω = 6.6 mA | 옴의 법칙, 본 설계 |

## 5. USB-C

| 항목 | 값 | 출처 |
|---|---|---|
| 커넥터 형상 | USB Type-C, 8.94 × 3.26 mm 리셉터클 | https://www.usb.org/usb-type-c (USB-IF) |
| 케이블 | 데이터선이 있는 케이블 필요(충전 전용 불가) | https://www.usb.org/usb-charger |

케이스 뒷벽 컷아웃은 플러그 셸(8.34 × 2.56 mm)보다 크게 9.6 × 3.6 mm로 잡아 오버몰드가 들어갈
여유를 뒀다. 리셉터클 돌출량은 위 §1의 미확인 항목.

## 6. 소프트웨어 의존성 (실행 환경)

| 항목 | 버전 | 출처 |
|---|---|---|
| pico-sdk | 1.5.1 | https://github.com/raspberrypi/pico-sdk/releases/tag/1.5.1 |
| ARM GNU toolchain | 12.3.rel1 (`arm-none-eabi`) | https://developer.arm.com/downloads/-/arm-gnu-toolchain-downloads |
| CMake / Ninja | ≥ 3.13 / 임의 | https://cmake.org/ , https://ninja-build.org/ |
| Python | 3.11 이상 (3.12.16에서 검증) | https://www.python.org/ |
| pyserial | 3.5 | https://pypi.org/project/pyserial/ |
| simpleobsws (obs-websocket v5 클라이언트) | 1.4.3 | https://pypi.org/project/simpleobsws/ |
| websockets (모의 OBS 서버) | 17.4 | https://pypi.org/project/websockets/ |
| trimesh / manifold3d / shapely / mapbox_earcut (CAD 생성) | 5.x / 3.x / 2.2 / 1.x | https://pypi.org/ |
| Three.js | 0.170.0 (CDN) | https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.js |

## 7. obs-websocket v5 요청 이름

`GetVersion`, `GetRecordStatus`, `StartRecord`, `StopRecord`, `GetSceneList`,
`GetCurrentProgramScene`, `SetCurrentProgramScene`, `GetInputList`, `GetInputMute`,
`ToggleInputMute` — 모두 공식 프로토콜 문서의 요청 이름이다.

- 프로토콜 문서: https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md

이 저장소의 모의 서버(`host/mock_obs.py`)는 위 요청 중 이 제품이 쓰는 부분집합만 구현한다.
실제 OBS(30.x)에 대고 검증하지는 않았다 — HARDWARE_VERIFICATION.md §5 참조.
