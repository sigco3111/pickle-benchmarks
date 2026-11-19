"""Device <-> host text protocol codec.

Wire format (one message per line, ASCII):

    D HELLO v=1 fw=1.0.0 sid=0A1B2C3D      device announces itself
    D CMD seq=12 id=REC_TOGGLE              a user action, needs an ACK
    D PING t=12345                          once per second
    D NOTE code=NO_ACK                      diagnostic, no reply expected

    H HELLO v=1                             host is present
    H ACK seq=12 ok=1 [err=CODE]            command result
    H STATE rec=0 t=0 scene="Standby" idx=0 cnt=2 mute=0
    H PONG t=12345                          answer to D PING
    H ERR code=OBS_DOWN text="..."          host side problem

Values are bare tokens or double quoted strings; scene names arrive quoted
because OBS scene names may contain spaces.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

PROTO_VERSION = 1

_QUOTED = re.compile(r'"((?:[^"\\]|\\.)*)"')


@dataclass
class DeviceMessage:
    direction: str
    kind: str
    fields: dict[str, str] = field(default_factory=dict)

    def get(self, key: str, default: str | None = None) -> str | None:
        return self.fields.get(key, default)

    def get_int(self, key: str, default: int | None = None) -> int | None:
        raw = self.fields.get(key)
        if raw is None or raw == "":
            return default
        try:
            return int(raw, 10)
        except ValueError:
            return default


def _tokenize(line: str) -> list[str]:
    """Split on whitespace, honouring double quoted values that may contain spaces."""
    tokens: list[str] = []
    buf: list[str] = []
    in_quote = False
    escape = False
    for ch in line:
        if escape:
            buf.append(ch)
            escape = False
            continue
        if in_quote and ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_quote = not in_quote
            buf.append(ch)
            continue
        if ch.isspace() and not in_quote:
            if buf:
                tokens.append("".join(buf))
                buf = []
            continue
        buf.append(ch)
    if buf:
        tokens.append("".join(buf))
    return tokens


def _unquote(value: str) -> str:
    if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
        inner = value[1:-1]
        return inner.replace('\\"', '"').replace("\\\\", "\\")
    return value


def parse_line(line: str) -> DeviceMessage | None:
    """Parse one protocol line; returns None when the line is not a message."""
    line = line.strip()
    if not line:
        return None
    tokens = _tokenize(line)
    if len(tokens) < 2:
        return None
    direction, kind = tokens[0], tokens[1]
    if direction not in ("D", "H") or not kind.isupper():
        return None
    msg = DeviceMessage(direction, kind)
    for token in tokens[2:]:
        if "=" in token:
            key, _, value = token.partition("=")
            msg.fields[key] = _unquote(value)
        else:
            msg.fields[token] = ""
    return msg


def quote(value: str) -> str:
    """Bare token when possible, otherwise a quoted and escaped string."""
    if value and all(0x21 <= ord(c) <= 0x7E and c not in '"\\' for c in value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


# ---------------------------------------------------------------- host -> device


def hello() -> str:
    return f"H HELLO v={PROTO_VERSION}"


def pong(t_ms: int) -> str:
    return f"H PONG t={int(t_ms)}"


def ack(seq: int, ok: bool, err: str | None = None) -> str:
    line = f"H ACK seq={int(seq)} ok={1 if ok else 0}"
    if err:
        line += f" err={err}"
    return line


def err(code: str, text: str = "") -> str:
    line = f"H ERR code={code}"
    if text:
        line += f" text={quote(text)}"
    return line


@dataclass
class ObsStateSnapshot:
    rec: bool
    elapsed_s: int
    scene: str
    idx: int
    count: int
    mute: bool


def state(snapshot: ObsStateSnapshot) -> str:
    return (
        f"H STATE rec={1 if snapshot.rec else 0} t={int(snapshot.elapsed_s)} "
        f"scene={quote(snapshot.scene)} idx={int(snapshot.idx)} "
        f"cnt={int(snapshot.count)} mute={1 if snapshot.mute else 0}"
    )
