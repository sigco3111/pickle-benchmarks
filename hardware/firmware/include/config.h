/*
 * TakeDeck TD-01 — USB OBS recording controller
 * config.h : board pin map, timings and protocol constants.
 *
 * The pin map is fixed for the Seeed Studio XIAO RP2040 (RP2040, USB-C).
 * GPIO numbers are the RP2040 pin numbers the XIAO exposes on D0..D10
 * (see HARDWARE_SOURCES.md for the manufacturer pin map).
 */
#ifndef TD_CONFIG_H
#define TD_CONFIG_H

#define TD_FW_VERSION   "1.0.0"
#define TD_PROTO_VERSION 1

/* ---- Key input (active low, internal pull-ups) ---- */
#define PIN_KEY_REC     26  /* XIAO D0 */
#define PIN_KEY_PREV    27  /* XIAO D1 */
#define PIN_KEY_NEXT    28  /* XIAO D2 */
#define PIN_KEY_MUTE    29  /* XIAO D3 */

/* ---- I2C bus to the SSD1306 (I2C0) ---- */
#define PIN_I2C_SDA      6  /* XIAO D4 */
#define PIN_I2C_SCL      7  /* XIAO D5 */
#define OLED_I2C_ADDR  0x3C
#define OLED_I2C_BAUD  400000

/* ---- Recording indicator ---- */
#define PIN_LED_REC      0  /* XIAO D6, through 220 ohm */

/* ---- Timing (milliseconds) ---- */
#define KEY_SCAN_MS         2   /* key matrix sample period        */
#define KEY_DEBOUNCE_MS    15   /* stable time before a new state   */
#define CMD_ACK_TIMEOUT_MS 700  /* wait for H ACK before resend     */
#define CMD_DUP_WINDOW_MS   30  /* identical press events inside one
                                   debounce cycle are one press      */
#define CMD_MAX_ATTEMPTS      3 /* initial send + 2 repeats         */
#define HELLO_RETRY_MS     2000 /* D HELLO while host is silent     */
#define PING_PERIOD_MS     1000 /* D PING period                    */
#define LINK_STALE_MS      3000 /* host silence that means "lost"   */
#define NOTICE_SHOW_MS     1500 /* duration of a transient notice   */
#define UI_REFRESH_MS        50 /* display redraw period            */

/* ---- LED blink used when the OBS state is unknown ---- */
#define LED_UNKNOWN_PERIOD_MS 1000
#define LED_UNKNOWN_ON_MS      120

#define TD_CMD_QUEUE_LEN 4

#endif /* TD_CONFIG_H */
