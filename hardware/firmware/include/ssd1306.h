/*
 * ssd1306.h — minimal SSD1306 128x64 I2C driver (hardware layer).
 *
 * Only what this product needs: init, page addressing and a paged flush.
 * No dynamic allocation, no external library.
 */
#ifndef TD_SSD1306_H
#define TD_SSD1306_H

#include <stdbool.h>
#include <stdint.h>

#include "ui.h"

void ssd1306_init(void);

/* true when the controller answered its address at init time. */
bool ssd1306_present(void);

/* Push one 8-pixel page (0..7) of the framebuffer. Returns 0 on success. */
int ssd1306_flush_page(const uint8_t fb[TD_FB_SIZE], int page);

/* Push the whole framebuffer (8 pages). Returns the number of failed pages. */
int ssd1306_flush(const uint8_t fb[TD_FB_SIZE]);

/* Contrast 0..255 (dimming for a dark room, see HARDWARE_README.md). */
void ssd1306_set_contrast(uint8_t value);

#endif /* TD_SSD1306_H */
