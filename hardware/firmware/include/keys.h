/*
 * keys.h — 4 key debounce (pure logic, host testable).
 *
 * Sample the raw pin level (1 = released with pull-up, 0 = pressed) every
 * KEY_SCAN_MS. A new state is accepted only after it has been stable for
 * KEY_DEBOUNCE_MS. Press events are reported once per physical press; there
 * is no auto-repeat. The same debounce also swallows contact bounce on
 * release and the short glitch that a USB hot-plug can inject on the pins.
 */
#ifndef TD_KEYS_H
#define TD_KEYS_H

#include <stdint.h>

#define TD_KEY_COUNT 4

typedef enum {
    TD_KEY_REC = 0,
    TD_KEY_PREV = 1,
    TD_KEY_NEXT = 2,
    TD_KEY_MUTE = 3
} td_key_id_t;

typedef struct {
    uint8_t  stable;      /* 0 = pressed, 1 = released */
    uint8_t  raw_last;
    uint32_t change_ms;   /* time the raw level last differed from stable */
    uint8_t  initialized;
} td_key_t;

typedef struct {
    td_key_t key[TD_KEY_COUNT];
    uint32_t press_count[TD_KEY_COUNT];
    uint32_t bounce_ignored;   /* raw transitions that did not survive debounce */
} td_keys_t;

void td_keys_init(td_keys_t *ks, uint32_t now_ms, const uint8_t raw[TD_KEY_COUNT]);

/* Returns a bitmask of keys that went down since the previous call. */
uint8_t td_keys_update(td_keys_t *ks, uint32_t now_ms, const uint8_t raw[TD_KEY_COUNT]);

/* 1 while the key is debounced-pressed. */
int td_keys_down(const td_keys_t *ks, td_key_id_t id);

#endif /* TD_KEYS_H */
