# host/ — TakeDeck 브리지

USB 시리얼(CDC)로 들어온 컨트롤러 명령을 **obs-websocket v5**(OBS Studio 28+)로 옮기고,
OBS의 실제 상태를 다시 컨트롤러로 밀어 주는 작은 상주 프로그램.

```bash
python3 -m pip install -r requirements.txt
export TAKEDECK_OBS_PASSWORD='...'        # OBS에 비밀번호를 설정한 경우
python3 -m takedeck --mute-input "Mic/Aux"
```

## 설계 요점

| 문제 | 처리 |
|---|---|
| OBS가 죽거나 재시작 | 1→2→4…15초 백오프로 재접속, 그동안 `H ERR code=OBS_DOWN`을 1초 간격으로 보내 기기에 표시 |
| 케이블 재삽입 | 링크가 끊기면 포트를 다시 찾아 2초 간격으로 재시도(새 세션 ID로 핸드셰이크) |
| 명령 중복 | `(세션 ID, 시퀀스)` 키로 실행 결과를 캐시. 재전송·ACK 유실·브리지 재시작에도 토글이 두 번 실행되지 않음(`--ack-cache`) |
| 토글의 의미 | `REC_TOGGLE`은 실행 직전에 OBS 상태를 다시 조회해 시작/중지를 결정 |
| 장면 순환 | obs-websocket에는 "다음 장면" 요청이 없으므로 목록을 받아 인덱스를 계산 (OBS는 최신 장면을 앞에 주므로 뒤집어 사용) |
| 상태 반영 | 250 ms 주기 폴링. OBS UI에서 직접 녹화를 켜도 LED가 따라간다 |

## 구성

| 파일 | 역할 |
|---|---|
| `takedeck/protocol.py` | 장치↔호스트 텍스트 프로토콜 코덱 |
| `takedeck/obs.py` | `ObsBackend` 인터페이스 + `simpleobsws` 구현 |
| `takedeck/link.py` | pyserial 시리얼 링크(수신 스레드), 포트 탐색, 데모용 루프백 |
| `takedeck/bridge.py` | 핵심 상태 기계, 중복 차단 캐시, 재연결 |
| `takedeck/cli.py` | 실행 진입점, 인자, 신호 처리 |
| `mock_obs.py` | obs-websocket v5 모의 서버(인증 포함). OBS 없이 개발·시험용 |

## 테스트

```bash
python3 -m pytest tests -v
```

- `tests/test_protocol.py` — 코덱
- `tests/test_bridge.py` — 상태 기계 (가짜 링크·가짜 OBS)
- `tests/test_obs_ws.py` — 실제 `simpleobsws` 클라이언트 ↔ 모의 서버 (msgpack, 인증, 오류)
- `tests/test_integration.py` — **실제 펌웨어 시뮬레이터**(`../firmware/test/host_sim`) ↔ 브리지 ↔ 모의 OBS

`test_integration.py`는 `firmware/test/build/host_sim`이 있어야 한다:

```bash
cd ../firmware/test && CC=gcc ./run_host_tests.sh
```

## 모의 OBS로 개발하기

```bash
python3 mock_obs.py --port 4455 --password test
TAKEDECK_OBS_PASSWORD=test python3 -m takedeck --port /dev/ttyACM0
```

모의 서버는 `GetVersion`, `GetRecordStatus`, `StartRecord`, `StopRecord`, `ToggleRecord`,
`GetSceneList`, `GetCurrentProgramScene`, `SetCurrentProgramScene`, `GetInputList`,
`GetInputMute`, `ToggleInputMute`만 구현한다. 그 외 요청은 `204 unknown request type`으로 거절한다.

## 인증정보

비밀번호는 파일에 저장하지 않는다. `--obs-password` 또는 `TAKEDECK_OBS_PASSWORD`만 사용하고,
로그에도 남기지 않는다.
