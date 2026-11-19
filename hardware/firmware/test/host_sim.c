/*
 * host_sim.c — runs the real firmware application code on the PC.
 *
 * The application layer (app.c, keys.c, protocol.c, ui.c) is hardware
 * independent, so this simulator drives exactly the same state machine the
 * RP2040 runs, with the pins replaced by commands read from stdin and the USB
 * CDC port replaced by stdout. host/tests use it to test the Python bridge
 * against real firmware logic instead of a hand written fake.
 *
 * stdin commands (one per line):
 *   PRESS <REC|PREV|NEXT|MUTE>   drive the key low for 30 ms
 *   HOST <protocol line>         deliver a host->device line ("H ...")
 *   LED                          print "#LED <0|1>"
 *   FB                           print "#FB <hash> <notice>"
 *   SPEED <factor>               multiply the simulated clock (default 1.0)
 *   RESET                        re-initialise the application (new session)
 *   QUIT                         exit
 *
 * Every line the firmware would write to USB is printed to stdout verbatim,
 * diagnostics are prefixed with '#'.
 */
#define _DEFAULT_SOURCE
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <sys/select.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include "app.h"
#include "config.h"
#include "keys.h"
#include "protocol.h"
#include "ui.h"

static td_app_t app;
static td_keys_t keys;
static uint8_t fb[TD_FB_SIZE];
static uint32_t base_real_ms;
static double speed = 1.0;
static uint32_t session = 0x0BADC0DEu;
static uint8_t raw[TD_KEY_COUNT] = {1, 1, 1, 1};
static uint32_t hold_until[TD_KEY_COUNT];
static uint32_t last_tick_ms;
static int last_led_reported = -1;
static int last_link_reported = -1;

static uint32_t real_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint32_t)(ts.tv_sec * 1000u + ts.tv_nsec / 1000000u);
}

static uint32_t now_ms(void)
{
    return (uint32_t)((real_ms() - base_real_ms) * speed);
}

static uint32_t fb_hash(void)
{
    uint32_t h = 2166136261u;
    for (int i = 0; i < TD_FB_SIZE; i++) {
        h ^= fb[i];
        h *= 16777619u;
    }
    return h;
}

static void emit(void *ctx, const char *line)
{
    (void)ctx;
    printf("%s\n", line);
    fflush(stdout);
}

static void app_start(uint32_t now)
{
    td_linebuf_t dummy;
    (void)dummy;
    memset(raw, 1, sizeof(raw));
    for (int i = 0; i < TD_KEY_COUNT; i++)
        td_keys_init(&keys, now, raw), hold_until[i] = 0;
    td_keys_init(&keys, now, raw);
    td_app_init(&app, now, session, emit, NULL);
    last_tick_ms = now;
}

static int key_from_name(const char *name)
{
    if (strcmp(name, "REC") == 0) return TD_KEY_REC;
    if (strcmp(name, "PREV") == 0) return TD_KEY_PREV;
    if (strcmp(name, "NEXT") == 0) return TD_KEY_NEXT;
    if (strcmp(name, "MUTE") == 0) return TD_KEY_MUTE;
    return -1;
}

static void handle_command(const char *line)
{
    if (strncmp(line, "PRESS ", 6) == 0) {
        int k = key_from_name(line + 6);
        if (k >= 0) {
            raw[k] = 0;
            hold_until[k] = now_ms() + 30;
        }
    } else if (strncmp(line, "HOST ", 5) == 0) {
        td_msg_t msg;
        if (td_proto_parse(line + 5, &msg) == 0) {
            td_app_on_msg(&app, now_ms(), &msg);
            if (getenv("TAKEDECK_SIM_TRACE"))
                fprintf(stderr, "#RX %s\n", msg.kind);
        }
    } else if (strcmp(line, "LED") == 0) {
        printf("#LED %d link=%d valid=%d rec=%d\n", app.led_on ? 1 : 0, (int)app.link, (int)app.obs.obs_valid, (int)app.obs.rec);
        fflush(stdout);
    } else if (strcmp(line, "FB") == 0) {
        ui_render(&app, now_ms(), fb);
        printf("#FB %08X %s\n", fb_hash(), app.notice);
        fflush(stdout);
    } else if (strncmp(line, "SPEED ", 6) == 0) {
        double s = atof(line + 6);
        if (s > 0.0) {
            base_real_ms = real_ms() - (uint32_t)(now_ms() / s);
            speed = s;
        }
    } else if (strcmp(line, "RESET") == 0) {
        session += 1;
        base_real_ms = real_ms();
        app_start(now_ms());
    } else if (strcmp(line, "QUIT") == 0) {
        exit(0);
    }
}

int main(void)
{
    base_real_ms = real_ms();
    setvbuf(stdout, NULL, _IOLBF, 0);
    app_start(now_ms());

    /* stdin is read with read(2), not stdio: mixing fgets with select() loses
     * lines that stdio already buffered. */
    char inbuf[4096];
    size_t inlen = 0;
    for (;;) {
        fd_set rfds;
        struct timeval tv = {0, 1000};
        FD_ZERO(&rfds);
        FD_SET(STDIN_FILENO, &rfds);
        if (select(STDIN_FILENO + 1, &rfds, NULL, NULL, &tv) > 0) {
            char chunk[512];
            ssize_t got = read(STDIN_FILENO, chunk, sizeof(chunk));
            if (got <= 0)
                exit(0);
            for (ssize_t i = 0; i < got && inlen < sizeof(inbuf) - 1; i++)
                inbuf[inlen++] = chunk[i];
            /* consume every complete line in the buffer */
            size_t start = 0;
            for (size_t i = 0; i < inlen; i++) {
                if (inbuf[i] != '\n')
                    continue;
                size_t len = i - start;
                while (len > 0 && inbuf[start + len - 1] == '\r')
                    len--;
                if (len > 0) {
                    char line[512];
                    size_t copy = len < sizeof(line) - 1 ? len : sizeof(line) - 1;
                    memcpy(line, inbuf + start, copy);
                    line[copy] = '\0';
                    handle_command(line);
                }
                start = i + 1;
            }
            if (start > 0) {
                memmove(inbuf, inbuf + start, inlen - start);
                inlen -= start;
            }
            continue;
        }

        uint32_t now = now_ms();
        for (int i = 0; i < TD_KEY_COUNT; i++) {
            if (raw[i] == 0 && (int32_t)(now - hold_until[i]) >= 0)
                raw[i] = 1;
        }
        uint8_t presses = td_keys_update(&keys, now, raw);
        for (int i = 0; i < TD_KEY_COUNT; i++)
            if (presses & (1u << i))
                td_app_on_press(&app, now, (td_key_id_t)i);

        td_app_tick(&app, now);
        last_tick_ms = now;

        /* diagnostics for host/tests: the physical LED level whenever it
         * changes, so a test can assert "the LED follows OBS". */
        if ((int)app.link != last_link_reported) {
            static const char *names[] = {"BOOT", "WAIT", "UP", "LOST"};
            last_link_reported = app.link;
            printf("#LINK %s\n", names[app.link]);
            fflush(stdout);
        }

        if ((int)app.led_on != last_led_reported) {
            last_led_reported = app.led_on;
            printf("#LED %d link=%d valid=%d rec=%d\n", app.led_on ? 1 : 0, (int)app.link, (int)app.obs.obs_valid, (int)app.obs.rec);
            fflush(stdout);
        }
    }
}
