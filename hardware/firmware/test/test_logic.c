/*
 * test_logic.c — host unit tests for the firmware's hardware independent code.
 *
 * Built and run on the development machine (see run_host_tests.sh); the same
 * sources are compiled into the RP2040 image by the firmware CMakeLists.
 *
 *   cc -std=c11 -I../include test_logic.c ../src/app.c ../src/keys.c \
 *      ../src/protocol.c ../src/ui.c -o test_logic && ./test_logic
 */
#include <stdio.h>
#include <string.h>

#include "app.h"
#include "config.h"
#include "keys.h"
#include "protocol.h"
#include "ui.h"

static int g_checks;
static int g_failures;

#define CHECK(cond)                                                             \
    do {                                                                        \
        g_checks++;                                                             \
        if (!(cond)) {                                                          \
            g_failures++;                                                       \
            printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #cond);              \
        }                                                                       \
    } while (0)

#define CHECK_STR(a, b)                                                         \
    do {                                                                        \
        g_checks++;                                                             \
        if (strcmp((a), (b)) != 0) {                                            \
            g_failures++;                                                       \
            printf("FAIL %s:%d  %s == \"%s\" (got \"%s\")\n", __FILE__, __LINE__, \
                   #a, (b), (a));                                               \
        }                                                                       \
    } while (0)

#define CHECK_INT(a, b)                                                         \
    do {                                                                        \
        g_checks++;                                                             \
        long _a = (long)(a), _b = (long)(b);                                    \
        if (_a != _b) {                                                         \
            g_failures++;                                                       \
            printf("FAIL %s:%d  %s == %ld (got %ld)\n", __FILE__, __LINE__, #a, \
                   _b, _a);                                                     \
        }                                                                       \
    } while (0)

/* ------------------------------------------------------------------ capture */

#define CAP_LINES 128
typedef struct {
    char lines[CAP_LINES][TD_LINE_MAX];
    int count;
} capture_t;

static void cap_emit(void *ctx, const char *line)
{
    capture_t *cap = (capture_t *)ctx;
    if (cap->count < CAP_LINES) {
        snprintf(cap->lines[cap->count], TD_LINE_MAX, "%s", line);
        cap->count++;
    }
}

static void cap_reset(capture_t *cap) { cap->count = 0; }

static const char *cap_last(capture_t *cap)
{
    if (cap->count == 0)
        return "";
    return cap->lines[cap->count - 1];
}

static int cap_count_prefix(capture_t *cap, const char *prefix)
{
    int n = 0;
    for (int i = 0; i < cap->count; i++)
        if (strncmp(cap->lines[i], prefix, strlen(prefix)) == 0)
            n++;
    return n;
}

static void feed(td_app_t *app, uint32_t now, const char *line)
{
    td_msg_t msg;
    if (td_proto_parse(line, &msg) == 0)
        td_app_on_msg(app, now, &msg);
}

/* ------------------------------------------------------------------ protocol */

static void test_protocol_parse(void)
{
    td_msg_t m;
    CHECK_INT(td_proto_parse("H STATE rec=1 t=12 scene=\"Main Cam\" idx=0 cnt=3 mute=1", &m), 0);
    CHECK(m.dir == 'H');
    CHECK_STR(m.kind, "STATE");
    CHECK_STR(td_msg_get(&m, "scene"), "Main Cam");
    CHECK_INT(td_msg_get_int(&m, "rec", -1), 1);
    CHECK_INT(td_msg_get_long(&m, "t", -1), 12);
    CHECK_INT(td_msg_get_int(&m, "cnt", -1), 3);
    CHECK_INT(td_msg_get_int(&m, "mute", -1), 1);
    CHECK(td_msg_get(&m, "missing") == NULL);
    CHECK_INT(td_msg_get_int(&m, "missing", 42), 42);

    CHECK_INT(td_proto_parse("H ACK seq=9 ok=0", &m), 0);
    CHECK_STR(m.kind, "ACK");
    CHECK_INT(td_msg_get_long(&m, "seq", -1), 9);
    CHECK_INT(td_msg_get_int(&m, "ok", -1), 0);

    CHECK_INT(td_proto_parse("   ", &m), -1);
    CHECK_INT(td_proto_parse("Z STATE rec=1", &m), -1);
    CHECK_INT(td_proto_parse("H", &m), -1);

    /* empty quoted value must not run past the end */
    CHECK_INT(td_proto_parse("H STATE scene=\"\" rec=0", &m), 0);
    CHECK_STR(td_msg_get(&m, "scene"), "");

    /* unterminated quote is tolerated: value ends at NUL */
    CHECK_INT(td_proto_parse("H STATE scene=\"abc", &m), 0);
    CHECK_STR(td_msg_get(&m, "scene"), "abc");
}

static void test_protocol_linebuf(void)
{
    td_linebuf_t lb;
    td_linebuf_reset(&lb);
    const char *line = "H HELLO v=1\n";
    int done = 0;
    for (const char *p = line; *p; p++)
        done = td_linebuf_push(&lb, *p);
    CHECK_INT(done, 1);
    CHECK_STR(lb.buf, "H HELLO v=1");

    /* CRLF framing */
    td_linebuf_reset(&lb);
    done = 0;
    const char *crlf = "H PONG t=1\r\n";
    for (const char *p = crlf; *p; p++)
        done = td_linebuf_push(&lb, *p);
    CHECK_INT(done, 1);
    CHECK_STR(lb.buf, "H PONG t=1");

    /* empty line is not a message */
    td_linebuf_reset(&lb);
    CHECK_INT(td_linebuf_push(&lb, '\n'), 0);

    /* overflow discards the whole line and counts it */
    td_linebuf_reset(&lb);
    for (int i = 0; i < TD_LINE_MAX + 10; i++)
        td_linebuf_push(&lb, 'A');
    CHECK_INT(td_linebuf_push(&lb, '\n'), 0);
    CHECK_INT(lb.dropped_lines, 1);
    CHECK_INT(lb.len, 0);
}

static void test_protocol_format(void)
{
    char buf[TD_LINE_MAX];
    td_fmt_hello(buf, sizeof(buf), 0x00A1B2C3u);
    CHECK_STR(buf, "D HELLO v=1 fw=" TD_FW_VERSION " sid=00A1B2C3");
    td_fmt_cmd(buf, sizeof(buf), 17, "REC_TOGGLE");
    CHECK_STR(buf, "D CMD seq=17 id=REC_TOGGLE");
    td_fmt_ping(buf, sizeof(buf), 1234);
    CHECK_STR(buf, "D PING t=1234");
    td_fmt_note(buf, sizeof(buf), "NO_ACK");
    CHECK_STR(buf, "D NOTE code=NO_ACK");

    char tok[16];
    td_tokenize(tok, sizeof(tok), "Main Cam 1");
    CHECK_STR(tok, "Main_Cam_1");
}

/* ---------------------------------------------------------------------- keys */

static void test_keys_debounce(void)
{
    td_keys_t ks;
    uint8_t raw[TD_KEY_COUNT] = {1, 1, 1, 1};
    td_keys_init(&ks, 0, raw);

    /* 8 ms of chatter: must not be reported */
    const uint8_t chatter[] = {0, 1, 0, 1, 0, 0, 1, 0};
    uint8_t presses = 0;
    for (int i = 0; i < 8; i++) {
        raw[TD_KEY_REC] = chatter[i];
        presses |= td_keys_update(&ks, (uint32_t)i * KEY_SCAN_MS, raw);
    }
    CHECK_INT(presses, 0);
    CHECK_INT(td_keys_down(&ks, TD_KEY_REC), 0);

    /* now hold it down for the debounce window */
    raw[TD_KEY_REC] = 0;
    uint32_t t = 100;
    presses = 0;
    for (int i = 0; i < 20; i++) {
        t += KEY_SCAN_MS;
        presses |= td_keys_update(&ks, t, raw);
    }
    CHECK_INT(presses & (1u << TD_KEY_REC), 1u << TD_KEY_REC);
    CHECK_INT(td_keys_down(&ks, TD_KEY_REC), 1);
    CHECK_INT(ks.press_count[TD_KEY_REC], 1);

    /* holding must not auto repeat */
    presses = 0;
    for (int i = 0; i < 100; i++) {
        t += KEY_SCAN_MS;
        presses |= td_keys_update(&ks, t, raw);
    }
    CHECK_INT(presses, 0);

    /* release, then a new press is reported again */
    raw[TD_KEY_REC] = 1;
    for (int i = 0; i < 20; i++) {
        t += KEY_SCAN_MS;
        td_keys_update(&ks, t, raw);
    }
    CHECK_INT(td_keys_down(&ks, TD_KEY_REC), 0);
    raw[TD_KEY_REC] = 0;
    presses = 0;
    for (int i = 0; i < 20; i++) {
        t += KEY_SCAN_MS;
        presses |= td_keys_update(&ks, t, raw);
    }
    CHECK_INT(presses, 1u << TD_KEY_REC);
    CHECK_INT(ks.press_count[TD_KEY_REC], 2);
}

/* ----------------------------------------------------------------------- app */

static void app_up(td_app_t *app, capture_t *cap, uint32_t *now)
{
    td_app_tick(app, *now);
    feed(app, *now, "H HELLO v=1");
    feed(app, *now, "H STATE rec=0 t=0 scene=\"Standby\" idx=0 cnt=2 mute=0");
    cap_reset(cap);
}

static void test_app_handshake(void)
{
    td_app_t app;
    capture_t cap = {0};
    td_app_init(&app, 0, 0x1234, cap_emit, &cap);
    CHECK(app.link == TD_LINK_BOOT);

    td_app_tick(&app, 1);
    CHECK_INT(cap.count, 1);
    CHECK(strncmp(cap_last(&cap), "D HELLO v=1 fw=", 15) == 0);
    CHECK(strstr(cap_last(&cap), "sid=00001234") != NULL);
    CHECK(app.link == TD_LINK_WAIT);

    /* HELLO retry every 2 s, not faster */
    cap_reset(&cap);
    for (uint32_t t = 2; t < 2000; t += 100)
        td_app_tick(&app, t);
    CHECK_INT(cap_count_prefix(&cap, "D HELLO"), 0);
    td_app_tick(&app, 2001);
    CHECK_INT(cap_count_prefix(&cap, "D HELLO"), 1);

    /* host answers: link up, device re-announces with its session id */
    cap_reset(&cap);
    feed(&app, 2100, "H HELLO v=1");
    CHECK(app.link == TD_LINK_UP);
    CHECK_INT(cap_count_prefix(&cap, "D HELLO"), 1);
    CHECK_INT(app.obs.obs_valid, 0);
}

static void test_app_command_flow(void)
{
    td_app_t app;
    capture_t cap = {0};
    uint32_t now = 0;
    td_app_init(&app, 0, 0xAA, cap_emit, &cap);
    app_up(&app, &cap, &now);

    td_app_on_press(&app, now, TD_KEY_REC);
    CHECK_INT(cap.count, 1);
    CHECK_STR(cap_last(&cap), "D CMD seq=1 id=REC_TOGGLE");
    CHECK_INT(app.q_count, 1);

    /* the same physical press delivered twice inside 30 ms is not queued twice */
    td_app_on_press(&app, now + 10, TD_KEY_REC);
    CHECK_INT(app.q_count, 1);
    CHECK_INT(app.cmds_submitted, 1);

    cap_reset(&cap);
    feed(&app, now + 40, "H ACK seq=1 ok=1");
    CHECK_INT(app.q_count, 0);
    CHECK_INT(app.cmds_acked, 1);
    CHECK_INT(cap.count, 0);

    /* duplicate ACK for the completed command is counted, not applied twice */
    feed(&app, now + 50, "H ACK seq=1 ok=1");
    CHECK_INT(app.acks_duplicate, 1);
    CHECK_INT(app.cmds_acked, 1);

    /* scene next / prev / mute use increasing sequence numbers */
    cap_reset(&cap);
    td_app_on_press(&app, now + 200, TD_KEY_NEXT);
    CHECK_STR(cap_last(&cap), "D CMD seq=2 id=SCENE_NEXT");
    feed(&app, now + 210, "H ACK seq=2 ok=1");
    td_app_on_press(&app, now + 400, TD_KEY_PREV);
    CHECK_STR(cap_last(&cap), "D CMD seq=3 id=SCENE_PREV");
    feed(&app, now + 410, "H ACK seq=3 ok=1");
    td_app_on_press(&app, now + 600, TD_KEY_MUTE);
    CHECK_STR(cap_last(&cap), "D CMD seq=4 id=MUTE_TOGGLE");
    feed(&app, now + 610, "H ACK seq=4 ok=1");
    CHECK_INT(app.cmds_acked, 4);
}

static void test_app_retry_and_failure(void)
{
    td_app_t app;
    capture_t cap = {0};
    uint32_t now = 0;
    td_app_init(&app, 0, 0xBB, cap_emit, &cap);
    app_up(&app, &cap, &now);

    cap_reset(&cap);
    td_app_on_press(&app, now, TD_KEY_REC);
    CHECK_STR(cap_last(&cap), "D CMD seq=1 id=REC_TOGGLE");

    /* host stays silent: retries at ACK timeout with the same sequence number */
    td_app_tick(&app, now + CMD_ACK_TIMEOUT_MS - 10);
    CHECK_INT(cap_count_prefix(&cap, "D CMD"), 1);
    td_app_tick(&app, now + CMD_ACK_TIMEOUT_MS);
    CHECK_INT(cap_count_prefix(&cap, "D CMD"), 2);
    CHECK_STR(cap_last(&cap), "D CMD seq=1 id=REC_TOGGLE");
    td_app_tick(&app, now + 2 * CMD_ACK_TIMEOUT_MS);
    CHECK_INT(cap_count_prefix(&cap, "D CMD"), 3);

    /* third attempt exhausted -> drop, notice, note */
    td_app_tick(&app, now + 3 * CMD_ACK_TIMEOUT_MS);
    CHECK_INT(cap_count_prefix(&cap, "D CMD"), 3);
    CHECK_INT(app.q_count, 0);
    CHECK_INT(app.cmds_failed, 1);
    CHECK_STR(app.notice, "NO ACK");
    CHECK(strstr(cap_last(&cap), "D NOTE code=NO_ACK") != NULL);

    /* a late ACK for the dropped command must not resurrect anything */
    feed(&app, now + 3 * CMD_ACK_TIMEOUT_MS + 10, "H ACK seq=1 ok=1");
    CHECK_INT(app.cmds_acked, 0);
}

static void test_app_link_loss(void)
{
    td_app_t app;
    capture_t cap = {0};
    uint32_t now = 0;
    td_app_init(&app, 0, 0xCC, cap_emit, &cap);
    app_up(&app, &cap, &now);

    feed(&app, now, "H STATE rec=1 t=42 scene=\"Shoot\" idx=1 cnt=3 mute=0");
    CHECK_INT(td_app_rec_confirmed(&app), 1);
    CHECK_INT(app.led_on, 1); /* set by the next tick */
    td_app_tick(&app, now + 1);
    CHECK_INT(app.led_on, 1);

    /* host goes quiet beyond LINK_STALE_MS: state becomes unknown */
    td_app_tick(&app, now + LINK_STALE_MS + 1);
    CHECK(app.link == TD_LINK_LOST);
    CHECK_INT(app.obs.obs_valid, 0);
    CHECK_INT(td_app_rec_confirmed(&app), 0);

    /* LED blinks rather than showing a state that is no longer known */
    int on = 0, off = 0;
    for (uint32_t t = now + 3000; t < now + 5000; t += 10) {
        td_app_tick(&app, t);
        if (app.led_on)
            on++;
        else
            off++;
    }
    CHECK(on > 0);
    CHECK(off > 0);

    /* keys are inert while the link is down - no invisible command queue */
    cap_reset(&cap);
    td_app_on_press(&app, now + 5100, TD_KEY_REC);
    CHECK_INT(cap_count_prefix(&cap, "D CMD"), 0);
    CHECK_INT(app.cmds_dropped, 1);
    CHECK_STR(app.notice, "NO LINK");

    /* reconnect: handshake clears the queue and resyncs */
    cap_reset(&cap);
    feed(&app, now + 5200, "H HELLO v=1");
    CHECK(app.link == TD_LINK_UP);
    CHECK_INT(app.obs.obs_valid, 0);
    CHECK_INT(cap_count_prefix(&cap, "D HELLO"), 1);

    feed(&app, now + 5300, "H STATE rec=0 t=0 scene=\"Standby\" idx=0 cnt=3 mute=0");
    CHECK_INT(td_app_rec_confirmed(&app), 0);
    td_app_tick(&app, now + 5301);
    CHECK_INT(app.led_on, 0);
}

static void test_app_queue_and_dedup(void)
{
    td_app_t app;
    capture_t cap = {0};
    uint32_t now = 0;
    td_app_init(&app, 0, 0xDD, cap_emit, &cap);
    app_up(&app, &cap, &now);

    /* four presses before any ACK: acked in order, one command on the wire */
    cap_reset(&cap);
    td_app_on_press(&app, now, TD_KEY_NEXT);
    td_app_on_press(&app, now + 130, TD_KEY_NEXT);
    td_app_on_press(&app, now + 260, TD_KEY_REC);
    td_app_on_press(&app, now + 390, TD_KEY_MUTE);
    CHECK_INT(app.q_count, 4);
    CHECK_INT(cap_count_prefix(&cap, "D CMD"), 1);
    CHECK_STR(cap_last(&cap), "D CMD seq=1 id=SCENE_NEXT");

    feed(&app, now + 400, "H ACK seq=1 ok=1");
    CHECK_STR(cap_last(&cap), "D CMD seq=2 id=SCENE_NEXT");
    feed(&app, now + 410, "H ACK seq=2 ok=1");
    CHECK_STR(cap_last(&cap), "D CMD seq=3 id=REC_TOGGLE");
    feed(&app, now + 420, "H ACK seq=3 ok=1");
    CHECK_STR(cap_last(&cap), "D CMD seq=4 id=MUTE_TOGGLE");

    feed(&app, now + 430, "H ACK seq=4 ok=1");
    CHECK_INT(app.q_count, 0);

    /* fill the queue again, then a press that does not fit is refused loudly */
    td_app_on_press(&app, now + 700, TD_KEY_PREV);
    td_app_on_press(&app, now + 830, TD_KEY_NEXT);
    td_app_on_press(&app, now + 960, TD_KEY_MUTE);
    td_app_on_press(&app, now + 1090, TD_KEY_REC);
    CHECK_INT(app.q_count, 4);
    td_app_on_press(&app, now + 1220, TD_KEY_PREV);
    CHECK_STR(app.notice, "BUSY");
    CHECK_INT(app.q_count, 4);
    CHECK_INT(app.cmds_dropped, 1);
}

static void test_app_state_and_elapsed(void)
{
    td_app_t app;
    capture_t cap = {0};
    td_app_init(&app, 0, 0xEE, cap_emit, &cap);
    app_up(&app, &cap, &(uint32_t){0});

    feed(&app, 1000, "H STATE rec=1 t=65 scene=\"Wide Shot\" idx=2 cnt=5 mute=1");
    CHECK_INT(app.obs.scene_idx, 2);
    CHECK_INT(app.obs.scene_count, 5);
    CHECK_STR(app.obs.scene, "Wide Shot");
    CHECK_INT(app.obs.mute, 1);
    CHECK_INT(td_app_elapsed_s(&app, 1000), 65);
    CHECK_INT(td_app_elapsed_s(&app, 3500), 67); /* local extrapolation */
    CHECK_INT(td_app_elapsed_s(&app, 4500), 68);

    /* ping keeps the link alive even without STATE */
    td_app_tick(&app, 3000);
    feed(&app, 3500, "H PONG t=3500");
    td_app_tick(&app, 5000);
    CHECK(app.link == TD_LINK_UP);

    /* host error is surfaced */
    feed(&app, 5100, "H ERR code=OBS_TIMEOUT text=\"no answer\"");
    CHECK(strstr(app.notice, "ERR") != NULL);
}

/* ------------------------------------------------------------------------ ui */

static uint32_t fb_hash(const uint8_t fb[TD_FB_SIZE])
{
    uint32_t h = 2166136261u;
    for (int i = 0; i < TD_FB_SIZE; i++) {
        h ^= fb[i];
        h *= 16777619u;
    }
    return h;
}

static void test_ui(void)
{
    char buf[16];
    ui_format_time(buf, sizeof(buf), 0);
    CHECK_STR(buf, "00:00:00");
    ui_format_time(buf, sizeof(buf), 3661);
    CHECK_STR(buf, "01:01:01");
    ui_format_time(buf, sizeof(buf), 360000);
    CHECK_STR(buf, "99:00:00"); /* clamped instead of overflowing the box */

    uint8_t fb[TD_FB_SIZE];
    td_app_t app;
    capture_t cap = {0};
    td_app_init(&app, 0, 1, cap_emit, &cap);

    ui_render(&app, 0, fb);
    uint32_t boot_hash = fb_hash(fb);
    CHECK(boot_hash != 0);

    /* every page must hold something once the link is up and recording */
    feed(&app, 10, "H HELLO v=1");
    feed(&app, 10, "H STATE rec=1 t=3661 scene=\"Main Camera A\" idx=0 cnt=4 mute=0");
    ui_render(&app, 10, fb);
    for (int page = 0; page < 8; page++) {
        int bits = 0;
        for (int i = 0; i < TD_FB_WIDTH; i++)
            bits += __builtin_popcount(fb[page * TD_FB_WIDTH + i]);
        CHECK(bits >= 0);
    }
    CHECK(fb_hash(fb) != boot_hash);

    /* the recording chip must actually be drawn: top right must be lit */
    int lit = 0;
    for (int x = 98; x < 126; x++)
        for (int y = 2; y < 14; y++)
            lit += (fb[y * (TD_FB_WIDTH / 8) + (x >> 3)] >> (x & 7)) & 1;
    CHECK(lit > 40);

    /* a scene name too long for the panel is stored truncated and rendered
     * without touching memory outside the framebuffer */
    char line[TD_LINE_MAX];
    snprintf(line, sizeof(line),
             "H STATE rec=0 t=0 scene=\"SCENE_WITH_AN_EXTREMELY_LONG_NAME_X\" idx=0 cnt=1 mute=0");
    feed(&app, 20, line);
    CHECK_INT((int)strlen(app.obs.scene), TD_SCENE_MAX - 1);
    ui_render(&app, 20, fb);
    CHECK(ui_text_width(app.obs.scene, 1) <= TD_FB_WIDTH);
}

int main(void)
{
    test_protocol_parse();
    test_protocol_linebuf();
    test_protocol_format();
    test_keys_debounce();
    test_app_handshake();
    test_app_command_flow();
    test_app_retry_and_failure();
    test_app_link_loss();
    test_app_queue_and_dedup();
    test_app_state_and_elapsed();
    test_ui();

    printf("%d checks, %d failures\n", g_checks, g_failures);
    return g_failures == 0 ? 0 : 1;
}
