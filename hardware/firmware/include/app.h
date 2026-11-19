/*
 * app.h — controller state machine (pure logic, host testable).
 *
 * The application layer owns everything that is not a pin: link supervision,
 * the command queue with sequence numbers and retries, the copy of the OBS
 * state that the display and the LED show, and the transient notices.
 *
 * Hardware code (main.c) only feeds it: key presses, received protocol lines
 * and a millisecond tick. Everything it wants to send leaves through emit().
 */
#ifndef TD_APP_H
#define TD_APP_H

#include <stdint.h>

#include "config.h"
#include "keys.h"
#include "protocol.h"

#define TD_SCENE_MAX 20

typedef enum {
    TD_LINK_BOOT = 0,   /* power on, no host handshake yet        */
    TD_LINK_WAIT,       /* sending D HELLO, waiting for H HELLO   */
    TD_LINK_UP,         /* host answered and is being heard       */
    TD_LINK_LOST        /* host went silent: state is unknown     */
} td_link_t;

typedef struct {
    uint8_t  rec;          /* last confirmed recording state   */
    uint8_t  obs_valid;    /* a STATE has been received        */
    uint32_t elapsed_s;    /* elapsed seconds from the host    */
    uint32_t elapsed_base_ms; /* local time of that report     */
    char     scene[TD_SCENE_MAX];
    int      scene_idx;
    int      scene_count;
    uint8_t  mute;
} td_obs_t;

typedef struct {
    uint32_t seq;
    char     id[16];
    uint8_t  attempts;
    uint32_t sent_ms;
    uint8_t  used;
} td_cmd_t;

typedef void (*td_emit_fn)(void *ctx, const char *line);

typedef struct {
    td_link_t  link;
    td_obs_t   obs;
    uint32_t   session_id;
    uint32_t   seq_next;

    uint32_t   last_host_ms;
    uint32_t   last_hello_ms;
    uint32_t   last_ping_ms;

    td_cmd_t   queue[TD_CMD_QUEUE_LEN];
    uint8_t    q_head;
    uint8_t    q_count;

    uint32_t   last_submit_ms;
    char       last_submit_id[16];

    char       notice[24];
    uint32_t   notice_until;
    uint8_t    dirty;        /* display needs a redraw      */
    uint8_t    led_on;
    uint32_t   last_drawn_sec; /* elapsed value already pushed to the UI */

    /* diagnostics, exported for tests and for the USB status line */
    uint32_t   cmds_submitted;
    uint32_t   cmds_sent;
    uint32_t   cmds_acked;
    uint32_t   cmds_retried;
    uint32_t   cmds_dropped;   /* pressed while the link was down      */
    uint32_t   cmds_failed;    /* no ACK after CMD_MAX_ATTEMPTS        */
    uint32_t   acks_duplicate;
    uint32_t   line_errors;

    td_emit_fn emit;
    void      *emit_ctx;
} td_app_t;

void td_app_init(td_app_t *app, uint32_t now_ms, uint32_t session_id,
                 td_emit_fn emit, void *ctx);

/* Feed one parsed host message. */
void td_app_on_msg(td_app_t *app, uint32_t now_ms, const td_msg_t *msg);

/* Feed one debounced key press. */
void td_app_on_press(td_app_t *app, uint32_t now_ms, td_key_id_t key);

/* Call at 1..5 ms resolution: timeouts, retries, LED phase, notices. */
void td_app_tick(td_app_t *app, uint32_t now_ms);

/* Seconds the display should show (host value plus local extrapolation). */
uint32_t td_app_elapsed_s(const td_app_t *app, uint32_t now_ms);

/* True when the recording state is known and recording. */
int td_app_rec_confirmed(const td_app_t *app);

#endif /* TD_APP_H */
