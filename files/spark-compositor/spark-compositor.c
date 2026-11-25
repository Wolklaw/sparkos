/*
 * spark-compositor: SparkOS's own Wayland compositor (experimental), on wlroots 0.19.
 * Structure follows tinywl; the layer, lock and output handling follows what sway and dwl do.
 *
 * What it is: floating windows (xdg-shell and XWayland), any number of outputs with their own
 * mode, scale, transform and position, the protocols a shell and screen capture need, and a
 * small config file. What it is not: a replacement for KWin yet (no HDR, no tested VRR, no
 * mixed-refresh handling beyond what wlroots does per output). See briefs/spark-compositor.md.
 *
 * Config: ~/.config/spark/compositor/compositor.conf (and outputs.conf next to it), see
 * README.md. Test mode: SPARK_HEADLESS_OUTPUTS=N makes N virtual outputs, no GPU.
 */
#define _GNU_SOURCE
#include <assert.h>
#include <ctype.h>
#include <errno.h>
#include <getopt.h>
#include <math.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#include <linux/input-event-codes.h>
#include <wayland-server-core.h>
#include <wlr/backend.h>
#include <wlr/backend/headless.h>
#include <wlr/backend/multi.h>
#include <wlr/backend/session.h>
#include <wlr/render/allocator.h>
#include <wlr/render/wlr_renderer.h>
#include <wlr/types/wlr_alpha_modifier_v1.h>
#include <wlr/types/wlr_compositor.h>
#include <wlr/types/wlr_content_type_v1.h>
#include <wlr/types/wlr_cursor.h>
#include <wlr/types/wlr_cursor_shape_v1.h>
#include <wlr/types/wlr_data_control_v1.h>
#include <wlr/types/wlr_data_device.h>
#include <wlr/types/wlr_export_dmabuf_v1.h>
#include <wlr/types/wlr_ext_data_control_v1.h>
#include <wlr/types/wlr_ext_foreign_toplevel_list_v1.h>
#include <wlr/types/wlr_ext_image_capture_source_v1.h>
#include <wlr/types/wlr_ext_image_copy_capture_v1.h>
#include <wlr/types/wlr_foreign_toplevel_management_v1.h>
#include <wlr/types/wlr_fractional_scale_v1.h>
#include <wlr/types/wlr_gamma_control_v1.h>
#include <wlr/types/wlr_idle_inhibit_v1.h>
#include <wlr/types/wlr_idle_notify_v1.h>
#include <wlr/types/wlr_keyboard.h>
#include <wlr/types/wlr_layer_shell_v1.h>
#include <wlr/types/wlr_linux_dmabuf_v1.h>
#include <wlr/types/wlr_output.h>
#include <wlr/types/wlr_output_layout.h>
#include <wlr/types/wlr_output_management_v1.h>
#include <wlr/types/wlr_output_power_management_v1.h>
#include <wlr/types/wlr_pointer.h>
#include <wlr/types/wlr_pointer_constraints_v1.h>
#include <wlr/types/wlr_presentation_time.h>
#include <wlr/types/wlr_primary_selection.h>
#include <wlr/types/wlr_primary_selection_v1.h>
#include <wlr/types/wlr_relative_pointer_v1.h>
#include <wlr/types/wlr_scene.h>
#include <wlr/types/wlr_screencopy_v1.h>
#include <wlr/types/wlr_seat.h>
#include <wlr/types/wlr_session_lock_v1.h>
#include <wlr/types/wlr_single_pixel_buffer_v1.h>
#include <wlr/types/wlr_subcompositor.h>
#include <wlr/types/wlr_tearing_control_v1.h>
#include <wlr/types/wlr_viewporter.h>
#include <wlr/types/wlr_virtual_keyboard_v1.h>
#include <wlr/types/wlr_virtual_pointer_v1.h>
#include <wlr/types/wlr_xcursor_manager.h>
#include <wlr/types/wlr_xdg_activation_v1.h>
#include <wlr/types/wlr_xdg_decoration_v1.h>
#include <wlr/types/wlr_xdg_output_v1.h>
#include <wlr/types/wlr_xdg_shell.h>
#include <wlr/util/log.h>
#include <wlr/xwayland.h>
#include <xkbcommon/xkbcommon.h>

#define LISTEN(sig, l, fn) do { (l)->notify = fn; wl_signal_add(&(sig), (l)); } while (0)
#define UNLISTEN(l) wl_list_remove(&(l)->link)

enum scene_layer { L_BG, L_BOTTOM, L_WINDOWS, L_TOP, L_FULLSCREEN, L_OVERLAY, L_LOCK, L_COUNT };
enum cursor_mode { CURSOR_PASSTHROUGH, CURSOR_MOVE, CURSOR_RESIZE };
enum action { A_EXEC, A_CLOSE, A_QUIT, A_FOCUS_NEXT, A_FULLSCREEN, A_MAXIMIZE, A_OUTPUT_NEXT, A_RELOAD };

struct bind { struct wl_list link; uint32_t mods; xkb_keysym_t sym; enum action action; char *arg; };
struct out_cfg {
	struct wl_list link;
	char *name;            /* output name or "*" */
	int w, h; double hz;   /* mode; 0 = preferred */
	double scale;
	enum wl_output_transform transform;
	bool has_pos; int x, y;
	bool enabled, vrr;
};

struct server {
	struct wl_display *display;
	struct wl_event_loop *loop;
	struct wlr_backend *backend;
	struct wlr_session *session;
	struct wlr_renderer *renderer;
	struct wlr_allocator *allocator;
	struct wlr_compositor *compositor;
	struct wlr_scene *scene;
	struct wlr_scene_output_layout *scene_layout;
	struct wlr_scene_tree *layers[L_COUNT];
	struct wlr_output_layout *output_layout;
	struct wl_list outputs;
	struct wlr_xdg_shell *xdg_shell;
	struct wlr_layer_shell_v1 *layer_shell;
	struct wlr_xwayland *xwayland;
	struct wl_list views;       /* front to back */
	struct wl_list layer_surfaces;
	struct wl_list out_cfgs;
	struct wl_list binds;

	struct wlr_seat *seat;
	struct wlr_cursor *cursor;
	struct wlr_xcursor_manager *xcursor;
	struct wl_list keyboards;
	enum cursor_mode cursor_mode;
	struct view *grab_view;
	double grab_x, grab_y;
	struct wlr_box grab_box;
	uint32_t resize_edges;
	struct wlr_surface *cursor_focus_surface;
	struct wlr_pointer_constraint_v1 *active_constraint;

	struct view *focused_view;
	struct layer_surface *focused_layer;
	struct wlr_output *focused_output;

	struct wlr_idle_notifier_v1 *idle;
	struct wlr_idle_inhibit_manager_v1 *idle_inhibit;
	int inhibitors;
	struct wlr_foreign_toplevel_manager_v1 *ftl_mgr;
	struct wlr_ext_foreign_toplevel_list_v1 *ext_ftl;
	struct wlr_output_manager_v1 *output_mgr;
	struct wlr_tearing_control_manager_v1 *tearing;
	struct wlr_pointer_constraints_v1 *constraints;
	struct wlr_relative_pointer_manager_v1 *relative;
	struct wlr_xdg_activation_v1 *activation;

	struct wlr_session_lock_manager_v1 *lock_mgr;
	struct wlr_session_lock_v1 *lock;
	struct wlr_scene_tree *lock_tree;
	struct wlr_scene_rect *lock_rect;
	bool locked;
	struct wlr_surface *lock_focus;

	struct wl_listener new_output, new_xdg_toplevel, new_xdg_popup, new_layer_surface, new_input,
		new_xwayland_surface, xwayland_ready, request_set_cursor, request_set_selection,
		request_set_primary, cursor_motion, cursor_motion_abs, cursor_button, cursor_axis,
		cursor_frame, new_deco, new_lock, new_inhibitor, activate, ftl_new_obj, tearing_new,
		cursor_shape, layout_change, output_apply, output_test, new_constraint, new_vkb,
		new_vptr, om_set_mode, pointer_focus_change, seat_destroy_dummy;
};

struct output {
	struct wl_list link;
	struct server *server;
	struct wlr_output *wlr_output;
	struct wlr_scene_output *scene_output;
	struct wlr_box usable;
	struct wl_listener frame, request_state, destroy;
};

struct view {
	struct wl_list link;
	struct server *server;
	bool is_x11, mapped, unmanaged, fullscreen, maximized;
	struct wlr_xdg_toplevel *xdg;
	struct wlr_xwayland_surface *xw;
	struct wlr_scene_tree *tree;
	struct wlr_scene_tree *content;
	int x, y;
	struct wlr_box saved;     /* geometry before fullscreen / maximize */
	struct wlr_foreign_toplevel_handle_v1 *ftl;
	struct wlr_ext_foreign_toplevel_handle_v1 *ext_ftl;
	struct wlr_tearing_control_v1 *tearing_obj;
	struct wl_listener map, unmap, commit, destroy, request_move, request_resize,
		request_maximize, request_fullscreen, set_title, set_app_id, ftl_activate,
		ftl_close, ftl_fullscreen, ftl_maximize, xw_associate, xw_dissociate,
		xw_request_configure, xw_set_geometry, xw_override;
	/* the surface's own map/unmap/commit listeners are live only between associate/dissociate */
	bool surface_listening;
};

struct keyboard {
	struct wl_list link;
	struct server *server;
	struct wlr_keyboard *wlr;
	struct wl_listener modifiers, key, destroy;
	uint32_t handled[16]; int nhandled;
};

struct layer_surface {
	struct wl_list link;
	struct server *server;
	struct wlr_layer_surface_v1 *wlr;
	struct wlr_scene_layer_surface_v1 *scene;
	struct wlr_scene_tree *popups;
	bool mapped;
	struct wl_listener map, unmap, commit, destroy, new_popup;
};

struct popup { struct wlr_xdg_popup *wlr; struct wl_listener commit, destroy; };
struct deco { struct wlr_xdg_toplevel_decoration_v1 *wlr; struct wl_listener mode, destroy, commit; bool waiting; };
struct lock_surface { struct wlr_session_lock_surface_v1 *wlr; struct wl_listener destroy, map; struct server *server; };
struct inhibitor_ref { struct server *server; struct wl_listener destroy; };
struct tearing_ref { struct wlr_tearing_control_v1 *obj; struct wl_listener destroy; };

static struct server S;

static void focus_view(struct view *v, struct wlr_surface *prefer);
static void arrange_layers(struct output *o);
static void publish_output_config(struct server *s);
static void update_cursor_focus(struct server *s, uint32_t time);
static void focus_layer_or_view(struct server *s);

/* ---------- small helpers ---------- */

static void spawn(const char *cmd) {
	pid_t p = fork();
	if (p < 0) return;
	if (p == 0) {
		setsid();
		pid_t q = fork();
		if (q != 0) _exit(0);
		signal(SIGPIPE, SIG_DFL);
		execl("/bin/sh", "sh", "-c", cmd, (char *)NULL);
		_exit(127);
	}
	waitpid(p, NULL, 0);
}

static char *trim(char *s) {
	while (isspace((unsigned char)*s)) s++;
	char *e = s + strlen(s);
	while (e > s && isspace((unsigned char)e[-1])) *--e = 0;
	return s;
}

/* ---------- config ---------- */

static uint32_t parse_mod(const char *n) {
	if (!strcasecmp(n, "super") || !strcasecmp(n, "logo") || !strcasecmp(n, "mod4")) return WLR_MODIFIER_LOGO;
	if (!strcasecmp(n, "alt") || !strcasecmp(n, "mod1")) return WLR_MODIFIER_ALT;
	if (!strcasecmp(n, "ctrl") || !strcasecmp(n, "control")) return WLR_MODIFIER_CTRL;
	if (!strcasecmp(n, "shift")) return WLR_MODIFIER_SHIFT;
	return 0;
}

static bool parse_combo(char *combo, uint32_t *mods, xkb_keysym_t *sym) {
	*mods = 0; *sym = XKB_KEY_NoSymbol;
	char *save = NULL;
	for (char *t = strtok_r(combo, "+", &save); t; t = strtok_r(NULL, "+", &save)) {
		t = trim(t);
		uint32_t m = parse_mod(t);
		if (m) *mods |= m;
		else *sym = xkb_keysym_from_name(t, XKB_KEYSYM_CASE_INSENSITIVE);
	}
	return *sym != XKB_KEY_NoSymbol;
}

static bool parse_action(const char *name, enum action *a) {
	static const struct { const char *n; enum action a; } t[] = {
		{"exec", A_EXEC}, {"close", A_CLOSE}, {"quit", A_QUIT}, {"focus-next", A_FOCUS_NEXT},
		{"fullscreen", A_FULLSCREEN}, {"maximize", A_MAXIMIZE}, {"output-next", A_OUTPUT_NEXT},
		{"reload", A_RELOAD},
	};
	for (size_t i = 0; i < sizeof t / sizeof *t; i++) if (!strcmp(name, t[i].n)) { *a = t[i].a; return true; }
	return false;
}

static void add_bind(struct server *s, const char *combo, enum action a, const char *arg, bool front) {
	char buf[128];
	snprintf(buf, sizeof buf, "%s", combo);
	struct bind *b = calloc(1, sizeof *b);
	if (!parse_combo(buf, &b->mods, &b->sym)) { wlr_log(WLR_ERROR, "bad key combo '%s'", combo); free(b); return; }
	b->action = a; b->arg = arg ? strdup(arg) : NULL;
	if (front) wl_list_insert(&s->binds, &b->link); else wl_list_insert(s->binds.prev, &b->link);
}

static void set_default_binds(struct server *s) {
	add_bind(s, "Super+Return", A_EXEC, "spark-terminal || foot || xterm", false);
	add_bind(s, "Super+q", A_CLOSE, NULL, false);
	add_bind(s, "Alt+F4", A_CLOSE, NULL, false);
	add_bind(s, "Alt+Tab", A_FOCUS_NEXT, NULL, false);
	add_bind(s, "Super+Tab", A_FOCUS_NEXT, NULL, false);
	add_bind(s, "Super+f", A_FULLSCREEN, NULL, false);
	add_bind(s, "Super+Up", A_MAXIMIZE, NULL, false);
	add_bind(s, "Super+o", A_OUTPUT_NEXT, NULL, false);
	add_bind(s, "Super+Shift+r", A_RELOAD, NULL, false);
	add_bind(s, "Super+Shift+e", A_QUIT, NULL, false);
}

static struct out_cfg *find_out_cfg(struct server *s, const char *name) {
	struct out_cfg *wild = NULL, *c;
	wl_list_for_each(c, &s->out_cfgs, link) {
		if (!strcmp(c->name, name)) return c;
		if (!strcmp(c->name, "*")) wild = c;
	}
	return wild;
}

static void parse_output_line(struct server *s, char *rest) {
	char *save = NULL;
	char *name = strtok_r(rest, " \t", &save);
	if (!name) return;
	struct out_cfg *c = calloc(1, sizeof *c);
	c->name = strdup(name); c->scale = 1.0; c->enabled = true; c->transform = WL_OUTPUT_TRANSFORM_NORMAL;
	for (char *kv = strtok_r(NULL, " \t", &save); kv; kv = strtok_r(NULL, " \t", &save)) {
		char *eq = strchr(kv, '=');
		if (!eq) continue;
		*eq = 0; char *v = eq + 1;
		if (!strcmp(kv, "mode")) { double hz = 0; int w, h; int n = sscanf(v, "%dx%d@%lf", &w, &h, &hz);
			if (n >= 2) { c->w = w; c->h = h; c->hz = hz; } }
		else if (!strcmp(kv, "scale")) c->scale = atof(v) > 0 ? atof(v) : 1.0;
		else if (!strcmp(kv, "pos")) { if (sscanf(v, "%d,%d", &c->x, &c->y) == 2) c->has_pos = true; }
		else if (!strcmp(kv, "enabled")) c->enabled = strcmp(v, "off") && strcmp(v, "false") && strcmp(v, "0");
		else if (!strcmp(kv, "vrr")) c->vrr = !strcmp(v, "on") || !strcmp(v, "true") || !strcmp(v, "1");
		else if (!strcmp(kv, "transform")) {
			static const struct { const char *n; enum wl_output_transform t; } T[] = {
				{"normal", 0}, {"0", 0}, {"90", 1}, {"180", 2}, {"270", 3}, {"flipped", 4},
				{"flipped-90", 5}, {"flipped-180", 6}, {"flipped-270", 7} };
			for (size_t i = 0; i < sizeof T / sizeof *T; i++) if (!strcmp(v, T[i].n)) c->transform = T[i].t;
		}
	}
	wl_list_insert(s->out_cfgs.prev, &c->link);
}

static void load_config_file(struct server *s, const char *path) {
	FILE *f = fopen(path, "r");
	if (!f) return;
	char line[512];
	while (fgets(line, sizeof line, f)) {
		char *l = trim(line);
		if (!*l || *l == '#') continue;
		if (!strncmp(l, "output ", 7)) parse_output_line(s, l + 7);
		else if (!strncmp(l, "bind ", 5)) {
			/* bind COMBO ACTION [ARGUMENT...] */
			char *save = NULL, *combo = strtok_r(l + 5, " \t", &save), *act = strtok_r(NULL, " \t", &save);
			char *arg = save ? trim(save) : NULL;
			enum action a;
			if (combo && act && parse_action(act, &a)) add_bind(s, combo, a, arg, true);
			else wlr_log(WLR_ERROR, "bad bind line in %s: %s", path, l);
		}
	}
	fclose(f);
	wlr_log(WLR_INFO, "read %s", path);
}

static void load_config(struct server *s) {
	const char *dir = getenv("SPARK_COMPOSITOR_CONFIG_DIR");
	char base[512], path[600];
	if (dir) snprintf(base, sizeof base, "%s", dir);
	else {
		const char *xdg = getenv("XDG_CONFIG_HOME"), *home = getenv("HOME");
		if (xdg && *xdg) snprintf(base, sizeof base, "%s/spark/compositor", xdg);
		else snprintf(base, sizeof base, "%s/.config/spark/compositor", home ? home : "");
	}
	snprintf(path, sizeof path, "%s/outputs.conf", base); load_config_file(s, path);
	snprintf(path, sizeof path, "%s/compositor.conf", base); load_config_file(s, path);
}

static void free_config(struct server *s) {
	struct out_cfg *c, *ct;
	wl_list_for_each_safe(c, ct, &s->out_cfgs, link) { wl_list_remove(&c->link); free(c->name); free(c); }
	struct bind *b, *bt;
	wl_list_for_each_safe(b, bt, &s->binds, link) { wl_list_remove(&b->link); free(b->arg); free(b); }
}

/* ---------- outputs ---------- */

static struct output *output_of(struct server *s, struct wlr_output *wo) {
	struct output *o;
	wl_list_for_each(o, &s->outputs, link) if (o->wlr_output == wo) return o;
	return NULL;
}

static struct wlr_output *output_at_cursor(struct server *s) {
	struct wlr_output *o = wlr_output_layout_output_at(s->output_layout, s->cursor->x, s->cursor->y);
	if (o) return o;
	struct output *first = wl_container_of(s->outputs.next, first, link);
	return wl_list_empty(&s->outputs) ? NULL : first->wlr_output;
}

/* The mode that matches w x h, nearest refresh to hz (hz 0 = highest). */
static struct wlr_output_mode *pick_mode(struct wlr_output *wo, int w, int h, double hz) {
	struct wlr_output_mode *m, *best = NULL;
	wl_list_for_each(m, &wo->modes, link) {
		if (m->width != w || m->height != h) continue;
		if (!best) { best = m; continue; }
		double d1 = hz > 0 ? fabs(m->refresh / 1000.0 - hz) : -m->refresh;
		double d2 = hz > 0 ? fabs(best->refresh / 1000.0 - hz) : -best->refresh;
		if (d1 < d2) best = m;
	}
	return best;
}

static void apply_cfg_to_state(struct wlr_output *wo, struct out_cfg *c, struct wlr_output_state *st) {
	if (!c) {
		struct wlr_output_mode *pm = wlr_output_preferred_mode(wo);
		wlr_output_state_set_enabled(st, true);
		if (pm) wlr_output_state_set_mode(st, pm);
		return;
	}
	wlr_output_state_set_enabled(st, c->enabled);
	if (c->w > 0) {
		struct wlr_output_mode *m = pick_mode(wo, c->w, c->h, c->hz);
		if (m) wlr_output_state_set_mode(st, m);
		else wlr_output_state_set_custom_mode(st, c->w, c->h, c->hz > 0 ? (int)(c->hz * 1000) : 0);
	} else {
		struct wlr_output_mode *pm = wlr_output_preferred_mode(wo);
		if (pm) wlr_output_state_set_mode(st, pm);
	}
	wlr_output_state_set_scale(st, (float)c->scale);
	wlr_output_state_set_transform(st, c->transform);
	if (c->vrr) wlr_output_state_set_adaptive_sync_enabled(st, true);
}

static void output_frame(struct wl_listener *l, void *data) {
	struct output *o = wl_container_of(l, o, frame);
	struct server *s = o->server;
	struct wlr_scene_output *so = o->scene_output;
	struct wlr_output *wo = o->wlr_output;

	struct view *fv = s->focused_view;
	bool tear = fv && fv->fullscreen && fv->tearing_obj &&
		fv->tearing_obj->current == WP_TEARING_CONTROL_V1_PRESENTATION_HINT_ASYNC;
	if (tear && wo->needs_frame) {
		/* Tearing: a fullscreen game that asked for async presentation gets it, if the
		 * driver accepts the flip. Everything else stays vsynced. */
		struct wlr_output_state st;
		wlr_output_state_init(&st);
		if (wlr_scene_output_build_state(so, &st, NULL)) {
			st.tearing_page_flip = true;
			if (!wlr_output_test_state(wo, &st)) st.tearing_page_flip = false;
			wlr_output_commit_state(wo, &st);
		}
		wlr_output_state_finish(&st);
	} else {
		wlr_scene_output_commit(so, NULL);
	}
	struct timespec now; clock_gettime(CLOCK_MONOTONIC, &now);
	wlr_scene_output_send_frame_done(so, &now);
}

static void output_request_state(struct wl_listener *l, void *data) {
	struct output *o = wl_container_of(l, o, request_state);
	const struct wlr_output_event_request_state *e = data;
	wlr_output_commit_state(o->wlr_output, e->state);
	arrange_layers(o);
	publish_output_config(o->server);
}

static void output_destroy(struct wl_listener *l, void *data) {
	struct output *o = wl_container_of(l, o, destroy);
	struct server *s = o->server;
	UNLISTEN(&o->frame); UNLISTEN(&o->request_state); UNLISTEN(&o->destroy);
	wl_list_remove(&o->link);
	if (s->focused_output == o->wlr_output) s->focused_output = NULL;
	/* layer surfaces of this output lose their output; the client is told to close */
	struct layer_surface *ls, *lt;
	wl_list_for_each_safe(ls, lt, &s->layer_surfaces, link)
		if (ls->wlr->output == o->wlr_output) { ls->wlr->output = NULL; wlr_layer_surface_v1_destroy(ls->wlr); }
	free(o);
	publish_output_config(s);
}

static void refit_views(struct server *s) {
	struct view *v;
	wl_list_for_each(v, &s->views, link) {
		struct wlr_box b;
		if (!v->mapped || wlr_output_layout_output_at(s->output_layout, v->x + 40, v->y + 40)) continue;
		/* the window is on an output that went away: bring it to the first output */
		struct wlr_output *wo = output_at_cursor(s);
		if (!wo) continue;
		wlr_output_layout_get_box(s->output_layout, wo, &b);
		v->x = b.x + 60; v->y = b.y + 60;
		wlr_scene_node_set_position(&v->tree->node, v->x, v->y);
	}
}

static void new_output(struct wl_listener *l, void *data) {
	struct server *s = wl_container_of(l, s, new_output);
	struct wlr_output *wo = data;
	if (!wlr_output_init_render(wo, s->allocator, s->renderer)) return;

	struct out_cfg *c = find_out_cfg(s, wo->name);
	struct wlr_output_state st;
	wlr_output_state_init(&st);
	apply_cfg_to_state(wo, c, &st);
	bool ok = wlr_output_commit_state(wo, &st);
	if (!ok && c) { /* the configured mode failed: fall back to the preferred one */
		wlr_output_state_finish(&st); wlr_output_state_init(&st);
		apply_cfg_to_state(wo, NULL, &st);
		ok = wlr_output_commit_state(wo, &st);
	}
	wlr_output_state_finish(&st);
	if (!ok) { wlr_log(WLR_ERROR, "output %s could not be enabled", wo->name); return; }
	if (c && !c->enabled) return;

	struct output *o = calloc(1, sizeof *o);
	o->server = s; o->wlr_output = wo;
	wo->data = o;
	LISTEN(wo->events.frame, &o->frame, output_frame);
	LISTEN(wo->events.request_state, &o->request_state, output_request_state);
	LISTEN(wo->events.destroy, &o->destroy, output_destroy);
	wl_list_insert(&s->outputs, &o->link);

	struct wlr_output_layout_output *lo = (c && c->has_pos)
		? wlr_output_layout_add(s->output_layout, wo, c->x, c->y)
		: wlr_output_layout_add_auto(s->output_layout, wo);
	o->scene_output = wlr_scene_output_create(s->scene, wo);
	wlr_scene_output_layout_add_output(s->scene_layout, lo, o->scene_output);
	if (!s->focused_output) s->focused_output = wo;

	struct wlr_box b; wlr_output_layout_get_box(s->output_layout, wo, &b);
	o->usable = b;
	int tw, th; wlr_output_transformed_resolution(wo, &tw, &th);
	wlr_log(WLR_INFO, "output %s: %dx%d@%.3f scale %.2f transform %d at %d,%d", wo->name, tw, th,
		wo->refresh / 1000.0, wo->scale, wo->transform, b.x, b.y);
	arrange_layers(o);
	if (s->locked && s->lock_rect) wlr_scene_rect_set_size(s->lock_rect, 100000, 100000);
	publish_output_config(s);
}

static void layout_changed(struct wl_listener *l, void *data) {
	struct server *s = wl_container_of(l, s, layout_change);
	struct output *o;
	wl_list_for_each(o, &s->outputs, link) arrange_layers(o);
	refit_views(s);
	publish_output_config(s);
}

/* wlr-output-management: apply or test a client's configuration (Spark Settings, wlr-randr). */
static bool apply_output_config(struct server *s, struct wlr_output_configuration_v1 *cfg, bool test) {
	struct wlr_output_configuration_head_v1 *h;
	bool ok = true;
	wl_list_for_each(h, &cfg->heads, link) {
		struct wlr_output *wo = h->state.output;
		struct wlr_output_state st;
		wlr_output_state_init(&st);
		wlr_output_state_set_enabled(&st, h->state.enabled);
		if (h->state.enabled) {
			if (h->state.mode) wlr_output_state_set_mode(&st, h->state.mode);
			else wlr_output_state_set_custom_mode(&st, h->state.custom_mode.width,
				h->state.custom_mode.height, h->state.custom_mode.refresh);
			wlr_output_state_set_scale(&st, h->state.scale);
			wlr_output_state_set_transform(&st, h->state.transform);
			wlr_output_state_set_adaptive_sync_enabled(&st, h->state.adaptive_sync_enabled);
		}
		ok &= test ? wlr_output_test_state(wo, &st) : wlr_output_commit_state(wo, &st);
		wlr_output_state_finish(&st);
	}
	if (ok && !test) {
		wl_list_for_each(h, &cfg->heads, link) {
			struct wlr_output *wo = h->state.output;
			if (h->state.enabled) wlr_output_layout_add(s->output_layout, wo, h->state.x, h->state.y);
			else wlr_output_layout_remove(s->output_layout, wo);
		}
	}
	return ok;
}

static void output_config_apply(struct wl_listener *l, void *data) {
	struct server *s = wl_container_of(l, s, output_apply);
	struct wlr_output_configuration_v1 *cfg = data;
	if (apply_output_config(s, cfg, false)) wlr_output_configuration_v1_send_succeeded(cfg);
	else wlr_output_configuration_v1_send_failed(cfg);
	wlr_output_configuration_v1_destroy(cfg);
	publish_output_config(s);
}

static void output_config_test(struct wl_listener *l, void *data) {
	struct server *s = wl_container_of(l, s, output_test);
	struct wlr_output_configuration_v1 *cfg = data;
	if (apply_output_config(s, cfg, true)) wlr_output_configuration_v1_send_succeeded(cfg);
	else wlr_output_configuration_v1_send_failed(cfg);
	wlr_output_configuration_v1_destroy(cfg);
}

static void publish_output_config(struct server *s) {
	struct wlr_output_configuration_v1 *cfg = wlr_output_configuration_v1_create();
	struct output *o;
	wl_list_for_each(o, &s->outputs, link) {
		struct wlr_output_configuration_head_v1 *h = wlr_output_configuration_head_v1_create(cfg, o->wlr_output);
		struct wlr_box b;
		wlr_output_layout_get_box(s->output_layout, o->wlr_output, &b);
		h->state.x = b.x; h->state.y = b.y;
	}
	wlr_output_manager_v1_set_configuration(s->output_mgr, cfg);
	/* clients also learn the new scale for fractional-scale */
	struct view *v;
	wl_list_for_each(v, &s->views, link) {
		struct wlr_surface *surf = v->is_x11 ? (v->xw ? v->xw->surface : NULL) : v->xdg->base->surface;
		struct wlr_output *wo = wlr_output_layout_output_at(s->output_layout, v->x + 1, v->y + 1);
		if (surf && wo) wlr_fractional_scale_v1_notify_scale(surf, wo->scale);
	}
}

/* ---------- layer shell ---------- */

static void arrange_layers(struct output *o) {
	struct server *s = o->server;
	struct wlr_box full;
	wlr_output_layout_get_box(s->output_layout, o->wlr_output, &full);
	struct wlr_box usable = full;
	for (int pass = 0; pass < 2; pass++) {
		/* pass 0: exclusive-zone surfaces, so they shrink the area before the others lay out */
		for (int layer = ZWLR_LAYER_SHELL_V1_LAYER_OVERLAY; layer >= 0; layer--) {
			struct layer_surface *ls;
			wl_list_for_each(ls, &s->layer_surfaces, link) {
				if (!ls->wlr->initialized || ls->wlr->output != o->wlr_output || (int)ls->wlr->current.layer != layer) continue;
				bool excl = ls->wlr->current.exclusive_zone > 0;
				if ((pass == 0) != excl) continue;
				wlr_scene_layer_surface_v1_configure(ls->scene, &full, &usable);
			}
		}
	}
	o->usable = usable;
}

static void layer_commit(struct wl_listener *l, void *data) {
	struct layer_surface *ls = wl_container_of(l, ls, commit);
	struct wlr_layer_surface_v1 *w = ls->wlr;
	if (!w->output) return;
	struct output *o = output_of(ls->server, w->output);
	if (w->initial_commit || w->current.committed) {
		static const enum scene_layer map[] = { L_BG, L_BOTTOM, L_TOP, L_OVERLAY };
		struct wlr_scene_tree *want = ls->server->layers[map[w->current.layer]];
		if (ls->scene->tree->node.parent != want) wlr_scene_node_reparent(&ls->scene->tree->node, want);
		if (o) arrange_layers(o);
	}
	if (w->initial_commit && w->surface->mapped == false) { /* configure happens in arrange */ }
}

static void layer_map(struct wl_listener *l, void *data) {
	struct layer_surface *ls = wl_container_of(l, ls, map);
	ls->mapped = true;
	struct server *s = ls->server;
	wlr_log(WLR_INFO, "mapped layer surface namespace=%s layer=%d on %s", ls->wlr->namespace,
		ls->wlr->current.layer, ls->wlr->output ? ls->wlr->output->name : "?");
	if (ls->wlr->current.keyboard_interactive == ZWLR_LAYER_SURFACE_V1_KEYBOARD_INTERACTIVITY_EXCLUSIVE &&
	    ls->wlr->current.layer >= ZWLR_LAYER_SHELL_V1_LAYER_TOP && !s->locked) {
		s->focused_layer = ls;
		focus_layer_or_view(s);
	}
}

static void layer_unmap(struct wl_listener *l, void *data) {
	struct layer_surface *ls = wl_container_of(l, ls, unmap);
	ls->mapped = false;
	struct server *s = ls->server;
	if (s->focused_layer == ls) { s->focused_layer = NULL; focus_layer_or_view(s); }
	if (ls->wlr->output) { struct output *o = output_of(s, ls->wlr->output); if (o) arrange_layers(o); }
}

static void layer_destroy(struct wl_listener *l, void *data) {
	struct layer_surface *ls = wl_container_of(l, ls, destroy);
	struct server *s = ls->server;
	if (s->focused_layer == ls) s->focused_layer = NULL;
	struct wlr_output *wo = ls->wlr->output;
	UNLISTEN(&ls->map); UNLISTEN(&ls->unmap); UNLISTEN(&ls->commit); UNLISTEN(&ls->destroy);
	UNLISTEN(&ls->new_popup);
	wl_list_remove(&ls->link);
	free(ls);
	if (wo) { struct output *o = output_of(s, wo); if (o) arrange_layers(o); }
	focus_layer_or_view(s);
}

static void popup_commit(struct wl_listener *l, void *data) {
	struct popup *p = wl_container_of(l, p, commit);
	if (p->wlr->base->initial_commit) {
		struct wlr_box b = {0};
		struct wlr_xdg_surface *parent = wlr_xdg_surface_try_from_wlr_surface(p->wlr->parent);
		(void)parent;
		struct wlr_output *wo = output_at_cursor(&S);
		if (wo) wlr_output_layout_get_box(S.output_layout, wo, &b);
		wlr_xdg_surface_schedule_configure(p->wlr->base);
	}
}
static void popup_destroy(struct wl_listener *l, void *data) {
	struct popup *p = wl_container_of(l, p, destroy);
	UNLISTEN(&p->commit); UNLISTEN(&p->destroy); free(p);
}

static void make_popup(struct wlr_xdg_popup *wp, struct wlr_scene_tree *parent_tree) {
	struct popup *p = calloc(1, sizeof *p);
	p->wlr = wp;
	wp->base->data = wlr_scene_xdg_surface_create(parent_tree, wp->base);
	LISTEN(wp->base->surface->events.commit, &p->commit, popup_commit);
	LISTEN(wp->events.destroy, &p->destroy, popup_destroy);
}

static void layer_new_popup(struct wl_listener *l, void *data) {
	struct layer_surface *ls = wl_container_of(l, ls, new_popup);
	make_popup(data, ls->popups);
}

static void new_layer_surface(struct wl_listener *l, void *data) {
	struct server *s = wl_container_of(l, s, new_layer_surface);
	struct wlr_layer_surface_v1 *w = data;
	if (!w->output) {
		struct wlr_output *wo = s->focused_output ? s->focused_output : output_at_cursor(s);
		if (!wo) { wlr_layer_surface_v1_destroy(w); return; }
		w->output = wo;
	}
	struct layer_surface *ls = calloc(1, sizeof *ls);
	ls->server = s; ls->wlr = w;
	static const enum scene_layer map[] = { L_BG, L_BOTTOM, L_TOP, L_OVERLAY };
	ls->scene = wlr_scene_layer_surface_v1_create(s->layers[map[w->pending.layer]], w);
	ls->popups = wlr_scene_tree_create(s->layers[L_OVERLAY]);
	wl_list_insert(&s->layer_surfaces, &ls->link);
	LISTEN(w->surface->events.commit, &ls->commit, layer_commit);
	LISTEN(w->surface->events.map, &ls->map, layer_map);
	LISTEN(w->surface->events.unmap, &ls->unmap, layer_unmap);
	LISTEN(w->events.destroy, &ls->destroy, layer_destroy);
	LISTEN(w->events.new_popup, &ls->new_popup, layer_new_popup);
	/* the first configure goes out from layer_commit, once the client has committed */
}

/* ---------- focus ---------- */

static struct wlr_surface *view_surface(struct view *v) {
	if (v->is_x11) return v->xw ? v->xw->surface : NULL;
	return v->xdg->base->surface;
}

static void view_activate(struct view *v, bool on) {
	if (v->is_x11) { if (v->xw) wlr_xwayland_surface_activate(v->xw, on); }
	else wlr_xdg_toplevel_set_activated(v->xdg, on);
	if (v->ftl) wlr_foreign_toplevel_handle_v1_set_activated(v->ftl, on);
}

static void send_keyboard_focus(struct server *s, struct wlr_surface *surf) {
	struct wlr_keyboard *kb = wlr_seat_get_keyboard(s->seat);
	if (!surf) { wlr_seat_keyboard_notify_clear_focus(s->seat); return; }
	if (kb) wlr_seat_keyboard_notify_enter(s->seat, surf, kb->keycodes, kb->num_keycodes, &kb->modifiers);
	else wlr_seat_keyboard_notify_enter(s->seat, surf, NULL, 0, NULL);
}

/* Decide who has the keyboard: the lock surface, an exclusive layer surface, else a window. */
static void focus_layer_or_view(struct server *s) {
	if (s->locked) {
		send_keyboard_focus(s, s->lock_focus);
		return;
	}
	if (s->focused_layer && s->focused_layer->mapped) {
		send_keyboard_focus(s, s->focused_layer->wlr->surface);
		return;
	}
	if (s->focused_view && s->focused_view->mapped) send_keyboard_focus(s, view_surface(s->focused_view));
	else send_keyboard_focus(s, NULL);
}

static void focus_view(struct view *v, struct wlr_surface *prefer) {
	struct server *s = &S;
	if (!v) return;
	if (s->focused_view == v && !s->focused_layer) return;
	if (s->focused_view && s->focused_view != v && s->focused_view->mapped) view_activate(s->focused_view, false);
	s->focused_view = v;
	s->focused_layer = NULL;
	wlr_scene_node_raise_to_top(&v->tree->node);
	wl_list_remove(&v->link);
	wl_list_insert(&s->views, &v->link);
	view_activate(v, true);
	struct wlr_box b = { v->x, v->y, 1, 1 };
	struct wlr_output *wo = wlr_output_layout_output_at(s->output_layout, b.x + 1, b.y + 1);
	if (wo) s->focused_output = wo;
	focus_layer_or_view(s);
	(void)prefer;
}

static struct view *next_view(struct server *s) {
	/* the window behind the focused one, mapped and managed */
	struct view *v;
	int n = 0;
	wl_list_for_each(v, &s->views, link) if (v->mapped && !v->unmanaged) n++;
	if (n < 2) return NULL;
	struct view *last = NULL;
	wl_list_for_each(v, &s->views, link) if (v->mapped && !v->unmanaged) last = v;
	return last;
}

/* ---------- views ---------- */

static void view_box(struct view *v, struct wlr_box *b) {
	if (v->is_x11) { b->x = 0; b->y = 0; b->width = v->xw->width; b->height = v->xw->height; }
	else { *b = v->xdg->base->geometry; }
}

static void view_place(struct view *v, int x, int y) {
	v->x = x; v->y = y;
	wlr_scene_node_set_position(&v->tree->node, x, y);
	if (v->is_x11 && v->xw) wlr_xwayland_surface_configure(v->xw, x, y, v->xw->width, v->xw->height);
}

static void view_resize(struct view *v, int w, int h) {
	if (w < 40) w = 40;
	if (h < 30) h = 30;
	if (v->is_x11) wlr_xwayland_surface_configure(v->xw, v->x, v->y, w, h);
	else wlr_xdg_toplevel_set_size(v->xdg, w, h);
}

static struct wlr_output *view_output(struct view *v) {
	struct wlr_box b; view_box(v, &b);
	struct wlr_output *wo = wlr_output_layout_output_at(S.output_layout, v->x + b.width / 2, v->y + b.height / 2);
	return wo ? wo : output_at_cursor(&S);
}

static void view_set_fullscreen(struct view *v, bool on) {
	if (v->fullscreen == on) return;
	struct server *s = v->server;
	if (on) {
		struct wlr_box b; view_box(v, &b);
		v->saved = (struct wlr_box){ v->x, v->y, b.width, b.height };
	}
	v->fullscreen = on;
	if (v->is_x11) wlr_xwayland_surface_set_fullscreen(v->xw, on);
	else wlr_xdg_toplevel_set_fullscreen(v->xdg, on);
	if (v->ftl) wlr_foreign_toplevel_handle_v1_set_fullscreen(v->ftl, on);
	wlr_scene_node_reparent(&v->tree->node, s->layers[on ? L_FULLSCREEN : L_WINDOWS]);
	if (on) {
		struct wlr_output *wo = view_output(v);
		struct wlr_box ob; wlr_output_layout_get_box(s->output_layout, wo, &ob);
		view_place(v, ob.x, ob.y);
		view_resize(v, ob.width, ob.height);
	} else {
		view_place(v, v->saved.x, v->saved.y);
		view_resize(v, v->saved.width, v->saved.height);
	}
}

static void view_set_maximized(struct view *v, bool on) {
	if (v->fullscreen) return;
	if (on == v->maximized) return;
	if (on) {
		struct wlr_box b; view_box(v, &b);
		v->saved = (struct wlr_box){ v->x, v->y, b.width, b.height };
		struct output *o = output_of(v->server, view_output(v));
		if (!o) return;
		v->maximized = true;
		view_place(v, o->usable.x, o->usable.y);
		view_resize(v, o->usable.width, o->usable.height);
	} else {
		v->maximized = false;
		view_place(v, v->saved.x, v->saved.y);
		view_resize(v, v->saved.width, v->saved.height);
	}
	if (!v->is_x11) wlr_xdg_toplevel_set_maximized(v->xdg, on);
	if (v->ftl) wlr_foreign_toplevel_handle_v1_set_maximized(v->ftl, on);
}

static void view_close(struct view *v) {
	if (v->is_x11) wlr_xwayland_surface_close(v->xw);
	else wlr_xdg_toplevel_send_close(v->xdg);
}

static void view_titles(struct view *v) {
	const char *title = v->is_x11 ? v->xw->title : v->xdg->title;
	const char *app = v->is_x11 ? v->xw->class : v->xdg->app_id;
	if (v->ftl) {
		wlr_foreign_toplevel_handle_v1_set_title(v->ftl, title ? title : "");
		wlr_foreign_toplevel_handle_v1_set_app_id(v->ftl, app ? app : "");
	}
	if (v->ext_ftl) {
		struct wlr_ext_foreign_toplevel_handle_v1_state st = { .title = title ? title : "", .app_id = app ? app : "" };
		wlr_ext_foreign_toplevel_handle_v1_update_state(v->ext_ftl, &st);
	}
}
static void view_set_title(struct wl_listener *l, void *d) { struct view *v = wl_container_of(l, v, set_title); view_titles(v); }
static void view_set_app_id(struct wl_listener *l, void *d) { struct view *v = wl_container_of(l, v, set_app_id); view_titles(v); }

static void ftl_activate(struct wl_listener *l, void *d) { struct view *v = wl_container_of(l, v, ftl_activate); focus_view(v, NULL); }
static void ftl_close(struct wl_listener *l, void *d) { struct view *v = wl_container_of(l, v, ftl_close); view_close(v); }
static void ftl_fullscreen(struct wl_listener *l, void *d) {
	struct view *v = wl_container_of(l, v, ftl_fullscreen);
	struct wlr_foreign_toplevel_handle_v1_fullscreen_event *e = d;
	view_set_fullscreen(v, e->fullscreen);
}
static void ftl_maximize(struct wl_listener *l, void *d) {
	struct view *v = wl_container_of(l, v, ftl_maximize);
	struct wlr_foreign_toplevel_handle_v1_maximized_event *e = d;
	view_set_maximized(v, e->maximized);
}

static void view_map(struct wl_listener *l, void *data) {
	struct view *v = wl_container_of(l, v, map);
	struct server *s = v->server;
	struct wlr_surface *surf = view_surface(v);
	v->mapped = true;
	wlr_log(WLR_INFO, "mapped %s window app_id=%s title=%s", v->is_x11 ? (v->unmanaged ? "x11-unmanaged" : "x11") : "xdg",
		v->is_x11 ? (v->xw->class ? v->xw->class : "") : (v->xdg->app_id ? v->xdg->app_id : ""),
		v->is_x11 ? (v->xw->title ? v->xw->title : "") : (v->xdg->title ? v->xdg->title : ""));
	if (v->unmanaged) {
		wlr_scene_node_set_position(&v->tree->node, v->xw->x, v->xw->y);
		wlr_scene_node_reparent(&v->tree->node, s->layers[L_TOP]);
		if (wlr_xwayland_surface_override_redirect_wants_focus(v->xw) && !s->locked)
			wlr_seat_keyboard_notify_enter(s->seat, surf, NULL, 0, NULL);
		return;
	}
	wl_list_insert(&s->views, &v->link);
	/* place new windows near the middle of the focused output's usable area, cascaded */
	struct wlr_output *wo = s->focused_output ? s->focused_output : output_at_cursor(s);
	struct output *o = wo ? output_of(s, wo) : NULL;
	struct wlr_box b; view_box(v, &b);
	if (o) {
		static int cascade;
		int cx = o->usable.x + (o->usable.width - b.width) / 2 + (cascade % 6) * 28;
		int cy = o->usable.y + (o->usable.height - b.height) / 2 + (cascade % 6) * 28;
		cascade++;
		if (cx < o->usable.x) cx = o->usable.x;
		if (cy < o->usable.y) cy = o->usable.y;
		v->x = cx; v->y = cy;
	}
	wlr_scene_node_set_position(&v->tree->node, v->x, v->y);
	if (v->is_x11) wlr_xwayland_surface_configure(v->xw, v->x, v->y, v->xw->width, v->xw->height);

	v->ftl = wlr_foreign_toplevel_handle_v1_create(s->ftl_mgr);
	LISTEN(v->ftl->events.request_activate, &v->ftl_activate, ftl_activate);
	LISTEN(v->ftl->events.request_close, &v->ftl_close, ftl_close);
	LISTEN(v->ftl->events.request_fullscreen, &v->ftl_fullscreen, ftl_fullscreen);
	LISTEN(v->ftl->events.request_maximize, &v->ftl_maximize, ftl_maximize);
	struct wlr_ext_foreign_toplevel_handle_v1_state st = { .title = "", .app_id = "" };
	v->ext_ftl = wlr_ext_foreign_toplevel_handle_v1_create(s->ext_ftl, &st);
	view_titles(v);
	if (wo && surf) wlr_fractional_scale_v1_notify_scale(surf, wo->scale);
	focus_view(v, NULL);
	if (!v->is_x11 && v->xdg->requested.fullscreen) view_set_fullscreen(v, true);
}

static void view_unmap(struct wl_listener *l, void *data) {
	struct view *v = wl_container_of(l, v, unmap);
	struct server *s = v->server;
	v->mapped = false;
	if (v->unmanaged) return;
	if (s->cursor_mode != CURSOR_PASSTHROUGH && s->grab_view == v) { s->cursor_mode = CURSOR_PASSTHROUGH; s->grab_view = NULL; }
	if (v->ftl) {
		UNLISTEN(&v->ftl_activate); UNLISTEN(&v->ftl_close); UNLISTEN(&v->ftl_fullscreen); UNLISTEN(&v->ftl_maximize);
		wlr_foreign_toplevel_handle_v1_destroy(v->ftl); v->ftl = NULL;
	}
	if (v->ext_ftl) { wlr_ext_foreign_toplevel_handle_v1_destroy(v->ext_ftl); v->ext_ftl = NULL; }
	wl_list_remove(&v->link);
	wl_list_init(&v->link);
	if (s->focused_view == v) {
		s->focused_view = NULL;
		struct view *n;
		wl_list_for_each(n, &s->views, link) if (n->mapped) { focus_view(n, NULL); break; }
		if (!s->focused_view) focus_layer_or_view(s);
	}
}

static void view_commit(struct wl_listener *l, void *data) {
	struct view *v = wl_container_of(l, v, commit);
	if (!v->is_x11 && v->xdg->base->initial_commit) wlr_xdg_toplevel_set_size(v->xdg, 0, 0);
}

static void view_unlisten_surface(struct view *v) {
	if (!v->surface_listening) return;
	UNLISTEN(&v->map); UNLISTEN(&v->unmap); UNLISTEN(&v->commit);
	v->surface_listening = false;
}

static void view_destroy(struct wl_listener *l, void *data) {
	struct view *v = wl_container_of(l, v, destroy);
	struct server *s = v->server;
	if (v->mapped) view_unmap(&v->unmap, NULL);
	view_unlisten_surface(v);
	UNLISTEN(&v->destroy);
	if (!v->is_x11) {
		UNLISTEN(&v->request_move); UNLISTEN(&v->request_resize); UNLISTEN(&v->request_maximize);
		UNLISTEN(&v->request_fullscreen); UNLISTEN(&v->set_title); UNLISTEN(&v->set_app_id);
	} else {
		/* every listener added in new_xwayland_surface: wlroots asserts the surface's signals
		 * are empty when it is destroyed, so one left behind aborts the compositor */
		UNLISTEN(&v->xw_associate); UNLISTEN(&v->xw_dissociate); UNLISTEN(&v->xw_request_configure);
		UNLISTEN(&v->set_title); UNLISTEN(&v->set_app_id); UNLISTEN(&v->xw_override);
	}
	if (s->focused_view == v) s->focused_view = NULL;
	if (s->grab_view == v) { s->grab_view = NULL; s->cursor_mode = CURSOR_PASSTHROUGH; }
	wlr_scene_node_destroy(&v->tree->node);
	free(v);
}

static void begin_grab(struct server *s, struct view *v, enum cursor_mode mode, uint32_t edges) {
	if (!v || v->fullscreen) return;
	s->grab_view = v; s->cursor_mode = mode;
	struct wlr_box b; view_box(v, &b);
	if (mode == CURSOR_MOVE) { s->grab_x = s->cursor->x - v->x; s->grab_y = s->cursor->y - v->y; }
	else {
		s->grab_box = (struct wlr_box){ v->x, v->y, b.width, b.height };
		s->resize_edges = edges;
		s->grab_x = s->cursor->x; s->grab_y = s->cursor->y;
	}
	if (v->maximized) { v->maximized = false; if (!v->is_x11) wlr_xdg_toplevel_set_maximized(v->xdg, false); }
}

static void view_request_move(struct wl_listener *l, void *d) {
	struct view *v = wl_container_of(l, v, request_move);
	if (S.focused_view == v) begin_grab(&S, v, CURSOR_MOVE, 0);
}
static void view_request_resize(struct wl_listener *l, void *d) {
	struct view *v = wl_container_of(l, v, request_resize);
	struct wlr_xdg_toplevel_resize_event *e = d;
	if (S.focused_view == v) begin_grab(&S, v, CURSOR_RESIZE, e->edges);
}
static void view_request_maximize(struct wl_listener *l, void *d) {
	struct view *v = wl_container_of(l, v, request_maximize);
	if (!v->xdg->base->initialized) return;
	view_set_maximized(v, v->xdg->requested.maximized);
	wlr_xdg_surface_schedule_configure(v->xdg->base);
}
static void view_request_fullscreen(struct wl_listener *l, void *d) {
	struct view *v = wl_container_of(l, v, request_fullscreen);
	if (!v->xdg->base->initialized) return;
	view_set_fullscreen(v, v->xdg->requested.fullscreen);
	wlr_xdg_surface_schedule_configure(v->xdg->base);
}

static struct view *make_view(struct server *s) {
	struct view *v = calloc(1, sizeof *v);
	v->server = s;
	wl_list_init(&v->link);
	v->tree = wlr_scene_tree_create(s->layers[L_WINDOWS]);
	v->tree->node.data = v;
	return v;
}

static void new_xdg_toplevel(struct wl_listener *l, void *data) {
	struct server *s = wl_container_of(l, s, new_xdg_toplevel);
	struct wlr_xdg_toplevel *t = data;
	struct view *v = make_view(s);
	v->xdg = t;
	v->content = wlr_scene_xdg_surface_create(v->tree, t->base);
	t->base->data = v->tree;
	v->surface_listening = true;
	LISTEN(t->base->surface->events.map, &v->map, view_map);
	LISTEN(t->base->surface->events.unmap, &v->unmap, view_unmap);
	LISTEN(t->base->surface->events.commit, &v->commit, view_commit);
	LISTEN(t->events.destroy, &v->destroy, view_destroy);
	LISTEN(t->events.request_move, &v->request_move, view_request_move);
	LISTEN(t->events.request_resize, &v->request_resize, view_request_resize);
	LISTEN(t->events.request_maximize, &v->request_maximize, view_request_maximize);
	LISTEN(t->events.request_fullscreen, &v->request_fullscreen, view_request_fullscreen);
	LISTEN(t->events.set_title, &v->set_title, view_set_title);
	LISTEN(t->events.set_app_id, &v->set_app_id, view_set_app_id);
}

static void new_xdg_popup(struct wl_listener *l, void *data) {
	struct wlr_xdg_popup *p = data;
	/* A popup made with a null parent gets one later from zwlr_layer_surface_v1.get_popup, and
	 * layer_new_popup places it then (into the layer surface's popup tree); the same goes for a
	 * popup whose parent is a layer surface. Only popups of xdg surfaces are placed here. */
	if (!p->parent) return;
	struct wlr_xdg_surface *parent = wlr_xdg_surface_try_from_wlr_surface(p->parent);
	if (!parent || !parent->data) return;
	make_popup(p, parent->data);
}

/* XWayland */

static void xw_associate(struct wl_listener *l, void *d) {
	struct view *v = wl_container_of(l, v, xw_associate);
	v->surface_listening = true;
	LISTEN(v->xw->surface->events.map, &v->map, view_map);
	LISTEN(v->xw->surface->events.unmap, &v->unmap, view_unmap);
	v->content = wlr_scene_subsurface_tree_create(v->tree, v->xw->surface);
	wl_list_init(&v->commit.link); /* no commit handler for X11 views */
}
static void xw_dissociate(struct wl_listener *l, void *d) {
	struct view *v = wl_container_of(l, v, xw_dissociate);
	if (!v->surface_listening) return;
	UNLISTEN(&v->map); UNLISTEN(&v->unmap);
	v->surface_listening = false;
	if (v->content) { wlr_scene_node_destroy(&v->content->node); v->content = NULL; }
}
static void xw_request_configure(struct wl_listener *l, void *d) {
	struct view *v = wl_container_of(l, v, xw_request_configure);
	struct wlr_xwayland_surface_configure_event *e = d;
	if (!v->mapped || v->unmanaged) { wlr_xwayland_surface_configure(v->xw, e->x, e->y, e->width, e->height); return; }
	/* managed windows keep their place; only the size request is honoured */
	wlr_xwayland_surface_configure(v->xw, v->x, v->y, e->width, e->height);
}
static void xw_override_changed(struct wl_listener *l, void *d) {
	struct view *v = wl_container_of(l, v, xw_override);
	v->unmanaged = v->xw->override_redirect;
}

static void new_xwayland_surface(struct wl_listener *l, void *data) {
	struct server *s = wl_container_of(l, s, new_xwayland_surface);
	struct wlr_xwayland_surface *x = data;
	struct view *v = make_view(s);
	v->is_x11 = true; v->xw = x;
	v->unmanaged = x->override_redirect;
	v->x = x->x; v->y = x->y;
	/* these are live from creation; the surface listeners are added on associate */
	wl_list_init(&v->map.link); wl_list_init(&v->unmap.link); wl_list_init(&v->commit.link);
	LISTEN(x->events.destroy, &v->destroy, view_destroy);
	LISTEN(x->events.associate, &v->xw_associate, xw_associate);
	LISTEN(x->events.dissociate, &v->xw_dissociate, xw_dissociate);
	LISTEN(x->events.request_configure, &v->xw_request_configure, xw_request_configure);
	LISTEN(x->events.set_title, &v->set_title, view_set_title);
	LISTEN(x->events.set_class, &v->set_app_id, view_set_app_id);
	LISTEN(x->events.set_override_redirect, &v->xw_override, xw_override_changed);
}

static void xwayland_ready(struct wl_listener *l, void *data) {
	struct server *s = wl_container_of(l, s, xwayland_ready);
	wlr_xwayland_set_seat(s->xwayland, s->seat);
	struct wlr_xcursor *xc = wlr_xcursor_manager_get_xcursor(s->xcursor, "default", 1);
	if (xc && xc->image_count > 0) {
		struct wlr_xcursor_image *im = xc->images[0];
		wlr_xwayland_set_cursor(s->xwayland, im->buffer, im->width * 4, im->width, im->height, im->hotspot_x, im->hotspot_y);
	}
	wlr_log(WLR_INFO, "XWayland ready on %s", s->xwayland->display_name);
}

/* ---------- decorations, activation, tearing, idle ---------- */

static void deco_mode(struct wl_listener *l, void *d) {
	struct deco *dc = wl_container_of(l, dc, mode);
	if (dc->wlr->toplevel->base->initialized)
		wlr_xdg_toplevel_decoration_v1_set_mode(dc->wlr, WLR_XDG_TOPLEVEL_DECORATION_V1_MODE_SERVER_SIDE);
}
static void deco_commit(struct wl_listener *l, void *d) {
	struct deco *dc = wl_container_of(l, dc, commit);
	if (!dc->wlr->toplevel->base->initial_commit) return;
	UNLISTEN(&dc->commit); dc->waiting = false;
	wlr_xdg_toplevel_decoration_v1_set_mode(dc->wlr, WLR_XDG_TOPLEVEL_DECORATION_V1_MODE_SERVER_SIDE);
}
static void deco_destroy(struct wl_listener *l, void *d) {
	struct deco *dc = wl_container_of(l, dc, destroy);
	if (dc->waiting) UNLISTEN(&dc->commit);
	UNLISTEN(&dc->mode); UNLISTEN(&dc->destroy); free(dc);
}
/* Server side means "the compositor draws the frame"; the Spark compositor draws none yet, which
 * is what Qt, GTK4 and games without their own frame expect to see answered. */
static void new_deco(struct wl_listener *l, void *data) {
	struct wlr_xdg_toplevel_decoration_v1 *w = data;
	struct deco *dc = calloc(1, sizeof *dc);
	dc->wlr = w;
	LISTEN(w->events.request_mode, &dc->mode, deco_mode);
	LISTEN(w->events.destroy, &dc->destroy, deco_destroy);
	if (w->toplevel->base->initialized) deco_mode(&dc->mode, NULL);
	else { dc->waiting = true; LISTEN(w->toplevel->base->surface->events.commit, &dc->commit, deco_commit); }
}

static void activate_request(struct wl_listener *l, void *data) {
	struct server *s = wl_container_of(l, s, activate);
	struct wlr_xdg_activation_v1_request_activate_event *e = data;
	struct view *v;
	wl_list_for_each(v, &s->views, link)
		if (v->mapped && view_surface(v) == e->surface) { if (!s->locked) focus_view(v, NULL); return; }
}

static void tearing_destroy(struct wl_listener *l, void *d) {
	struct tearing_ref *t = wl_container_of(l, t, destroy);
	struct view *v;
	wl_list_for_each(v, &S.views, link) if (v->tearing_obj == t->obj) v->tearing_obj = NULL;
	UNLISTEN(&t->destroy); free(t);
}
static void tearing_new(struct wl_listener *l, void *data) {
	struct server *s = wl_container_of(l, s, tearing_new);
	struct wlr_tearing_control_v1 *obj = data;
	struct tearing_ref *t = calloc(1, sizeof *t);
	t->obj = obj;
	LISTEN(obj->events.destroy, &t->destroy, tearing_destroy);
	/* tie the object to its window when the surface is a view */
	struct view *v;
	wl_list_for_each(v, &s->views, link) if (view_surface(v) == obj->surface) v->tearing_obj = obj;
}

static void inhibitor_destroy(struct wl_listener *l, void *d) {
	struct inhibitor_ref *r = wl_container_of(l, r, destroy);
	r->server->inhibitors--;
	wlr_idle_notifier_v1_set_inhibited(r->server->idle, r->server->inhibitors > 0);
	UNLISTEN(&r->destroy); free(r);
}
static void new_inhibitor(struct wl_listener *l, void *data) {
	struct server *s = wl_container_of(l, s, new_inhibitor);
	struct wlr_idle_inhibitor_v1 *in = data;
	struct inhibitor_ref *r = calloc(1, sizeof *r);
	r->server = s;
	LISTEN(in->events.destroy, &r->destroy, inhibitor_destroy);
	s->inhibitors++;
	wlr_idle_notifier_v1_set_inhibited(s->idle, true);
}

/* ---------- session lock ---------- */

static void lock_surface_destroy(struct wl_listener *l, void *d) {
	struct lock_surface *ls = wl_container_of(l, ls, destroy);
	if (ls->server->lock_focus == ls->wlr->surface) { ls->server->lock_focus = NULL; focus_layer_or_view(ls->server); }
	UNLISTEN(&ls->destroy); free(ls);
}

static void lock_new_surface(struct wl_listener *l, void *data) {
	struct server *s = &S;
	struct wlr_session_lock_surface_v1 *w = data;
	struct lock_surface *ls = calloc(1, sizeof *ls);
	ls->wlr = w; ls->server = s;
	struct output *o = w->output ? output_of(s, w->output) : NULL;
	if (o) {
		struct wlr_box b; wlr_output_layout_get_box(s->output_layout, o->wlr_output, &b);
		struct wlr_scene_tree *t = wlr_scene_subsurface_tree_create(s->lock_tree, w->surface);
		wlr_scene_node_set_position(&t->node, b.x, b.y);
		wlr_session_lock_surface_v1_configure(w, b.width, b.height);
	}
	LISTEN(w->events.destroy, &ls->destroy, lock_surface_destroy);
	if (!s->lock_focus) { s->lock_focus = w->surface; focus_layer_or_view(s); }
	/* tell the client it is locked once every output has a lock surface */
	int surfaces = 0, outs = wl_list_length(&s->outputs);
	struct wlr_session_lock_surface_v1 *x;
	wl_list_for_each(x, &s->lock->surfaces, link) surfaces++;
	if (surfaces >= outs) { wlr_session_lock_v1_send_locked(s->lock); wlr_log(WLR_INFO, "session locked"); }
}

static void lock_unlock(struct wl_listener *l, void *d) {
	struct server *s = &S;
	wlr_log(WLR_INFO, "session unlocked");
	s->locked = false;
	s->lock_focus = NULL;
	if (s->lock_rect) { wlr_scene_node_destroy(&s->lock_rect->node); s->lock_rect = NULL; }
	if (s->lock_tree) { wlr_scene_node_destroy(&s->lock_tree->node); s->lock_tree = NULL; }
	s->lock = NULL;
	focus_layer_or_view(s);
	update_cursor_focus(s, 0);
}

static struct wl_listener lock_new_surface_l, lock_unlock_l, lock_destroy_l;
static void lock_destroy(struct wl_listener *l, void *d) {
	/* a lock client that dies leaves the session locked (black) until a new lock client unlocks */
	struct server *s = &S;
	UNLISTEN(&lock_new_surface_l); UNLISTEN(&lock_unlock_l); UNLISTEN(&lock_destroy_l);
	s->lock = NULL;
	s->lock_focus = NULL;
	if (s->lock_tree) wlr_scene_node_destroy(&s->lock_tree->node);
	s->lock_tree = wlr_scene_tree_create(s->layers[L_LOCK]);
}

static void new_lock(struct wl_listener *l, void *data) {
	struct server *s = wl_container_of(l, s, new_lock);
	struct wlr_session_lock_v1 *lock = data;
	if (s->lock) { wlr_session_lock_v1_destroy(lock); return; }
	s->lock = lock;
	if (!s->locked) {
		s->lock_tree = wlr_scene_tree_create(s->layers[L_LOCK]);
		float black[4] = {0, 0, 0, 1};
		s->lock_rect = wlr_scene_rect_create(s->layers[L_LOCK], 100000, 100000, black);
		wlr_scene_node_lower_to_bottom(&s->lock_rect->node);
		wlr_scene_node_set_position(&s->lock_rect->node, -50000, -50000);
	}
	s->locked = true;
	s->focused_layer = NULL;
	if (s->lock_tree) wlr_scene_node_raise_to_top(&s->lock_tree->node);
	LISTEN(lock->events.new_surface, &lock_new_surface_l, lock_new_surface);
	LISTEN(lock->events.unlock, &lock_unlock_l, lock_unlock);
	LISTEN(lock->events.destroy, &lock_destroy_l, lock_destroy);
	if (wl_list_empty(&s->outputs)) wlr_session_lock_v1_send_locked(lock);
}

/* ---------- input ---------- */

static void notify_activity(struct server *s) { wlr_idle_notifier_v1_notify_activity(s->idle, s->seat); }

static struct view *view_from_node(struct wlr_scene_node *node) {
	for (struct wlr_scene_tree *t = node->parent; t; t = t->node.parent)
		if (t->node.data) return t->node.data;
	if (node->data) return node->data;
	return NULL;
}

/* What is under the cursor. While locked, only the lock tree counts. */
static struct view *pick(struct server *s, double lx, double ly, struct wlr_surface **surf, double *sx, double *sy) {
	*surf = NULL;
	struct wlr_scene_node *root = s->locked && s->lock_tree ? &s->lock_tree->node : &s->scene->tree.node;
	double nx, ny;
	struct wlr_scene_node *n = wlr_scene_node_at(root, lx, ly, &nx, &ny);
	if (!n || n->type != WLR_SCENE_NODE_BUFFER) return NULL;
	struct wlr_scene_buffer *sb = wlr_scene_buffer_from_node(n);
	struct wlr_scene_surface *ss = wlr_scene_surface_try_from_buffer(sb);
	if (!ss) return NULL;
	*surf = ss->surface; *sx = nx; *sy = ny;
	return s->locked ? NULL : view_from_node(n);
}

static void set_cursor_name(struct server *s, const char *name) {
	wlr_cursor_set_xcursor(s->cursor, s->xcursor, name);
}

static void check_constraint(struct server *s, struct wlr_surface *focus) {
	struct wlr_pointer_constraint_v1 *c = focus ? wlr_pointer_constraints_v1_constraint_for_surface(s->constraints, focus, s->seat) : NULL;
	if (c == s->active_constraint) return;
	if (s->active_constraint) wlr_pointer_constraint_v1_send_deactivated(s->active_constraint);
	s->active_constraint = c;
	if (c) wlr_pointer_constraint_v1_send_activated(c);
}

static void update_cursor_focus(struct server *s, uint32_t time) {
	if (s->cursor_mode == CURSOR_MOVE && s->grab_view) {
		view_place(s->grab_view, s->cursor->x - s->grab_x, s->cursor->y - s->grab_y);
		return;
	}
	if (s->cursor_mode == CURSOR_RESIZE && s->grab_view) {
		struct view *v = s->grab_view;
		double dx = s->cursor->x - s->grab_x, dy = s->cursor->y - s->grab_y;
		struct wlr_box nb = s->grab_box;
		if (s->resize_edges & WLR_EDGE_TOP) { nb.y += dy; nb.height -= dy; }
		else if (s->resize_edges & WLR_EDGE_BOTTOM) nb.height += dy;
		if (s->resize_edges & WLR_EDGE_LEFT) { nb.x += dx; nb.width -= dx; }
		else if (s->resize_edges & WLR_EDGE_RIGHT) nb.width += dx;
		if (nb.width < 40 || nb.height < 30) return;
		view_place(v, nb.x, nb.y);
		view_resize(v, nb.width, nb.height);
		return;
	}
	struct wlr_surface *surf; double sx, sy;
	struct view *v = pick(s, s->cursor->x, s->cursor->y, &surf, &sx, &sy);
	(void)v;
	if (!surf) {
		set_cursor_name(s, "default");
		wlr_seat_pointer_clear_focus(s->seat);
		check_constraint(s, NULL);
		return;
	}
	wlr_seat_pointer_notify_enter(s->seat, surf, sx, sy);
	wlr_seat_pointer_notify_motion(s->seat, time, sx, sy);
	check_constraint(s, surf);
}

static void process_motion(struct server *s, uint32_t time, struct wlr_input_device *dev,
		double dx, double dy, double dx_u, double dy_u) {
	notify_activity(s);
	wlr_relative_pointer_manager_v1_send_relative_motion(s->relative, s->seat, (uint64_t)time * 1000, dx, dy, dx_u, dy_u);
	if (s->active_constraint && s->active_constraint->surface == s->seat->pointer_state.focused_surface) {
		/* a locked or confined pointer (games, remote desktop): relative motion only */
		return;
	}
	if (dev) wlr_cursor_move(s->cursor, dev, dx, dy);
	update_cursor_focus(s, time);
	struct wlr_output *wo = wlr_output_layout_output_at(s->output_layout, s->cursor->x, s->cursor->y);
	if (wo) s->focused_output = wo;
}

static void cursor_motion(struct wl_listener *l, void *data) {
	struct server *s = wl_container_of(l, s, cursor_motion);
	struct wlr_pointer_motion_event *e = data;
	process_motion(s, e->time_msec, &e->pointer->base, e->delta_x, e->delta_y, e->unaccel_dx, e->unaccel_dy);
}
static void cursor_motion_abs(struct wl_listener *l, void *data) {
	struct server *s = wl_container_of(l, s, cursor_motion_abs);
	struct wlr_pointer_motion_absolute_event *e = data;
	notify_activity(s);
	wlr_cursor_warp_absolute(s->cursor, &e->pointer->base, e->x, e->y);
	update_cursor_focus(s, e->time_msec);
}

static uint32_t mods_of(struct server *s) {
	struct wlr_keyboard *kb = wlr_seat_get_keyboard(s->seat);
	return kb ? wlr_keyboard_get_modifiers(kb) : 0;
}

static void cursor_button(struct wl_listener *l, void *data) {
	struct server *s = wl_container_of(l, s, cursor_button);
	struct wlr_pointer_button_event *e = data;
	notify_activity(s);
	if (e->state == WL_POINTER_BUTTON_STATE_RELEASED && s->cursor_mode != CURSOR_PASSTHROUGH) {
		s->cursor_mode = CURSOR_PASSTHROUGH; s->grab_view = NULL;
		wlr_seat_pointer_notify_button(s->seat, e->time_msec, e->button, e->state);
		update_cursor_focus(s, e->time_msec);
		return;
	}
	struct wlr_surface *surf; double sx, sy;
	struct view *v = pick(s, s->cursor->x, s->cursor->y, &surf, &sx, &sy);
	if (e->state == WL_POINTER_BUTTON_STATE_PRESSED && !s->locked) {
		if (v && (mods_of(s) & WLR_MODIFIER_LOGO) && (e->button == BTN_LEFT || e->button == BTN_RIGHT)) {
			focus_view(v, surf);
			if (e->button == BTN_LEFT) begin_grab(s, v, CURSOR_MOVE, 0);
			else {
				struct wlr_box b; view_box(v, &b);
				uint32_t edges = (s->cursor->x < v->x + b.width / 2 ? WLR_EDGE_LEFT : WLR_EDGE_RIGHT) |
					(s->cursor->y < v->y + b.height / 2 ? WLR_EDGE_TOP : WLR_EDGE_BOTTOM);
				begin_grab(s, v, CURSOR_RESIZE, edges);
			}
			return; /* the window does not see the click */
		}
		if (v) focus_view(v, surf);
		else if (surf) {
			/* a layer surface that takes keyboard focus on click (on-demand) */
			struct layer_surface *ls;
			wl_list_for_each(ls, &s->layer_surfaces, link)
				if (ls->wlr->surface == wlr_surface_get_root_surface(surf) &&
				    ls->wlr->current.keyboard_interactive != ZWLR_LAYER_SURFACE_V1_KEYBOARD_INTERACTIVITY_NONE) {
					s->focused_layer = ls; focus_layer_or_view(s);
				}
		}
	}
	wlr_seat_pointer_notify_button(s->seat, e->time_msec, e->button, e->state);
}
static void cursor_axis(struct wl_listener *l, void *data) {
	struct server *s = wl_container_of(l, s, cursor_axis);
	struct wlr_pointer_axis_event *e = data;
	notify_activity(s);
	wlr_seat_pointer_notify_axis(s->seat, e->time_msec, e->orientation, e->delta, e->delta_discrete,
		e->source, e->relative_direction);
}
static void cursor_frame(struct wl_listener *l, void *data) {
	struct server *s = wl_container_of(l, s, cursor_frame);
	wlr_seat_pointer_notify_frame(s->seat);
}

static void request_set_cursor(struct wl_listener *l, void *data) {
	struct server *s = wl_container_of(l, s, request_set_cursor);
	struct wlr_seat_pointer_request_set_cursor_event *e = data;
	if (s->seat->pointer_state.focused_client == e->seat_client)
		wlr_cursor_set_surface(s->cursor, e->surface, e->hotspot_x, e->hotspot_y);
}
static void cursor_shape_request(struct wl_listener *l, void *data) {
	struct server *s = wl_container_of(l, s, cursor_shape);
	struct wlr_cursor_shape_manager_v1_request_set_shape_event *e = data;
	if (e->device_type != WLR_CURSOR_SHAPE_MANAGER_V1_DEVICE_TYPE_POINTER) return;
	if (s->seat->pointer_state.focused_client == e->seat_client)
		wlr_cursor_set_xcursor(s->cursor, s->xcursor, wlr_cursor_shape_v1_name(e->shape));
}
static void request_set_selection(struct wl_listener *l, void *data) {
	struct server *s = wl_container_of(l, s, request_set_selection);
	struct wlr_seat_request_set_selection_event *e = data;
	wlr_seat_set_selection(s->seat, e->source, e->serial);
}
static void request_set_primary(struct wl_listener *l, void *data) {
	struct server *s = wl_container_of(l, s, request_set_primary);
	struct wlr_seat_request_set_primary_selection_event *e = data;
	wlr_seat_set_primary_selection(s->seat, e->source, e->serial);
}

static void new_constraint(struct wl_listener *l, void *data) {
	struct server *s = wl_container_of(l, s, new_constraint);
	struct wlr_pointer_constraint_v1 *c = data;
	if (s->seat->pointer_state.focused_surface == c->surface) check_constraint(s, c->surface);
}

static bool run_action(struct server *s, struct bind *b);

static bool handle_key(struct server *s, struct keyboard *k, uint32_t keycode, enum wl_keyboard_key_state st) {
	if (st == WL_KEYBOARD_KEY_STATE_RELEASED) {
		for (int i = 0; i < k->nhandled; i++)
			if (k->handled[i] == keycode) { k->handled[i] = k->handled[--k->nhandled]; return true; }
		return false;
	}
	const xkb_keysym_t *syms;
	int n = xkb_state_key_get_syms(k->wlr->xkb_state, keycode + 8, &syms);
	uint32_t mods = wlr_keyboard_get_modifiers(k->wlr);
	for (int i = 0; i < n; i++) {
		/* VT switch works even while locked */
		if (syms[i] >= XKB_KEY_XF86Switch_VT_1 && syms[i] <= XKB_KEY_XF86Switch_VT_12) {
			if (s->session) wlr_session_change_vt(s->session, syms[i] - XKB_KEY_XF86Switch_VT_1 + 1);
			return true;
		}
	}
	if (s->locked) return false;
	for (int i = 0; i < n; i++) {
		xkb_keysym_t sym = xkb_keysym_to_lower(syms[i]);
		struct bind *b;
		wl_list_for_each(b, &s->binds, link) {
			if (b->sym != sym || b->mods != (mods & (WLR_MODIFIER_LOGO | WLR_MODIFIER_ALT | WLR_MODIFIER_CTRL | WLR_MODIFIER_SHIFT))) continue;
			if (!run_action(s, b)) continue;
			if (k->nhandled < 16) k->handled[k->nhandled++] = keycode;
			return true;
		}
	}
	return false;
}

static void kb_modifiers(struct wl_listener *l, void *d) {
	struct keyboard *k = wl_container_of(l, k, modifiers);
	wlr_seat_set_keyboard(k->server->seat, k->wlr);
	wlr_seat_keyboard_notify_modifiers(k->server->seat, &k->wlr->modifiers);
}
static void kb_key(struct wl_listener *l, void *data) {
	struct keyboard *k = wl_container_of(l, k, key);
	struct server *s = k->server;
	struct wlr_keyboard_key_event *e = data;
	notify_activity(s);
	if (handle_key(s, k, e->keycode, e->state)) return;
	wlr_seat_set_keyboard(s->seat, k->wlr);
	wlr_seat_keyboard_notify_key(s->seat, e->time_msec, e->keycode, e->state);
}
static void kb_destroy(struct wl_listener *l, void *d) {
	struct keyboard *k = wl_container_of(l, k, destroy);
	UNLISTEN(&k->modifiers); UNLISTEN(&k->key); UNLISTEN(&k->destroy);
	wl_list_remove(&k->link); free(k);
}

static void add_keyboard(struct server *s, struct wlr_keyboard *kb) {
	struct xkb_context *ctx = xkb_context_new(XKB_CONTEXT_NO_FLAGS);
	struct xkb_rule_names names = {0}; /* XKB_DEFAULT_* environment variables apply */
	struct xkb_keymap *km = xkb_keymap_new_from_names(ctx, &names, XKB_KEYMAP_COMPILE_NO_FLAGS);
	wlr_keyboard_set_keymap(kb, km);
	xkb_keymap_unref(km); xkb_context_unref(ctx);
	wlr_keyboard_set_repeat_info(kb, 25, 600);
	struct keyboard *k = calloc(1, sizeof *k);
	k->server = s; k->wlr = kb;
	LISTEN(kb->events.modifiers, &k->modifiers, kb_modifiers);
	LISTEN(kb->events.key, &k->key, kb_key);
	LISTEN(kb->base.events.destroy, &k->destroy, kb_destroy);
	wlr_seat_set_keyboard(s->seat, kb);
	wl_list_insert(&s->keyboards, &k->link);
}

static void update_caps(struct server *s) {
	uint32_t caps = WL_SEAT_CAPABILITY_POINTER;
	if (!wl_list_empty(&s->keyboards)) caps |= WL_SEAT_CAPABILITY_KEYBOARD;
	wlr_seat_set_capabilities(s->seat, caps);
}

static void new_input(struct wl_listener *l, void *data) {
	struct server *s = wl_container_of(l, s, new_input);
	struct wlr_input_device *d = data;
	if (d->type == WLR_INPUT_DEVICE_KEYBOARD) add_keyboard(s, wlr_keyboard_from_input_device(d));
	else if (d->type == WLR_INPUT_DEVICE_POINTER) wlr_cursor_attach_input_device(s->cursor, d);
	update_caps(s);
}
static void new_vkb(struct wl_listener *l, void *data) {
	struct server *s = wl_container_of(l, s, new_vkb);
	struct wlr_virtual_keyboard_v1 *vk = data;
	add_keyboard(s, &vk->keyboard);
	update_caps(s);
}
static void new_vptr(struct wl_listener *l, void *data) {
	struct server *s = wl_container_of(l, s, new_vptr);
	struct wlr_virtual_pointer_v1_new_pointer_event *e = data;
	wlr_cursor_attach_input_device(s->cursor, &e->new_pointer->pointer.base);
}

/* ---------- actions ---------- */

static bool run_action(struct server *s, struct bind *b) {
	switch (b->action) {
	case A_EXEC: if (b->arg) spawn(b->arg); return true;
	case A_CLOSE: if (s->focused_view) { view_close(s->focused_view); return true; } return false;
	case A_QUIT: wl_display_terminate(s->display); return true;
	case A_FOCUS_NEXT: { struct view *n = next_view(s); if (n) { focus_view(n, NULL); return true; } return false; }
	case A_FULLSCREEN: if (s->focused_view) { view_set_fullscreen(s->focused_view, !s->focused_view->fullscreen); return true; } return false;
	case A_MAXIMIZE: if (s->focused_view) { view_set_maximized(s->focused_view, !s->focused_view->maximized); return true; } return false;
	case A_OUTPUT_NEXT: {
		if (!s->focused_view) return false;
		struct wlr_output *cur = view_output(s->focused_view);
		struct wlr_output *nxt = wlr_output_layout_adjacent_output(s->output_layout, WLR_DIRECTION_RIGHT, cur, 0, 0);
		if (!nxt) nxt = wlr_output_layout_adjacent_output(s->output_layout, WLR_DIRECTION_LEFT, cur, 0, 0);
		if (!nxt || nxt == cur) return false;
		struct wlr_box a, bb; wlr_output_layout_get_box(s->output_layout, cur, &a); wlr_output_layout_get_box(s->output_layout, nxt, &bb);
		view_place(s->focused_view, s->focused_view->x - a.x + bb.x, s->focused_view->y - a.y + bb.y);
		return true;
	}
	case A_RELOAD: free_config(s); set_default_binds(s); load_config(s); return true;
	}
	return false;
}

/* ---------- main ---------- */

static int on_signal(int sig, void *data) { wl_display_terminate(S.display); return 0; }

int main(int argc, char **argv) {
	const char *startup = NULL;
	int c;
	while ((c = getopt(argc, argv, "s:dh")) != -1) {
		if (c == 's') startup = optarg;
		else if (c == 'd') wlr_log_init(WLR_DEBUG, NULL);
		else { fprintf(stderr, "usage: %s [-s startup-command] [-d]\n", argv[0]); return c == 'h' ? 0 : 1; }
	}
	if (!getenv("WLR_LOG_INIT")) wlr_log_init(WLR_INFO, NULL);
	signal(SIGPIPE, SIG_IGN);

	struct server *s = &S;
	wl_list_init(&s->outputs); wl_list_init(&s->views); wl_list_init(&s->layer_surfaces);
	wl_list_init(&s->out_cfgs); wl_list_init(&s->binds); wl_list_init(&s->keyboards);
	set_default_binds(s);
	load_config(s);

	s->display = wl_display_create();
	s->loop = wl_display_get_event_loop(s->display);
	wl_event_loop_add_signal(s->loop, SIGINT, on_signal, NULL);
	wl_event_loop_add_signal(s->loop, SIGTERM, on_signal, NULL);

	const char *hl = getenv("SPARK_HEADLESS_OUTPUTS");
	if (hl) s->backend = wlr_headless_backend_create(s->loop);
	else s->backend = wlr_backend_autocreate(s->loop, &s->session);
	if (!s->backend) { wlr_log(WLR_ERROR, "no backend"); return 1; }
	s->renderer = wlr_renderer_autocreate(s->backend);
	if (!s->renderer) { wlr_log(WLR_ERROR, "no renderer"); return 1; }
	wlr_renderer_init_wl_display(s->renderer, s->display);
	s->allocator = wlr_allocator_autocreate(s->backend, s->renderer);
	if (!s->allocator) { wlr_log(WLR_ERROR, "no allocator"); return 1; }

	s->compositor = wlr_compositor_create(s->display, 6, s->renderer);
	wlr_subcompositor_create(s->display);
	wlr_data_device_manager_create(s->display);
	s->output_layout = wlr_output_layout_create(s->display);
	s->scene = wlr_scene_create();
	s->scene_layout = wlr_scene_attach_output_layout(s->scene, s->output_layout);
	for (int i = 0; i < L_COUNT; i++) s->layers[i] = wlr_scene_tree_create(&s->scene->tree);

	/* windows and shells */
	s->xdg_shell = wlr_xdg_shell_create(s->display, 6);
	s->new_xdg_toplevel.notify = new_xdg_toplevel; wl_signal_add(&s->xdg_shell->events.new_toplevel, &s->new_xdg_toplevel);
	s->new_xdg_popup.notify = new_xdg_popup; wl_signal_add(&s->xdg_shell->events.new_popup, &s->new_xdg_popup);
	s->layer_shell = wlr_layer_shell_v1_create(s->display, 4);
	LISTEN(s->layer_shell->events.new_surface, &s->new_layer_surface, new_layer_surface);
	struct wlr_xdg_decoration_manager_v1 *deco = wlr_xdg_decoration_manager_v1_create(s->display);
	LISTEN(deco->events.new_toplevel_decoration, &s->new_deco, new_deco);
	s->lock_mgr = wlr_session_lock_manager_v1_create(s->display);
	LISTEN(s->lock_mgr->events.new_lock, &s->new_lock, new_lock);

	/* what a shell, a task list and screen capture ask for */
	s->ftl_mgr = wlr_foreign_toplevel_manager_v1_create(s->display);
	s->ext_ftl = wlr_ext_foreign_toplevel_list_v1_create(s->display, 1);
	s->idle = wlr_idle_notifier_v1_create(s->display);
	s->idle_inhibit = wlr_idle_inhibit_v1_create(s->display);
	LISTEN(s->idle_inhibit->events.new_inhibitor, &s->new_inhibitor, new_inhibitor);
	s->activation = wlr_xdg_activation_v1_create(s->display);
	LISTEN(s->activation->events.request_activate, &s->activate, activate_request);
	wlr_fractional_scale_manager_v1_create(s->display, 1);
	wlr_viewporter_create(s->display);
	wlr_single_pixel_buffer_manager_v1_create(s->display);
	wlr_presentation_create(s->display, s->backend, 2);
	wlr_xdg_output_manager_v1_create(s->display, s->output_layout);
	wlr_alpha_modifier_v1_create(s->display);
	wlr_content_type_manager_v1_create(s->display, 1);
	wlr_primary_selection_v1_device_manager_create(s->display);
	wlr_data_control_manager_v1_create(s->display);
	wlr_ext_data_control_manager_v1_create(s->display, 1);
	wlr_screencopy_manager_v1_create(s->display);
	wlr_export_dmabuf_manager_v1_create(s->display);
	wlr_ext_output_image_capture_source_manager_v1_create(s->display, 1);
	wlr_ext_image_copy_capture_manager_v1_create(s->display, 1);
	struct wlr_gamma_control_manager_v1 *gamma = wlr_gamma_control_manager_v1_create(s->display);
	wlr_scene_set_gamma_control_manager_v1(s->scene, gamma);
	wlr_output_power_manager_v1_create(s->display);
	s->output_mgr = wlr_output_manager_v1_create(s->display);
	LISTEN(s->output_mgr->events.apply, &s->output_apply, output_config_apply);
	LISTEN(s->output_mgr->events.test, &s->output_test, output_config_test);
	LISTEN(s->output_layout->events.change, &s->layout_change, layout_changed);
	s->tearing = wlr_tearing_control_manager_v1_create(s->display, 1);
	LISTEN(s->tearing->events.new_object, &s->tearing_new, tearing_new);
	s->constraints = wlr_pointer_constraints_v1_create(s->display);
	LISTEN(s->constraints->events.new_constraint, &s->new_constraint, new_constraint);
	s->relative = wlr_relative_pointer_manager_v1_create(s->display);
	struct wlr_virtual_keyboard_manager_v1 *vk = wlr_virtual_keyboard_manager_v1_create(s->display);
	LISTEN(vk->events.new_virtual_keyboard, &s->new_vkb, new_vkb);
	struct wlr_virtual_pointer_manager_v1 *vp = wlr_virtual_pointer_manager_v1_create(s->display);
	LISTEN(vp->events.new_virtual_pointer, &s->new_vptr, new_vptr);
	if (wlr_renderer_get_texture_formats(s->renderer, WLR_BUFFER_CAP_DMABUF)) wlr_linux_dmabuf_v1_create_with_renderer(s->display, 5, s->renderer);

	/* seat and cursor */
	s->seat = wlr_seat_create(s->display, "seat0");
	s->cursor = wlr_cursor_create();
	wlr_cursor_attach_output_layout(s->cursor, s->output_layout);
	s->xcursor = wlr_xcursor_manager_create(NULL, 24);
	LISTEN(s->cursor->events.motion, &s->cursor_motion, cursor_motion);
	LISTEN(s->cursor->events.motion_absolute, &s->cursor_motion_abs, cursor_motion_abs);
	LISTEN(s->cursor->events.button, &s->cursor_button, cursor_button);
	LISTEN(s->cursor->events.axis, &s->cursor_axis, cursor_axis);
	LISTEN(s->cursor->events.frame, &s->cursor_frame, cursor_frame);
	LISTEN(s->seat->events.request_set_cursor, &s->request_set_cursor, request_set_cursor);
	LISTEN(s->seat->events.request_set_selection, &s->request_set_selection, request_set_selection);
	LISTEN(s->seat->events.request_set_primary_selection, &s->request_set_primary, request_set_primary);
	struct wlr_cursor_shape_manager_v1 *shape = wlr_cursor_shape_manager_v1_create(s->display, 1);
	LISTEN(shape->events.request_set_shape, &s->cursor_shape, cursor_shape_request);
	LISTEN(s->backend->events.new_input, &s->new_input, new_input);
	LISTEN(s->backend->events.new_output, &s->new_output, new_output);
	update_caps(s);

	/* XWayland, started when the first X11 client connects */
	s->xwayland = wlr_xwayland_create(s->display, s->compositor, true);
	if (s->xwayland) {
		LISTEN(s->xwayland->events.new_surface, &s->new_xwayland_surface, new_xwayland_surface);
		LISTEN(s->xwayland->events.ready, &s->xwayland_ready, xwayland_ready);
		setenv("DISPLAY", s->xwayland->display_name, true);
	}

	const char *sock = wl_display_add_socket_auto(s->display);
	if (!sock) { wlr_log(WLR_ERROR, "no socket"); return 1; }
	if (!wlr_backend_start(s->backend)) { wlr_log(WLR_ERROR, "backend failed to start"); return 1; }

	if (hl) {
		int n = atoi(hl);
		for (int i = 0; i < n && i < 8; i++) wlr_headless_add_output(s->backend, 1920, 1080);
	}
	setenv("WAYLAND_DISPLAY", sock, true);
	setenv("XDG_SESSION_TYPE", "wayland", true);
	printf("WAYLAND_DISPLAY=%s\n", sock);
	if (s->xwayland) printf("DISPLAY=%s\n", s->xwayland->display_name);
	fflush(stdout);
	wlr_log(WLR_INFO, "spark-compositor running on %s", sock);
	if (startup) spawn(startup);

	wl_display_run(s->display);

	wl_display_destroy_clients(s->display);
	/* wlroots asserts that nothing still listens to an object's signals when it is destroyed:
	 * take every server-wide listener off first (a crash here is one core dump per logout) */
	struct wl_listener *server_listeners[] = {
		&s->new_xdg_toplevel, &s->new_xdg_popup, &s->new_layer_surface, &s->new_lock,
		&s->new_inhibitor, &s->activate, &s->output_apply, &s->output_test, &s->layout_change,
		&s->tearing_new, &s->new_constraint, &s->cursor_motion, &s->cursor_motion_abs,
		&s->cursor_button, &s->cursor_axis, &s->cursor_frame, &s->request_set_cursor,
		&s->request_set_selection, &s->request_set_primary, &s->new_input, &s->new_output,
		&s->new_deco, &s->new_vkb, &s->new_vptr, &s->cursor_shape,
	};
	for (size_t i = 0; i < sizeof server_listeners / sizeof *server_listeners; i++)
		UNLISTEN(server_listeners[i]);
	if (s->xwayland) {
		UNLISTEN(&s->new_xwayland_surface);
		UNLISTEN(&s->xwayland_ready);
		wlr_xwayland_destroy(s->xwayland);
	}
	wlr_scene_node_destroy(&s->scene->tree.node);
	wlr_xcursor_manager_destroy(s->xcursor);
	wlr_output_layout_destroy(s->output_layout);
	wlr_cursor_destroy(s->cursor);
	wlr_allocator_destroy(s->allocator);
	wlr_renderer_destroy(s->renderer);
	wlr_backend_destroy(s->backend);
	wl_display_destroy(s->display);
	free_config(s);
	return 0;
}
