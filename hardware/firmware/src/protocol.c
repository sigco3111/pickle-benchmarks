#include "protocol.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "config.h"

static int is_space(char c) { return c == ' ' || c == '\t'; }

void td_linebuf_reset(td_linebuf_t *lb)
{
    lb->len = 0;
    lb->overflow = 0;
    lb->buf[0] = '\0';
}

int td_linebuf_push(td_linebuf_t *lb, char c)
{
    if (c == '\r')
        return 0;

    if (c == '\n') {
        lb->buf[lb->len] = '\0';
        if (lb->overflow) {
            /* discard the whole corrupt line, ask the caller for nothing */
            lb->dropped_lines++;
            lb->overflow = 0;
            lb->len = 0;
            lb->buf[0] = '\0';
            return 0;
        }
        int complete = lb->len > 0;
        lb->len = 0;
        return complete;
    }

    if (lb->len >= TD_LINE_MAX) {
        lb->overflow = 1;
        return 0;
    }
    lb->buf[lb->len++] = c;
    return 0;
}

static void copy_bounded(char *dst, size_t cap, const char *src, size_t n)
{
    if (cap == 0)
        return;
    size_t i = 0;
    for (; i < n && i + 1 < cap; i++)
        dst[i] = src[i];
    dst[i] = '\0';
}

int td_proto_parse(const char *line, td_msg_t *msg)
{
    memset(msg, 0, sizeof(*msg));
    if (!line)
        return -1;

    const char *p = line;
    while (is_space(*p))
        p++;
    if (*p == '\0')
        return -1;

    msg->dir = *p++;
    if (msg->dir != 'D' && msg->dir != 'H')
        return -1;
    while (is_space(*p))
        p++;

    /* kind */
    size_t start = 0;
    while (p[start] && !is_space(p[start]))
        start++;
    if (start == 0)
        return -1;
    copy_bounded(msg->kind, sizeof(msg->kind), p, start);
    p += start;

    while (*p) {
        while (is_space(*p))
            p++;
        if (*p == '\0')
            break;

        const char *key = p;
        size_t klen = 0;
        while (p[klen] && p[klen] != '=' && !is_space(p[klen]))
            klen++;

        const char *val = NULL;
        size_t vlen = 0;

        if (p[klen] == '=') {
            p += klen + 1;
            if (*p == '"') {
                p++;
                val = p;
                while (*p && *p != '"')
                    p++;
                vlen = (size_t)(p - val);
                if (*p == '"')
                    p++;
            } else {
                val = p;
                while (*p && !is_space(*p))
                    p++;
                vlen = (size_t)(p - val);
            }
        } else {
            /* bare token without '=': key only */
            val = "";
            vlen = 0;
            p = key + klen;
        }

        if (msg->n_kv < TD_MAX_KV) {
            td_kv_t *kv = &msg->kv[msg->n_kv++];
            copy_bounded(kv->key, sizeof(kv->key), key, klen);
            copy_bounded(kv->val, sizeof(kv->val), val, vlen);
        } else {
            msg->truncated = 1;
        }
    }
    return 0;
}

const char *td_msg_get(const td_msg_t *msg, const char *key)
{
    for (uint8_t i = 0; i < msg->n_kv; i++)
        if (strcmp(msg->kv[i].key, key) == 0)
            return msg->kv[i].val;
    return NULL;
}

int td_msg_get_int(const td_msg_t *msg, const char *key, int def)
{
    const char *v = td_msg_get(msg, key);
    if (!v || !*v)
        return def;
    char *end = NULL;
    long parsed = strtol(v, &end, 10);
    if (end == v)
        return def;
    return (int)parsed;
}

long td_msg_get_long(const td_msg_t *msg, const char *key, long def)
{
    const char *v = td_msg_get(msg, key);
    if (!v || !*v)
        return def;
    char *end = NULL;
    long parsed = strtol(v, &end, 10);
    if (end == v)
        return def;
    return parsed;
}

int td_fmt_hello(char *out, size_t cap, uint32_t session_id)
{
    int n = snprintf(out, cap, "D HELLO v=%d fw=%s sid=%08lX",
                     TD_PROTO_VERSION, TD_FW_VERSION, (unsigned long)session_id);
    return n < 0 ? 0 : n;
}

int td_fmt_hello_nosid(char *out, size_t cap)
{
    int n = snprintf(out, cap, "D HELLO v=%d fw=%s", TD_PROTO_VERSION, TD_FW_VERSION);
    return n < 0 ? 0 : n;
}

int td_fmt_cmd(char *out, size_t cap, uint32_t seq, const char *id)
{
    int n = snprintf(out, cap, "D CMD seq=%lu id=%s", (unsigned long)seq, id);
    return n < 0 ? 0 : n;
}

int td_fmt_ping(char *out, size_t cap, uint32_t t_ms)
{
    int n = snprintf(out, cap, "D PING t=%lu", (unsigned long)t_ms);
    return n < 0 ? 0 : n;
}

int td_fmt_note(char *out, size_t cap, const char *code)
{
    int n = snprintf(out, cap, "D NOTE code=%s", code);
    return n < 0 ? 0 : n;
}

void td_tokenize(char *dst, size_t cap, const char *src)
{
    if (cap == 0)
        return;
    size_t i = 0;
    for (; src && src[i] && i + 1 < cap; i++) {
        unsigned char c = (unsigned char)src[i];
        if (c == ' ' || c == '\t' || c == '\n' || c == '\r' || c < 0x20)
            dst[i] = '_';
        else
            dst[i] = (char)c;
    }
    dst[i] = '\0';
}
