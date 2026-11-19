#include "ui.h"

#include <stdio.h>
#include <string.h>

#include "font5x7.h"

static inline void px(uint8_t fb[TD_FB_SIZE], int x, int y, int on)
{
    if (x < 0 || y < 0 || x >= TD_FB_WIDTH || y >= TD_FB_HEIGHT)
        return;
    int index = y * (TD_FB_WIDTH / 8) + (x >> 3);
    uint8_t mask = (uint8_t)(1u << (x & 7));
    if (on)
        fb[index] |= mask;
    else
        fb[index] &= (uint8_t)~mask;
}

void ui_clear(uint8_t fb[TD_FB_SIZE]) { memset(fb, 0, TD_FB_SIZE); }

void ui_fill(uint8_t fb[TD_FB_SIZE], int x, int y, int w, int h, int on)
{
    for (int yy = y; yy < y + h; yy++)
        for (int xx = x; xx < x + w; xx++)
            px(fb, xx, yy, on);
}

void ui_frame(uint8_t fb[TD_FB_SIZE], int x, int y, int w, int h, int on)
{
    for (int xx = x; xx < x + w; xx++) {
        px(fb, xx, y, on);
        px(fb, xx, y + h - 1, on);
    }
    for (int yy = y; yy < y + h; yy++) {
        px(fb, x, yy, on);
        px(fb, x + w - 1, yy, on);
    }
}

void ui_hline(uint8_t fb[TD_FB_SIZE], int x, int y, int w)
{
    for (int i = 0; i < w; i++)
        px(fb, x + i, y, 1);
}

int ui_text_width(const char *text, int scale)
{
    if (!text)
        return 0;
    int n = (int)strlen(text);
    if (n == 0)
        return 0;
    return n * 6 * scale - scale; /* no trailing column gap after the last glyph */
}

void ui_text(uint8_t fb[TD_FB_SIZE], int x, int y, const char *text, int scale, int inverse)
{
    if (!text || scale < 1)
        return;

    int width = ui_text_width(text, scale);
    if (inverse) {
        /* solid chip behind the text, glyph pixels punched out */
        ui_fill(fb, x - 1, y - 1, width + 2, TD_FONT_H * scale + 2, 1);
    }

    int cx = x;
    for (const char *p = text; *p; p++) {
        unsigned char ch = (unsigned char)*p;
        if (ch >= 'a' && ch <= 'z')
            ch = (unsigned char)(ch - 'a' + 'A');
        int idx = (int)ch - TD_FONT_FIRST;
        if (idx < 0 || idx > (TD_FONT_LAST - TD_FONT_FIRST))
            idx = '?' - TD_FONT_FIRST;

        for (int col = 0; col < TD_FONT_W; col++) {
            uint8_t bits = TD_FONT5X7[idx][col];
            for (int row = 0; row < TD_FONT_H; row++) {
                int on = (bits >> row) & 1;
                if (!on)
                    continue;
                int value = inverse ? 0 : 1;
                for (int sy = 0; sy < scale; sy++)
                    for (int sx = 0; sx < scale; sx++)
                        px(fb, cx + col * scale + sx, y + row * scale + sy, value);
            }
        }
        cx += 6 * scale;
    }
}

void ui_format_time(char *buf, unsigned cap, uint32_t seconds)
{
    uint32_t h = seconds / 3600u;
    uint32_t m = (seconds % 3600u) / 60u;
    uint32_t s = seconds % 60u;
    if (h > 99)
        h = 99;
    snprintf(buf, cap, "%02lu:%02lu:%02lu", (unsigned long)h, (unsigned long)m,
             (unsigned long)s);
}

static const char *link_label(const td_app_t *app)
{
    switch (app->link) {
    case TD_LINK_UP:
        if (!app->obs.obs_valid)
            return "SYNCING";
        return "USB LINK OK";
    case TD_LINK_LOST:
        return "LINK LOST";
    case TD_LINK_WAIT:
        return "WAIT FOR OBS";
    case TD_LINK_BOOT:
    default:
        return "BOOT";
    }
}

void ui_render(const td_app_t *app, uint32_t now_ms, uint8_t fb[TD_FB_SIZE])
{
    char buf[32];
    ui_clear(fb);

    /* Row 1: big elapsed time, top left. */
    ui_format_time(buf, sizeof(buf), td_app_elapsed_s(app, now_ms));
    ui_text(fb, 2, 2, buf, 2, 0);

    /* Row 1 right: recording chip. Solid block = confirmed recording. */
    int rec = td_app_rec_confirmed(app);
    int known = (app->link == TD_LINK_UP) && app->obs.obs_valid;
    if (rec)
        ui_text(fb, 100, 4, "REC", 1, 1);
    else if (!known)
        ui_text(fb, 94, 4, "REC ?", 1, 0);
    else
        ui_text(fb, 102, 4, "IDLE", 1, 0);

    ui_hline(fb, 0, 16, TD_FB_WIDTH);

    /* Row 2: scene counter and mute chip. */
    if (app->obs.scene_count > 0)
        snprintf(buf, sizeof(buf), "SCENE %02d/%02d", app->obs.scene_idx + 1,
                 app->obs.scene_count);
    else
        snprintf(buf, sizeof(buf), "SCENE --");
    ui_text(fb, 0, 19, buf, 1, 0);
    if (app->obs.mute)
        ui_text(fb, 104, 19, "MUTE", 1, 1);

    /* Row 3: scene name, clipped to the panel. */
    char name[TD_SCENE_MAX];
    snprintf(name, sizeof(name), "%s", app->obs.scene[0] ? app->obs.scene : "--");
    while (ui_text_width(name, 1) > TD_FB_WIDTH - 2 && strlen(name) > 1)
        name[strlen(name) - 1] = '\0';
    ui_text(fb, 0, 28, name, 1, 0);

    ui_hline(fb, 0, 37, TD_FB_WIDTH);

    /* Row 4: link quality - the honest answer to "am I connected?". */
    ui_text(fb, 0, 40, link_label(app), 1, 0);
    if (app->link == TD_LINK_UP) {
        snprintf(buf, sizeof(buf), "Q%u", (unsigned)app->q_count);
        ui_text(fb, 112, 40, buf, 1, 0);
    }

    /* Row 5: transient notice (inverted) or the firmware banner. */
    if (app->notice[0])
        ui_text(fb, 0, 51, app->notice, 1, 1);
    else
        ui_text(fb, 0, 51, "TAKEDECK  USB OBS CTRL", 1, 0);
}
