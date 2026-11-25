/*
 * spark-wl-windows: the Spark shell's window list in the Spark compositor session (no KWin).
 * Binds zwlr_foreign_toplevel_manager_v1 and wl_output (for output names), prints every
 * change as one JSON line on stdout:
 *   [{"id":"3","title":"..","app":"..","cls":"..","pid":0,"minimized":false,
 *     "attention":false,"active":true,"output":"DP-1"}, ...]
 * and acts on lines from stdin: "activate ID", "minimize ID", "unminimize ID", "close ID",
 * "maximize ID", "unmaximize ID". Exits when the compositor or stdin goes away.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <poll.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <wayland-client.h>
#include "ftl-protocol.h"

struct out { struct wl_list link; struct wl_output *wl; uint32_t name_id; char *name; };
struct win {
	struct wl_list link;
	struct zwlr_foreign_toplevel_handle_v1 *h;
	unsigned id;
	char *title, *app;
	bool minimized, active, maximized, fullscreen;
	struct wl_output *output;
};

static struct wl_display *dpy;
static struct wl_seat *seat;
static struct zwlr_foreign_toplevel_manager_v1 *mgr;
static struct wl_list outs, wins;
static unsigned next_id = 1;
static bool dirty;

static void set_str(char **dst, const char *src) { free(*dst); *dst = strdup(src ? src : ""); }

static void json_str(FILE *f, const char *s) {
	fputc('"', f);
	for (const unsigned char *p = (const unsigned char *)(s ? s : ""); *p; p++) {
		if (*p == '"' || *p == '\\') { fputc('\\', f); fputc(*p, f); }
		else if (*p == '\n') fputs("\\n", f);
		else if (*p < 0x20) fprintf(f, "\\u%04x", *p);
		else fputc(*p, f);
	}
	fputc('"', f);
}

static const char *out_name(struct wl_output *o) {
	struct out *x;
	wl_list_for_each(x, &outs, link) if (x->wl == o) return x->name ? x->name : "";
	return "";
}

static void emit(void) {
	dirty = false;
	fputc('[', stdout);
	bool first = true;
	struct win *w;
	wl_list_for_each_reverse(w, &wins, link) {
		if (!first) fputc(',', stdout);
		first = false;
		printf("{\"id\":\"%u\",\"title\":", w->id); json_str(stdout, w->title);
		fputs(",\"app\":", stdout); json_str(stdout, w->app);
		fputs(",\"cls\":", stdout); json_str(stdout, w->app);
		printf(",\"pid\":0,\"minimized\":%s,\"attention\":false,\"active\":%s,\"maximized\":%s,\"output\":",
			w->minimized ? "true" : "false", w->active ? "true" : "false", w->maximized ? "true" : "false");
		json_str(stdout, out_name(w->output));
		fputc('}', stdout);
	}
	fputs("]\n", stdout);
	fflush(stdout);
}

/* toplevel handle */
static void h_title(void *d, struct zwlr_foreign_toplevel_handle_v1 *h, const char *t) { set_str(&((struct win *)d)->title, t); }
static void h_app(void *d, struct zwlr_foreign_toplevel_handle_v1 *h, const char *a) { set_str(&((struct win *)d)->app, a); }
static void h_enter(void *d, struct zwlr_foreign_toplevel_handle_v1 *h, struct wl_output *o) { ((struct win *)d)->output = o; }
static void h_leave(void *d, struct zwlr_foreign_toplevel_handle_v1 *h, struct wl_output *o) {
	struct win *w = d;
	if (w->output == o) w->output = NULL;
}
static void h_state(void *d, struct zwlr_foreign_toplevel_handle_v1 *h, struct wl_array *st) {
	struct win *w = d;
	w->minimized = w->active = w->maximized = w->fullscreen = false;
	uint32_t *s;
	wl_array_for_each(s, st) {
		if (*s == ZWLR_FOREIGN_TOPLEVEL_HANDLE_V1_STATE_MINIMIZED) w->minimized = true;
		else if (*s == ZWLR_FOREIGN_TOPLEVEL_HANDLE_V1_STATE_ACTIVATED) w->active = true;
		else if (*s == ZWLR_FOREIGN_TOPLEVEL_HANDLE_V1_STATE_MAXIMIZED) w->maximized = true;
		else if (*s == ZWLR_FOREIGN_TOPLEVEL_HANDLE_V1_STATE_FULLSCREEN) w->fullscreen = true;
	}
}
static void h_done(void *d, struct zwlr_foreign_toplevel_handle_v1 *h) { dirty = true; }
static void h_closed(void *d, struct zwlr_foreign_toplevel_handle_v1 *h) {
	struct win *w = d;
	wl_list_remove(&w->link);
	zwlr_foreign_toplevel_handle_v1_destroy(w->h);
	free(w->title); free(w->app); free(w);
	dirty = true;
}
static void h_parent(void *d, struct zwlr_foreign_toplevel_handle_v1 *h, struct zwlr_foreign_toplevel_handle_v1 *p) {}
static const struct zwlr_foreign_toplevel_handle_v1_listener h_listener = {
	.title = h_title, .app_id = h_app, .output_enter = h_enter, .output_leave = h_leave,
	.state = h_state, .done = h_done, .closed = h_closed, .parent = h_parent,
};

static void m_toplevel(void *d, struct zwlr_foreign_toplevel_manager_v1 *m, struct zwlr_foreign_toplevel_handle_v1 *h) {
	struct win *w = calloc(1, sizeof *w);
	w->h = h; w->id = next_id++;
	w->title = strdup(""); w->app = strdup("");
	wl_list_insert(&wins, &w->link);
	zwlr_foreign_toplevel_handle_v1_add_listener(h, &h_listener, w);
}
static void m_finished(void *d, struct zwlr_foreign_toplevel_manager_v1 *m) { exit(0); }
static const struct zwlr_foreign_toplevel_manager_v1_listener m_listener = { .toplevel = m_toplevel, .finished = m_finished };

/* outputs: only the name matters */
static void o_geometry(void *d, struct wl_output *o, int32_t x, int32_t y, int32_t pw, int32_t ph, int32_t sp, const char *mk, const char *md, int32_t t) {}
static void o_mode(void *d, struct wl_output *o, uint32_t f, int32_t w, int32_t h, int32_t r) {}
static void o_done(void *d, struct wl_output *o) { dirty = true; }
static void o_scale(void *d, struct wl_output *o, int32_t f) {}
static void o_name(void *d, struct wl_output *o, const char *n) { set_str(&((struct out *)d)->name, n); }
static void o_desc(void *d, struct wl_output *o, const char *n) {}
static const struct wl_output_listener o_listener = {
	.geometry = o_geometry, .mode = o_mode, .done = o_done, .scale = o_scale, .name = o_name, .description = o_desc };

static void reg_global(void *d, struct wl_registry *r, uint32_t name, const char *iface, uint32_t ver) {
	if (!strcmp(iface, zwlr_foreign_toplevel_manager_v1_interface.name)) {
		mgr = wl_registry_bind(r, name, &zwlr_foreign_toplevel_manager_v1_interface, ver < 3 ? ver : 3);
		zwlr_foreign_toplevel_manager_v1_add_listener(mgr, &m_listener, NULL);
	} else if (!strcmp(iface, wl_seat_interface.name) && !seat) {
		seat = wl_registry_bind(r, name, &wl_seat_interface, 1);
	} else if (!strcmp(iface, wl_output_interface.name) && ver >= 4) {
		struct out *o = calloc(1, sizeof *o);
		o->name_id = name;
		o->wl = wl_registry_bind(r, name, &wl_output_interface, 4);
		wl_list_insert(&outs, &o->link);
		wl_output_add_listener(o->wl, &o_listener, o);
	}
}
static void reg_remove(void *d, struct wl_registry *r, uint32_t name) {
	struct out *o, *t;
	wl_list_for_each_safe(o, t, &outs, link) if (o->name_id == name) {
		struct win *w;
		wl_list_for_each(w, &wins, link) if (w->output == o->wl) w->output = NULL;
		wl_output_release(o->wl);
		wl_list_remove(&o->link); free(o->name); free(o);
		dirty = true;
	}
}
static const struct wl_registry_listener reg_listener = { .global = reg_global, .global_remove = reg_remove };

static void command(char *line) {
	char verb[32]; unsigned id;
	if (sscanf(line, "%31s %u", verb, &id) != 2) return;
	struct win *w, *hit = NULL;
	wl_list_for_each(w, &wins, link) if (w->id == id) hit = w;
	if (!hit) return;
	if (!strcmp(verb, "activate")) { if (seat) zwlr_foreign_toplevel_handle_v1_activate(hit->h, seat); }
	else if (!strcmp(verb, "minimize")) zwlr_foreign_toplevel_handle_v1_set_minimized(hit->h);
	else if (!strcmp(verb, "unminimize")) zwlr_foreign_toplevel_handle_v1_unset_minimized(hit->h);
	else if (!strcmp(verb, "close")) zwlr_foreign_toplevel_handle_v1_close(hit->h);
	else if (!strcmp(verb, "maximize")) zwlr_foreign_toplevel_handle_v1_set_maximized(hit->h);
	else if (!strcmp(verb, "unmaximize")) zwlr_foreign_toplevel_handle_v1_unset_maximized(hit->h);
	wl_display_flush(dpy);
}

int main(void) {
	wl_list_init(&outs); wl_list_init(&wins);
	dpy = wl_display_connect(NULL);
	if (!dpy) { fprintf(stderr, "spark-wl-windows: no Wayland display\n"); return 1; }
	struct wl_registry *reg = wl_display_get_registry(dpy);
	wl_registry_add_listener(reg, &reg_listener, NULL);
	wl_display_roundtrip(dpy);
	if (!mgr) { fprintf(stderr, "spark-wl-windows: the compositor has no wlr-foreign-toplevel\n"); return 1; }
	wl_display_roundtrip(dpy);
	wl_display_roundtrip(dpy);
	emit();
	char buf[4096]; size_t used = 0;
	for (;;) {
		while (wl_display_prepare_read(dpy) != 0) wl_display_dispatch_pending(dpy);
		wl_display_flush(dpy);
		struct pollfd p[2] = { { wl_display_get_fd(dpy), POLLIN, 0 }, { 0, POLLIN, 0 } };
		if (poll(p, 2, -1) < 0) { wl_display_cancel_read(dpy); if (errno == EINTR) continue; return 1; }
		if (p[0].revents & POLLIN) { if (wl_display_read_events(dpy) < 0) return 0; }
		else wl_display_cancel_read(dpy);
		if (p[0].revents & (POLLERR | POLLHUP)) return 0;
		if (wl_display_dispatch_pending(dpy) < 0) return 0;
		if (p[1].revents & (POLLIN | POLLHUP)) {
			ssize_t n = read(0, buf + used, sizeof buf - 1 - used);
			if (n <= 0) return 0;
			used += n; buf[used] = 0;
			char *nl;
			while ((nl = memchr(buf, '\n', used))) {
				*nl = 0; command(buf);
				size_t rest = used - (nl + 1 - buf);
				memmove(buf, nl + 1, rest); used = rest; buf[used] = 0;
			}
			if (used == sizeof buf - 1) used = 0;
		}
		if (dirty) emit();
	}
}
