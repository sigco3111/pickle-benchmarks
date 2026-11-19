/*
 * TakeDeck TD-01 — USB OBS recording controller
 * main.c : hardware glue.
 *
 * Everything that can be tested without a board lives in app.c / protocol.c /
 * keys.c / ui.c. This file only initialises pins, pumps the 1 ms loop and
 * moves bytes between the USB CDC port and the application layer.
 */
#include <stdio.h>
#include <string.h>

#include "app.h"
#include "config.h"
#include "hardware/gpio.h"
#include "pico/rand.h"
#include "pico/stdlib.h"
#include "protocol.h"
#include "ssd1306.h"
#include "ui.h"

static td_app_t    app;
static td_keys_t   keys;
static td_linebuf_t rx;
static uint8_t     fb[TD_FB_SIZE];

static int      s_flush_page = 0;
static uint8_t  s_need_flush = 0;
static uint32_t s_last_ui_ms = 0;
static uint32_t s_last_scan_ms = 0;

static void emit_line(void *ctx, const char *line)
{
    (void)ctx;
    /* stdio over USB CDC: dropped by the SDK when no host is listening. */
    fputs(line, stdout);
    fputc('\n', stdout);
    fflush(stdout);
}

static uint32_t read_session_id(void)
{
    /* A fresh session id per boot: the host uses (sid, seq) to drop duplicates
     * that survive a USB re-enumeration. */
#if defined(PICO_ON_DEVICE) && PICO_ON_DEVICE
    return get_rand_32();
#else
    return 0x54440001u;
#endif
}

static void pins_init(void)
{
    const uint8_t pins[TD_KEY_COUNT] = {PIN_KEY_REC, PIN_KEY_PREV, PIN_KEY_NEXT, PIN_KEY_MUTE};
    for (int i = 0; i < TD_KEY_COUNT; i++) {
        gpio_init(pins[i]);
        gpio_set_dir(pins[i], GPIO_IN);
        gpio_pull_up(pins[i]);
    }
    gpio_init(PIN_LED_REC);
    gpio_set_dir(PIN_LED_REC, GPIO_OUT);
    gpio_put(PIN_LED_REC, 0);
}

static void read_raw(uint8_t raw[TD_KEY_COUNT])
{
    const uint8_t pins[TD_KEY_COUNT] = {PIN_KEY_REC, PIN_KEY_PREV, PIN_KEY_NEXT, PIN_KEY_MUTE};
    for (int i = 0; i < TD_KEY_COUNT; i++)
        raw[i] = (uint8_t)gpio_get(pins[i]); /* 1 = released */
}

static void pump_serial(uint32_t now_ms)
{
    int c;
    while ((c = getchar_timeout_us(0)) >= 0) {
        if (td_linebuf_push(&rx, (char)c)) {
            td_msg_t msg;
            if (td_proto_parse(rx.buf, &msg) == 0) {
                td_app_on_msg(&app, now_ms, &msg);
            } else {
                app.line_errors++;
            }
        }
    }
}

int main(void)
{
    stdio_init_all();
    pins_init();
    ssd1306_init();

    uint32_t now = to_ms_since_boot(get_absolute_time());
    td_linebuf_reset(&rx);

    uint8_t raw[TD_KEY_COUNT];
    read_raw(raw);
    td_keys_init(&keys, now, raw);
    td_app_init(&app, now, read_session_id(), emit_line, NULL);

    ui_render(&app, now, fb);
    ssd1306_flush(fb);
    app.dirty = 0;

    for (;;) {
        now = to_ms_since_boot(get_absolute_time());

        pump_serial(now);

        if ((uint32_t)(now - s_last_scan_ms) >= KEY_SCAN_MS) {
            s_last_scan_ms = now;
            read_raw(raw);
            uint8_t presses = td_keys_update(&keys, now, raw);
            for (int i = 0; i < TD_KEY_COUNT; i++)
                if (presses & (1u << i))
                    td_app_on_press(&app, now, (td_key_id_t)i);
        }

        td_app_tick(&app, now);
        gpio_put(PIN_LED_REC, app.led_on ? 1 : 0);

        if (app.dirty && (uint32_t)(now - s_last_ui_ms) >= 10) {
            app.dirty = 0;
            s_last_ui_ms = now;
            ui_render(&app, now, fb);
            s_need_flush = 1;
            s_flush_page = 0;
        }

        /* One 128-byte page per pass keeps the loop responsive (~1.3 ms at
         * 400 kHz); a full refresh therefore takes ~10 ms. */
        if (s_need_flush) {
            ssd1306_flush_page(fb, s_flush_page);
            if (++s_flush_page >= 8) {
                s_flush_page = 0;
                s_need_flush = 0;
            }
        }

        tight_loop_contents();
    }
}
