/*
 * protocol.h — newline delimited key/value text protocol over USB CDC.
 *
 * Every message is one ASCII line terminated by '\n'. A line starts with a
 * direction tag ("D" device->host, "H" host->device) and a message kind.
 * Values are either bare tokens (no spaces) or double quoted strings.
 *
 * This module contains no hardware access so it can be compiled for the host
 * and unit tested (see test/test_logic.c).
 */
#ifndef TD_PROTOCOL_H
#define TD_PROTOCOL_H

#include <stddef.h>
#include <stdint.h>

#define TD_LINE_MAX 192
#define TD_MAX_KV   8
#define TD_KEY_MAX  16
#define TD_VAL_MAX  40

typedef struct {
    char key[TD_KEY_MAX];
    char val[TD_VAL_MAX];
} td_kv_t;

typedef struct {
    char     dir;                 /* 'D' or 'H' */
    char     kind[12];            /* HELLO, CMD, PING, STATE, ACK, PONG, ERR, NOTE */
    td_kv_t  kv[TD_MAX_KV];
    uint8_t  n_kv;
    uint8_t  truncated;           /* 1 if the line did not fit the buffer */
} td_msg_t;

/* Line accumulator used by the receive path. */
typedef struct {
    char   buf[TD_LINE_MAX + 1];
    size_t len;
    uint8_t overflow;
    uint32_t dropped_lines;
} td_linebuf_t;

void td_linebuf_reset(td_linebuf_t *lb);

/*
 * Push one received byte. Returns 1 when a complete line is available in
 * lb->buf (already NUL terminated), 0 otherwise. '\r' is ignored.
 * A line that overflows is discarded and counted in dropped_lines.
 */
int td_linebuf_push(td_linebuf_t *lb, char c);

/*
 * Parse a line into msg. Returns 0 on success, -1 when the line is empty or
 * malformed. Unknown kinds still parse (kind is copied verbatim) so the caller
 * can ignore them.
 */
int td_proto_parse(const char *line, td_msg_t *msg);

/* Value lookup helpers; return NULL when the key is absent. */
const char *td_msg_get(const td_msg_t *msg, const char *key);
int  td_msg_get_int(const td_msg_t *msg, const char *key, int def);
long td_msg_get_long(const td_msg_t *msg, const char *key, long def);

/* ---- formatting (always NUL terminates, returns strlen) ---- */
int td_fmt_hello(char *out, size_t cap, uint32_t session_id);
int td_fmt_hello_nosid(char *out, size_t cap); /* handshake request variant */
int td_fmt_cmd(char *out, size_t cap, uint32_t seq, const char *id);
int td_fmt_ping(char *out, size_t cap, uint32_t t_ms);
int td_fmt_note(char *out, size_t cap, const char *code);

/* Copy src into dst as a bare token, replacing spaces and control characters
 * with '_'. Used for scene names arriving from OBS so that a device-side echo
 * can never break framing. */
void td_tokenize(char *dst, size_t cap, const char *src);

#endif /* TD_PROTOCOL_H */
