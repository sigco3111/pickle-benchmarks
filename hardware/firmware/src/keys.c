#include "keys.h"

#include "config.h"

void td_keys_init(td_keys_t *ks, uint32_t now_ms, const uint8_t raw[TD_KEY_COUNT])
{
    for (int i = 0; i < TD_KEY_COUNT; i++) {
        ks->key[i].stable = raw[i] ? 1 : 0;
        ks->key[i].raw_last = ks->key[i].stable;
        ks->key[i].change_ms = now_ms;
        ks->key[i].initialized = 1;
        ks->press_count[i] = 0;
    }
    ks->bounce_ignored = 0;
}

uint8_t td_keys_update(td_keys_t *ks, uint32_t now_ms, const uint8_t raw[TD_KEY_COUNT])
{
    uint8_t presses = 0;

    for (int i = 0; i < TD_KEY_COUNT; i++) {
        td_key_t *k = &ks->key[i];
        uint8_t level = raw[i] ? 1 : 0;

        if (level != k->raw_last) {
            k->raw_last = level;
            k->change_ms = now_ms;
            ks->bounce_ignored++;
            continue;
        }

        if (level != k->stable && (now_ms - k->change_ms) >= KEY_DEBOUNCE_MS) {
            k->stable = level;
            if (level == 0) { /* 0 = pressed */
                presses |= (uint8_t)(1u << i);
                ks->press_count[i]++;
            }
        }
    }
    return presses;
}

int td_keys_down(const td_keys_t *ks, td_key_id_t id)
{
    unsigned index = (unsigned)id;
    if (index >= TD_KEY_COUNT)
        return 0;
    return ks->key[index].stable == 0;
}
