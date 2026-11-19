#include "ssd1306.h"

#include <string.h>

#include "config.h"
#include "hardware/gpio.h"
#include "hardware/i2c.h"
#include "pico/time.h"

#define SSD1306_CTRL_CMD  0x00
#define SSD1306_CTRL_DATA 0x40

static bool s_present = false;

static void cmd(uint8_t c)
{
    uint8_t buf[2] = {SSD1306_CTRL_CMD, c};
    i2c_write_blocking(i2c0, OLED_I2C_ADDR, buf, 2, false);
}

static void cmd2(uint8_t a, uint8_t b)
{
    uint8_t buf[3] = {SSD1306_CTRL_CMD, a, b};
    i2c_write_blocking(i2c0, OLED_I2C_ADDR, buf, 3, false);
}

void ssd1306_init(void)
{
    /* The module is a 3.3 V part with its own charge pump; the bus pull-ups
     * live on the module PCB, so no internal pull-up is enabled here. */
    i2c_init(i2c0, OLED_I2C_BAUD);
    gpio_set_function(PIN_I2C_SDA, GPIO_FUNC_I2C);
    gpio_set_function(PIN_I2C_SCL, GPIO_FUNC_I2C);
    gpio_pull_up(PIN_I2C_SDA);
    gpio_pull_up(PIN_I2C_SCL);

    sleep_ms(20); /* panel power-up */

    /* Probe: a write to the control register fails when nothing answers. */
    uint8_t probe[2] = {SSD1306_CTRL_CMD, 0xAE};
    s_present = i2c_write_blocking(i2c0, OLED_I2C_ADDR, probe, 2, false) == 2;
    if (!s_present)
        return;

    cmd(0xAE);            /* display off while configuring   */
    cmd2(0xD5, 0x80);     /* clock divide / oscillator       */
    cmd2(0xA8, 0x3F);     /* multiplex 64                    */
    cmd2(0xD3, 0x00);     /* display offset 0                */
    cmd(0x40);            /* start line 0                    */
    cmd2(0x8D, 0x14);     /* charge pump on                  */
    cmd2(0x20, 0x02);     /* page addressing mode            */
    cmd(0xA1);            /* segment remap                   */
    cmd(0xC8);            /* COM scan direction remapped     */
    cmd2(0xDA, 0x12);     /* COM pins: alternative config    */
    cmd2(0x81, 0xCF);     /* contrast                        */
    cmd2(0xD9, 0xF1);     /* pre-charge period               */
    cmd2(0xDB, 0x40);     /* VCOMH deselect level            */
    cmd(0xA4);            /* resume from RAM                 */
    cmd(0xA6);            /* normal (non inverted) display   */
    cmd(0x2E);            /* deactivate scroll               */
    cmd(0xAF);            /* display on                      */
}

bool ssd1306_present(void) { return s_present; }

void ssd1306_set_contrast(uint8_t value)
{
    cmd2(0x81, value);
}

int ssd1306_flush_page(const uint8_t fb[TD_FB_SIZE], int page)
{
    if (!s_present || page < 0 || page > 7)
        return -1;

    cmd((uint8_t)(0xB0 | page)); /* page start address */
    cmd(0x00);                   /* lower column       */
    cmd(0x10);                   /* upper column       */

    /* 128 bytes of GDDRAM plus the control byte, sent in one transaction */
    uint8_t buf[1 + TD_FB_WIDTH];
    buf[0] = SSD1306_CTRL_DATA;
    memcpy(&buf[1], fb + page * TD_FB_WIDTH, TD_FB_WIDTH);
    int rc = i2c_write_blocking(i2c0, OLED_I2C_ADDR, buf, sizeof(buf), false);
    return rc == (int)sizeof(buf) ? 0 : -1;
}

int ssd1306_flush(const uint8_t fb[TD_FB_SIZE])
{
    int failures = 0;
    for (int page = 0; page < 8; page++)
        if (ssd1306_flush_page(fb, page) != 0)
            failures++;
    return failures;
}
