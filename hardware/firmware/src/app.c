#include "app.h"

#include <stdio.h>
#include <string.h>

static void emit(td_app_t *app, const char *line)
{
    if (app->emit && line && *line)
        app->emit(app->emit_ctx, line);
}

static void set_notice(td_app_t *app, uint32_t now_ms, const char *text)
{
    snprintf(app->notice, sizeof(app->notice), "%s", text);
    app->notice_until = now_ms + NOTICE_SHOW_MS;
    app->dirty = 1;
}

static void mark_dirty(td_app_t *app) { app->dirty = 1; }

void td_app_init(td_app_t *app, uint32_t now_ms, uint32_t session_id,
                 td_emit_fn emit_fn, void *ctx)
{
    memset(app, 0, sizeof(*app));
    app->link = TD_LINK_BOOT;
    app->session_id = session_id;
    app->seq_next = 1;
    app->obs.obs_valid = 0;
    app->obs.scene[0] = '\0';
    app->emit = emit_fn;
    app->emit_ctx = ctx;
    app->dirty = 1;
    /* make the first tick send D HELLO immediately */
    app->last_hello_ms = now_ms - HELLO_RETRY_MS;
    app->last_ping_ms = now_ms;
    app->last_host_ms = now_ms - LINK_STALE_MS;
    app->last_submit_ms = now_ms - 1000;
}

uint32_t td_app_elapsed_s(const td_app_t *app, uint32_t now_ms)
{
    uint32_t secs = app->obs.elapsed_s;
    if (app->obs.rec && app->obs.obs_valid && app->link == TD_LINK_UP) {
        uint32_t add = (now_ms - app->obs.elapsed_base_ms) / 1000u;
        secs += add;
    }
    return secs;
}

int td_app_rec_confirmed(const td_app_t *app)
{
    return app->link == TD_LINK_UP && app->obs.obs_valid && app->obs.rec;
}

/* ---------------------------------------------------------------- queue */

static td_cmd_t *active_cmd(td_app_t *app)
{
    if (app->q_count == 0)
        return NULL;
    return &app->queue[app->q_head];
}

static void queue_pop(td_app_t *app)
{
    if (app->q_count == 0)
        return;
    app->queue[app->q_head].used = 0;
    app->q_head = (uint8_t)((app->q_head + 1) % TD_CMD_QUEUE_LEN);
    app->q_count--;
}

static void queue_clear(td_app_t *app)
{
    for (int i = 0; i < TD_CMD_QUEUE_LEN; i++)
        app->queue[i].used = 0;
    app->q_head = 0;
    app->q_count = 0;
}

static void send_active(td_app_t *app, uint32_t now_ms)
{
    td_cmd_t *c = active_cmd(app);
    if (!c)
        return;
    char line[TD_LINE_MAX];
    td_fmt_cmd(line, sizeof(line), c->seq, c->id);
    emit(app, line);
    if (c->attempts > 0)
        app->cmds_retried++;
    c->attempts++;
    c->sent_ms = now_ms;
    app->cmds_sent++;
}

static void submit(td_app_t *app, uint32_t now_ms, const char *id)
{
    /* Guard against a duplicated press event reaching the queue twice.
     * The window is deliberately shorter than a human double tap: two real
     * presses 60 ms apart (NEXT, NEXT) must both be sent. */
    if (strcmp(app->last_submit_id, id) == 0 &&
        (uint32_t)(now_ms - app->last_submit_ms) < CMD_DUP_WINDOW_MS)
        return;

    if (app->link != TD_LINK_UP) {
        app->cmds_dropped++;
        set_notice(app, now_ms, "NO LINK");
        return;
    }

    if (app->q_count >= TD_CMD_QUEUE_LEN) {
        app->cmds_dropped++;
        set_notice(app, now_ms, "BUSY");
        return;
    }

    uint8_t idx = (uint8_t)((app->q_head + app->q_count) % TD_CMD_QUEUE_LEN);
    td_cmd_t *c = &app->queue[idx];
    c->seq = app->seq_next++;
    snprintf(c->id, sizeof(c->id), "%s", id);
    c->attempts = 0;
    c->sent_ms = now_ms;
    c->used = 1;
    app->q_count++;
    app->last_submit_ms = now_ms;
    snprintf(app->last_submit_id, sizeof(app->last_submit_id), "%s", id);
    app->cmds_submitted++;

    if (app->q_count == 1)
        send_active(app, now_ms);
}

/* ---------------------------------------------------------------- input */

void td_app_on_press(td_app_t *app, uint32_t now_ms, td_key_id_t key)
{
    switch (key) {
    case TD_KEY_REC:  submit(app, now_ms, "REC_TOGGLE");  break;
    case TD_KEY_PREV: submit(app, now_ms, "SCENE_PREV");  break;
    case TD_KEY_NEXT: submit(app, now_ms, "SCENE_NEXT");  break;
    case TD_KEY_MUTE: submit(app, now_ms, "MUTE_TOGGLE"); break;
    default: break;
    }
    mark_dirty(app);
}

/* ------------------------------------------------------- host messages */

static void handle_hello(td_app_t *app, uint32_t now_ms)
{
    int was_up = (app->link == TD_LINK_UP);
    app->last_host_ms = now_ms;
    if (!was_up) {
        app->link = TD_LINK_UP;
        app->obs.obs_valid = 0;   /* resync from the next STATE */
        queue_clear(app);         /* commands from the old session are void */
        set_notice(app, now_ms, "LINKED");
        char line[TD_LINE_MAX];
        td_fmt_hello(line, sizeof(line), app->session_id);
        emit(app, line);
        app->last_hello_ms = now_ms;
    }
    mark_dirty(app);
}

static void handle_state(td_app_t *app, uint32_t now_ms, const td_msg_t *msg)
{
    app->last_host_ms = now_ms;
    if (app->link != TD_LINK_UP)
        app->link = TD_LINK_UP;

    app->obs.rec = (uint8_t)(td_msg_get_int(msg, "rec", 0) ? 1 : 0);
    app->obs.obs_valid = 1;
    app->obs.elapsed_s = (uint32_t)td_msg_get_long(msg, "t", (long)app->obs.elapsed_s);
    app->obs.elapsed_base_ms = now_ms;
    app->obs.scene_idx = td_msg_get_int(msg, "idx", app->obs.scene_idx);
    app->obs.scene_count = td_msg_get_int(msg, "cnt", app->obs.scene_count);
    app->obs.mute = (uint8_t)(td_msg_get_int(msg, "mute", 0) ? 1 : 0);

    const char *scene = td_msg_get(msg, "scene");
    if (scene) {
        snprintf(app->obs.scene, sizeof(app->obs.scene), "%s", scene);
    }
    mark_dirty(app);
}

static void handle_ack(td_app_t *app, uint32_t now_ms, const td_msg_t *msg)
{
    app->last_host_ms = now_ms;
    uint32_t seq = (uint32_t)td_msg_get_long(msg, "seq", -1L);
    int ok = td_msg_get_int(msg, "ok", 1);

    td_cmd_t *c = active_cmd(app);
    if (c && c->used && c->seq == seq) {
        queue_pop(app);
        app->cmds_acked++;
        if (!ok) {
            app->cmds_failed++;
            set_notice(app, now_ms, "CMD REJECTED");
        }
        if (app->q_count > 0)
            send_active(app, now_ms);
        mark_dirty(app);
        return;
    }

    /* Duplicate ACK of a command that already completed: harmless, count it. */
    for (int i = 0; i < TD_CMD_QUEUE_LEN; i++) {
        if (app->queue[i].used && app->queue[i].seq == seq)
            return; /* still queued but not active - ignore */
    }
    app->acks_duplicate++;
}

static void handle_err(td_app_t *app, uint32_t now_ms, const td_msg_t *msg)
{
    app->last_host_ms = now_ms;
    const char *code = td_msg_get(msg, "code");
    if (!code)
        code = "HOST ERR";
    char text[24];
    snprintf(text, sizeof(text), "ERR %s", code);
    set_notice(app, now_ms, text);
}

void td_app_on_msg(td_app_t *app, uint32_t now_ms, const td_msg_t *msg)
{
    if (!msg || msg->dir != 'H') {
        app->line_errors++;
        return;
    }

    if (strcmp(msg->kind, "HELLO") == 0) {
        handle_hello(app, now_ms);
    } else if (strcmp(msg->kind, "STATE") == 0) {
        handle_state(app, now_ms, msg);
    } else if (strcmp(msg->kind, "ACK") == 0) {
        handle_ack(app, now_ms, msg);
    } else if (strcmp(msg->kind, "PONG") == 0) {
        app->last_host_ms = now_ms;
    } else if (strcmp(msg->kind, "ERR") == 0) {
        handle_err(app, now_ms, msg);
    } else {
        /* unknown kind: still proves the host is alive */
        app->last_host_ms = now_ms;
    }
}

/* ----------------------------------------------------------------- tick */

static void manage_link(td_app_t *app, uint32_t now_ms)
{
    if (app->link == TD_LINK_UP &&
        (uint32_t)(now_ms - app->last_host_ms) > LINK_STALE_MS) {
        app->link = TD_LINK_LOST;
        app->obs.obs_valid = 0;   /* recording state is now unknown */
        queue_clear(app);
        set_notice(app, now_ms, "LINK LOST");
        emit(app, "D NOTE code=LINK_LOST");
        app->last_hello_ms = now_ms - HELLO_RETRY_MS;
    }

    if (app->link != TD_LINK_UP) {
        if ((uint32_t)(now_ms - app->last_hello_ms) >= HELLO_RETRY_MS) {
            char line[TD_LINE_MAX];
            td_fmt_hello(line, sizeof(line), app->session_id);
            emit(app, line);
            app->last_hello_ms = now_ms;
            if (app->link == TD_LINK_BOOT)
                app->link = TD_LINK_WAIT;
        }
        return;
    }

    if ((uint32_t)(now_ms - app->last_ping_ms) >= PING_PERIOD_MS) {
        char line[TD_LINE_MAX];
        td_fmt_ping(line, sizeof(line), now_ms);
        emit(app, line);
        app->last_ping_ms = now_ms;
    }
}

static void manage_queue(td_app_t *app, uint32_t now_ms)
{
    td_cmd_t *c = active_cmd(app);
    if (!c)
        return;

    if ((uint32_t)(now_ms - c->sent_ms) < CMD_ACK_TIMEOUT_MS)
        return;

    if (c->attempts >= CMD_MAX_ATTEMPTS) {
        queue_pop(app);
        app->cmds_failed++;
        set_notice(app, now_ms, "NO ACK");
        emit(app, "D NOTE code=NO_ACK");
        if (app->q_count > 0)
            send_active(app, now_ms);
        return;
    }
    send_active(app, now_ms);
}

static uint8_t led_phase(td_app_t *app, uint32_t now_ms)
{
    if (td_app_rec_confirmed(app))
        return 1;                                   /* solid: recording       */
    if (app->link == TD_LINK_UP && app->obs.obs_valid && !app->obs.rec)
        return 0;                                   /* solid off: not recording */
    /* unknown: host silent, or reconnecting and no STATE yet */
    uint32_t phase = now_ms % LED_UNKNOWN_PERIOD_MS;
    return (uint8_t)(phase < LED_UNKNOWN_ON_MS);
}

void td_app_tick(td_app_t *app, uint32_t now_ms)
{
    manage_link(app, now_ms);
    manage_queue(app, now_ms);

    uint8_t led = led_phase(app, now_ms);
    if (led != app->led_on) {
        app->led_on = led;
        mark_dirty(app);
    }

    if (app->notice[0] && (int32_t)(now_ms - app->notice_until) >= 0) {
        app->notice[0] = '\0';
        mark_dirty(app);
    }

    /* elapsed time is redrawn once a second */
    if (app->obs.rec && app->obs.obs_valid && app->link == TD_LINK_UP) {
        uint32_t secs = td_app_elapsed_s(app, now_ms);
        if (secs != app->last_drawn_sec) {
            app->last_drawn_sec = secs;
            mark_dirty(app);
        }
    }
}
