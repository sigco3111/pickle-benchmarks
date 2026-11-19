/*
 * ui.h — 128x64 monochrome framebuffer rendering (pure logic).
 *
 * ui_render() builds the whole screen from the application state. It does not
 * touch the bus, so the same code is used by the firmware, by the host tests
 * and (via a small PPM dump) to check layout without hardware.
 */
#ifndef TD_UI_H
#define TD_UI_H

#include <stdint.h>

#include "app.h"

#define TD_FB_WIDTH  128
#define TD_FB_HEIGHT 64
#define TD_FB_SIZE   (TD_FB_WIDTH * TD_FB_HEIGHT / 8)

void ui_clear(uint8_t fb[TD_FB_SIZE]);
void ui_fill(uint8_t fb[TD_FB_SIZE], int x, int y, int w, int h, int on);
void ui_frame(uint8_t fb[TD_FB_SIZE], int x, int y, int w, int h, int on);
void ui_hline(uint8_t fb[TD_FB_SIZE], int x, int y, int w);
void ui_text(uint8_t fb[TD_FB_SIZE], int x, int y, const char *text, int scale, int inverse);
int  ui_text_width(const char *text, int scale);

/* Compose the screen for the current state. */
void ui_render(const td_app_t *app, uint32_t now_ms, uint8_t fb[TD_FB_SIZE]);

/* "HH:MM:SS" (hours wrap at 99) into buf (at least 9 bytes). */
void ui_format_time(char *buf, unsigned cap, uint32_t seconds);

#endif /* TD_UI_H */
