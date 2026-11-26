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
#include <stdarg.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#include <linux/input-event-codes.h>
#include <cairo.h>
#include <wlr/interfaces/wlr_buffer.h>
#include <drm_fourcc.h>
#include <pango/pangocairo.h>
#include <librsvg/rsvg.h>
#include <dirent.h>
#include <strings.h>
#include <wayland-server-core.h>
#include <wlr/backend.h>
#include <wlr/backend/headless.h>
#include <wlr/backend/multi.h>
#include <wlr/backend/session.h>
#include <wlr/backend/libinput.h>
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
#include <wlr/interfaces/wlr_ext_image_capture_source_v1.h>
#include <wlr/render/swapchain.h>
#include <wlr/util/addon.h>
#include "ext-image-capture-source-v1-protocol.h"
#include <wlr/types/wlr_ext_image_copy_capture_v1.h>
#include <wlr/types/wlr_foreign_toplevel_management_v1.h>
#include <wlr/types/wlr_fractional_scale_v1.h>
#include <wlr/types/wlr_gamma_control_v1.h>
#include <wlr/types/wlr_idle_inhibit_v1.h>
#include <wlr/types/wlr_idle_notify_v1.h>
#include <wlr/types/wlr_keyboard.h>
#include <wlr/types/wlr_color_management_v1.h>
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
#include <wlr/types/wlr_linux_drm_syncobj_v1.h>
#include <wlr/types/wlr_viewporter.h>
#include <wlr/types/wlr_virtual_keyboard_v1.h>
#include <wlr/types/wlr_virtual_pointer_v1.h>
#include <wlr/types/wlr_xcursor_manager.h>
#include <wlr/types/wlr_xdg_activation_v1.h>
#include <wlr/types/wlr_xdg_decoration_v1.h>
#include <wlr/types/wlr_xdg_output_v1.h>
#include <wlr/types/wlr_xdg_shell.h>
#include <wlr/util/log.h>
#include <drm_fourcc.h>
#include <wlr/xwayland.h>
#include <xkbcommon/xkbcommon.h>

#define LISTEN(sig, l, fn) do { (l)->notify = fn; wl_signal_add(&(sig), (l)); } while (0)
#define UNLISTEN(l) wl_list_remove(&(l)->link)

enum scene_layer { L_BG, L_BOTTOM, L_WINDOWS, L_TOP, L_FULLSCREEN, L_OVERLAY, L_LOCK, L_COUNT };
enum cursor_mode { CURSOR_PASSTHROUGH, CURSOR_MOVE, CURSOR_RESIZE };
enum action { A_EXEC, A_CLOSE, A_QUIT, A_FOCUS_NEXT, A_FULLSCREEN, A_MAXIMIZE, A_OUTPUT_NEXT, A_RELOAD,
	A_SNAP_LEFT, A_SNAP_RIGHT, A_RESTORE_DOWN, A_SHOW_DESKTOP, A_NONE };

struct bind { struct wl_list link; uint32_t mods; xkb_keysym_t sym; enum action action; char *arg; };
/* mouse / touchpad / keyboard lines of compositor.conf; -1 (or NAN for accel) = leave as is */
struct ptr_cfg { double accel; int flat, natural, left_handed, tap, dwt; };
struct kb_cfg { char layout[64], variant[64], options[128]; int rate, delay; };

struct out_cfg {
	struct wl_list link;
	char *name;            /* output name or "*" */
	int w, h; double hz;   /* mode; 0 = preferred */
	double scale;
	enum wl_output_transform transform;
	bool has_pos; int x, y;
	bool enabled, vrr, hdr;
	double sdr_white;      /* cd/m2 for SDR white on an HDR screen; 0 = 203 (wlroots) */
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
	/* a bind on Super_L/Super_R alone runs when that key is released with nothing pressed
	 * or clicked in between, like the Windows key opening Start; 0 = no tap pending */
	uint32_t tap_keycode;
	/* Alt+Tab switcher: open while the modifier that opened it is held; sel indexes the
	 * switcher list (most recently focused first) */
	struct { bool on; int sel; uint32_t mods; struct wlr_scene_buffer *buf; } sw;

	struct wlr_seat *seat;
	struct wlr_cursor *cursor;
	struct wlr_xcursor_manager *xcursor;
	char xcursor_theme_now[64]; int xcursor_size_now;
	bool xwayland_up;
	struct wl_list keyboards;
	struct wl_list pointers;          /* struct pointer_dev */
	struct ptr_cfg mouse_cfg, touchpad_cfg;
	struct kb_cfg kb_cfg;
	char cursor_theme[64]; int cursor_size;   /* cursor theme= size= line; "" = default */
	enum cursor_mode cursor_mode;
	struct view *grab_view;
	double grab_x, grab_y;
	struct wlr_box grab_box;
	uint32_t resize_edges;
	/* Windows-style snap while dragging: the zone under the cursor and its preview */
	int snap_zone;
	/* implicit grab: while a button is held, motion stays with the surface it was pressed on */
	struct wlr_surface *hold_surface;
	double hold_dx, hold_dy;
	struct wlr_scene_rect *snap_preview;
	struct wlr_surface *cursor_focus_surface;
	struct wlr_pointer_constraint_v1 *active_constraint;

	struct view *focused_view;
	struct layer_surface *focused_layer;
	struct view *hover_view;              /* title bar under the cursor (for button hover) */
	struct view *last_bar_view; uint32_t last_bar_time;   /* double-click on a title bar */
	struct view *press_view; double press_x, press_y;     /* maximized bar pressed: drag after 8px */
	struct wlr_output *focused_output;

	struct wlr_idle_notifier_v1 *idle;
	struct wlr_idle_inhibit_manager_v1 *idle_inhibit;
	int inhibitors;
	/* idle: lock, screens off, suspend after so many seconds without input (0 = never) */
	struct { int lock, screen_off, suspend; } idle_cfg;
	struct wl_event_source *idle_timer;
	int64_t idle_since, idle_tick_at;     /* CLOCK_BOOTTIME ms */
	bool idle_lock_done, idle_suspend_done, screens_off;
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
	bool lock_sent;   /* locked was sent to the current lock client (wlroots aborts on a second one) */
	struct wlr_surface *lock_focus;

	struct wl_listener renderer_lost;
	bool want_vulkan;                     /* HDR asked for the Vulkan renderer at start */
	struct wl_listener new_output, new_xdg_toplevel, new_xdg_popup, new_layer_surface, new_input,
		new_xwayland_surface, xwayland_ready, request_set_cursor, request_set_selection,
		request_set_primary, cursor_motion, cursor_motion_abs, cursor_button, cursor_axis,
		cursor_frame, new_deco, new_lock, new_inhibitor, activate, ftl_new_obj, tearing_new,
		cursor_shape, layout_change, output_apply, output_test, new_constraint, new_vkb,
		new_vptr, om_set_mode, pointer_focus_change, seat_destroy_dummy;
};

struct output {
	struct wlr_color_transform *hdr_tr;   /* SDR white at sdr_white nits, then PQ; NULL = wlroots' own */
	double sdr_white;                     /* what SDR white is on this screen in HDR (cd/m2) */
	struct wl_list link;
	struct server *server;
	struct wlr_output *wlr_output;
	struct wlr_scene_output *scene_output;
	struct wlr_box usable;
	struct wl_listener frame, request_state, destroy;
	bool dpms_off;                        /* powered down by the idle timer */
	/* tearing test result, kept for one fullscreen window at one refresh rate. The pointer is
	 * only compared, never followed, and view_destroy clears it. */
	struct view *tear_view;
	int tear_refresh;
	bool tear_ok;
};

struct view {
	struct wl_list link;
	struct server *server;
	bool is_x11, mapped, unmanaged, fullscreen, maximized, minimized;
	bool tiled;               /* snapped to half a screen; saved holds the size to go back to */
	int tile_zone;            /* which half, while tiled */
	bool desktop_hidden;      /* minimized by Super+D; the next Super+D brings it back */
	/* compositor-drawn title bar: for xdg windows that asked for server-side decorations and
	 * X11 windows without a Motif "no decorations" hint. It sits above the content, at y < 0. */
	bool ssd;
	/* an X11 window that mapped without a frame draws its own title bar: it never gets ours.
	 * Wine apps like Battle.net ask for a frame once maximized (their style gains a caption). */
	bool x11_own_frame;
	struct wlr_scene_tree *deco;
	struct wlr_scene_buffer *deco_bar;
	struct wlr_scene_rect *deco_edge[4];
	char *deco_title;
	int deco_w, deco_h, deco_hover, deco_hover_drawn; float deco_scale;
	bool activated, deco_active, deco_max, deco_shown;
	struct wlr_output *ftl_out;
	/* the output this window was on before that output went away (monitor powered off or
	 * replugged); it goes back there, at the same offset, when the output returns */
	char home_out[24]; int home_dx, home_dy;
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
		xw_request_configure, xw_set_geometry, xw_override, xw_content_destroy,
		request_minimize, ftl_minimize, xw_set_deco;
	/* the surface's own map/unmap/commit listeners are live only between associate/dissociate */
	bool surface_listening;
};

struct keyboard {
	struct wl_list link;
	struct server *server;
	struct wlr_keyboard *wlr;
	struct wl_listener modifiers, key, destroy;
	uint32_t handled[16]; int nhandled;
	bool is_virtual;          /* virtual keyboards bring their own keymap */
};

struct pointer_dev {
	struct wl_list link;
	struct wlr_input_device *dev;
	struct wl_listener destroy;
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
static void deco_sync(struct view *v);
static void view_set_minimized(struct view *v, bool on);

static void focus_view(struct view *v, struct wlr_surface *prefer);
static void arrange_layers(struct output *o);
static void publish_output_config(struct server *s);
static void update_cursor_focus(struct server *s, uint32_t time);
static void refocus_soon(struct server *s);
static void view_place(struct view *v, int x, int y);
static const char *view_app_id(struct view *v) {
	const char *a = v->is_x11 ? (v->xw ? v->xw->class : NULL) : (v->xdg ? v->xdg->app_id : NULL);
	return a ? a : "";
}
static void focus_layer_or_view(struct server *s);
static void switcher_close(struct server *s, bool commit);
static void switcher_draw(struct server *s);

/* ---------- small helpers ---------- */

static void spawn(const char *cmd) {
	pid_t p = fork();
	if (p < 0) return;
	if (p == 0) {
		setsid();
		pid_t q = fork();
		if (q != 0) _exit(0);
		/* the event loop blocks SIGHUP/SIGINT/SIGTERM (signalfd) and ignores SIGPIPE; children
		 * would inherit that, survive the logout's SIGTERM, and the shell's restart loop would
		 * attach a leftover shell to the next session's compositor (black screens on relogin) */
		sigset_t none; sigemptyset(&none);
		sigprocmask(SIG_SETMASK, &none, NULL);
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
		{"reload", A_RELOAD}, {"snap-left", A_SNAP_LEFT}, {"snap-right", A_SNAP_RIGHT},
		{"restore-down", A_RESTORE_DOWN}, {"show-desktop", A_SHOW_DESKTOP}, {"none", A_NONE},
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
	add_bind(s, "Ctrl+Alt+t", A_EXEC, "spark-terminal || foot || xterm", false);
	/* the Spark apps' own keys (X-KDE-Shortcuts in their desktop entries; kglobalaccel reads
	 * those on Plasma, and nothing from KDE runs here) */
	add_bind(s, "Ctrl+Shift+Escape", A_EXEC, "spark-monitor", false);
	add_bind(s, "Super+Escape", A_EXEC, "spark-monitor", false);
	add_bind(s, "Ctrl+Escape", A_EXEC, "spark-monitor", false);
	add_bind(s, "Super+period", A_EXEC, "spark-emoji", false);
	add_bind(s, "Super+v", A_EXEC, "spark-notes --clipboard", false);
	add_bind(s, "XF86Calculator", A_EXEC, "spark-calc", false);
	add_bind(s, "Super+e", A_EXEC, "spark-files", false);
	add_bind(s, "Super+i", A_EXEC, "spark-settings", false);
	add_bind(s, "Super+Alt+g", A_EXEC, "spark-clips --save", false);
	add_bind(s, "Super+q", A_CLOSE, NULL, false);
	add_bind(s, "Alt+F4", A_CLOSE, NULL, false);
	add_bind(s, "Alt+Tab", A_FOCUS_NEXT, NULL, false);
	add_bind(s, "Super+Tab", A_FOCUS_NEXT, NULL, false);
	add_bind(s, "Super+f", A_FULLSCREEN, NULL, false);
	add_bind(s, "Super+Up", A_MAXIMIZE, NULL, false);
	/* Windows 7: Super+Left/Right snap to half a screen, Super+Down restores then minimizes,
	 * Super+D shows the desktop and brings the windows back */
	add_bind(s, "Super+Left", A_SNAP_LEFT, NULL, false);
	add_bind(s, "Super+Right", A_SNAP_RIGHT, NULL, false);
	add_bind(s, "Super+Down", A_RESTORE_DOWN, NULL, false);
	add_bind(s, "Super+d", A_SHOW_DESKTOP, NULL, false);
	add_bind(s, "Super+o", A_OUTPUT_NEXT, NULL, false);
	add_bind(s, "Super+Ctrl+Shift+r", A_RELOAD, NULL, false);
	add_bind(s, "Super+Shift+e", A_QUIT, NULL, false);
	add_bind(s, "Super+l", A_EXEC, "loginctl lock-session", false);
	add_bind(s, "Super_L", A_EXEC, "spark-shell --toggle", false);
	add_bind(s, "Super_R", A_EXEC, "spark-shell --toggle", false);
	add_bind(s, "Print", A_EXEC, "spark-snip image", false);
	add_bind(s, "Super+Shift+s", A_EXEC, "spark-snip image", false);
	add_bind(s, "Super+Shift+t", A_EXEC, "spark-snip text", false);
	add_bind(s, "Super+Shift+r", A_EXEC, "spark-snip video", false);
#define SHELL_KEY "gdbus call --session --dest dev.wolklaw.SparkShell --object-path /Shell --method dev.wolklaw.SparkShell.Key "
	add_bind(s, "XF86AudioRaiseVolume", A_EXEC, SHELL_KEY "volume-up", false);
	add_bind(s, "XF86AudioLowerVolume", A_EXEC, SHELL_KEY "volume-down", false);
	add_bind(s, "XF86AudioMute", A_EXEC, SHELL_KEY "mute", false);
	add_bind(s, "XF86AudioPlay", A_EXEC, SHELL_KEY "play-pause", false);
	add_bind(s, "XF86AudioPause", A_EXEC, SHELL_KEY "play-pause", false);
	add_bind(s, "XF86AudioNext", A_EXEC, SHELL_KEY "next", false);
	add_bind(s, "XF86AudioPrev", A_EXEC, SHELL_KEY "previous", false);
	add_bind(s, "XF86AudioStop", A_EXEC, SHELL_KEY "stop", false);
	add_bind(s, "XF86MonBrightnessUp", A_EXEC, SHELL_KEY "brightness-up", false);
	add_bind(s, "XF86MonBrightnessDown", A_EXEC, SHELL_KEY "brightness-down", false);
#undef SHELL_KEY
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
		else if (!strcmp(kv, "sdr_white")) { double w = atof(v); c->sdr_white = w >= 80 && w <= 1000 ? w : 0; }
		else if (!strcmp(kv, "hdr")) c->hdr = !strcmp(v, "on") || !strcmp(v, "true") || !strcmp(v, "1");
		else if (!strcmp(kv, "transform")) {
			static const struct { const char *n; enum wl_output_transform t; } T[] = {
				{"normal", 0}, {"0", 0}, {"90", 1}, {"180", 2}, {"270", 3}, {"flipped", 4},
				{"flipped-90", 5}, {"flipped-180", 6}, {"flipped-270", 7} };
			for (size_t i = 0; i < sizeof T / sizeof *T; i++) if (!strcmp(v, T[i].n)) c->transform = T[i].t;
		}
	}
	wl_list_insert(s->out_cfgs.prev, &c->link);
}

static int cfg_bool(const char *v) {
	return !strcmp(v, "on") || !strcmp(v, "true") || !strcmp(v, "1") || !strcmp(v, "yes");
}

/* cursor theme=Breeze_Light size=24 */
static void parse_cursor_line(struct server *s, char *rest) {
	char *save = NULL;
	for (char *kv = strtok_r(rest, " \t", &save); kv; kv = strtok_r(NULL, " \t", &save)) {
		char *eq = strchr(kv, '=');
		if (!eq) continue;
		*eq = 0; const char *v = eq + 1;
		if (!strcmp(kv, "theme") && !strchr(v, '/')) snprintf(s->cursor_theme, sizeof s->cursor_theme, "%s", v);
		else if (!strcmp(kv, "size")) { int n = atoi(v); if (n >= 12 && n <= 128) s->cursor_size = n; }
	}
}

static void reset_input_cfg(struct server *s) {
	s->cursor_theme[0] = 0; s->cursor_size = 24;
	struct ptr_cfg none = { NAN, -1, -1, -1, -1, -1 };
	s->mouse_cfg = none; s->touchpad_cfg = none;
	memset(&s->kb_cfg, 0, sizeof s->kb_cfg);
	s->kb_cfg.rate = 25; s->kb_cfg.delay = 600;
	s->idle_cfg.lock = s->idle_cfg.screen_off = s->idle_cfg.suspend = 0;
}

/* idle lock=SECONDS screen_off=SECONDS suspend=SECONDS (0 or missing = never) */
static void parse_idle_line(struct server *s, char *rest) {
	char *save = NULL;
	for (char *kv = strtok_r(rest, " \t", &save); kv; kv = strtok_r(NULL, " \t", &save)) {
		char *eq = strchr(kv, '=');
		if (!eq) continue;
		*eq = 0;
		int v = atoi(eq + 1);
		if (v < 0) v = 0;
		if (v > 0 && v < 30) v = 30;      /* never lock or blank before the user can react */
		if (!strcmp(kv, "lock")) s->idle_cfg.lock = v;
		else if (!strcmp(kv, "screen_off")) s->idle_cfg.screen_off = v;
		else if (!strcmp(kv, "suspend")) s->idle_cfg.suspend = v;
	}
}

/* mouse|touchpad accel=-1..1 profile=flat|adaptive natural= left_handed= tap= dwt= */
static void parse_pointer_line(struct ptr_cfg *c, char *rest) {
	char *save = NULL;
	for (char *kv = strtok_r(rest, " \t", &save); kv; kv = strtok_r(NULL, " \t", &save)) {
		char *eq = strchr(kv, '=');
		if (!eq) continue;
		*eq = 0; const char *v = eq + 1;
		if (!strcmp(kv, "accel")) { double a = atof(v); c->accel = a < -1 ? -1 : a > 1 ? 1 : a; }
		else if (!strcmp(kv, "profile")) c->flat = !strcmp(v, "flat");
		else if (!strcmp(kv, "natural")) c->natural = cfg_bool(v);
		else if (!strcmp(kv, "left_handed")) c->left_handed = cfg_bool(v);
		else if (!strcmp(kv, "tap")) c->tap = cfg_bool(v);
		else if (!strcmp(kv, "dwt")) c->dwt = cfg_bool(v);
	}
}

/* keyboard layout=us,ca variant=,fr options=grp:alt_shift_toggle repeat_rate=25 repeat_delay=600 */
static void parse_keyboard_line(struct kb_cfg *c, char *rest) {
	char *save = NULL;
	for (char *kv = strtok_r(rest, " \t", &save); kv; kv = strtok_r(NULL, " \t", &save)) {
		char *eq = strchr(kv, '=');
		if (!eq) continue;
		*eq = 0; const char *v = eq + 1;
		if (!strcmp(kv, "layout")) snprintf(c->layout, sizeof c->layout, "%s", v);
		else if (!strcmp(kv, "variant")) snprintf(c->variant, sizeof c->variant, "%s", v);
		else if (!strcmp(kv, "options")) snprintf(c->options, sizeof c->options, "%s", v);
		else if (!strcmp(kv, "repeat_rate")) { int r = atoi(v); if (r >= 1 && r <= 100) c->rate = r; }
		else if (!strcmp(kv, "repeat_delay")) { int d = atoi(v); if (d >= 100 && d <= 2000) c->delay = d; }
	}
}

static void load_config_file(struct server *s, const char *path) {
	FILE *f = fopen(path, "r");
	if (!f) return;
	char line[512];
	while (fgets(line, sizeof line, f)) {
		char *l = trim(line);
		if (!*l || *l == '#') continue;
		if (!strncmp(l, "output ", 7)) parse_output_line(s, l + 7);
		else if (!strncmp(l, "mouse ", 6)) parse_pointer_line(&s->mouse_cfg, l + 6);
		else if (!strncmp(l, "touchpad ", 9)) parse_pointer_line(&s->touchpad_cfg, l + 9);
		else if (!strncmp(l, "keyboard ", 9)) parse_keyboard_line(&s->kb_cfg, l + 9);
		else if (!strncmp(l, "cursor ", 7)) parse_cursor_line(s, l + 7);
		else if (!strncmp(l, "idle ", 5)) parse_idle_line(s, l + 5);
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
	reset_input_cfg(s);
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

/* HDR10: PQ transfer, BT.2020 primaries, 10-bit buffers. Needs the Vulkan renderer (the only
 * one that can convert on output) and a screen whose EDID says it takes PQ and BT.2020.
 * SDR windows are mapped to 203 cd/m2 white, the BT.2408 reference level. */
static bool output_can_hdr(struct wlr_output *wo) {
	return wo->renderer && wo->renderer->features.output_color_transform &&
		(wo->supported_transfer_functions & WLR_COLOR_TRANSFER_FUNCTION_ST2084_PQ) &&
		(wo->supported_primaries & WLR_COLOR_NAMED_PRIMARIES_BT2020);
}

static void output_state_set_hdr(struct wlr_output *wo, struct wlr_output_state *st, bool on) {
	if (on && !output_can_hdr(wo)) {
		wlr_log(WLR_INFO, "output %s: hdr=on asked, but %s", wo->name,
			!(wo->renderer && wo->renderer->features.output_color_transform)
				? "the renderer cannot (not Vulkan)" : "the screen does not report PQ + BT.2020");
		on = false;
	}
	if (on) {
		wlr_output_state_set_render_format(st, DRM_FORMAT_XRGB2101010);
		wlr_output_state_set_image_description(st, &(struct wlr_output_image_description){
			.primaries = WLR_COLOR_NAMED_PRIMARIES_BT2020,
			.transfer_function = WLR_COLOR_TRANSFER_FUNCTION_ST2084_PQ,
		});
	} else if (wo->image_description) {
		wlr_output_state_set_render_format(st, DRM_FORMAT_XRGB8888);
		wlr_output_state_set_image_description(st, NULL);
	}
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
	output_state_set_hdr(wo, st, c->hdr);
}

/* On an HDR screen with sdr_white set, the scene is handed this transform instead of working
 * one out from the output's image description (which pins SDR white at 203 cd/m2). wlroots
 * refuses a supplied transform next to a description, so the frame state says "no description"
 * while the scene builds it, and that flag is taken off before the commit so the screen stays
 * in HDR. */
static void output_hdr_setup(struct output *o, double white) {
	if (o->hdr_tr) { wlr_color_transform_unref(o->hdr_tr); o->hdr_tr = NULL; }
	o->sdr_white = white > 0 ? white : 203;
	if (!o->wlr_output->image_description || white <= 0) return;
	struct wlr_color_primaries srgb, bt2020;
	wlr_color_primaries_from_named(&srgb, WLR_COLOR_NAMED_PRIMARIES_SRGB);
	wlr_color_primaries_from_named(&bt2020, WLR_COLOR_NAMED_PRIMARIES_BT2020);
	float m[9];
	wlr_color_primaries_transform_absolute_colorimetric(&srgb, &bt2020, m);
	for (int i = 0; i < 9; i++) m[i] *= (float)(white / 10000.0);
	struct wlr_color_transform *parts[2] = {
		wlr_color_transform_init_matrix(m),
		wlr_color_transform_init_linear_to_inverse_eotf(WLR_COLOR_TRANSFER_FUNCTION_ST2084_PQ),
	};
	if (parts[0] && parts[1]) o->hdr_tr = wlr_color_transform_init_pipeline(parts, 2);
	if (parts[0]) wlr_color_transform_unref(parts[0]);
	if (parts[1]) wlr_color_transform_unref(parts[1]);
	wlr_log(WLR_INFO, "output %s: HDR, SDR white at %.0f cd/m2", o->wlr_output->name, white);
}

static bool output_build_state(struct output *o, struct wlr_output_state *st) {
	bool custom = o->hdr_tr && o->wlr_output->image_description;
	if (!custom) return wlr_scene_output_build_state(o->scene_output, st, NULL);
	/* Every frame, so any rebuild the scene decides on sees no description. The transform is
	 * passed through as-is (same pointer), so the renderer keeps its cached setup. */
	wlr_output_state_set_image_description(st, NULL);
	struct wlr_scene_output_state_options opt = { .color_transform = o->hdr_tr };
	bool ok = wlr_scene_output_build_state(o->scene_output, st, &opt);
	st->committed &= ~WLR_OUTPUT_STATE_IMAGE_DESCRIPTION;
	return ok;
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
		if (output_build_state(o, &st)) {
			/* a test commit is a full atomic check in the kernel: do it once per fullscreen
			 * window and mode, not every frame. A refused tearing commit is redone vsynced. */
			if (o->tear_view != fv || o->tear_refresh != wo->refresh) {
				o->tear_view = fv; o->tear_refresh = wo->refresh;
				st.tearing_page_flip = true;
				o->tear_ok = wlr_output_test_state(wo, &st);
				wlr_log(WLR_INFO, "output %s: tearing %s", wo->name, o->tear_ok ? "on" : "refused by the driver");
			}
			st.tearing_page_flip = o->tear_ok;
			if (!wlr_output_commit_state(wo, &st) && st.tearing_page_flip) {
				o->tear_ok = false;
				st.tearing_page_flip = false;
				wlr_output_commit_state(wo, &st);
			}
		}
		wlr_output_state_finish(&st);
	} else if (o->hdr_tr && wo->image_description) {
		if (wlr_scene_output_needs_frame(so)) {
			struct wlr_output_state st;
			wlr_output_state_init(&st);
			if (output_build_state(o, &st)) wlr_output_commit_state(wo, &st);
			wlr_output_state_finish(&st);
		}
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

/* before an output leaves the layout: note which windows were on it, so refit_views can
 * bring them back when it returns */
static void remember_homes(struct server *s, struct wlr_output *wo) {
	struct wlr_box ob;
	wlr_output_layout_get_box(s->output_layout, wo, &ob);
	if (wlr_box_empty(&ob)) return;
	struct view *v;
	wl_list_for_each(v, &s->views, link) {
		if (!v->mapped || v->unmanaged || v->home_out[0]) continue;
		if (!wlr_box_contains_point(&ob, v->x + 40, v->y + 40)) continue;
		snprintf(v->home_out, sizeof v->home_out, "%s", wo->name);
		v->home_dx = v->x - ob.x; v->home_dy = v->y - ob.y;
	}
}

static void output_destroy(struct wl_listener *l, void *data) {
	struct output *o = wl_container_of(l, o, destroy);
	struct server *s = o->server;
	UNLISTEN(&o->frame); UNLISTEN(&o->request_state); UNLISTEN(&o->destroy);
	if (o->hdr_tr) wlr_color_transform_unref(o->hdr_tr);
	wl_list_remove(&o->link);
	if (s->focused_output == o->wlr_output) s->focused_output = NULL;
	struct view *vw;
	wl_list_for_each(vw, &s->views, link) if (vw->ftl_out == o->wlr_output) vw->ftl_out = NULL;
	remember_homes(s, o->wlr_output);
	/* layer surfaces of this output lose their output; the client is told to close */
	struct layer_surface *ls, *lt;
	wl_list_for_each_safe(ls, lt, &s->layer_surfaces, link)
		if (ls->wlr->output == o->wlr_output) { ls->wlr->output = NULL; wlr_layer_surface_v1_destroy(ls->wlr); }
	free(o);
	publish_output_config(s);
}

static void refit_views(struct server *s) {
	struct view *v;
	/* windows whose output came back go home first */
	wl_list_for_each(v, &s->views, link) {
		if (!v->home_out[0]) continue;
		struct output *o;
		wl_list_for_each(o, &s->outputs, link) {
			if (strcmp(o->wlr_output->name, v->home_out)) continue;
			struct wlr_box hb; wlr_output_layout_get_box(s->output_layout, o->wlr_output, &hb);
			if (wlr_box_empty(&hb)) break;
			v->home_out[0] = 0;
			if (!v->mapped) break;
			v->x = hb.x + v->home_dx; v->y = hb.y + v->home_dy;
			if (v->x + 40 >= hb.x + hb.width) v->x = hb.x + 60;
			if (v->y + 40 >= hb.y + hb.height) v->y = hb.y + 60;
			view_place(v, v->x, v->y);
			wlr_log(WLR_INFO, "window app_id=%s back on %s", view_app_id(v), o->wlr_output->name);
			break;
		}
	}
	wl_list_for_each(v, &s->views, link) {
		struct wlr_box b;
		if (!v->mapped || wlr_output_layout_output_at(s->output_layout, v->x + 40, v->y + 40)) continue;
		/* the window is on an output that went away: bring it to the first output */
		struct wlr_output *wo = output_at_cursor(s);
		if (!wo) continue;
		wlr_output_layout_get_box(s->output_layout, wo, &b);
		view_place(v, b.x + 60, b.y + 60);
		wlr_log(WLR_INFO, "window app_id=%s moved to %s (its output went away)", view_app_id(v), wo->name);
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
	/* step down one setting at a time, so a refused HDR or VRR request keeps the mode,
	 * scale and rotation instead of dropping straight to the preferred mode */
	struct out_cfg t; if (c) t = *c;
	if (!ok && c && t.hdr) { /* HDR refused: same settings in SDR */
		wlr_log(WLR_ERROR, "output %s: HDR was refused, using SDR", wo->name);
		wlr_output_state_finish(&st); wlr_output_state_init(&st);
		t.hdr = false; apply_cfg_to_state(wo, &t, &st);
		ok = wlr_output_commit_state(wo, &st);
	}
	if (!ok && c && t.vrr) { /* adaptive sync refused: same settings without it */
		wlr_log(WLR_ERROR, "output %s: adaptive sync was refused, turning it off", wo->name);
		wlr_output_state_finish(&st); wlr_output_state_init(&st);
		t.vrr = false; apply_cfg_to_state(wo, &t, &st);
		ok = wlr_output_commit_state(wo, &st);
	}
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
	output_hdr_setup(o, c ? c->sdr_white : 0);

	struct wlr_box b; wlr_output_layout_get_box(s->output_layout, wo, &b);
	o->usable = b;
	int tw, th; wlr_output_transformed_resolution(wo, &tw, &th);
	wlr_log(WLR_INFO, "output %s: %dx%d@%.3f scale %.2f transform %d at %d,%d hdr %s (screen %s)", wo->name, tw, th,
		wo->refresh / 1000.0, wo->scale, wo->transform, b.x, b.y, wo->image_description ? "on" : "off",
		output_can_hdr(wo) ? "can" : "cannot");
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
			if (!test && wo->renderer != s->renderer) wlr_output_init_render(wo, s->allocator, s->renderer);
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
			else { remember_homes(s, wo); wlr_output_layout_remove(s->output_layout, wo); }
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
				/* the surface's popups (panel menus, popovers) live in their own tree above
				 * everything: it has to follow the surface, or they open at the layout's 0,0 */
				wlr_scene_node_set_position(&ls->popups->node, ls->scene->tree->node.x, ls->scene->tree->node.y);
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
	refocus_soon(s);
}

static void layer_unmap(struct wl_listener *l, void *data) {
	struct layer_surface *ls = wl_container_of(l, ls, unmap);
	ls->mapped = false;
	struct server *s = ls->server;
	if (s->focused_layer == ls) { s->focused_layer = NULL; focus_layer_or_view(s); }
	if (ls->wlr->output) { struct output *o = output_of(s, ls->wlr->output); if (o) arrange_layers(o); }
	refocus_soon(s);
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

/* Keep a popup on the output it opens on: wlroots flips or slides it per its positioner rules,
 * given the output's box in the coordinates of the popup's root (window or layer surface). The
 * root is the tree right under one of the scene layers: a view's tree, or a layer surface's
 * popup tree (kept at the surface's position by arrange_layers). */
static void popup_unconstrain(struct popup *p) {
	struct wlr_scene_tree *t = p->wlr->base->data;
	if (!t) return;
	struct wlr_scene_tree *root = t;
	for (;;) {
		struct wlr_scene_tree *up = root->node.parent;
		if (!up) return;
		bool is_layer = false;
		for (int i = 0; i < L_COUNT; i++) if (S.layers[i] == up) is_layer = true;
		if (is_layer) break;
		root = up;
	}
	int rx, ry;
	if (!wlr_scene_node_coords(&root->node, &rx, &ry)) return;
	struct wlr_output *wo = wlr_output_layout_output_at(S.output_layout, S.cursor->x, S.cursor->y);
	if (!wo) wo = output_at_cursor(&S);
	if (!wo) return;
	struct wlr_box b;
	wlr_output_layout_get_box(S.output_layout, wo, &b);
	b.x -= rx; b.y -= ry;
	wlr_xdg_popup_unconstrain_from_box(p->wlr, &b);
}

static void popup_commit(struct wl_listener *l, void *data) {
	struct popup *p = wl_container_of(l, p, commit);
	if (p->wlr->base->initial_commit) {
		popup_unconstrain(p);
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
	v->activated = on;
	deco_sync(v);
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

/* an X11 override-redirect surface (menu, popup) that is still up */
static bool unmanaged_has(struct server *s, struct wlr_surface *surf) {
	(void)s;
	struct wlr_xwayland_surface *x = surf ? wlr_xwayland_surface_try_from_wlr_surface(surf) : NULL;
	return x && x->override_redirect;
}

static void focus_view(struct view *v, struct wlr_surface *prefer) {
	struct server *s = &S;
	if (!v) return;
	if (v->unmanaged) {
		/* an X11 menu or popup (a Tk drop-down in Spark Settings): it may take the keyboard, but
		 * it never joins the window list; clicking one used to put it there, and once the menu
		 * was gone the list held freed memory and the session crashed on the next window change */
		struct wlr_surface *surf = view_surface(v);
		if (surf && !s->locked && wlr_xwayland_surface_override_redirect_wants_focus(v->xw))
			send_keyboard_focus(s, surf);
		return;
	}
	if (v->minimized) { view_set_minimized(v, false); return; }
	if (s->focused_view == v && !s->focused_layer) {
		/* already the active window: still make sure the keyboard is on it (a popup may have had it) */
		struct wlr_surface *surf = view_surface(v);
		if (surf && s->seat->keyboard_state.focused_surface != surf && !s->locked &&
				!(s->seat->keyboard_state.focused_surface && unmanaged_has(s, s->seat->keyboard_state.focused_surface)))
			focus_layer_or_view(s);
		return;
	}
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
	if (v->ftl) {
		struct wlr_box b; view_box(v, &b);
		struct wlr_output *wo = wlr_output_layout_output_at(S.output_layout, x + b.width / 2, y + b.height / 2);
		if (wo && wo != v->ftl_out) {
			if (v->ftl_out) wlr_foreign_toplevel_handle_v1_output_leave(v->ftl, v->ftl_out);
			wlr_foreign_toplevel_handle_v1_output_enter(v->ftl, wo);
			v->ftl_out = wo;
		}
	}
}

/* a frame (title bar) drawn by the compositor: xdg windows that asked for server-side
 * decorations, X11 windows without a Motif "no decorations" hint */
#define TB_H 30
static bool view_has_frame(struct view *v) {
	if (v->unmanaged) return false;
	if (v->is_x11) return v->xw && !v->x11_own_frame && v->xw->decorations == WLR_XWAYLAND_SURFACE_DECORATIONS_ALL;
	return v->ssd;
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
	deco_sync(v);
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
		int dh = view_has_frame(v) ? TB_H : 0;
		view_place(v, o->usable.x, o->usable.y + dh);
		view_resize(v, o->usable.width, o->usable.height - dh);
	} else {
		v->maximized = false;
		/* mapped maximized (Wine restoring its last state): the saved size is the whole screen,
		   so un-maximizing would change nothing. Fall back to two thirds of the screen, centred. */
		struct output *o = output_of(v->server, view_output(v));
		if (o && (v->saved.width <= 0 || v->saved.height <= 0 ||
		          (v->saved.width >= o->usable.width - 8 && v->saved.height >= o->usable.height - TB_H - 8))) {
			v->saved.width = o->usable.width * 2 / 3; v->saved.height = o->usable.height * 2 / 3;
			v->saved.x = o->usable.x + (o->usable.width - v->saved.width) / 2;
			v->saved.y = o->usable.y + (o->usable.height - v->saved.height) / 2;
		}
		view_place(v, v->saved.x, v->saved.y);
		view_resize(v, v->saved.width, v->saved.height);
	}
	if (v->is_x11) wlr_xwayland_surface_set_maximized(v->xw, on, on);
	else wlr_xdg_toplevel_set_maximized(v->xdg, on);
	if (v->ftl) wlr_foreign_toplevel_handle_v1_set_maximized(v->ftl, on);
	deco_sync(v);
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
	deco_sync(v);
}
/* ---------- title bars ---------- */

#define TB_BTN 42
#define TB_EDGE 6
enum { HIT_NONE, HIT_BAR, HIT_MIN, HIT_MAX, HIT_CLOSE, HIT_EDGE };

struct cbuf { struct wlr_buffer base; cairo_surface_t *cs; };
static void cbuf_destroy(struct wlr_buffer *b) {
	struct cbuf *c = wl_container_of(b, c, base);
	cairo_surface_destroy(c->cs); free(c);
}
static bool cbuf_begin(struct wlr_buffer *b, uint32_t flags, void **data, uint32_t *format, size_t *stride) {
	struct cbuf *c = wl_container_of(b, c, base);
	if (flags & WLR_BUFFER_DATA_PTR_ACCESS_WRITE) return false;
	*data = cairo_image_surface_get_data(c->cs);
	*format = DRM_FORMAT_ARGB8888;
	*stride = cairo_image_surface_get_stride(c->cs);
	return true;
}
static void cbuf_end(struct wlr_buffer *b) { (void)b; }
static const struct wlr_buffer_impl cbuf_impl = {
	.destroy = cbuf_destroy, .begin_data_ptr_access = cbuf_begin, .end_data_ptr_access = cbuf_end };

static void ink(cairo_t *cr, uint32_t rgb, double a) {
	cairo_set_source_rgba(cr, ((rgb >> 16) & 255) / 255.0, ((rgb >> 8) & 255) / 255.0, (rgb & 255) / 255.0, a);
}

/* Spark house style (the BotWatch app palette): flat dark bar, 1px line, mono caps-free title,
 * the magenta/cyan channel slip on the active window's title as the only decoration */
static void deco_render(struct view *v, int w, float scale, bool active, int hover, const char *title) {
	int pw = (int)ceilf(w * scale), ph = (int)ceilf(TB_H * scale);
	struct cbuf *c = calloc(1, sizeof *c);
	c->cs = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, pw, ph);
	wlr_buffer_init(&c->base, &cbuf_impl, pw, ph);
	cairo_t *cr = cairo_create(c->cs);
	cairo_scale(cr, scale, scale);
	ink(cr, active ? 0x0e1f22 : 0x0a1517, 1); cairo_paint(cr);
	ink(cr, active ? 0x1f6a66 : 0x143a3d, 1); cairo_rectangle(cr, 0, TB_H - 1, w, 1); cairo_fill(cr);
	uint32_t fg = active ? 0xd4f1ec : 0x6f9f98;
	int bx = w - 3 * TB_BTN;
	for (int i = 0; i < 3; i++) {
		int part = HIT_MIN + i, x = bx + i * TB_BTN;
		bool hov = hover == part;
		if (hov) { ink(cr, part == HIT_CLOSE ? 0xff4d8d : 0x12292c, 1); cairo_rectangle(cr, x, 0, TB_BTN, TB_H - 1); cairo_fill(cr); }
		ink(cr, hov && part == HIT_CLOSE ? 0x04090b : fg, 1);
		cairo_set_line_width(cr, 1.5);
		double cx = x + TB_BTN / 2.0, cy = (TB_H - 1) / 2.0;
		if (part == HIT_MIN) { cairo_move_to(cr, cx - 5, cy + 3.5); cairo_line_to(cr, cx + 5, cy + 3.5); }
		else if (part == HIT_MAX && v->maximized) {
			cairo_rectangle(cr, cx - 5.25, cy - 2.25, 8, 8);
			cairo_move_to(cr, cx - 2.25, cy - 2.25); cairo_line_to(cr, cx - 2.25, cy - 5.25);
			cairo_line_to(cr, cx + 5.75, cy - 5.25); cairo_line_to(cr, cx + 5.75, cy + 2.75);
			cairo_line_to(cr, cx + 2.75, cy + 2.75);
		} else if (part == HIT_MAX) cairo_rectangle(cr, cx - 5.25, cy - 5.25, 10, 10);
		else {
			cairo_move_to(cr, cx - 5, cy - 5); cairo_line_to(cr, cx + 5, cy + 5);
			cairo_move_to(cr, cx + 5, cy - 5); cairo_line_to(cr, cx - 5, cy + 5);
		}
		cairo_stroke(cr);
	}
	int tw = bx - 24;
	if (tw > 0 && title && *title) {
		PangoLayout *pl = pango_cairo_create_layout(cr);
		PangoFontDescription *fd = pango_font_description_from_string("Cascadia Mono, monospace Bold 9");
		pango_layout_set_font_description(pl, fd);
		pango_font_description_free(fd);
		pango_layout_set_text(pl, title, -1);
		pango_layout_set_width(pl, tw * PANGO_SCALE);
		pango_layout_set_ellipsize(pl, PANGO_ELLIPSIZE_END);
		int lw, lh; pango_layout_get_pixel_size(pl, &lw, &lh);
		double ty = (TB_H - 1 - lh) / 2.0;
		if (active) {
			ink(cr, 0xff2e88, 0.5); cairo_move_to(cr, 11, ty); pango_cairo_show_layout(cr, pl);
			ink(cr, 0x22d8ff, 0.5); cairo_move_to(cr, 13, ty); pango_cairo_show_layout(cr, pl);
		}
		ink(cr, fg, 1); cairo_move_to(cr, 12, ty); pango_cairo_show_layout(cr, pl);
		g_object_unref(pl);
	}
	cairo_destroy(cr);
	cairo_surface_flush(c->cs);
	wlr_scene_buffer_set_buffer(v->deco_bar, &c->base);
	wlr_scene_buffer_set_dest_size(v->deco_bar, w, TB_H);
	wlr_buffer_drop(&c->base);
}

static void deco_sync(struct view *v) {
	bool want = v->mapped && !v->fullscreen && view_has_frame(v);
	if (!want) {
		if (v->deco && v->deco_shown) { wlr_scene_node_set_enabled(&v->deco->node, false); v->deco_shown = false; }
		return;
	}
	if (!v->deco) {
		v->deco = wlr_scene_tree_create(v->tree);
		wlr_scene_node_lower_to_bottom(&v->deco->node);
		v->deco_bar = wlr_scene_buffer_create(v->deco, NULL);
		float none[4] = { 0, 0, 0, 0 };
		for (int i = 0; i < 4; i++) v->deco_edge[i] = wlr_scene_rect_create(v->deco, 1, 1, none);
		v->deco_w = -1;
	}
	if (!v->deco_shown) { wlr_scene_node_set_enabled(&v->deco->node, true); v->deco_shown = true; }
	struct wlr_box b; view_box(v, &b);
	int w = b.width, h = b.height;
	if (w < 1 || h < 1) return;
	struct wlr_output *wo = view_output(v);
	float scale = wo ? wo->scale : 1.0f;
	const char *title = v->is_x11 ? v->xw->title : v->xdg->title;
	if (!title) title = "";
	int hover = S.hover_view == v ? v->deco_hover : HIT_NONE;
	if (w == v->deco_w && h == v->deco_h && scale == v->deco_scale && v->activated == v->deco_active &&
	    v->maximized == v->deco_max && hover == v->deco_hover_drawn && v->deco_title && !strcmp(title, v->deco_title))
		return;
	v->deco_w = w; v->deco_h = h; v->deco_scale = scale; v->deco_active = v->activated;
	v->deco_max = v->maximized; v->deco_hover_drawn = hover;
	free(v->deco_title); v->deco_title = strdup(title);
	wlr_scene_node_set_position(&v->deco_bar->node, 0, -TB_H);
	deco_render(v, w, scale, v->activated, hover, title);
	/* invisible resize handles around the frame; none while maximized */
	const int E = TB_EDGE;
	struct wlr_box eb[4] = {
		{ -E, -TB_H - E, w + 2 * E, E }, { -E, h, w + 2 * E, E },
		{ -E, -TB_H, E, TB_H + h }, { w, -TB_H, E, TB_H + h } };
	for (int i = 0; i < 4; i++) {
		wlr_scene_node_set_enabled(&v->deco_edge[i]->node, !v->maximized);
		wlr_scene_node_set_position(&v->deco_edge[i]->node, eb[i].x, eb[i].y);
		wlr_scene_rect_set_size(v->deco_edge[i], eb[i].width, eb[i].height);
	}
}

/* which part of a frame is at lx,ly (NULL when no frame is there) */
static struct view *deco_at(struct server *s, double lx, double ly, int *part) {
	*part = HIT_NONE;
	if (s->locked) return NULL;
	double nx, ny;
	struct wlr_scene_node *n = wlr_scene_node_at(&s->scene->tree.node, lx, ly, &nx, &ny);
	if (!n || !n->parent) return NULL;
	struct view *v = NULL;
	for (struct wlr_scene_tree *t = n->parent; t; t = t->node.parent) if (t->node.data) { v = t->node.data; break; }
	if (!v || !v->deco || n->parent != v->deco) return NULL;
	if (n == &v->deco_bar->node) {
		struct wlr_box b; view_box(v, &b);
		double x = lx - v->x;
		int bx = b.width - 3 * TB_BTN;
		*part = x >= bx ? HIT_MIN + (int)((x - bx) / TB_BTN) : HIT_BAR;
		if (*part > HIT_CLOSE) *part = HIT_CLOSE;
	} else *part = HIT_EDGE;
	return v;
}

static uint32_t deco_edges(struct view *v, double lx, double ly) {
	struct wlr_box b; view_box(v, &b);
	double x = lx - v->x, y = ly - v->y;
	const int C = 20;
	bool outx = x < 0 || x >= b.width, outy = y < -TB_H || y >= b.height;
	uint32_t e = 0;
	if (x < 0 || (outy && x < C)) e |= WLR_EDGE_LEFT;
	else if (x >= b.width || (outy && x > b.width - C)) e |= WLR_EDGE_RIGHT;
	if (y < -TB_H || (outx && y < -TB_H + C)) e |= WLR_EDGE_TOP;
	else if (y >= b.height || (outx && y > b.height - C)) e |= WLR_EDGE_BOTTOM;
	return e;
}

static const char *edge_cursor(uint32_t e) {
	switch (e) {
	case WLR_EDGE_TOP: return "n-resize";
	case WLR_EDGE_BOTTOM: return "s-resize";
	case WLR_EDGE_LEFT: return "w-resize";
	case WLR_EDGE_RIGHT: return "e-resize";
	case WLR_EDGE_TOP | WLR_EDGE_LEFT: return "nw-resize";
	case WLR_EDGE_TOP | WLR_EDGE_RIGHT: return "ne-resize";
	case WLR_EDGE_BOTTOM | WLR_EDGE_LEFT: return "sw-resize";
	case WLR_EDGE_BOTTOM | WLR_EDGE_RIGHT: return "se-resize";
	}
	return "default";
}

static void deco_set_hover(struct server *s, struct view *v, int part) {
	if (s->hover_view != v) {
		struct view *old = s->hover_view;
		s->hover_view = v;
		if (old) { old->deco_hover = HIT_NONE; deco_sync(old); }
	}
	if (v && v->deco_hover != part) { v->deco_hover = part; deco_sync(v); }
}

/* minimized: hidden from the scene, still in the task list (foreign-toplevel says so) */
static void view_set_minimized(struct view *v, bool on) {
	struct server *s = v->server;
	if (v->minimized == on || v->unmanaged) return;
	v->minimized = on;
	wlr_scene_node_set_enabled(&v->tree->node, !on);
	if (v->ftl) wlr_foreign_toplevel_handle_v1_set_minimized(v->ftl, on);
	if (v->is_x11 && v->xw) wlr_xwayland_surface_set_minimized(v->xw, on);
	if (on) {
		if (s->grab_view == v) { s->grab_view = NULL; s->cursor_mode = CURSOR_PASSTHROUGH; }
		if (s->focused_view == v) {
			view_activate(v, false);
			s->focused_view = NULL;
			struct view *n;
			wl_list_for_each(n, &s->views, link)
				if (n != v && n->mapped && !n->minimized && !n->unmanaged) { focus_view(n, NULL); break; }
			if (!s->focused_view) focus_layer_or_view(s);
		}
	} else focus_view(v, NULL);
}

static void view_request_minimize(struct wl_listener *l, void *d) {
	struct view *v = wl_container_of(l, v, request_minimize);
	if (v->mapped) view_set_minimized(v, true);
}
static void xw_request_minimize(struct wl_listener *l, void *d) {
	struct view *v = wl_container_of(l, v, request_minimize);
	struct wlr_xwayland_minimize_event *e = d;
	if (v->mapped) view_set_minimized(v, e->minimize);
}
static void ftl_minimize(struct wl_listener *l, void *d) {
	struct view *v = wl_container_of(l, v, ftl_minimize);
	struct wlr_foreign_toplevel_handle_v1_minimized_event *e = d;
	view_set_minimized(v, e->minimized);
}
static void xw_set_deco(struct wl_listener *l, void *d) {
	struct view *v = wl_container_of(l, v, xw_set_deco);
	deco_sync(v);
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
	if (v->is_x11 && v->xw && v->xw->decorations != WLR_XWAYLAND_SURFACE_DECORATIONS_ALL) v->x11_own_frame = true;
	v->mapped = true;
	wlr_log(WLR_INFO, "mapped %s window app_id=%s title=%s", v->is_x11 ? (v->unmanaged ? "x11-unmanaged" : "x11") : "xdg",
		v->is_x11 ? (v->xw->class ? v->xw->class : "") : (v->xdg->app_id ? v->xdg->app_id : ""),
		v->is_x11 ? (v->xw->title ? v->xw->title : "") : (v->xdg->title ? v->xdg->title : ""));
	if (v->unmanaged) {
		wlr_scene_node_set_position(&v->tree->node, v->xw->x, v->xw->y);
		wlr_scene_node_reparent(&v->tree->node, s->layers[L_TOP]);
		if (wlr_xwayland_surface_override_redirect_wants_focus(v->xw) && !s->locked)
			wlr_seat_keyboard_notify_enter(s->seat, surf, NULL, 0, NULL);
		refocus_soon(s);
		return;
	}
	wl_list_insert(&s->views, &v->link);
	/* place new windows near the middle of the focused output's usable area, cascaded */
	struct wlr_output *wo = s->focused_output ? s->focused_output : output_at_cursor(s);
	struct output *o = wo ? output_of(s, wo) : NULL;
	struct wlr_box b; view_box(v, &b);
	/* an X11 window that asked for a position (USPosition / PPosition), like Spark Snip's
	 * per-screen overlays, keeps it as long as it lands on a screen */
	bool x11_pos = v->is_x11 && v->xw->size_hints && (v->xw->size_hints->flags & (1 | 4)) &&
		wlr_output_layout_output_at(s->output_layout, v->xw->x + b.width / 2, v->xw->y + b.height / 2);
	if (x11_pos) {
		v->x = v->xw->x; v->y = v->xw->y;
	} else if (o) {
		static int cascade;
		int cx = o->usable.x + (o->usable.width - b.width) / 2 + (cascade % 6) * 28;
		int cy = o->usable.y + (o->usable.height - b.height) / 2 + (cascade % 6) * 28;
		cascade++;
		int dh = view_has_frame(v) ? TB_H : 0;
		if (cx < o->usable.x) cx = o->usable.x;
		if (cy < o->usable.y + dh) cy = o->usable.y + dh;
		v->x = cx; v->y = cy;
	}
	wlr_scene_node_set_position(&v->tree->node, v->x, v->y);
	if (v->is_x11) wlr_xwayland_surface_configure(v->xw, v->x, v->y, v->xw->width, v->xw->height);

	v->ftl = wlr_foreign_toplevel_handle_v1_create(s->ftl_mgr);
	LISTEN(v->ftl->events.request_activate, &v->ftl_activate, ftl_activate);
	LISTEN(v->ftl->events.request_close, &v->ftl_close, ftl_close);
	LISTEN(v->ftl->events.request_fullscreen, &v->ftl_fullscreen, ftl_fullscreen);
	LISTEN(v->ftl->events.request_maximize, &v->ftl_maximize, ftl_maximize);
	LISTEN(v->ftl->events.request_minimize, &v->ftl_minimize, ftl_minimize);
	v->ftl_out = NULL;
	view_place(v, v->x, v->y);   /* tells the task list which output the window is on */
	struct wlr_ext_foreign_toplevel_handle_v1_state st = { .title = "", .app_id = "" };
	v->ext_ftl = wlr_ext_foreign_toplevel_handle_v1_create(s->ext_ftl, &st);
	view_titles(v);
	if (wo && surf) wlr_fractional_scale_v1_notify_scale(surf, wo->scale);
	focus_view(v, NULL);
	if (!v->is_x11 && v->xdg->requested.fullscreen) view_set_fullscreen(v, true);
	if (v->is_x11 && v->xw->fullscreen) view_set_fullscreen(v, true);
	/* mapped already maximized (Wine restoring its last state): take it as a maximize request,
	 * or the window keeps saying it is maximized at its normal size and cannot be dragged */
	if (!v->fullscreen && (v->is_x11 ? v->xw->maximized_horz || v->xw->maximized_vert
	                                 : v->xdg->requested.maximized)) view_set_maximized(v, true);
	refocus_soon(s);
}

static void view_unmap(struct wl_listener *l, void *data) {
	struct view *v = wl_container_of(l, v, unmap);
	struct server *s = v->server;
	v->mapped = false;
	refocus_soon(s);
	if (s->sw.on) switcher_draw(s);
	/* only a popup that never joined the window list takes this path: an X11 window can turn
	 * override-redirect after it mapped as a normal window, and returning here
	 * left it in s->views after it was freed, so the next walk of the list crashed the session */
	if (v->unmanaged && wl_list_empty(&v->link)) {
		/* a menu or popup that took the keyboard (Wine, Battle.net) gives it back to the window
		 * under it; without this typing went nowhere until Alt+Tab */
		struct wlr_surface *surf = view_surface(v);
		if (surf && s->seat->keyboard_state.focused_surface == surf) {
			send_keyboard_focus(s, NULL);
			if (s->focused_view && s->focused_view->mapped && !s->locked) view_activate(s->focused_view, true);
			focus_layer_or_view(s);
		}
		return;
	}
	if (s->cursor_mode != CURSOR_PASSTHROUGH && s->grab_view == v) { s->cursor_mode = CURSOR_PASSTHROUGH; s->grab_view = NULL; }
	if (v->ftl) {
		UNLISTEN(&v->ftl_activate); UNLISTEN(&v->ftl_close); UNLISTEN(&v->ftl_fullscreen); UNLISTEN(&v->ftl_maximize);
		UNLISTEN(&v->ftl_minimize);
		wlr_foreign_toplevel_handle_v1_destroy(v->ftl); v->ftl = NULL;
	}
	v->ftl_out = NULL;
	if (v->minimized) { v->minimized = false; wlr_scene_node_set_enabled(&v->tree->node, true); }
	if (s->hover_view == v) s->hover_view = NULL;
	if (s->last_bar_view == v) s->last_bar_view = NULL;
	if (s->press_view == v) s->press_view = NULL;
	deco_sync(v);
	if (v->ext_ftl) { wlr_ext_foreign_toplevel_handle_v1_destroy(v->ext_ftl); v->ext_ftl = NULL; }
	wl_list_remove(&v->link);
	wl_list_init(&v->link);
	if (s->focused_view == v) {
		s->focused_view = NULL;
		struct view *n;
		wl_list_for_each(n, &s->views, link) if (n->mapped && !n->minimized) { focus_view(n, NULL); break; }
		if (!s->focused_view) focus_layer_or_view(s);
	}
}

static void view_commit(struct wl_listener *l, void *data) {
	struct view *v = wl_container_of(l, v, commit);
	if (!v->is_x11 && v->xdg->base->initial_commit) wlr_xdg_toplevel_set_size(v->xdg, 0, 0);
	if (v->mapped) deco_sync(v);
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
		UNLISTEN(&v->request_minimize);
	} else {
		/* every listener added in new_xwayland_surface: wlroots asserts the surface's signals
		 * are empty when it is destroyed, so one left behind aborts the compositor */
		UNLISTEN(&v->xw_associate); UNLISTEN(&v->xw_dissociate); UNLISTEN(&v->xw_request_configure);
		UNLISTEN(&v->set_title); UNLISTEN(&v->set_app_id); UNLISTEN(&v->xw_override);
		UNLISTEN(&v->request_move); UNLISTEN(&v->request_resize); UNLISTEN(&v->request_maximize);
		UNLISTEN(&v->request_fullscreen); UNLISTEN(&v->request_minimize); UNLISTEN(&v->xw_set_deco);
	}
	if (s->focused_view == v) s->focused_view = NULL;
	if (s->hover_view == v) s->hover_view = NULL;
	if (s->last_bar_view == v) s->last_bar_view = NULL;
	if (s->press_view == v) s->press_view = NULL;
	free(v->deco_title);
	if (s->grab_view == v) { s->grab_view = NULL; s->cursor_mode = CURSOR_PASSTHROUGH; }
	struct output *o;
	wl_list_for_each(o, &s->outputs, link) if (o->tear_view == v) o->tear_view = NULL;
	/* the link is always initialised (make_view), so this is safe even when unmap already
	 * took the view out; a view left in s->views after free crashed later list walks */
	wl_list_remove(&v->link);
	wlr_scene_node_destroy(&v->tree->node);
	free(v);
}

enum { SNAP_NONE, SNAP_MAX, SNAP_LEFT, SNAP_RIGHT };

/* The box a snap zone fills on output o (the frame's title bar counts as part of it). */
static struct wlr_box snap_box(struct output *o, int zone) {
	struct wlr_box b = o->usable;
	if (zone == SNAP_LEFT) b.width /= 2;
	else if (zone == SNAP_RIGHT) { b.x += b.width / 2; b.width -= b.width / 2; }
	return b;
}

static void view_untile(struct view *v) {
	if (!v->tiled) return;
	v->tiled = false;
	view_resize(v, v->saved.width, v->saved.height);
	if (!v->is_x11 && wl_resource_get_version(v->xdg->resource) >= XDG_TOPLEVEL_STATE_TILED_LEFT_SINCE_VERSION)
		wlr_xdg_toplevel_set_tiled(v->xdg, 0);
}

static void view_tile(struct view *v, struct output *o, int zone) {
	if (!v->tiled) {
		struct wlr_box b; view_box(v, &b);
		v->saved = (struct wlr_box){ v->x, v->y, b.width, b.height };
	}
	v->tiled = true;
	v->tile_zone = zone;
	struct wlr_box b = snap_box(o, zone);
	wlr_log(WLR_INFO, "window app_id=%s snapped %s on %s", view_app_id(v),
		zone == SNAP_LEFT ? "left" : "right", o->wlr_output->name);
	int dh = view_has_frame(v) ? TB_H : 0;
	view_place(v, b.x, b.y + dh);
	view_resize(v, b.width, b.height - dh);
	if (!v->is_x11 && wl_resource_get_version(v->xdg->resource) >= XDG_TOPLEVEL_STATE_TILED_LEFT_SINCE_VERSION)
		wlr_xdg_toplevel_set_tiled(v->xdg, WLR_EDGE_TOP | WLR_EDGE_BOTTOM |
		(zone == SNAP_LEFT ? WLR_EDGE_LEFT : WLR_EDGE_RIGHT));
}

/* Which snap zone the cursor is in: an output edge with no other output beyond it. */
static int snap_zone_at(struct server *s, struct output **out) {
	double x = s->cursor->x, y = s->cursor->y;
	struct wlr_output *wo = wlr_output_layout_output_at(s->output_layout, x, y);
	struct output *o = wo ? output_of(s, wo) : NULL;
	*out = o;
	if (!o) return SNAP_NONE;
	struct wlr_box ob; wlr_output_layout_get_box(s->output_layout, wo, &ob);
	const double m = 3;
	bool free_top = !wlr_output_layout_output_at(s->output_layout, x, ob.y - 1);
	bool free_left = !wlr_output_layout_output_at(s->output_layout, ob.x - 1, y);
	bool free_right = !wlr_output_layout_output_at(s->output_layout, ob.x + ob.width, y);
	if (y < ob.y + m && free_top) return SNAP_MAX;
	if (x < ob.x + m && free_left) return SNAP_LEFT;
	if (x >= ob.x + ob.width - m && free_right) return SNAP_RIGHT;
	return SNAP_NONE;
}

static void snap_preview_set(struct server *s, int zone, struct output *o) {
	s->snap_zone = o ? zone : SNAP_NONE;
	if (s->snap_zone == SNAP_NONE) {
		if (s->snap_preview) wlr_scene_node_set_enabled(&s->snap_preview->node, false);
		return;
	}
	/* the accent colour at a quarter strength (premultiplied) */
	const float tint[4] = { 0.239f * 0.25f, 0.910f * 0.25f, 0.784f * 0.25f, 0.25f };
	if (!s->snap_preview) s->snap_preview = wlr_scene_rect_create(s->layers[L_WINDOWS], 1, 1, tint);
	struct wlr_box b = snap_box(o, zone);
	const int pad = 6;
	wlr_scene_node_set_position(&s->snap_preview->node, b.x + pad, b.y + pad);
	wlr_scene_rect_set_size(s->snap_preview, b.width - 2 * pad, b.height - 2 * pad);
	wlr_scene_node_raise_to_top(&s->snap_preview->node);
	wlr_scene_node_set_enabled(&s->snap_preview->node, true);
}

#define OWN_BAR_H 40
#define OWN_BAR_BUTTONS_W 160

static void begin_grab(struct server *s, struct view *v, enum cursor_mode mode, uint32_t edges) {
	if (!v || v->fullscreen) return;
	bool was_max = v->maximized || (v->tiled && mode == CURSOR_MOVE);
	if (v->tiled && mode == CURSOR_MOVE) {
		struct wlr_box tb; view_box(v, &tb);
		double fx = tb.width > 0 ? (s->cursor->x - v->x) / tb.width : 0.5, oy = s->cursor->y - v->y;
		view_untile(v);
		view_place(v, s->cursor->x - v->saved.width * fx, s->cursor->y - oy);
	} else if (v->maximized) {
		/* dragging a maximized window: back to its size, under the cursor where it was grabbed */
		struct wlr_box mb; view_box(v, &mb);
		double fx = mb.width > 0 ? (s->cursor->x - v->x) / mb.width : 0.5, oy = s->cursor->y - v->y;
		view_set_maximized(v, false);
		if (mode == CURSOR_MOVE) view_place(v, s->cursor->x - v->saved.width * fx, s->cursor->y - oy);
	}
	s->grab_view = v; s->cursor_mode = mode;
	struct wlr_box b; view_box(v, &b);
	if (was_max) { b.width = v->saved.width; b.height = v->saved.height; }   /* the client has not resized yet */
	if (mode == CURSOR_MOVE) { s->grab_x = s->cursor->x - v->x; s->grab_y = s->cursor->y - v->y; }
	else {
		s->grab_box = (struct wlr_box){ v->x, v->y, b.width, b.height };
		s->resize_edges = edges;
		s->grab_x = s->cursor->x; s->grab_y = s->cursor->y;
	}
}

static void view_request_move(struct wl_listener *l, void *d) {
	struct view *v = wl_container_of(l, v, request_move);
	if (S.focused_view == v && S.seat->pointer_state.button_count > 0) begin_grab(&S, v, CURSOR_MOVE, 0);
}
static void view_request_resize(struct wl_listener *l, void *d) {
	struct view *v = wl_container_of(l, v, request_resize);
	struct wlr_xdg_toplevel_resize_event *e = d;
	if (S.focused_view == v && S.seat->pointer_state.button_count > 0) begin_grab(&S, v, CURSOR_RESIZE, e->edges);
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
	LISTEN(t->events.request_minimize, &v->request_minimize, view_request_minimize);
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

/* The subsurface tree frees itself when the surface goes first (every X11 client at logout):
 * forget it then, or dissociate destroys it a second time */
static void xw_content_destroy(struct wl_listener *l, void *d) {
	struct view *v = wl_container_of(l, v, xw_content_destroy);
	UNLISTEN(&v->xw_content_destroy);
	v->content = NULL;
}
static void xw_associate(struct wl_listener *l, void *d) {
	struct view *v = wl_container_of(l, v, xw_associate);
	v->surface_listening = true;
	LISTEN(v->xw->surface->events.map, &v->map, view_map);
	LISTEN(v->xw->surface->events.unmap, &v->unmap, view_unmap);
	v->content = wlr_scene_subsurface_tree_create(v->tree, v->xw->surface);
	if (v->content) LISTEN(v->content->node.events.destroy, &v->xw_content_destroy, xw_content_destroy);
	LISTEN(v->xw->surface->events.commit, &v->commit, view_commit);   /* frame follows the size */
}
static void xw_dissociate(struct wl_listener *l, void *d) {
	struct view *v = wl_container_of(l, v, xw_dissociate);
	if (!v->surface_listening) return;
	UNLISTEN(&v->map); UNLISTEN(&v->unmap); UNLISTEN(&v->commit);
	v->surface_listening = false;
	if (v->content) {
		UNLISTEN(&v->xw_content_destroy);
		wlr_scene_node_destroy(&v->content->node); v->content = NULL;
	}
}
static void xw_request_configure(struct wl_listener *l, void *d) {
	struct view *v = wl_container_of(l, v, xw_request_configure);
	struct wlr_xwayland_surface_configure_event *e = d;
	if (!v->mapped || v->unmanaged) { wlr_xwayland_surface_configure(v->xw, e->x, e->y, e->width, e->height); return; }
	if (v->fullscreen || v->maximized) {
		/* answer with the box it already has (a synthetic ConfigureNotify when nothing
		 * changes), so the client stops waiting and the window keeps covering its screen */
		struct wlr_box b; view_box(v, &b);
		wlr_xwayland_surface_configure(v->xw, v->x, v->y, b.width, b.height);
		return;
	}
	/* managed windows keep their place; only the size request is honoured */
	wlr_xwayland_surface_configure(v->xw, v->x, v->y, e->width, e->height);
}
static void xw_override_changed(struct wl_listener *l, void *d) {
	struct view *v = wl_container_of(l, v, xw_override);
	v->unmanaged = v->xw->override_redirect;
}

/* _NET_WM_MOVERESIZE and _NET_WM_STATE from apps that draw their own title bar (Electron:
 * FreeSuite; Chromium; Java): without these, X11 windows could not be dragged or maximized */
static void xw_request_move(struct wl_listener *l, void *d) {
	struct view *v = wl_container_of(l, v, request_move);
	/* only while a button is held: Wine (Battle.net) can ask after a quick click is already over,
	 * and the window then followed the pointer until the next click */
	if (v->mapped && !v->unmanaged && S.seat->pointer_state.button_count > 0) begin_grab(&S, v, CURSOR_MOVE, 0);
}
static void xw_request_resize(struct wl_listener *l, void *d) {
	struct view *v = wl_container_of(l, v, request_resize);
	struct wlr_xwayland_resize_event *e = d;
	if (v->mapped && !v->unmanaged && S.seat->pointer_state.button_count > 0) begin_grab(&S, v, CURSOR_RESIZE, e->edges);
}
static void xw_request_maximize(struct wl_listener *l, void *d) {
	struct view *v = wl_container_of(l, v, request_maximize);
	if (!v->mapped || v->unmanaged) return;
	view_set_maximized(v, v->xw->maximized_horz || v->xw->maximized_vert);
}
static void xw_request_fullscreen(struct wl_listener *l, void *d) {
	struct view *v = wl_container_of(l, v, request_fullscreen);
	if (!v->mapped || v->unmanaged) return;
	view_set_fullscreen(v, v->xw->fullscreen);
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
	LISTEN(x->events.request_move, &v->request_move, xw_request_move);
	LISTEN(x->events.request_resize, &v->request_resize, xw_request_resize);
	LISTEN(x->events.request_maximize, &v->request_maximize, xw_request_maximize);
	LISTEN(x->events.request_fullscreen, &v->request_fullscreen, xw_request_fullscreen);
	LISTEN(x->events.request_minimize, &v->request_minimize, xw_request_minimize);
	LISTEN(x->events.set_decorations, &v->xw_set_deco, xw_set_deco);
}

static void xwayland_cursor(struct server *s) {
	if (!s->xwayland) return;
	struct wlr_xcursor *xc = wlr_xcursor_manager_get_xcursor(s->xcursor, "default", 1);
	if (xc && xc->image_count > 0) {
		struct wlr_xcursor_image *im = xc->images[0];
		wlr_xwayland_set_cursor(s->xwayland, wlr_xcursor_image_get_buffer(im), im->hotspot_x, im->hotspot_y);
	}
}

static void xwayland_ready(struct wl_listener *l, void *data) {
	struct server *s = wl_container_of(l, s, xwayland_ready);
	wlr_xwayland_set_seat(s->xwayland, s->seat);
	s->xwayland_up = true;
	xwayland_cursor(s);
	wlr_log(WLR_INFO, "XWayland ready on %s", s->xwayland->display_name);
}

/* ---------- decorations, activation, tearing, idle ---------- */

static void deco_mark_ssd(struct wlr_xdg_toplevel *t) {
	struct wlr_scene_tree *tree = t->base->data;
	struct view *v = tree ? tree->node.data : NULL;
	if (v && !v->ssd) { v->ssd = true; deco_sync(v); }
}
static void deco_mode(struct wl_listener *l, void *d) {
	struct deco *dc = wl_container_of(l, dc, mode);
	deco_mark_ssd(dc->wlr->toplevel);
	if (dc->wlr->toplevel->base->initialized)
		wlr_xdg_toplevel_decoration_v1_set_mode(dc->wlr, WLR_XDG_TOPLEVEL_DECORATION_V1_MODE_SERVER_SIDE);
}
static void deco_commit(struct wl_listener *l, void *d) {
	struct deco *dc = wl_container_of(l, dc, commit);
	if (!dc->wlr->toplevel->base->initial_commit) return;
	UNLISTEN(&dc->commit); dc->waiting = false;
	deco_mark_ssd(dc->wlr->toplevel);
	wlr_xdg_toplevel_decoration_v1_set_mode(dc->wlr, WLR_XDG_TOPLEVEL_DECORATION_V1_MODE_SERVER_SIDE);
}
static void deco_destroy(struct wl_listener *l, void *d) {
	struct deco *dc = wl_container_of(l, dc, destroy);
	if (dc->waiting) UNLISTEN(&dc->commit);
	UNLISTEN(&dc->mode); UNLISTEN(&dc->destroy); free(dc);
}
/* Server side means "the compositor draws the frame": deco_sync draws it (Qt apps such as Nova
 * ask for it; GTK draws its own and never asks). */
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
	struct server *s = ls->server;
	if (s->lock_focus == ls->wlr->surface) {
		/* its monitor went away: give the keyboard to another lock surface, never to a window */
		s->lock_focus = NULL;
		struct wlr_session_lock_surface_v1 *x;
		if (s->lock) wl_list_for_each(x, &s->lock->surfaces, link)
			if (x != ls->wlr) { s->lock_focus = x->surface; break; }
		focus_layer_or_view(s);
	}
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
	/* a monitor that reconnects while locked gets a new surface: locked was already sent */
	if (surfaces >= outs && !s->lock_sent) {
		s->lock_sent = true;
		wlr_session_lock_v1_send_locked(s->lock);
		wlr_log(WLR_INFO, "session locked");
	}
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

/* A window or panel that appears or goes away under a still pointer gets the pointer at
 * once: otherwise it only learns where the pointer is on the next motion (Spark Snip's
 * crosshair started where it was the last time). Runs once the loop is idle, after the
 * new surface is in the scene. */
static struct wl_event_source *refocus_src;
static void refocus_idle(void *data) {
	refocus_src = NULL;
	struct server *s = data;
	struct timespec now; clock_gettime(CLOCK_MONOTONIC, &now);
	if (s->cursor_mode == CURSOR_PASSTHROUGH)
		update_cursor_focus(s, (uint32_t)(now.tv_sec * 1000 + now.tv_nsec / 1000000));
}
static void refocus_soon(struct server *s) {
	if (refocus_src) return;
	refocus_src = wl_event_loop_add_idle(wl_display_get_event_loop(s->display), refocus_idle, s);
}
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
	s->lock_sent = false;
	if (!s->locked) {
		s->lock_tree = wlr_scene_tree_create(s->layers[L_LOCK]);
		float black[4] = {0, 0, 0, 1};
		s->lock_rect = wlr_scene_rect_create(s->layers[L_LOCK], 100000, 100000, black);
		wlr_scene_node_lower_to_bottom(&s->lock_rect->node);
		wlr_scene_node_set_position(&s->lock_rect->node, -50000, -50000);
	}
	switcher_close(s, false);
	s->locked = true;
	s->focused_layer = NULL;
	if (s->lock_tree) wlr_scene_node_raise_to_top(&s->lock_tree->node);
	LISTEN(lock->events.new_surface, &lock_new_surface_l, lock_new_surface);
	LISTEN(lock->events.unlock, &lock_unlock_l, lock_unlock);
	LISTEN(lock->events.destroy, &lock_destroy_l, lock_destroy);
	if (wl_list_empty(&s->outputs)) wlr_session_lock_v1_send_locked(lock);
}

/* ---------- input ---------- */

static int64_t boot_ms(void) {
	struct timespec t; clock_gettime(CLOCK_BOOTTIME, &t);
	return (int64_t)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}

/* Screens off without leaving the layout: windows keep their places and the panels their
 * screens. Outputs that were already off (by config) are left alone. */
static void screens_power(struct server *s, bool on) {
	if (s->screens_off == !on) return;
	s->screens_off = !on;
	struct output *o;
	wl_list_for_each(o, &s->outputs, link) {
		if (on ? !o->dpms_off : !o->wlr_output->enabled) continue;
		struct wlr_output_state st; wlr_output_state_init(&st);
		wlr_output_state_set_enabled(&st, on);
		if (!wlr_output_commit_state(o->wlr_output, &st))
			wlr_log(WLR_ERROR, "could not turn %s %s", o->wlr_output->name, on ? "on" : "off");
		else o->dpms_off = !on;
		wlr_output_state_finish(&st);
	}
	wlr_log(WLR_INFO, "screens %s", on ? "on" : "off (idle)");
	publish_output_config(s);             /* wlr-randr and Spark Settings see the real state */
}

static void notify_activity(struct server *s) {
	wlr_idle_notifier_v1_notify_activity(s->idle, s->seat);
	s->idle_since = boot_ms();
	s->idle_lock_done = s->idle_suspend_done = false;
	if (s->screens_off) screens_power(s, true);
}

#define IDLE_TICK_MS 5000
static int idle_tick(void *data) {
	struct server *s = data;
	int64_t now = boot_ms();
	/* a long gap between ticks means the machine slept: start counting again, or it would
	 * suspend again the moment it wakes */
	if (now - s->idle_tick_at > 4 * IDLE_TICK_MS) { s->idle_since = now; s->idle_suspend_done = false; }
	s->idle_tick_at = now;
	if (s->inhibitors > 0) s->idle_since = now;       /* a video or a game holds the screen on */
	/* apps that ask over D-Bus (org.freedesktop.ScreenSaver: Steam, Chrome, Discord): the
	 * shell answers them and keeps this file while any inhibit is held */
	{
		static char flag[512];
		if (!flag[0]) {
			const char *rt = getenv("XDG_RUNTIME_DIR");
			snprintf(flag, sizeof flag, "%s/spark-wl/idle-inhibit", rt ? rt : "/tmp");
		}
		if (access(flag, F_OK) == 0) s->idle_since = now;
	}
	/* so does any fullscreen window: a game played with a controller sends no input here */
	struct view *fv;
	wl_list_for_each(fv, &s->views, link)
		if (fv->mapped && fv->fullscreen && !fv->minimized) { s->idle_since = now; break; }
	int64_t idle = (now - s->idle_since) / 1000;
	int lock = s->idle_cfg.lock, off = s->idle_cfg.screen_off, sus = s->idle_cfg.suspend;
	/* locked: the lock screen goes dark after a minute, sooner if the setting says so */
	if (s->locked && off > 60) off = 60;
	if (lock > 0 && idle >= lock && !s->idle_lock_done && !s->locked) {
		s->idle_lock_done = true;
		wlr_log(WLR_INFO, "idle %llds: locking", (long long)idle);
		spawn("loginctl lock-session");
	}
	if (off > 0 && idle >= off && !s->screens_off) screens_power(s, false);
	if (sus > 0 && idle >= sus && !s->idle_suspend_done) {
		s->idle_suspend_done = true;
		wlr_log(WLR_INFO, "idle %llds: suspending", (long long)idle);
		spawn("systemctl suspend");
	}
	wl_event_source_timer_update(s->idle_timer, IDLE_TICK_MS);
	return 0;
}

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
	if (s->press_view && s->cursor_mode == CURSOR_PASSTHROUGH &&
	    fabs(s->cursor->x - s->press_x) + fabs(s->cursor->y - s->press_y) > 8) {
		struct view *pv = s->press_view;
		s->press_view = NULL;
		begin_grab(s, pv, CURSOR_MOVE, 0);
	}
	if (s->cursor_mode == CURSOR_MOVE && s->grab_view) {
		view_place(s->grab_view, s->cursor->x - s->grab_x, s->cursor->y - s->grab_y);
		struct output *so; int zone = snap_zone_at(s, &so);
		if (zone != s->snap_zone) snap_preview_set(s, zone, so);
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
	struct wlr_seat_pointer_state *ps = &s->seat->pointer_state;
	if (ps->button_count > 0 && ps->focused_surface && ps->focused_surface == s->hold_surface) {
		/* a drag that started in a window keeps going to it, even over a popup or panel above */
		wlr_seat_pointer_notify_motion(s->seat, time, s->cursor->x - s->hold_dx, s->cursor->y - s->hold_dy);
		return;
	}
	struct wlr_surface *surf; double sx, sy;
	struct view *v = pick(s, s->cursor->x, s->cursor->y, &surf, &sx, &sy);
	(void)v;
	int part = HIT_NONE;
	struct view *dv = surf ? NULL : deco_at(s, s->cursor->x, s->cursor->y, &part);
	deco_set_hover(s, dv, part);
	if (!surf) {
		set_cursor_name(s, dv && part == HIT_EDGE ? edge_cursor(deco_edges(dv, s->cursor->x, s->cursor->y)) : "default");
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
	if (e->state == WL_POINTER_BUTTON_STATE_PRESSED) s->tap_keycode = 0;   /* Super+drag is not a tap */
	if (e->state == WL_POINTER_BUTTON_STATE_PRESSED && s->seat->pointer_state.button_count == 0) {
		struct wlr_seat_pointer_state *ps = &s->seat->pointer_state;
		s->hold_surface = ps->focused_surface;
		s->hold_dx = s->cursor->x - ps->sx;
		s->hold_dy = s->cursor->y - ps->sy;
	}
	if (e->state == WL_POINTER_BUTTON_STATE_RELEASED) s->press_view = NULL;
	if (e->state == WL_POINTER_BUTTON_STATE_RELEASED && s->cursor_mode != CURSOR_PASSTHROUGH) {
		if (s->cursor_mode == CURSOR_MOVE && s->grab_view && s->snap_zone != SNAP_NONE) {
			struct output *so; int zone = snap_zone_at(s, &so);
			if (zone != SNAP_NONE && so) {
				struct view *gv = s->grab_view;
				if (zone == SNAP_MAX) {
					/* maximize on the output under the cursor: move it there first */
					struct wlr_box ub = so->usable;
					if (view_output(gv) != so->wlr_output) view_place(gv, ub.x, ub.y);
					view_set_maximized(gv, true);
				} else view_tile(gv, so, zone);
			}
		}
		snap_preview_set(s, SNAP_NONE, NULL);
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
		int part = HIT_NONE;
		struct view *dv = surf ? NULL : deco_at(s, s->cursor->x, s->cursor->y, &part);
		if (dv) {
			focus_view(dv, NULL);
			if (dv->minimized) return;
			if (e->button == BTN_LEFT) {
				if (part == HIT_BAR) {
					if (s->last_bar_view == dv && e->time_msec - s->last_bar_time < 400) {
						s->last_bar_view = NULL;
						view_set_maximized(dv, !dv->maximized);
					} else {
						s->last_bar_view = dv; s->last_bar_time = e->time_msec;
						if (dv->maximized) { s->press_view = dv; s->press_x = s->cursor->x; s->press_y = s->cursor->y; }
						else begin_grab(s, dv, CURSOR_MOVE, 0);
					}
				} else if (part == HIT_MIN) view_set_minimized(dv, true);
				else if (part == HIT_MAX) view_set_maximized(dv, !dv->maximized);
				else if (part == HIT_CLOSE) view_close(dv);
				else if (part == HIT_EDGE) begin_grab(s, dv, CURSOR_RESIZE, deco_edges(dv, s->cursor->x, s->cursor->y));
			} else if (e->button == BTN_MIDDLE && part == HIT_BAR) {
				view_set_minimized(dv, true);
			}
			return; /* the frame is the compositor's: no client sees this click */
		}
		if (v) {
			focus_view(v, surf);
			/* an X11 app that draws its own title bar (Battle.net): Wine does not move a maximized
			   window, so a drag from its top strip restores and moves it, like a Spark title bar.
			   The click still reaches the app; the move starts only after 8 px of motion. The
			   right end is left alone (its own minimize/maximize/close buttons). */
			struct wlr_box vb; view_box(v, &vb);
			if (e->button == BTN_LEFT && v->is_x11 && v->x11_own_frame && v->maximized &&
			    s->cursor->y - v->y < OWN_BAR_H && s->cursor->x < v->x + vb.width - OWN_BAR_BUTTONS_W) {
				s->press_view = v; s->press_x = s->cursor->x; s->press_y = s->cursor->y;
			}
		} else if (surf) {
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

/* ---------- Alt+Tab switcher ----------
 * Hold Alt, press Tab to step through the windows (Shift+Tab or the arrows go back), let go of
 * Alt to switch, Escape to stay. The compositor draws it: a panel of cards (app icon and name)
 * under the selected window's full title, centred on the screen in use. */

#define ALTTAB_MAX 40
#define ALTTAB_TW 132
#define ALTTAB_TH 120
#define ALTTAB_PAD 18
#define ALTTAB_HEAD 40
#define ALTTAB_ICON 56

/* snprintf for paths and short strings: false (and nothing useful in out) when it doesn't fit */
__attribute__((format(printf, 3, 4)))
static bool pathf(char *out, size_t n, const char *fmt, ...) {
	va_list ap; va_start(ap, fmt);
	int r = vsnprintf(out, n, fmt, ap);
	va_end(ap);
	return r >= 0 && (size_t)r < n;
}

static int switcher_list(struct server *s, struct view **out) {
	int n = 0;
	struct view *v;
	wl_list_for_each(v, &s->views, link)
		if (v->mapped && !v->unmanaged && n < ALTTAB_MAX) out[n++] = v;
	return n;
}

/* app name and icon file for an app_id, from its .desktop file and the icon themes; cached */
struct sw_app { struct wl_list link; char *id, *name, *icon; };
static struct wl_list sw_apps = { &sw_apps, &sw_apps };

static int data_dirs(char dirs[][256], int max) {
	int n = 0;
	const char *home = getenv("HOME"), *xh = getenv("XDG_DATA_HOME");
	if (xh && *xh) pathf(dirs[n++], 256, "%s", xh);
	else if (home) pathf(dirs[n++], 256, "%s/.local/share", home);
	const char *xd = getenv("XDG_DATA_DIRS");
	char buf[2048];
	pathf(buf, sizeof buf, "%s", xd && *xd ? xd : "/usr/local/share:/usr/share");
	for (char *save = NULL, *t = strtok_r(buf, ":", &save); t && n < max; t = strtok_r(NULL, ":", &save))
		if (*t) pathf(dirs[n++], 256, "%s", t);
	/* Flatpak apps (Steam): the session doesn't always pass XDG_DATA_DIRS to the compositor */
	char fp[2][256] = { "", "/var/lib/flatpak/exports/share" };
	if (home) pathf(fp[0], 256, "%s/.local/share/flatpak/exports/share", home);
	for (int f = 0; f < 2; f++) {
		bool have = !fp[f][0];
		for (int i = 0; i < n && !have; i++) have = !strcmp(dirs[i], fp[f]);
		if (!have && n < max) pathf(dirs[n++], 256, "%s", fp[f]);
	}
	return n;
}

/* reads Name= and Icon= of [Desktop Entry]; with wmclass set, only if StartupWMClass matches */
static bool desktop_read(const char *path, const char *wmclass, char *name, char *icon) {
	FILE *f = fopen(path, "r");
	if (!f) return false;
	char line[512], nm[128] = "", ic[256] = "", wc[128] = "";
	bool in = false, hidden = false;
	while (fgets(line, sizeof line, f)) {
		line[strcspn(line, "\r\n")] = 0;
		if (line[0] == '[') { if (in) break; in = !strcmp(line, "[Desktop Entry]"); continue; }
		if (!in) continue;
		if (!strncmp(line, "Name=", 5) && !nm[0]) pathf(nm, sizeof nm, "%s", line + 5);
		else if (!strncmp(line, "Icon=", 5)) pathf(ic, sizeof ic, "%s", line + 5);
		else if (!strncmp(line, "StartupWMClass=", 15)) pathf(wc, sizeof wc, "%s", line + 15);
		else if (!strcmp(line, "NoDisplay=true") || !strcmp(line, "Hidden=true")) hidden = true;
	}
	fclose(f);
	if (wmclass && (hidden || strcasecmp(wc, wmclass))) return false;
	if (nm[0]) pathf(name, 128, "%s", nm);
	if (ic[0]) pathf(icon, 256, "%s", ic);
	return true;
}

static bool icon_find(char dirs[][256], int nd, const char *icon, char *out) {
	if (!icon[0]) return false;
	if (icon[0] == '/') { pathf(out, 512, "%s", icon); return access(out, R_OK) == 0; }
	static const char *themes[] = { "SparkOS", "breeze-dark", "breeze", "hicolor" };
	static const char *pats[] = { "%s/icons/%s/apps/scalable/%s.svg", "%s/icons/%s/apps/48/%s.svg",
		"%s/icons/%s/scalable/apps/%s.svg", "%s/icons/%s/256x256/apps/%s.png", "%s/icons/%s/128x128/apps/%s.png",
		"%s/icons/%s/64x64/apps/%s.png", "%s/icons/%s/48x48/apps/%s.png" };
	for (size_t t = 0; t < sizeof themes / sizeof *themes; t++)
		for (int d = 0; d < nd; d++)
			for (size_t p = 0; p < sizeof pats / sizeof *pats; p++) {
				if (pathf(out, 512, pats[p], dirs[d], themes[t], icon) && access(out, R_OK) == 0) return true;
			}
	for (int d = 0; d < nd; d++) {
		pathf(out, 512, "%s/pixmaps/%s.svg", dirs[d], icon); if (access(out, R_OK) == 0) return true;
		pathf(out, 512, "%s/pixmaps/%s.png", dirs[d], icon); if (access(out, R_OK) == 0) return true;
	}
	return false;
}

static struct sw_app *sw_app_for(const char *id) {
	struct sw_app *a;
	wl_list_for_each(a, &sw_apps, link) if (!strcmp(a->id, id)) return a;
	char dirs[16][256]; int nd = data_dirs(dirs, 16);
	char name[128] = "", icon[256] = "", path[600];
	bool found = false;
	if (*id) {
		char low[128]; pathf(low, sizeof low, "%s", id);
		for (char *c = low; *c; c++) *c = tolower((unsigned char)*c);
		for (int d = 0; d < nd && !found; d++) {
			pathf(path, sizeof path, "%s/applications/%s.desktop", dirs[d], id);
			found = desktop_read(path, NULL, name, icon);
			if (!found) { pathf(path, sizeof path, "%s/applications/%s.desktop", dirs[d], low); found = desktop_read(path, NULL, name, icon); }
		}
		/* X11 apps: the window class, matched against StartupWMClass */
		for (int d = 0; d < nd && !found; d++) {
			char ad[300]; pathf(ad, sizeof ad, "%s/applications", dirs[d]);
			DIR *dir = opendir(ad);
			if (!dir) continue;
			struct dirent *e;
			while (!found && (e = readdir(dir))) {
				size_t l = strlen(e->d_name);
				if (l < 9 || strcmp(e->d_name + l - 8, ".desktop")) continue;
				pathf(path, sizeof path, "%s/%s", ad, e->d_name);
				found = desktop_read(path, id, name, icon);
			}
			closedir(dir);
		}
		if (!icon[0]) pathf(icon, sizeof icon, "%s", low);
	}
	char file[512] = "";
	if (!icon_find(dirs, nd, icon, file)) file[0] = 0;
	a = calloc(1, sizeof *a);
	a->id = strdup(id);
	a->name = strdup(name[0] ? name : (*id ? id : "Window"));
	a->icon = strdup(file);
	wl_list_insert(&sw_apps, &a->link);
	return a;
}

static void rrect(cairo_t *cr, double x, double y, double w, double h, double r) {
	cairo_new_sub_path(cr);
	cairo_arc(cr, x + w - r, y + r, r, -M_PI / 2, 0);
	cairo_arc(cr, x + w - r, y + h - r, r, 0, M_PI / 2);
	cairo_arc(cr, x + r, y + h - r, r, M_PI / 2, M_PI);
	cairo_arc(cr, x + r, y + r, r, M_PI, 3 * M_PI / 2);
	cairo_close_path(cr);
}

static void sw_text(cairo_t *cr, const char *text, const char *font, double x, double y, int w, uint32_t rgb, double a, bool slip) {
	PangoLayout *pl = pango_cairo_create_layout(cr);
	PangoFontDescription *fd = pango_font_description_from_string(font);
	pango_layout_set_font_description(pl, fd);
	pango_font_description_free(fd);
	pango_layout_set_text(pl, text, -1);
	pango_layout_set_width(pl, w * PANGO_SCALE);
	pango_layout_set_ellipsize(pl, PANGO_ELLIPSIZE_END);
	pango_layout_set_alignment(pl, PANGO_ALIGN_CENTER);
	if (slip) {
		ink(cr, 0xff2e88, 0.55); cairo_move_to(cr, x - 2, y); pango_cairo_show_layout(cr, pl);
		ink(cr, 0x22d8ff, 0.55); cairo_move_to(cr, x + 2, y); pango_cairo_show_layout(cr, pl);
	}
	ink(cr, rgb, a); cairo_move_to(cr, x, y); pango_cairo_show_layout(cr, pl);
	g_object_unref(pl);
}

static void sw_icon(cairo_t *cr, struct sw_app *a, double x, double y, double sz, bool dim) {
	bool drawn = false;
	size_t l = strlen(a->icon);
	cairo_save(cr);
	if (l > 4 && !strcmp(a->icon + l - 4, ".svg")) {
		RsvgHandle *h = rsvg_handle_new_from_file(a->icon, NULL);
		if (h) {
			RsvgRectangle vp = { x, y, sz, sz };
			if (dim) cairo_push_group(cr);
			drawn = rsvg_handle_render_document(h, cr, &vp, NULL);
			if (dim) { cairo_pop_group_to_source(cr); cairo_paint_with_alpha(cr, 0.5); }
			g_object_unref(h);
		}
	} else if (l > 4) {
		cairo_surface_t *img = cairo_image_surface_create_from_png(a->icon);
		int iw = cairo_image_surface_get_width(img), ih = cairo_image_surface_get_height(img);
		if (cairo_surface_status(img) == CAIRO_STATUS_SUCCESS && iw > 0 && ih > 0) {
			cairo_translate(cr, x, y);
			cairo_scale(cr, sz / iw, sz / ih);
			cairo_set_source_surface(cr, img, 0, 0);
			cairo_pattern_set_filter(cairo_get_source(cr), CAIRO_FILTER_GOOD);
			cairo_paint_with_alpha(cr, dim ? 0.5 : 1);
			drawn = true;
		}
		cairo_surface_destroy(img);
	}
	cairo_restore(cr);
	if (drawn) return;
	/* no icon: the app's first letter on a flat tile */
	ink(cr, 0x12292c, 1); rrect(cr, x, y, sz, sz, 3); cairo_fill(cr);
	char letter[8] = "?";
	if (a->name[0]) { gunichar c = g_unichar_toupper(g_utf8_get_char(a->name)); letter[g_unichar_to_utf8(c, letter)] = 0; }
	sw_text(cr, letter, "Cascadia Mono, monospace Bold 22", x, y + sz / 2 - 16, (int)sz, 0x3de8c8, dim ? 0.5 : 1, false);
}

static void switcher_draw(struct server *s) {
	struct view *list[ALTTAB_MAX];
	int n = switcher_list(s, list);
	if (!s->sw.on || n == 0) { if (s->sw.buf) wlr_scene_node_set_enabled(&s->sw.buf->node, false); return; }
	if (s->sw.sel >= n) s->sw.sel = n - 1;
	if (s->sw.sel < 0) s->sw.sel = 0;
	struct wlr_output *wo = s->focused_output ? s->focused_output : output_at_cursor(s);
	if (!wo) return;
	struct wlr_box ob; wlr_output_layout_get_box(s->output_layout, wo, &ob);
	int maxcols = (ob.width - 80 - 2 * ALTTAB_PAD) / ALTTAB_TW;
	if (maxcols < 1) maxcols = 1;
	int cols = n < maxcols ? n : maxcols, rows = (n + cols - 1) / cols;
	int w = cols * ALTTAB_TW + 2 * ALTTAB_PAD, h = ALTTAB_HEAD + rows * ALTTAB_TH + 2 * ALTTAB_PAD;
	if (w < 360) w = 360;
	float scale = wo->scale > 0 ? wo->scale : 1;
	int pw = (int)ceilf(w * scale), ph = (int)ceilf(h * scale);
	struct cbuf *c = calloc(1, sizeof *c);
	c->cs = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, pw, ph);
	wlr_buffer_init(&c->base, &cbuf_impl, pw, ph);
	cairo_t *cr = cairo_create(c->cs);
	cairo_scale(cr, scale, scale);
	/* panel: flat, 1px line, 3px corners */
	ink(cr, 0x04090b, 0.96); rrect(cr, 0, 0, w, h, 3); cairo_fill(cr);
	ink(cr, 0x1f6a66, 1); cairo_set_line_width(cr, 1); rrect(cr, 0.5, 0.5, w - 1, h - 1, 3); cairo_stroke(cr);
	struct view *selv = list[s->sw.sel];
	const char *title = selv->is_x11 ? selv->xw->title : selv->xdg->title;
	if (!title || !*title) title = sw_app_for(view_app_id(selv))->name;
	sw_text(cr, title, "Cascadia Mono, monospace Bold 11", ALTTAB_PAD, ALTTAB_PAD + 2, w - 2 * ALTTAB_PAD, 0xd4f1ec, 1, true);
	int x0 = (w - cols * ALTTAB_TW) / 2;
	for (int i = 0; i < n; i++) {
		struct view *v = list[i];
		struct sw_app *a = sw_app_for(view_app_id(v));
		double tx = x0 + (i % cols) * ALTTAB_TW, ty = ALTTAB_PAD + ALTTAB_HEAD + (i / cols) * ALTTAB_TH;
		bool sel = i == s->sw.sel;
		if (sel) {
			ink(cr, 0x12292c, 1); rrect(cr, tx + 4, ty + 2, ALTTAB_TW - 8, ALTTAB_TH - 4, 3); cairo_fill(cr);
			cairo_set_line_width(cr, 1.5);
			ink(cr, 0xff2e88, 0.8); rrect(cr, tx + 2.75, ty + 2.75, ALTTAB_TW - 8, ALTTAB_TH - 4, 3); cairo_stroke(cr);
			ink(cr, 0x22d8ff, 0.8); rrect(cr, tx + 5.25, ty + 2.75, ALTTAB_TW - 8, ALTTAB_TH - 4, 3); cairo_stroke(cr);
			ink(cr, 0x3de8c8, 1); rrect(cr, tx + 4.75, ty + 2.75, ALTTAB_TW - 9.5, ALTTAB_TH - 5.5, 3); cairo_stroke(cr);
		}
		sw_icon(cr, a, tx + (ALTTAB_TW - ALTTAB_ICON) / 2.0, ty + 16, ALTTAB_ICON, v->minimized);
		sw_text(cr, a->name, "Cascadia Mono, monospace Bold 9", tx + 10, ty + 16 + ALTTAB_ICON + 14, ALTTAB_TW - 20,
			sel ? 0xd4f1ec : 0x6f9f98, 1, false);
	}
	cairo_destroy(cr);
	cairo_surface_flush(c->cs);
	if (!s->sw.buf) s->sw.buf = wlr_scene_buffer_create(s->layers[L_OVERLAY], NULL);
	wlr_scene_buffer_set_buffer(s->sw.buf, &c->base);
	wlr_scene_buffer_set_dest_size(s->sw.buf, w, h);
	wlr_buffer_drop(&c->base);
	wlr_scene_node_set_position(&s->sw.buf->node, ob.x + (ob.width - w) / 2, ob.y + (ob.height - h) / 2);
	wlr_scene_node_raise_to_top(&s->sw.buf->node);
	wlr_scene_node_set_enabled(&s->sw.buf->node, true);
}

static void switcher_close(struct server *s, bool commit) {
	if (!s->sw.on) return;
	s->sw.on = false;
	if (s->sw.buf) wlr_scene_node_set_enabled(&s->sw.buf->node, false);
	if (!commit || s->locked) return;
	struct view *list[ALTTAB_MAX];
	int n = switcher_list(s, list);
	if (s->sw.sel < 0 || s->sw.sel >= n) return;
	struct view *v = list[s->sw.sel];
	const char *t = v->is_x11 ? v->xw->title : v->xdg->title;
	wlr_log(WLR_INFO, "switcher: picked app_id=%s title=%s", view_app_id(v), t ? t : "");
	v->desktop_hidden = false;
	if (v->minimized) view_set_minimized(v, false);
	else focus_view(v, NULL);
}

static void switcher_step(struct server *s, int d) {
	struct view *list[ALTTAB_MAX];
	int n = switcher_list(s, list);
	if (n == 0) { switcher_close(s, false); return; }
	s->sw.sel = ((s->sw.sel + d) % n + n) % n;
	switcher_draw(s);
}

/* opened by a focus-next bind held with a modifier; false when there's nothing to switch to */
static bool switcher_open(struct server *s, uint32_t mods, int dir) {
	struct view *list[ALTTAB_MAX];
	int n = switcher_list(s, list);
	if (n < 2) return false;
	s->sw.on = true;
	s->sw.mods = mods;
	/* the focused window is first unless something else (a menu, the shell) has the keyboard */
	s->sw.sel = list[0] == s->focused_view ? (dir > 0 ? 1 : n - 1) : (dir > 0 ? 0 : n - 1);
	switcher_draw(s);
	return true;
}

/* a key while the switcher is open; every key is the switcher's until it closes */
static void switcher_key(struct server *s, xkb_keysym_t sym, uint32_t mods) {
	switch (sym) {
	case XKB_KEY_Tab: switcher_step(s, (mods & WLR_MODIFIER_SHIFT) ? -1 : 1); break;
	case XKB_KEY_ISO_Left_Tab: case XKB_KEY_Left: case XKB_KEY_Up: switcher_step(s, -1); break;
	case XKB_KEY_Right: case XKB_KEY_Down: switcher_step(s, 1); break;
	case XKB_KEY_Escape: switcher_close(s, false); break;
	case XKB_KEY_Return: case XKB_KEY_KP_Enter: case XKB_KEY_space: switcher_close(s, true); break;
	default: break;
	}
}

static bool run_action(struct server *s, struct bind *b);

static bool handle_key(struct server *s, struct keyboard *k, uint32_t keycode, enum wl_keyboard_key_state st) {
	if (st == WL_KEYBOARD_KEY_STATE_RELEASED) {
		if (s->tap_keycode == keycode) {
			s->tap_keycode = 0;
			if (!s->locked) {
				xkb_keysym_t tsym = xkb_state_key_get_one_sym(k->wlr->xkb_state, keycode + 8);
				struct bind *b;
				wl_list_for_each(b, &s->binds, link)
					if (b->sym == tsym && b->mods == 0 && (b->action == A_NONE || run_action(s, b))) break;
			}
			return false;      /* the client saw the press, so it gets the release too */
		}
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
	s->tap_keycode = 0;
	if (s->locked) { switcher_close(s, false); return false; }
	if (s->sw.on) {
		for (int i = 0; i < n; i++) switcher_key(s, syms[i], mods);
		if (k->nhandled < 16) k->handled[k->nhandled++] = keycode;
		return true;
	}
	/* Alt+Shift+Tab opens the switcher on the last window */
	for (int i = 0; i < n; i++)
		if (syms[i] == XKB_KEY_ISO_Left_Tab && (mods & (WLR_MODIFIER_LOGO | WLR_MODIFIER_ALT | WLR_MODIFIER_CTRL)) == WLR_MODIFIER_ALT &&
		    switcher_open(s, WLR_MODIFIER_ALT, -1)) {
			if (k->nhandled < 16) k->handled[k->nhandled++] = keycode;
			return true;
		}
	for (int i = 0; i < n; i++) {
		if (syms[i] != XKB_KEY_Super_L && syms[i] != XKB_KEY_Super_R) continue;
		struct bind *b;
		wl_list_for_each(b, &s->binds, link)
			if (b->sym == syms[i] && b->mods == 0) { s->tap_keycode = keycode; break; }
		return false;      /* still a modifier: Super+Tab and the rest keep working */
	}
	for (int i = 0; i < n; i++) {
		xkb_keysym_t sym = xkb_keysym_to_lower(syms[i]);
		struct bind *b;
		wl_list_for_each(b, &s->binds, link) {
			if (b->sym != sym || b->mods != (mods & (WLR_MODIFIER_LOGO | WLR_MODIFIER_ALT | WLR_MODIFIER_CTRL | WLR_MODIFIER_SHIFT))) continue;
			if (b->action == A_NONE) return false;    /* "bind KEY none": the key goes to the app */
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
	if (k->server->sw.on && !(wlr_keyboard_get_modifiers(k->wlr) & k->server->sw.mods)) switcher_close(k->server, true);
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
	switcher_close(k->server, true);     /* its Alt can't come up any more */
	UNLISTEN(&k->modifiers); UNLISTEN(&k->key); UNLISTEN(&k->destroy);
	wl_list_remove(&k->link); free(k);
}

static void keyboard_apply_cfg(struct server *s, struct wlr_keyboard *kb) {
	struct kb_cfg *c = &s->kb_cfg;
	struct xkb_context *ctx = xkb_context_new(XKB_CONTEXT_NO_FLAGS);
	/* unset fields: the XKB_DEFAULT_* environment variables apply */
	struct xkb_rule_names names = { .layout = c->layout[0] ? c->layout : NULL,
		.variant = c->layout[0] ? c->variant : NULL, .options = c->options[0] ? c->options : NULL };
	struct xkb_keymap *km = xkb_keymap_new_from_names(ctx, &names, XKB_KEYMAP_COMPILE_NO_FLAGS);
	if (!km) {
		wlr_log(WLR_ERROR, "keyboard layout '%s' variant '%s' not found, using the default", c->layout, c->variant);
		km = xkb_keymap_new_from_names(ctx, &(struct xkb_rule_names){0}, XKB_KEYMAP_COMPILE_NO_FLAGS);
	}
	if (km) wlr_keyboard_set_keymap(kb, km);
	xkb_keymap_unref(km); xkb_context_unref(ctx);
	wlr_keyboard_set_repeat_info(kb, c->rate, c->delay);
}

static void add_keyboard_ex(struct server *s, struct wlr_keyboard *kb, bool is_virtual) {
	if (!is_virtual) keyboard_apply_cfg(s, kb);
	else if (!kb->keymap) {
		struct xkb_context *ctx = xkb_context_new(XKB_CONTEXT_NO_FLAGS);
		struct xkb_keymap *km = xkb_keymap_new_from_names(ctx, &(struct xkb_rule_names){0}, XKB_KEYMAP_COMPILE_NO_FLAGS);
		wlr_keyboard_set_keymap(kb, km);
		xkb_keymap_unref(km); xkb_context_unref(ctx);
		wlr_keyboard_set_repeat_info(kb, 25, 600);
	}
	struct keyboard *k = calloc(1, sizeof *k);
	k->server = s; k->wlr = kb; k->is_virtual = is_virtual;
	LISTEN(kb->events.modifiers, &k->modifiers, kb_modifiers);
	LISTEN(kb->events.key, &k->key, kb_key);
	LISTEN(kb->base.events.destroy, &k->destroy, kb_destroy);
	wlr_seat_set_keyboard(s->seat, kb);
	wl_list_insert(&s->keyboards, &k->link);
}

static void add_keyboard(struct server *s, struct wlr_keyboard *kb) { add_keyboard_ex(s, kb, false); }

static void pointer_apply_cfg(struct server *s, struct wlr_input_device *d) {
	if (!wlr_input_device_is_libinput(d)) return;
	struct libinput_device *h = wlr_libinput_get_device_handle(d);
	if (!h) return;
	bool touchpad = libinput_device_config_tap_get_finger_count(h) > 0;
	struct ptr_cfg *c = touchpad ? &s->touchpad_cfg : &s->mouse_cfg;
	if (!isnan(c->accel) && libinput_device_config_accel_is_available(h))
		libinput_device_config_accel_set_speed(h, c->accel);
	if (c->flat >= 0 && libinput_device_config_accel_is_available(h))
		libinput_device_config_accel_set_profile(h, c->flat ? LIBINPUT_CONFIG_ACCEL_PROFILE_FLAT
		                                                     : LIBINPUT_CONFIG_ACCEL_PROFILE_ADAPTIVE);
	if (c->natural >= 0 && libinput_device_config_scroll_has_natural_scroll(h))
		libinput_device_config_scroll_set_natural_scroll_enabled(h, c->natural);
	if (c->left_handed >= 0 && libinput_device_config_left_handed_is_available(h))
		libinput_device_config_left_handed_set(h, c->left_handed);
	if (touchpad && c->tap >= 0)
		libinput_device_config_tap_set_enabled(h, c->tap ? LIBINPUT_CONFIG_TAP_ENABLED : LIBINPUT_CONFIG_TAP_DISABLED);
	if (c->dwt >= 0 && libinput_device_config_dwt_is_available(h))
		libinput_device_config_dwt_set_enabled(h, c->dwt ? LIBINPUT_CONFIG_DWT_ENABLED : LIBINPUT_CONFIG_DWT_DISABLED);
}

static void pointer_destroy(struct wl_listener *l, void *data) {
	struct pointer_dev *p = wl_container_of(l, p, destroy);
	wl_list_remove(&p->destroy.link); wl_list_remove(&p->link); free(p);
}

/* (re)load the cursor theme when the config names another one; apps launched from now on
 * get it through XCURSOR_THEME/SIZE, and cursor-shape clients get it at once */
static void apply_cursor_cfg(struct server *s) {
	if (s->xcursor && !strcmp(s->xcursor_theme_now, s->cursor_theme) && s->xcursor_size_now == s->cursor_size)
		return;
	struct wlr_xcursor_manager *m = wlr_xcursor_manager_create(s->cursor_theme[0] ? s->cursor_theme : NULL,
	                                                           s->cursor_size);
	if (!m) return;
	struct wlr_xcursor_manager *old = s->xcursor;
	s->xcursor = m;
	snprintf(s->xcursor_theme_now, sizeof s->xcursor_theme_now, "%s", s->cursor_theme);
	s->xcursor_size_now = s->cursor_size;
	if (s->cursor_theme[0]) setenv("XCURSOR_THEME", s->cursor_theme, 1); else unsetenv("XCURSOR_THEME");
	char n[16]; snprintf(n, sizeof n, "%d", s->cursor_size); setenv("XCURSOR_SIZE", n, 1);
	if (old) {
		wlr_cursor_set_xcursor(s->cursor, s->xcursor, "default");
		wlr_xcursor_manager_destroy(old);
		if (s->xwayland_up) xwayland_cursor(s);
	}
}

/* after a config reload: keyboards and mice take the new settings at once */
static void apply_input_cfg(struct server *s) {
	apply_cursor_cfg(s);
	struct keyboard *k;
	wl_list_for_each(k, &s->keyboards, link) if (!k->is_virtual) keyboard_apply_cfg(s, k->wlr);
	struct pointer_dev *p;
	wl_list_for_each(p, &s->pointers, link) pointer_apply_cfg(s, p->dev);
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
	else if (d->type == WLR_INPUT_DEVICE_POINTER) {
		wlr_cursor_attach_input_device(s->cursor, d);
		struct pointer_dev *p = calloc(1, sizeof *p);
		p->dev = d;
		LISTEN(d->events.destroy, &p->destroy, pointer_destroy);
		wl_list_insert(&s->pointers, &p->link);
		pointer_apply_cfg(s, d);
	}
	update_caps(s);
}
static void new_vkb(struct wl_listener *l, void *data) {
	struct server *s = wl_container_of(l, s, new_vkb);
	struct wlr_virtual_keyboard_v1 *vk = data;
	add_keyboard_ex(s, &vk->keyboard, true);
	update_caps(s);
}
static void new_vptr(struct wl_listener *l, void *data) {
	struct server *s = wl_container_of(l, s, new_vptr);
	struct wlr_virtual_pointer_v1_new_pointer_event *e = data;
	wlr_cursor_attach_input_device(s->cursor, &e->new_pointer->pointer.base);
}

/* ---------- actions ---------- */

/* Super+Left/Right, as in Windows 7: snap the focused window to that half; pressed again on a
 * window already snapped there, it moves on to the next screen's far half, or comes back from the
 * other half to its own size */
static bool snap_key(struct server *s, int zone) {
	struct view *v = s->focused_view;
	if (!v || v->fullscreen || v->unmanaged) return false;
	struct output *o = output_of(s, view_output(v));
	if (!o) return false;
	if (v->maximized) {
		view_set_maximized(v, false);
		view_tile(v, o, zone);
		return true;
	}
	if (v->tiled && v->tile_zone != zone) {
		view_untile(v);
		view_place(v, v->saved.x, v->saved.y);
		return true;
	}
	if (v->tiled) {
		struct wlr_output *nx = wlr_output_layout_adjacent_output(s->output_layout,
			zone == SNAP_LEFT ? WLR_DIRECTION_LEFT : WLR_DIRECTION_RIGHT, o->wlr_output, 0, 0);
		struct output *no = nx ? output_of(s, nx) : NULL;
		if (!no) return false;
		view_tile(v, no, zone == SNAP_LEFT ? SNAP_RIGHT : SNAP_LEFT);
		return true;
	}
	view_tile(v, o, zone);
	return true;
}

static bool run_action(struct server *s, struct bind *b) {
	switch (b->action) {
	case A_EXEC: if (b->arg) spawn(b->arg); return true;
	case A_CLOSE: if (s->focused_view) { view_close(s->focused_view); return true; } return false;
	case A_QUIT: wl_display_terminate(s->display); return true;
	case A_FOCUS_NEXT: {
		/* held with a modifier (Alt+Tab): the switcher, until the modifier goes up */
		if (b->mods) { if (s->sw.on) { switcher_step(s, 1); return true; } return switcher_open(s, b->mods, 1); }
		struct view *n = next_view(s); if (n) { focus_view(n, NULL); return true; } return false; }
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
	case A_RELOAD: free_config(s); set_default_binds(s); load_config(s); apply_input_cfg(s); return true;
	case A_SNAP_LEFT: case A_SNAP_RIGHT: return snap_key(s, b->action == A_SNAP_LEFT ? SNAP_LEFT : SNAP_RIGHT);
	case A_RESTORE_DOWN: {
		struct view *v = s->focused_view;
		if (!v || v->fullscreen) return false;
		if (v->maximized) view_set_maximized(v, false);
		else if (v->tiled) { view_untile(v); view_place(v, v->saved.x, v->saved.y); }
		else view_set_minimized(v, true);
		return true;
	}
	case A_SHOW_DESKTOP: {
		/* (un)minimizing moves the focus, which reorders s->views: start the walk again after
		 * each change */
		bool any = false, again = true;
		struct view *v;
		while (again) {
			again = false;
			wl_list_for_each(v, &s->views, link) if (v->desktop_hidden) {
				v->desktop_hidden = false;
				if (v->mapped && v->minimized) { view_set_minimized(v, false); any = again = true; break; }
			}
		}
		if (any) return true;
		wl_list_for_each(v, &s->views, link)
			if (v->mapped && !v->minimized && !v->unmanaged) v->desktop_hidden = true;
		for (again = true; again; ) {
			again = false;
			wl_list_for_each(v, &s->views, link)
				if (v->desktop_hidden && !v->minimized) { view_set_minimized(v, true); again = true; break; }
		}
		return true;
	}
	case A_NONE: return false;
	}
	return false;
}

/* ---------- main ---------- */

static int on_signal(int sig, void *data) { wl_display_terminate(S.display); return 0; }
/* SIGHUP: read the config again (Spark Settings sends it after writing compositor.conf) */
static int on_reload_signal(int sig, void *data) {
	free_config(&S); set_default_binds(&S); load_config(&S); apply_input_cfg(&S);
	wlr_log(WLR_INFO, "config reloaded (SIGHUP)");
	return 0;
}

/* ---- Screen capture (ext-image-capture-source, used by grim and the screenshot portal) ----
 * The same as wlroots' output source, except on an HDR screen: there the screen's buffer holds
 * PQ / BT.2020 values, which look grey and washed out to every screenshot tool. Frames from an
 * HDR screen are drawn into an ordinary 8-bit buffer first, with SDR white brought back to
 * full white, so captures look like the screen does. Highlights above SDR white are clipped. */
struct cap_cursor {
	struct wlr_ext_image_capture_source_v1_cursor base;
	struct wlr_output *output;
	struct wlr_buffer *prev_buffer;
	bool initialized, needs_frame;
	struct wl_listener output_commit, prev_buffer_release;
};

struct cap_src {
	struct wlr_ext_image_capture_source_v1 base;
	struct wlr_addon addon;
	struct server *server;
	struct wlr_output *output;
	struct wl_listener output_commit;
	struct cap_cursor cursor;
	struct wlr_swapchain *sdr_chain;   /* 8-bit buffers for HDR screens */
	size_t num_started;
	bool sw_cursors_locked;
};

struct cap_frame_event {
	struct wlr_ext_image_capture_source_v1_frame_event base;
	struct wlr_buffer *buffer;
	struct timespec when;
};

static bool cap_hdr(struct cap_src *src) {
	return src->output->image_description != NULL &&
		src->output->image_description->transfer_function == WLR_COLOR_TRANSFER_FUNCTION_ST2084_PQ;
}

static void cap_start(struct wlr_ext_image_capture_source_v1 *base, bool with_cursors) {
	struct cap_src *src = wl_container_of(base, src, base);
	if (++src->num_started > 1) return;
	wlr_output_lock_attach_render(src->output, true);
	if (with_cursors) wlr_output_lock_software_cursors(src->output, true);
	src->sw_cursors_locked = with_cursors;
}

static void cap_stop(struct wlr_ext_image_capture_source_v1 *base) {
	struct cap_src *src = wl_container_of(base, src, base);
	if (src->num_started == 0 || --src->num_started > 0) return;
	wlr_output_lock_attach_render(src->output, false);
	if (src->sw_cursors_locked) wlr_output_lock_software_cursors(src->output, false);
}

static void cap_request_frame(struct wlr_ext_image_capture_source_v1 *base, bool schedule) {
	struct cap_src *src = wl_container_of(base, src, base);
	if (schedule) wlr_output_update_needs_frame(src->output);
}

/* Draw an HDR frame into an 8-bit buffer as SDR. Returns a locked buffer or NULL. */
static struct wlr_buffer *cap_hdr_to_sdr(struct cap_src *src, struct wlr_buffer *hdr) {
	struct wlr_output *wo = src->output;
	struct wlr_renderer *r = wo->renderer;
	if (!src->sdr_chain) return NULL;
	struct wlr_buffer *dst = wlr_swapchain_acquire(src->sdr_chain);
	if (!dst) return NULL;
	struct wlr_texture *tex = wlr_texture_from_buffer(r, hdr);
	if (!tex) { wlr_buffer_unlock(dst); return NULL; }
	struct wlr_render_pass *pass = wlr_renderer_begin_buffer_pass(r, dst, NULL);
	if (!pass) { wlr_texture_destroy(tex); wlr_buffer_unlock(dst); return NULL; }
	struct output *o = wo->data;
	double white = o && o->sdr_white > 0 ? o->sdr_white : 203;
	float mult = (float)(10000.0 / white);
	struct wlr_color_primaries prim;
	wlr_color_primaries_from_named(&prim, wo->image_description->primaries);
	wlr_render_pass_add_texture(pass, &(struct wlr_render_texture_options){
		.texture = tex,
		.blend_mode = WLR_RENDER_BLEND_MODE_NONE,
		.transfer_function = WLR_COLOR_TRANSFER_FUNCTION_ST2084_PQ,
		.primaries = &prim,
		.luminance_multiplier = &mult,
	});
	bool ok = wlr_render_pass_submit(pass);
	wlr_texture_destroy(tex);
	if (!ok) { wlr_buffer_unlock(dst); return NULL; }
	return dst;
}

static void cap_copy_frame(struct wlr_ext_image_capture_source_v1 *base,
		struct wlr_ext_image_copy_capture_frame_v1 *frame,
		struct wlr_ext_image_capture_source_v1_frame_event *base_event) {
	struct cap_src *src = wl_container_of(base, src, base);
	struct cap_frame_event *ev = wl_container_of(base_event, ev, base);
	struct wlr_buffer *buf = ev->buffer, *sdr = NULL;
	if (cap_hdr(src)) {
		sdr = cap_hdr_to_sdr(src, buf);
		if (!sdr) {
			wlr_ext_image_copy_capture_frame_v1_fail(frame,
				EXT_IMAGE_COPY_CAPTURE_FRAME_V1_FAILURE_REASON_UNKNOWN);
			return;
		}
		buf = sdr;
	}
	if (wlr_ext_image_copy_capture_frame_v1_copy_buffer(frame, buf, src->output->renderer))
		wlr_ext_image_copy_capture_frame_v1_ready(frame, src->output->transform, &ev->when);
	if (sdr) wlr_buffer_unlock(sdr);
}

static struct wlr_ext_image_capture_source_v1_cursor *cap_get_cursor(
		struct wlr_ext_image_capture_source_v1 *base, struct wlr_seat *seat) {
	struct cap_src *src = wl_container_of(base, src, base);
	return &src->cursor.base;
}

static const struct wlr_ext_image_capture_source_v1_interface cap_impl = {
	.start = cap_start,
	.stop = cap_stop,
	.request_frame = cap_request_frame,
	.copy_frame = cap_copy_frame,
	.get_pointer_cursor = cap_get_cursor,
};

static void cap_update_constraints(struct cap_src *src) {
	struct wlr_output *wo = src->output;
	if (!wo->enabled) return;
	if (cap_hdr(src)) {
		if (src->sdr_chain && (src->sdr_chain->width != wo->width || src->sdr_chain->height != wo->height)) {
			wlr_swapchain_destroy(src->sdr_chain);
			src->sdr_chain = NULL;
		}
		if (!src->sdr_chain) {
			const struct wlr_drm_format_set *set =
				wlr_output_get_primary_formats(wo, src->server->allocator->buffer_caps);
			const struct wlr_drm_format *fmt = set ? wlr_drm_format_set_get(set, DRM_FORMAT_XRGB8888) : NULL;
			if (fmt) src->sdr_chain = wlr_swapchain_create(src->server->allocator, wo->width, wo->height, fmt);
			if (!src->sdr_chain) wlr_log(WLR_ERROR, "capture %s: no 8-bit buffers for HDR captures", wo->name);
		}
		if (src->sdr_chain) {
			wlr_ext_image_capture_source_v1_set_constraints_from_swapchain(&src->base, src->sdr_chain, wo->renderer);
			return;
		}
	} else if (src->sdr_chain) {
		wlr_swapchain_destroy(src->sdr_chain);
		src->sdr_chain = NULL;
	}
	if (!wlr_output_configure_primary_swapchain(wo, NULL, &wo->swapchain)) return;
	wlr_ext_image_capture_source_v1_set_constraints_from_swapchain(&src->base, wo->swapchain, wo->renderer);
}

static void cap_output_commit(struct wl_listener *l, void *data) {
	struct cap_src *src = wl_container_of(l, src, output_commit);
	struct wlr_output_event_commit *event = data;
	if (event->state->committed & (WLR_OUTPUT_STATE_MODE | WLR_OUTPUT_STATE_RENDER_FORMAT |
			WLR_OUTPUT_STATE_ENABLED | WLR_OUTPUT_STATE_IMAGE_DESCRIPTION))
		cap_update_constraints(src);
	if (!(event->state->committed & WLR_OUTPUT_STATE_BUFFER)) return;
	struct wlr_buffer *buffer = event->state->buffer;
	pixman_region32_t full;
	pixman_region32_init_rect(&full, 0, 0, buffer->width, buffer->height);
	struct cap_frame_event ev = {
		.base = { .damage = (event->state->committed & WLR_OUTPUT_STATE_DAMAGE) ? &event->state->damage : &full },
		.buffer = buffer,
		.when = event->when,
	};
	wl_signal_emit_mutable(&src->base.events.frame, &ev);
	pixman_region32_fini(&full);
}

/* Cursor capture: unchanged from wlroots (the cursor plane is always SDR). */
static void cap_cursor_request_frame(struct wlr_ext_image_capture_source_v1 *base, bool schedule) {
	struct cap_cursor *c = wl_container_of(base, c, base);
	if (schedule) { wlr_output_update_needs_frame(c->output); c->needs_frame = true; }
}

static void cap_cursor_copy_frame(struct wlr_ext_image_capture_source_v1 *base,
		struct wlr_ext_image_copy_capture_frame_v1 *frame,
		struct wlr_ext_image_capture_source_v1_frame_event *base_event) {
	struct cap_cursor *c = wl_container_of(base, c, base);
	struct wlr_buffer *b = c->output->cursor_front_buffer;
	if (!b) {
		wlr_ext_image_copy_capture_frame_v1_fail(frame, EXT_IMAGE_COPY_CAPTURE_FRAME_V1_FAILURE_REASON_STOPPED);
		return;
	}
	if (!wlr_ext_image_copy_capture_frame_v1_copy_buffer(frame, b, c->output->renderer)) return;
	struct timespec now;
	clock_gettime(CLOCK_MONOTONIC, &now);
	wlr_ext_image_copy_capture_frame_v1_ready(frame, c->output->transform, &now);
}

static const struct wlr_ext_image_capture_source_v1_interface cap_cursor_impl = {
	.request_frame = cap_cursor_request_frame,
	.copy_frame = cap_cursor_copy_frame,
};

static void cap_cursor_update(struct cap_cursor *c) {
	struct wlr_output *wo = c->output;
	if (wo->cursor_swapchain && !c->initialized) {
		wlr_ext_image_capture_source_v1_set_constraints_from_swapchain(&c->base.base, wo->cursor_swapchain, wo->renderer);
		c->initialized = true;
	}
	struct wlr_output_cursor *oc = wo->hardware_cursor;
	if (!oc || !oc->visible) {
		c->base.entered = false;
		wl_signal_emit_mutable(&c->base.events.update, NULL);
		return;
	}
	if (wo->cursor_swapchain && ((int)c->base.base.width != wo->cursor_swapchain->width ||
			(int)c->base.base.height != wo->cursor_swapchain->height)) {
		c->base.base.width = wo->cursor_swapchain->width;
		c->base.base.height = wo->cursor_swapchain->height;
		wl_signal_emit_mutable(&c->base.base.events.constraints_update, NULL);
	}
	c->base.entered = true;
	c->base.x = round(oc->x);
	c->base.y = round(oc->y);
	c->base.hotspot.x = oc->hotspot_x;
	c->base.hotspot.y = oc->hotspot_y;
	wl_signal_emit_mutable(&c->base.events.update, NULL);
}

static void cap_cursor_prev_release(struct wl_listener *l, void *data) {
	struct cap_cursor *c = wl_container_of(l, c, prev_buffer_release);
	wl_list_remove(&c->prev_buffer_release.link);
	wl_list_init(&c->prev_buffer_release.link);
	c->prev_buffer = NULL;
}

static void cap_cursor_output_commit(struct wl_listener *l, void *data) {
	struct cap_cursor *c = wl_container_of(l, c, output_commit);
	struct wlr_output_event_commit *event = data;
	cap_cursor_update(c);
	struct wlr_buffer *b = c->output->cursor_front_buffer;
	if (b && (b != c->prev_buffer || c->needs_frame)) {
		pixman_region32_t full;
		pixman_region32_init_rect(&full, 0, 0, b->width, b->height);
		struct cap_frame_event ev = { .base = { .damage = &full }, .buffer = b, .when = event->when };
		wl_signal_emit_mutable(&c->base.base.events.frame, &ev);
		pixman_region32_fini(&full);
		c->prev_buffer = b;
		wl_list_remove(&c->prev_buffer_release.link);
		c->prev_buffer_release.notify = cap_cursor_prev_release;
		wl_signal_add(&b->events.release, &c->prev_buffer_release);
	}
	c->needs_frame = false;
}

static void cap_addon_destroy(struct wlr_addon *addon) {
	struct cap_src *src = wl_container_of(addon, src, addon);
	wlr_ext_image_capture_source_v1_finish(&src->base);
	wlr_ext_image_capture_source_v1_cursor_finish(&src->cursor.base);
	wl_list_remove(&src->cursor.output_commit.link);
	wl_list_remove(&src->cursor.prev_buffer_release.link);
	wl_list_remove(&src->output_commit.link);
	if (src->sdr_chain) wlr_swapchain_destroy(src->sdr_chain);
	wlr_addon_finish(&src->addon);
	free(src);
}

static const struct wlr_addon_interface cap_addon_impl = {
	.name = "spark_output_capture_source",
	.destroy = cap_addon_destroy,
};

static void cap_mgr_create_source(struct wl_client *client, struct wl_resource *mgr,
		uint32_t new_id, struct wl_resource *output_resource) {
	struct server *s = wl_resource_get_user_data(mgr);
	struct wlr_output *wo = wlr_output_from_resource(output_resource);
	if (!wo) { wlr_ext_image_capture_source_v1_create_resource(NULL, client, new_id); return; }
	struct cap_src *src;
	struct wlr_addon *addon = wlr_addon_find(&wo->addons, NULL, &cap_addon_impl);
	if (addon) {
		src = wl_container_of(addon, src, addon);
	} else {
		src = calloc(1, sizeof(*src));
		if (!src) { wl_resource_post_no_memory(mgr); return; }
		wlr_ext_image_capture_source_v1_init(&src->base, &cap_impl);
		wlr_addon_init(&src->addon, &wo->addons, NULL, &cap_addon_impl);
		src->server = s;
		src->output = wo;
		src->output_commit.notify = cap_output_commit;
		wl_signal_add(&wo->events.commit, &src->output_commit);
		cap_update_constraints(src);
		wlr_ext_image_capture_source_v1_cursor_init(&src->cursor.base, &cap_cursor_impl);
		src->cursor.output = wo;
		src->cursor.output_commit.notify = cap_cursor_output_commit;
		wl_signal_add(&wo->events.commit, &src->cursor.output_commit);
		wl_list_init(&src->cursor.prev_buffer_release.link);
		cap_cursor_update(&src->cursor);
	}
	wlr_ext_image_capture_source_v1_create_resource(&src->base, client, new_id);
}

static void cap_mgr_destroy(struct wl_client *client, struct wl_resource *r) {
	wl_resource_destroy(r);
}

static const struct ext_output_image_capture_source_manager_v1_interface cap_mgr_impl = {
	.create_source = cap_mgr_create_source,
	.destroy = cap_mgr_destroy,
};

static void cap_mgr_bind(struct wl_client *client, void *data, uint32_t version, uint32_t id) {
	struct wl_resource *r = wl_resource_create(client,
		&ext_output_image_capture_source_manager_v1_interface, version, id);
	if (!r) { wl_client_post_no_memory(client); return; }
	wl_resource_set_implementation(r, &cap_mgr_impl, data, NULL);
}

static struct wlr_renderer *make_renderer(struct server *s) {
	bool forced = getenv("WLR_RENDERER") != NULL;
	if (s->want_vulkan && !forced) setenv("WLR_RENDERER", "vulkan", 1);
	struct wlr_renderer *r = wlr_renderer_autocreate(s->backend);
	if (!r && s->want_vulkan && !forced) {
		wlr_log(WLR_ERROR, "the Vulkan renderer failed; HDR stays off");
		unsetenv("WLR_RENDERER");
		r = wlr_renderer_autocreate(s->backend);
	}
	if (s->want_vulkan && !forced) unsetenv("WLR_RENDERER");   /* not passed on to clients */
	return r;
}

/* A GPU reset (an AMD ring timeout, an Nvidia Xid) loses the renderer. Without a new one the
 * screen stays frozen until logout; with it, windows redraw and the session goes on. */
static void renderer_lost(struct wl_listener *l, void *data) {
	struct server *s = wl_container_of(l, s, renderer_lost);
	wlr_log(WLR_ERROR, "the GPU was reset: making a new renderer");
	struct wlr_renderer *r = make_renderer(s);
	if (!r) { wlr_log(WLR_ERROR, "no new renderer"); return; }
	struct wlr_allocator *a = wlr_allocator_autocreate(s->backend, r);
	if (!a) { wlr_log(WLR_ERROR, "no new allocator"); wlr_renderer_destroy(r); return; }
	struct wlr_renderer *old_r = s->renderer;
	struct wlr_allocator *old_a = s->allocator;
	s->renderer = r; s->allocator = a;
	wl_list_remove(&s->renderer_lost.link);
	wl_signal_add(&r->events.lost, &s->renderer_lost);
	wlr_compositor_set_renderer(s->compositor, r);
	struct output *o;
	wl_list_for_each(o, &s->outputs, link) {
		struct wlr_output *wo = o->wlr_output;
		/* HDR captures keep 8-bit buffers from the old allocator: drop them, they are made
		 * again on the next capture */
		struct wlr_addon *ad = wlr_addon_find(&wo->addons, NULL, &cap_addon_impl);
		if (ad) {
			struct cap_src *src = wl_container_of(ad, src, addon);
			if (src->sdr_chain) { wlr_swapchain_destroy(src->sdr_chain); src->sdr_chain = NULL; }
		}
		wlr_output_init_render(wo, a, r);
		o->tear_view = NULL;
		wlr_output_schedule_frame(wo);
	}
	wlr_allocator_destroy(old_a);
	wlr_renderer_destroy(old_r);
}

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
	wl_list_init(&s->pointers);
	set_default_binds(s);
	load_config(s);

	s->display = wl_display_create();
	/* libwayland's default is 4 KiB per client: a client that is busy for a moment (Spark Tray
	 * asking NetworkManager) gets disconnected when pointer and frame events fill it */
	wl_display_set_default_max_buffer_size(s->display, 1024 * 1024);
	s->loop = wl_display_get_event_loop(s->display);
	wl_event_loop_add_signal(s->loop, SIGINT, on_signal, NULL);
	wl_event_loop_add_signal(s->loop, SIGTERM, on_signal, NULL);
	wl_event_loop_add_signal(s->loop, SIGHUP, on_reload_signal, NULL);
	{	/* tells Spark Settings this compositor reloads on SIGHUP (older builds would die from it) */
		const char *rt = getenv("XDG_RUNTIME_DIR");
		char path[512];
		if (rt && snprintf(path, sizeof path, "%s/spark-compositor.pid", rt) < (int)sizeof path) {
			FILE *f = fopen(path, "w");
			if (f) { fprintf(f, "%d\n", getpid()); fclose(f); }
		}
	}

	const char *hl = getenv("SPARK_HEADLESS_OUTPUTS");
	if (hl) s->backend = wlr_headless_backend_create(s->loop);
	else s->backend = wlr_backend_autocreate(s->loop, &s->session);
	if (!s->backend) { wlr_log(WLR_ERROR, "no backend"); return 1; }
	bool want_hdr = false;
	struct out_cfg *oc;
	wl_list_for_each(oc, &s->out_cfgs, link) want_hdr |= oc->hdr && oc->enabled;
	s->want_vulkan = want_hdr;
	s->renderer = make_renderer(s);
	if (!s->renderer) { wlr_log(WLR_ERROR, "no renderer"); return 1; }
	LISTEN(s->renderer->events.lost, &s->renderer_lost, renderer_lost);
	wlr_renderer_init_wl_display(s->renderer, s->display);
	s->allocator = wlr_allocator_autocreate(s->backend, s->renderer);
	if (!s->allocator) { wlr_log(WLR_ERROR, "no allocator"); return 1; }

	/* explicit sync (linux-drm-syncobj): the Nvidia driver needs it for Wayland windows that
	 * don't flicker or stall, and Vulkan games on Mesa use it too. Only offered when both the
	 * renderer and the backend can wait on timelines; the scene applies the fences itself. */
	if (s->renderer->features.timeline && s->backend->features.timeline) {
		int drm_fd = wlr_renderer_get_drm_fd(s->renderer);
		if (drm_fd >= 0 && wlr_linux_drm_syncobj_manager_v1_create(s->display, 1, drm_fd))
			wlr_log(WLR_INFO, "explicit sync on");
	}

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
	s->idle_since = s->idle_tick_at = boot_ms();
	s->idle_timer = wl_event_loop_add_timer(wl_display_get_event_loop(s->display), idle_tick, s);
	wl_event_source_timer_update(s->idle_timer, IDLE_TICK_MS);
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
	wl_global_create(s->display, &ext_output_image_capture_source_manager_v1_interface, 1, s, cap_mgr_bind);
	wlr_ext_image_copy_capture_manager_v1_create(s->display, 1);
	struct wlr_gamma_control_manager_v1 *gamma = wlr_gamma_control_manager_v1_create(s->display);
	wlr_scene_set_gamma_control_manager_v1(s->scene, gamma);
	if (s->renderer->features.input_color_transform) {
		/* wp_color_manager_v1: games and players can say their buffers are HDR (PQ/BT.2020)
		 * or another colour space, and the scene converts them for each screen */
		size_t ntf = 0, npr = 0;
		enum wp_color_manager_v1_transfer_function *tfs =
			wlr_color_manager_v1_transfer_function_list_from_renderer(s->renderer, &ntf);
		enum wp_color_manager_v1_primaries *prs =
			wlr_color_manager_v1_primaries_list_from_renderer(s->renderer, &npr);
		const enum wp_color_manager_v1_render_intent intents[] = { WP_COLOR_MANAGER_V1_RENDER_INTENT_PERCEPTUAL };
		struct wlr_color_manager_v1 *cm = wlr_color_manager_v1_create(s->display, 2,
			&(struct wlr_color_manager_v1_options){
				.features = { .parametric = true, .set_mastering_display_primaries = true },
				.render_intents = intents, .render_intents_len = 1,
				.transfer_functions = tfs, .transfer_functions_len = ntf,
				.primaries = prs, .primaries_len = npr,
			});
		free(tfs); free(prs);
		if (cm) wlr_scene_set_color_manager_v1(s->scene, cm);
	}
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
	apply_cursor_cfg(s);
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

	if (s->idle_timer) { wl_event_source_remove(s->idle_timer); s->idle_timer = NULL; }
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
	UNLISTEN(&s->renderer_lost);
	wlr_renderer_destroy(s->renderer);
	wlr_backend_destroy(s->backend);
	wl_display_destroy(s->display);
	free_config(s);
	return 0;
}
