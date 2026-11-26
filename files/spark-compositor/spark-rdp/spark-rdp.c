/*
 * spark-rdp: the RDP server behind Spark Connect's "Take control" in the Spark session.
 *
 * FreeRDP's shadow server does the RDP side (TLS, NLA sign-in, codecs). This file adds the
 * part it is missing for spark-compositor: the picture comes from wlr-screencopy, the
 * mouse from wlr-virtual-pointer and the keyboard from zwp-virtual-keyboard.
 *
 *   spark-rdp DIR PORT [ADDRESS] [MONITOR]
 *
 * DIR holds shadow/shadow.crt and shadow/shadow.key (spark-share writes them). The user name
 * and the password come on stdin, one per line, so they never show in the process list;
 * spark-rdp turns them into a SAM file (DIR/sam, mode 0600) for NLA. ADDRESS defaults to
 * 127.0.0.1. MONITOR is the output index; the default is the first output, the main one.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/input-event-codes.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#include <wayland-client.h>
#include <xkbcommon/xkbcommon.h>

#include <winpr/input.h>
#include <winpr/synch.h>
#include <winpr/thread.h>
#include <winpr/sysinfo.h>
#include <winpr/cmdline.h>
#include <freerdp/freerdp.h>
#include <freerdp/codec/color.h>
#include <freerdp/codec/region.h>
#include <freerdp/server/shadow.h>

#include "screencopy-protocol.h"
#include "vptr-protocol.h"
#include "vkbd-protocol.h"
#include "xdg-output-protocol.h"

#define MAX_OUTPUTS 16

struct out {
	struct wl_output *wl;
	struct zxdg_output_v1 *xdg;
	int32_t pw, ph;          /* mode size in pixels */
	int32_t lx, ly, lw, lh;  /* logical position and size in the layout */
	int32_t transform;
};

/* One Wayland connection for the whole process. Requests are thread-safe in libwayland; the
 * input lock keeps key state and request order straight when several RDP threads send input. */
static struct {
	struct wl_display *display;
	struct wl_shm *shm;
	struct wl_seat *seat;
	struct zwlr_screencopy_manager_v1 *screencopy;
	struct zwlr_virtual_pointer_manager_v1 *vptr_mgr;
	struct zwp_virtual_keyboard_manager_v1 *vkbd_mgr;
	struct zxdg_output_manager_v1 *xdg_mgr;
	struct out outs[MAX_OUTPUTS];
	int nouts;

	struct zwlr_virtual_pointer_v1 *vptr;
	struct zwp_virtual_keyboard_v1 *vkbd;
	struct xkb_context *xkb;
	struct xkb_keymap *keymap;
	struct xkb_state *xkb_state;
	pthread_mutex_t input_lock;
} W = { .input_lock = PTHREAD_MUTEX_INITIALIZER };

static uint32_t now_ms(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return (uint32_t)(ts.tv_sec * 1000 + ts.tv_nsec / 1000000);
}

/* ---- outputs ---------------------------------------------------------------------------- */

static void out_geometry(void *data, struct wl_output *o, int32_t x, int32_t y, int32_t pw,
                         int32_t ph, int32_t sub, const char *make, const char *model,
                         int32_t transform)
{
	((struct out *)data)->transform = transform;
}
static void out_mode(void *data, struct wl_output *o, uint32_t flags, int32_t w, int32_t h,
                     int32_t refresh)
{
	struct out *out = data;
	if (flags & WL_OUTPUT_MODE_CURRENT) {
		out->pw = w;
		out->ph = h;
	}
}
static void out_done(void *data, struct wl_output *o) {}
static void out_scale(void *data, struct wl_output *o, int32_t f) {}
static void out_name(void *data, struct wl_output *o, const char *n) {}
static void out_desc(void *data, struct wl_output *o, const char *d) {}
static const struct wl_output_listener out_listener = {
	.geometry = out_geometry, .mode = out_mode, .done = out_done, .scale = out_scale,
	.name = out_name, .description = out_desc,
};

static void xo_pos(void *data, struct zxdg_output_v1 *x, int32_t lx, int32_t ly)
{
	struct out *out = data;
	out->lx = lx;
	out->ly = ly;
}
static void xo_size(void *data, struct zxdg_output_v1 *x, int32_t w, int32_t h)
{
	struct out *out = data;
	out->lw = w;
	out->lh = h;
}
static void xo_done(void *data, struct zxdg_output_v1 *x) {}
static void xo_name(void *data, struct zxdg_output_v1 *x, const char *n) {}
static void xo_desc(void *data, struct zxdg_output_v1 *x, const char *d) {}
static const struct zxdg_output_v1_listener xo_listener = {
	.logical_position = xo_pos, .logical_size = xo_size, .done = xo_done,
	.name = xo_name, .description = xo_desc,
};

/* ---- seat keyboard: borrow the compositor's keymap for the virtual keyboard ---------------- */

static int keymap_fd = -1;
static uint32_t keymap_size;

static void kb_keymap(void *data, struct wl_keyboard *k, uint32_t format, int32_t fd,
                      uint32_t size)
{
	if (format != WL_KEYBOARD_KEYMAP_FORMAT_XKB_V1) {
		close(fd);
		return;
	}
	if (keymap_fd >= 0)
		close(keymap_fd);
	keymap_fd = fd;
	keymap_size = size;
}
static void kb_enter(void *d, struct wl_keyboard *k, uint32_t s, struct wl_surface *sf,
                     struct wl_array *keys) {}
static void kb_leave(void *d, struct wl_keyboard *k, uint32_t s, struct wl_surface *sf) {}
static void kb_key(void *d, struct wl_keyboard *k, uint32_t s, uint32_t t, uint32_t key,
                   uint32_t st) {}
static void kb_mods(void *d, struct wl_keyboard *k, uint32_t s, uint32_t a, uint32_t b,
                    uint32_t c, uint32_t g) {}
static void kb_repeat(void *d, struct wl_keyboard *k, int32_t r, int32_t dl) {}
static const struct wl_keyboard_listener kb_listener = {
	.keymap = kb_keymap, .enter = kb_enter, .leave = kb_leave, .key = kb_key,
	.modifiers = kb_mods, .repeat_info = kb_repeat,
};

/* ---- registry ------------------------------------------------------------------------- */

static void reg_global(void *data, struct wl_registry *r, uint32_t name, const char *iface,
                       uint32_t version)
{
	if (!strcmp(iface, wl_shm_interface.name)) {
		W.shm = wl_registry_bind(r, name, &wl_shm_interface, 1);
	} else if (!strcmp(iface, wl_seat_interface.name) && !W.seat) {
		W.seat = wl_registry_bind(r, name, &wl_seat_interface, 1);
	} else if (!strcmp(iface, wl_output_interface.name) && W.nouts < MAX_OUTPUTS) {
		struct out *out = &W.outs[W.nouts++];
		out->wl = wl_registry_bind(r, name, &wl_output_interface, version < 4 ? version : 4);
		wl_output_add_listener(out->wl, &out_listener, out);
	} else if (!strcmp(iface, zwlr_screencopy_manager_v1_interface.name)) {
		W.screencopy = wl_registry_bind(r, name, &zwlr_screencopy_manager_v1_interface,
		                                version < 3 ? version : 3);
	} else if (!strcmp(iface, zwlr_virtual_pointer_manager_v1_interface.name)) {
		W.vptr_mgr = wl_registry_bind(r, name, &zwlr_virtual_pointer_manager_v1_interface, 1);
	} else if (!strcmp(iface, zwp_virtual_keyboard_manager_v1_interface.name)) {
		W.vkbd_mgr = wl_registry_bind(r, name, &zwp_virtual_keyboard_manager_v1_interface, 1);
	} else if (!strcmp(iface, zxdg_output_manager_v1_interface.name)) {
		W.xdg_mgr = wl_registry_bind(r, name, &zxdg_output_manager_v1_interface,
		                             version < 2 ? version : 2);
	}
}
static void reg_remove(void *data, struct wl_registry *r, uint32_t name) {}
static const struct wl_registry_listener reg_listener = {
	.global = reg_global, .global_remove = reg_remove,
};

static int wayland_connect(void)
{
	W.display = wl_display_connect(NULL);
	if (!W.display) {
		fprintf(stderr, "spark-rdp: no Wayland display (WAYLAND_DISPLAY unset or wrong)\n");
		return -1;
	}
	struct wl_registry *reg = wl_display_get_registry(W.display);
	wl_registry_add_listener(reg, &reg_listener, NULL);
	wl_display_roundtrip(W.display);
	if (W.xdg_mgr)
		for (int i = 0; i < W.nouts; i++) {
			W.outs[i].xdg = zxdg_output_manager_v1_get_xdg_output(W.xdg_mgr, W.outs[i].wl);
			zxdg_output_v1_add_listener(W.outs[i].xdg, &xo_listener, &W.outs[i]);
		}
	if (W.seat) {
		struct wl_keyboard *kb = wl_seat_get_keyboard(W.seat);
		wl_keyboard_add_listener(kb, &kb_listener, NULL);
	}
	wl_display_roundtrip(W.display);
	wl_display_roundtrip(W.display);

	const char *missing = !W.shm ? "wl_shm" : !W.screencopy ? "wlr-screencopy"
	                      : !W.vptr_mgr ? "wlr-virtual-pointer"
	                      : !W.vkbd_mgr ? "virtual-keyboard" : !W.nouts ? "an output" : NULL;
	if (missing) {
		fprintf(stderr, "spark-rdp: the compositor has no %s\n", missing);
		return -1;
	}
	for (int i = 0; i < W.nouts; i++) {
		struct out *o = &W.outs[i];
		if (!o->lw || !o->lh) { /* no xdg-output: assume scale 1 */
			o->lw = o->pw;
			o->lh = o->ph;
		}
	}
	return 0;
}

static int input_setup(void)
{
	W.vptr = zwlr_virtual_pointer_manager_v1_create_virtual_pointer(W.vptr_mgr, W.seat);
	W.vkbd = zwp_virtual_keyboard_manager_v1_create_virtual_keyboard(W.vkbd_mgr, W.seat);
	W.xkb = xkb_context_new(XKB_CONTEXT_NO_FLAGS);
	if (!W.xkb)
		return -1;

	if (keymap_fd >= 0) {
		char *map = mmap(NULL, keymap_size, PROT_READ, MAP_PRIVATE, keymap_fd, 0);
		if (map != MAP_FAILED) {
			W.keymap = xkb_keymap_new_from_buffer(W.xkb, map, strnlen(map, keymap_size),
			                                      XKB_KEYMAP_FORMAT_TEXT_V1,
			                                      XKB_KEYMAP_COMPILE_NO_FLAGS);
			munmap(map, keymap_size);
		}
	}
	if (!W.keymap) {
		struct xkb_rule_names names = { 0 };
		W.keymap = xkb_keymap_new_from_names(W.xkb, &names, XKB_KEYMAP_COMPILE_NO_FLAGS);
	}
	if (!W.keymap)
		return -1;
	W.xkb_state = xkb_state_new(W.keymap);

	/* Hand the virtual keyboard the same keymap, as a fresh sealed file. */
	char *text = xkb_keymap_get_as_string(W.keymap, XKB_KEYMAP_FORMAT_TEXT_V1);
	if (!text)
		return -1;
	size_t len = strlen(text) + 1;
	int fd = memfd_create("spark-rdp-keymap", MFD_CLOEXEC);
	if (fd < 0 || write(fd, text, len) != (ssize_t)len) {
		free(text);
		if (fd >= 0)
			close(fd);
		return -1;
	}
	free(text);
	zwp_virtual_keyboard_v1_keymap(W.vkbd, WL_KEYBOARD_KEYMAP_FORMAT_XKB_V1, fd, (uint32_t)len);
	close(fd);
	wl_display_flush(W.display);
	return 0;
}

/* ---- screen capture ------------------------------------------------------------------- */

struct frame {
	uint32_t format, width, height, stride;
	int ready, failed, buffer_done, y_invert, version3;
};

static void fr_buffer(void *data, struct zwlr_screencopy_frame_v1 *f, uint32_t format,
                      uint32_t w, uint32_t h, uint32_t stride)
{
	struct frame *fr = data;
	/* Take the first shm format we can read. */
	if (fr->width)
		return;
	if (format == WL_SHM_FORMAT_XRGB8888 || format == WL_SHM_FORMAT_ARGB8888 ||
	    format == WL_SHM_FORMAT_XBGR8888 || format == WL_SHM_FORMAT_ABGR8888 ||
	    format == WL_SHM_FORMAT_XRGB2101010 || format == WL_SHM_FORMAT_ARGB2101010 ||
	    format == WL_SHM_FORMAT_XBGR2101010 || format == WL_SHM_FORMAT_ABGR2101010) {
		fr->format = format;
		fr->width = w;
		fr->height = h;
		fr->stride = stride;
	}
}
static void fr_flags(void *data, struct zwlr_screencopy_frame_v1 *f, uint32_t flags)
{
	((struct frame *)data)->y_invert = !!(flags & ZWLR_SCREENCOPY_FRAME_V1_FLAGS_Y_INVERT);
}
static void fr_ready(void *data, struct zwlr_screencopy_frame_v1 *f, uint32_t a, uint32_t b,
                     uint32_t c)
{
	((struct frame *)data)->ready = 1;
}
static void fr_failed(void *data, struct zwlr_screencopy_frame_v1 *f)
{
	((struct frame *)data)->failed = 1;
}
static void fr_damage(void *data, struct zwlr_screencopy_frame_v1 *f, uint32_t x, uint32_t y,
                      uint32_t w, uint32_t h) {}
static void fr_dmabuf(void *data, struct zwlr_screencopy_frame_v1 *f, uint32_t fmt, uint32_t w,
                      uint32_t h) {}
static void fr_buffer_done(void *data, struct zwlr_screencopy_frame_v1 *f)
{
	((struct frame *)data)->buffer_done = 1;
}
static const struct zwlr_screencopy_frame_v1_listener fr_listener = {
	.buffer = fr_buffer, .flags = fr_flags, .ready = fr_ready, .failed = fr_failed,
	.damage = fr_damage, .linux_dmabuf = fr_dmabuf, .buffer_done = fr_buffer_done,
};

static struct {
	struct wl_buffer *buffer;
	void *data;
	size_t size;
	uint32_t format, width, height, stride;
	BYTE *frame;            /* last capture, BGRX32, top-down */
	uint32_t frame_stride;
} SHM;

static void shm_drop(void)
{
	if (SHM.buffer)
		wl_buffer_destroy(SHM.buffer);
	if (SHM.data)
		munmap(SHM.data, SHM.size);
	free(SHM.frame);
	memset(&SHM, 0, sizeof SHM);
}

static int shm_ensure(const struct frame *fr)
{
	if (SHM.buffer && SHM.format == fr->format && SHM.width == fr->width &&
	    SHM.height == fr->height && SHM.stride == fr->stride)
		return 0;
	shm_drop();
	size_t size = (size_t)fr->stride * fr->height;
	int fd = memfd_create("spark-rdp-frame", MFD_CLOEXEC);
	if (fd < 0)
		return -1;
	if (ftruncate(fd, (off_t)size) < 0) {
		close(fd);
		return -1;
	}
	void *data = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
	if (data == MAP_FAILED) {
		close(fd);
		return -1;
	}
	struct wl_shm_pool *pool = wl_shm_create_pool(W.shm, fd, (int32_t)size);
	SHM.buffer = wl_shm_pool_create_buffer(pool, 0, (int32_t)fr->width, (int32_t)fr->height,
	                                       (int32_t)fr->stride, fr->format);
	wl_shm_pool_destroy(pool);
	close(fd);
	SHM.data = data;
	SHM.size = size;
	SHM.format = fr->format;
	SHM.width = fr->width;
	SHM.height = fr->height;
	SHM.stride = fr->stride;
	SHM.frame_stride = fr->width * 4;
	SHM.frame = calloc(fr->height, SHM.frame_stride);
	return SHM.frame ? 0 : -1;
}

static UINT32 rdp_format(uint32_t shm_format)
{
	switch (shm_format) {
	case WL_SHM_FORMAT_ARGB8888: return PIXEL_FORMAT_BGRA32;
	case WL_SHM_FORMAT_XBGR8888: return PIXEL_FORMAT_RGBX32;
	case WL_SHM_FORMAT_ABGR8888: return PIXEL_FORMAT_RGBA32;
	default:                     return PIXEL_FORMAT_BGRX32;
	}
}

static int is_10bit(uint32_t f)
{
	return f == WL_SHM_FORMAT_XRGB2101010 || f == WL_SHM_FORMAT_ARGB2101010 ||
	       f == WL_SHM_FORMAT_XBGR2101010 || f == WL_SHM_FORMAT_ABGR2101010;
}

/* FreeRDP has no 10-bit formats: keep the top 8 bits of each channel. A 10-bit monitor
 * (spark-compositor picks XRGB2101010 when the output supports it) captures this way. */
static int copy_10bit(int y_invert)
{
	int bgr = SHM.format == WL_SHM_FORMAT_XBGR2101010 || SHM.format == WL_SHM_FORMAT_ABGR2101010;
	for (uint32_t y = 0; y < SHM.height; y++) {
		const uint32_t *src = (const uint32_t *)((const BYTE *)SHM.data +
		                                         (size_t)(y_invert ? SHM.height - 1 - y : y) * SHM.stride);
		BYTE *dst = SHM.frame + (size_t)y * SHM.frame_stride;
		for (uint32_t x = 0; x < SHM.width; x++) {
			uint32_t p = src[x];
			BYTE hi = (BYTE)(p >> 22), mid = (BYTE)(p >> 12), lo = (BYTE)(p >> 2);
			dst[4 * x + 0] = bgr ? hi : lo;  /* B */
			dst[4 * x + 1] = mid;            /* G */
			dst[4 * x + 2] = bgr ? lo : hi;  /* R */
			dst[4 * x + 3] = 0xff;
		}
	}
	return 1;
}

/* Copy one picture of output `idx` into SHM.frame. 1 = new picture, 0 = none this time. */
static int capture(int idx)
{
	struct frame fr = { 0 };
	struct zwlr_screencopy_frame_v1 *f =
	    zwlr_screencopy_manager_v1_capture_output(W.screencopy, 1, W.outs[idx].wl);
	fr.version3 = zwlr_screencopy_frame_v1_get_version(f) >= 3;
	zwlr_screencopy_frame_v1_add_listener(f, &fr_listener, &fr);

	while (!fr.failed && !(fr.version3 ? fr.buffer_done : fr.width != 0))
		if (wl_display_dispatch(W.display) < 0)
			goto lost;
	if (fr.failed || !fr.width || shm_ensure(&fr) < 0) {
		zwlr_screencopy_frame_v1_destroy(f);
		return 0;
	}
	zwlr_screencopy_frame_v1_copy(f, SHM.buffer);
	while (!fr.ready && !fr.failed)
		if (wl_display_dispatch(W.display) < 0)
			goto lost;
	zwlr_screencopy_frame_v1_destroy(f);
	if (!fr.ready)
		return 0;
	if (is_10bit(SHM.format))
		return copy_10bit(fr.y_invert);
	if (!freerdp_image_copy_no_overlap(SHM.frame, PIXEL_FORMAT_BGRX32, SHM.frame_stride, 0, 0,
	                                   SHM.width, SHM.height, SHM.data, rdp_format(SHM.format),
	                                   SHM.stride, 0, 0, NULL,
	                                   fr.y_invert ? FREERDP_FLIP_VERTICAL : FREERDP_FLIP_NONE))
		return 0;
	return 1;
lost:
	fprintf(stderr, "spark-rdp: lost the compositor\n");
	return -1;
}

/* ---- the shadow subsystem ------------------------------------------------------------- */

typedef struct {
	rdpShadowSubsystem common;
	HANDLE thread;
	int out;            /* captured output */
} SparkSubsystem;

static void fill_monitor(MONITOR_DEF *m, const struct out *o, int primary)
{
	m->left = o->lx > 0 ? o->lx : 0;
	m->top = o->ly > 0 ? o->ly : 0;
	m->right = m->left + o->pw - 1;
	m->bottom = m->top + o->ph - 1;
	m->flags = primary ? 1 : 0;
}

static UINT32 spark_enum_monitors(MONITOR_DEF *monitors, UINT32 max)
{
	UINT32 n = 0;
	for (int i = 0; i < W.nouts && n < max; i++)
		fill_monitor(&monitors[n++], &W.outs[i], i == 0);
	return n;
}

static void layout_box(int32_t *x0, int32_t *y0, int32_t *x1, int32_t *y1)
{
	*x0 = *y0 = INT32_MAX;
	*x1 = *y1 = INT32_MIN;
	for (int i = 0; i < W.nouts; i++) {
		const struct out *o = &W.outs[i];
		if (o->lx < *x0) *x0 = o->lx;
		if (o->ly < *y0) *y0 = o->ly;
		if (o->lx + o->lw > *x1) *x1 = o->lx + o->lw;
		if (o->ly + o->lh > *y1) *y1 = o->ly + o->lh;
	}
}

/* x, y are pixels in the shared picture; move the pointer to that spot in the layout. */
static void pointer_move(SparkSubsystem *s, UINT16 x, UINT16 y)
{
	const struct out *o = &W.outs[s->out];
	int32_t x0, y0, x1, y1;
	layout_box(&x0, &y0, &x1, &y1);
	int64_t lx = o->lx + (o->pw ? (int64_t)x * o->lw / o->pw : x);
	int64_t ly = o->ly + (o->ph ? (int64_t)y * o->lh / o->ph : y);
	if (lx >= o->lx + o->lw) lx = o->lx + o->lw - 1;
	if (ly >= o->ly + o->lh) ly = o->ly + o->lh - 1;
	zwlr_virtual_pointer_v1_motion_absolute(W.vptr, now_ms(), (uint32_t)(lx - x0),
	                                        (uint32_t)(ly - y0), (uint32_t)(x1 - x0),
	                                        (uint32_t)(y1 - y0));
}

static void pointer_button(uint32_t button, int down)
{
	zwlr_virtual_pointer_v1_button(W.vptr, now_ms(), button,
	                               down ? WL_POINTER_BUTTON_STATE_PRESSED
	                                    : WL_POINTER_BUTTON_STATE_RELEASED);
}

static BOOL spark_mouse(rdpShadowSubsystem *sub, rdpShadowClient *client, UINT16 flags, UINT16 x,
                        UINT16 y)
{
	SparkSubsystem *s = (SparkSubsystem *)sub;
	pthread_mutex_lock(&W.input_lock);
	if (flags & (PTR_FLAGS_WHEEL | PTR_FLAGS_HWHEEL)) {
		/* RDP: positive turns scroll up (or left); Wayland: positive is down (or right). */
		int steps = (flags & PTR_FLAGS_WHEEL_NEGATIVE) ? 1 : -1;
		uint32_t axis = (flags & PTR_FLAGS_WHEEL) ? WL_POINTER_AXIS_VERTICAL_SCROLL
		                                          : WL_POINTER_AXIS_HORIZONTAL_SCROLL;
		zwlr_virtual_pointer_v1_axis_source(W.vptr, WL_POINTER_AXIS_SOURCE_WHEEL);
		zwlr_virtual_pointer_v1_axis_discrete(W.vptr, now_ms(), axis,
		                                      wl_fixed_from_int(15 * steps), steps);
		zwlr_virtual_pointer_v1_frame(W.vptr);
	} else {
		if (flags & PTR_FLAGS_MOVE)
			pointer_move(s, x, y);
		int down = !!(flags & PTR_FLAGS_DOWN);
		if (flags & PTR_FLAGS_BUTTON1)
			pointer_button(BTN_LEFT, down);
		else if (flags & PTR_FLAGS_BUTTON2)
			pointer_button(BTN_RIGHT, down);
		else if (flags & PTR_FLAGS_BUTTON3)
			pointer_button(BTN_MIDDLE, down);
		zwlr_virtual_pointer_v1_frame(W.vptr);
	}
	wl_display_flush(W.display);
	pthread_mutex_unlock(&W.input_lock);
	return TRUE;
}

static BOOL spark_ext_mouse(rdpShadowSubsystem *sub, rdpShadowClient *client, UINT16 flags,
                            UINT16 x, UINT16 y)
{
	SparkSubsystem *s = (SparkSubsystem *)sub;
	pthread_mutex_lock(&W.input_lock);
	pointer_move(s, x, y);
	int down = !!(flags & PTR_XFLAGS_DOWN);
	if (flags & PTR_XFLAGS_BUTTON1)
		pointer_button(BTN_SIDE, down);
	else if (flags & PTR_XFLAGS_BUTTON2)
		pointer_button(BTN_EXTRA, down);
	zwlr_virtual_pointer_v1_frame(W.vptr);
	wl_display_flush(W.display);
	pthread_mutex_unlock(&W.input_lock);
	return TRUE;
}

static BOOL spark_rel_mouse(rdpShadowSubsystem *sub, rdpShadowClient *client, UINT16 flags,
                            INT16 dx, INT16 dy)
{
	pthread_mutex_lock(&W.input_lock);
	zwlr_virtual_pointer_v1_motion(W.vptr, now_ms(), wl_fixed_from_int(dx),
	                               wl_fixed_from_int(dy));
	zwlr_virtual_pointer_v1_frame(W.vptr);
	wl_display_flush(W.display);
	pthread_mutex_unlock(&W.input_lock);
	return TRUE;
}

static BOOL spark_key(rdpShadowSubsystem *sub, rdpShadowClient *client, UINT16 flags, UINT8 code)
{
	DWORD scancode = code;
	if (flags & KBD_FLAGS_EXTENDED)
		scancode |= KBDEXT;
	DWORD vk = GetVirtualKeyCodeFromVirtualScanCode(scancode, WINPR_KBD_TYPE_IBM_ENHANCED);
	if (flags & KBD_FLAGS_EXTENDED)
		vk |= KBDEXT;
	DWORD key = GetKeycodeFromVirtualKeyCode(vk, WINPR_KEYCODE_TYPE_EVDEV);
	if (!key)
		return TRUE;

	int down = !(flags & KBD_FLAGS_RELEASE);
	pthread_mutex_lock(&W.input_lock);
	zwp_virtual_keyboard_v1_key(W.vkbd, now_ms(), key,
	                            down ? WL_KEYBOARD_KEY_STATE_PRESSED
	                                 : WL_KEYBOARD_KEY_STATE_RELEASED);
	/* wlroots doesn't work out modifiers for virtual keyboards; send them ourselves. */
	if (xkb_state_update_key(W.xkb_state, key + 8, down ? XKB_KEY_DOWN : XKB_KEY_UP)) {
		zwp_virtual_keyboard_v1_modifiers(
		    W.vkbd, xkb_state_serialize_mods(W.xkb_state, XKB_STATE_MODS_DEPRESSED),
		    xkb_state_serialize_mods(W.xkb_state, XKB_STATE_MODS_LATCHED),
		    xkb_state_serialize_mods(W.xkb_state, XKB_STATE_MODS_LOCKED),
		    xkb_state_serialize_layout(W.xkb_state, XKB_STATE_LAYOUT_EFFECTIVE));
	}
	wl_display_flush(W.display);
	pthread_mutex_unlock(&W.input_lock);
	return TRUE;
}

static BOOL spark_unicode(rdpShadowSubsystem *sub, rdpShadowClient *client, UINT16 flags,
                          UINT16 code)
{
	return TRUE; /* viewers send scancodes; nothing to do */
}

static BOOL spark_sync(rdpShadowSubsystem *sub, rdpShadowClient *client, UINT32 flags)
{
	return TRUE;
}

static int process_message(SparkSubsystem *s, wMessage *msg)
{
	if (msg->id == SHADOW_MSG_IN_REFRESH_REQUEST_ID)
		shadow_subsystem_frame_update(&s->common);
	if (msg->Free)
		msg->Free(msg);
	return 1;
}

static int resize_if_needed(SparkSubsystem *s)
{
	rdpShadowServer *server = s->common.server;
	const struct out *o = &W.outs[s->out];
	if ((UINT32)SHM.width == server->surface->width &&
	    (UINT32)SHM.height == server->surface->height)
		return 0;
	struct out tmp = *o;
	tmp.pw = (int32_t)SHM.width;
	tmp.ph = (int32_t)SHM.height;
	W.outs[s->out].pw = tmp.pw;
	W.outs[s->out].ph = tmp.ph;
	s->common.numMonitors = spark_enum_monitors(s->common.monitors, 16);
	fill_monitor(&s->common.virtualScreen, &tmp, 1);
	if (!shadow_screen_resize(server->screen))
		return -1;
	return 1;
}

static int grab(SparkSubsystem *s)
{
	rdpShadowServer *server = s->common.server;
	rdpShadowSurface *surface = server->surface;
	if (ArrayList_Count(server->clients) < 1)
		return 0;

	int rc = capture(s->out);
	if (rc <= 0)
		return rc;
	if (resize_if_needed(s) < 0)
		return -1;
	surface = server->surface;

	EnterCriticalSection(&surface->lock);
	RECTANGLE_16 rect = { 0, 0, (UINT16)surface->width, (UINT16)surface->height };
	int changed = shadow_capture_compare_with_format(
	    surface->data, surface->format, surface->scanline, surface->width, surface->height,
	    SHM.frame, PIXEL_FORMAT_BGRX32, SHM.frame_stride, &rect);
	if (changed > 0) {
		region16_union_rect(&surface->invalidRegion, &surface->invalidRegion, &rect);
		freerdp_image_copy_no_overlap(surface->data, surface->format, surface->scanline,
		                              rect.left, rect.top, rect.right - rect.left,
		                              rect.bottom - rect.top, SHM.frame, PIXEL_FORMAT_BGRX32,
		                              SHM.frame_stride, rect.left, rect.top, NULL,
		                              FREERDP_FLIP_NONE);
	}
	LeaveCriticalSection(&surface->lock);

	if (changed > 0) {
		shadow_subsystem_frame_update(&s->common);
		if (ArrayList_Count(server->clients) == 1) {
			rdpShadowClient *c = ArrayList_GetItem(server->clients, 0);
			if (c) {
				UINT32 fps = shadow_encoder_preferred_fps(c->encoder);
				s->common.captureFrameRate = fps ? (fps > 30 ? 30 : fps) : 16;
			}
		}
		EnterCriticalSection(&surface->lock);
		region16_clear(&surface->invalidRegion);
		LeaveCriticalSection(&surface->lock);
	}
	return 1;
}

static DWORD WINAPI spark_thread(LPVOID arg)
{
	SparkSubsystem *s = arg;
	wMessagePipe *pipe = s->common.MsgPipe;
	HANDLE events[] = { MessageQueue_Event(pipe->In) };
	s->common.captureFrameRate = 16;
	UINT64 next = GetTickCount64();

	for (;;) {
		UINT64 t = GetTickCount64();
		DWORD wait = t >= next ? 0 : (DWORD)(next - t);
		WaitForMultipleObjects(1, events, FALSE, wait);

		wMessage msg;
		if (WaitForSingleObject(events[0], 0) == WAIT_OBJECT_0 &&
		    MessageQueue_Peek(pipe->In, &msg, TRUE)) {
			if (msg.id == WMQ_QUIT)
				break;
			process_message(s, &msg);
		}
		if (GetTickCount64() >= next) {
			if (grab(s) < 0) {
				/* The compositor is gone: stop the server so spark-share sees us exit. */
				SetEvent(s->common.server->StopEvent);
				break;
			}
			next = GetTickCount64() + 1000 / (s->common.captureFrameRate ? s->common.captureFrameRate : 16);
		}
	}
	ExitThread(0);
	return 0;
}

static int spark_init(rdpShadowSubsystem *sub)
{
	SparkSubsystem *s = (SparkSubsystem *)sub;
	s->out = (int)sub->selectedMonitor < W.nouts ? (int)sub->selectedMonitor : 0;
	/* Report only the shared output, as monitor 0, so the shadow screen is exactly it. */
	sub->numMonitors = spark_enum_monitors(sub->monitors, 16);
	sub->selectedMonitor = (UINT32)s->out;
	fill_monitor(&sub->virtualScreen, &W.outs[s->out], 1);
	if (input_setup() < 0) {
		fprintf(stderr, "spark-rdp: could not set up the virtual keyboard\n");
		return -1;
	}
	return 1;
}

static int spark_uninit(rdpShadowSubsystem *sub)
{
	shm_drop();
	return 1;
}

static int spark_start(rdpShadowSubsystem *sub)
{
	SparkSubsystem *s = (SparkSubsystem *)sub;
	s->thread = CreateThread(NULL, 0, spark_thread, s, 0, NULL);
	return s->thread ? 1 : -1;
}

static int spark_stop(rdpShadowSubsystem *sub)
{
	SparkSubsystem *s = (SparkSubsystem *)sub;
	if (s->thread) {
		if (MessageQueue_PostQuit(sub->MsgPipe->In, 0))
			WaitForSingleObject(s->thread, INFINITE);
		CloseHandle(s->thread);
		s->thread = NULL;
	}
	return 1;
}

static rdpShadowSubsystem *spark_new(void)
{
	SparkSubsystem *s = calloc(1, sizeof *s);
	if (!s)
		return NULL;
	s->common.SynchronizeEvent = spark_sync;
	s->common.KeyboardEvent = spark_key;
	s->common.UnicodeKeyboardEvent = spark_unicode;
	s->common.MouseEvent = spark_mouse;
	s->common.ExtendedMouseEvent = spark_ext_mouse;
	s->common.RelMouseEvent = spark_rel_mouse;
	return &s->common;
}

static void spark_free(rdpShadowSubsystem *sub)
{
	spark_uninit(sub);
	free(sub);
}

static int spark_entry(RDP_SHADOW_ENTRY_POINTS *ep)
{
	ep->New = spark_new;
	ep->Free = spark_free;
	ep->Init = spark_init;
	ep->Uninit = spark_uninit;
	ep->Start = spark_start;
	ep->Stop = spark_stop;
	ep->EnumMonitors = spark_enum_monitors;
	return 1;
}

/* ---- sign-in ---------------------------------------------------------------------------- */

static int valid_user(const char *u)
{
	if (!*u || strlen(u) > 64)
		return 0;
	for (const char *p = u; *p; p++)
		if (!((*p >= 'a' && *p <= 'z') || (*p >= 'A' && *p <= 'Z') ||
		      (*p >= '0' && *p <= '9') || *p == '-' || *p == '_' || *p == '.'))
			return 0;
	return 1;
}

static char *read_line(void)
{
	char *line = NULL;
	size_t cap = 0;
	ssize_t n = getline(&line, &cap, stdin);
	if (n < 0) {
		free(line);
		return NULL;
	}
	while (n > 0 && (line[n - 1] == '\n' || line[n - 1] == '\r'))
		line[--n] = 0;
	return line;
}

/* MD4 (RFC 1320), only for the NT hash below: Fedora's OpenSSL leaves MD4 out of its default
 * provider, so WinPR's NTOWFv1A fails there. */
#define MD4_ROTL(x, n) (((x) << (n)) | ((x) >> (32 - (n))))
static void md4_block(uint32_t st[4], const uint8_t *p)
{
	uint32_t x[16];
	for (int i = 0; i < 16; i++)
		x[i] = (uint32_t)p[i * 4] | (uint32_t)p[i * 4 + 1] << 8 | (uint32_t)p[i * 4 + 2] << 16 |
		       (uint32_t)p[i * 4 + 3] << 24;
	uint32_t a = st[0], b = st[1], c = st[2], d = st[3];
	static const int r1[4] = { 3, 7, 11, 19 }, r2[4] = { 3, 5, 9, 13 }, r3[4] = { 3, 9, 11, 15 };
	static const int o3[16] = { 0, 8, 4, 12, 2, 10, 6, 14, 1, 9, 5, 13, 3, 11, 7, 15 };
	for (int i = 0; i < 16; i++) {
		uint32_t t = a + ((b & c) | (~b & d)) + x[i];
		a = d; d = c; c = b; b = MD4_ROTL(t, r1[i % 4]);
	}
	for (int i = 0; i < 16; i++) {
		uint32_t t = a + ((b & c) | (b & d) | (c & d)) + x[(i % 4) * 4 + i / 4] + 0x5a827999u;
		a = d; d = c; c = b; b = MD4_ROTL(t, r2[i % 4]);
	}
	for (int i = 0; i < 16; i++) {
		uint32_t t = a + (b ^ c ^ d) + x[o3[i]] + 0x6ed9eba1u;
		a = d; d = c; c = b; b = MD4_ROTL(t, r3[i % 4]);
	}
	st[0] += a; st[1] += b; st[2] += c; st[3] += d;
}

static void md4(const uint8_t *msg, size_t len, uint8_t out[16])
{
	uint32_t st[4] = { 0x67452301u, 0xefcdab89u, 0x98badcfeu, 0x10325476u };
	uint8_t block[64];
	size_t i = 0;
	for (; i + 64 <= len; i += 64)
		md4_block(st, msg + i);
	size_t rest = len - i;
	memset(block, 0, sizeof block);
	memcpy(block, msg + i, rest);
	block[rest] = 0x80;
	if (rest >= 56) {
		md4_block(st, block);
		memset(block, 0, sizeof block);
	}
	uint64_t bits = (uint64_t)len * 8;
	for (int k = 0; k < 8; k++)
		block[56 + k] = (uint8_t)(bits >> (8 * k));
	md4_block(st, block);
	for (int k = 0; k < 16; k++)
		out[k] = (uint8_t)(st[k / 4] >> (8 * (k % 4)));
	explicit_bzero(block, sizeof block);
}

/* NT hash: MD4 of the password in UTF-16LE. 0 on bad UTF-8. */
static int nt_hash(const char *pw, uint8_t out[16])
{
	size_t n = strlen(pw);
	uint8_t *u = malloc(n * 4 + 1);
	size_t m = 0;
	if (!u)
		return 0;
	const unsigned char *s = (const unsigned char *)pw;
	for (size_t i = 0; i < n;) {
		uint32_t cp;
		int extra;
		if (s[i] < 0x80) { cp = s[i]; extra = 0; }
		else if ((s[i] & 0xe0) == 0xc0) { cp = s[i] & 0x1f; extra = 1; }
		else if ((s[i] & 0xf0) == 0xe0) { cp = s[i] & 0x0f; extra = 2; }
		else if ((s[i] & 0xf8) == 0xf0) { cp = s[i] & 0x07; extra = 3; }
		else goto bad;
		if (i + (size_t)extra >= n + (extra ? 0 : 1))
			goto bad;
		for (int k = 1; k <= extra; k++) {
			if ((s[i + k] & 0xc0) != 0x80)
				goto bad;
			cp = (cp << 6) | (s[i + k] & 0x3f);
		}
		i += (size_t)extra + 1;
		if (cp >= 0x10000) {
			cp -= 0x10000;
			uint16_t hi = (uint16_t)(0xd800 + (cp >> 10)), lo = (uint16_t)(0xdc00 + (cp & 0x3ff));
			u[m++] = hi & 0xff; u[m++] = hi >> 8;
			u[m++] = lo & 0xff; u[m++] = lo >> 8;
		} else {
			u[m++] = cp & 0xff; u[m++] = (uint8_t)(cp >> 8);
		}
	}
	md4(u, m, out);
	explicit_bzero(u, n * 4 + 1);
	free(u);
	return 1;
bad:
	explicit_bzero(u, n * 4 + 1);
	free(u);
	return 0;
}

/* Write DIR/sam with one account: user:domain:LM:NT::: (empty domain and LM). */
static char *write_sam(const char *dir, const char *user, const char *password)
{
	BYTE hash[16];
	if (!nt_hash(password, hash)) {
		errno = EINVAL;
		return NULL;
	}
	char *path = NULL;
	if (asprintf(&path, "%s/sam", dir) < 0)
		return NULL;
	unlink(path);
	int fd = open(path, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
	FILE *f = fd >= 0 ? fdopen(fd, "w") : NULL;
	if (!f) {
		if (fd >= 0)
			close(fd);
		free(path);
		return NULL;
	}
	fprintf(f, "%s:::", user);
	for (int i = 0; i < 16; i++)
		fprintf(f, "%02x", hash[i]);
	fprintf(f, ":::\n");
	int bad = fclose(f) != 0;
	memset(hash, 0, sizeof hash);
	if (bad) {
		unlink(path);
		free(path);
		return NULL;
	}
	return path;
}

/* ---- main ------------------------------------------------------------------------------- */

int main(int argc, char **argv)
{
	if (argc < 3 || argc > 5) {
		fprintf(stderr, "usage: spark-rdp DIR PORT [ADDRESS] [MONITOR]  (user and password on stdin)\n");
		return 2;
	}
	const char *dir = argv[1];
	char *end = NULL;
	long port = strtol(argv[2], &end, 10);
	if (!end || *end || port < 1 || port > 65535) {
		fprintf(stderr, "spark-rdp: bad port\n");
		return 2;
	}
	const char *address = argc > 3 ? argv[3] : "127.0.0.1";
	const char *monitor = argc > 4 ? argv[4] : NULL;

	char *user = read_line();
	char *password = read_line();
	if (!user || !password || !valid_user(user) || !*password) {
		fprintf(stderr, "spark-rdp: expected a user name and a password on stdin\n");
		return 2;
	}
	char *sam = write_sam(dir, user, password);
	explicit_bzero(password, strlen(password));
	free(password);
	free(user);
	if (!sam) {
		fprintf(stderr, "spark-rdp: could not write the sign-in file: %s\n", strerror(errno));
		return 1;
	}

	if (wayland_connect() < 0) {
		unlink(sam);
		return 3;
	}

	shadow_subsystem_set_entry(spark_entry);
	rdpShadowServer *server = shadow_server_new();
	int status = 1;
	if (!server)
		goto out;

	rdpSettings *st = server->settings;
	if (!freerdp_settings_set_bool(st, FreeRDP_NlaSecurity, TRUE) ||
	    !freerdp_settings_set_bool(st, FreeRDP_TlsSecurity, FALSE) ||
	    !freerdp_settings_set_bool(st, FreeRDP_RdpSecurity, FALSE) ||
	    !freerdp_settings_set_bool(st, FreeRDP_ExtSecurity, FALSE) ||
	    !freerdp_settings_set_uint32(st, FreeRDP_ColorDepth, 32) ||
	    !freerdp_settings_set_bool(st, FreeRDP_NSCodec, TRUE) ||
	    !freerdp_settings_set_bool(st, FreeRDP_RemoteFxCodec, TRUE) ||
	    !freerdp_settings_set_bool(st, FreeRDP_RemoteFxImageCodec, TRUE) ||
	    !freerdp_settings_set_uint32(st, FreeRDP_RemoteFxRlgrMode, RLGR3) ||
	    !freerdp_settings_set_bool(st, FreeRDP_GfxH264, TRUE) ||
	    !freerdp_settings_set_bool(st, FreeRDP_GfxAVC444, TRUE) ||
	    !freerdp_settings_set_bool(st, FreeRDP_GfxAVC444v2, TRUE) ||
	    !freerdp_settings_set_bool(st, FreeRDP_GfxProgressive, TRUE) ||
	    !freerdp_settings_set_bool(st, FreeRDP_GfxProgressiveV2, TRUE) ||
	    !freerdp_settings_set_bool(st, FreeRDP_MouseUseRelativeMove, FALSE) ||
	    !freerdp_settings_set_bool(st, FreeRDP_HasRelativeMouseEvent, FALSE) ||
	    !freerdp_settings_set_bool(st, FreeRDP_HasExtendedMouseEvent, TRUE) ||
	    !freerdp_settings_set_bool(st, FreeRDP_HasHorizontalWheel, TRUE))
		goto out;

	/* Port, address, monitor and the SAM file go through FreeRDP's own option parser. */
	char *a_port = NULL, *a_bind = NULL, *a_sam = NULL, *a_mon = NULL;
	if (asprintf(&a_port, "/port:%ld", port) < 0 || asprintf(&a_bind, "/bind-address:%s", address) < 0 ||
	    asprintf(&a_sam, "/sam-file:%s", sam) < 0 ||
	    asprintf(&a_mon, "/monitors:%s", monitor ? monitor : "0") < 0)
		goto out;
	char *args[] = { argv[0], a_port, a_bind, a_sam, a_mon, "/max-connections:1",
	                 "/log-level:WARN", NULL };
	COMMAND_LINE_ARGUMENT_A table[] = {
		{ "log-level", COMMAND_LINE_VALUE_REQUIRED, "<level>", NULL, NULL, -1, NULL, "log level" },
		{ "port", COMMAND_LINE_VALUE_REQUIRED, "<number>", NULL, NULL, -1, NULL, "port" },
		{ "bind-address", COMMAND_LINE_VALUE_REQUIRED, "<address>", NULL, NULL, -1, NULL, "address" },
		{ "monitors", COMMAND_LINE_VALUE_OPTIONAL, "<n>", NULL, NULL, -1, NULL, "monitor" },
		{ "max-connections", COMMAND_LINE_VALUE_REQUIRED, "<number>", NULL, NULL, -1, NULL, "max" },
		{ "sam-file", COMMAND_LINE_VALUE_REQUIRED, "<file>", NULL, NULL, -1, NULL, "SAM file" },
		{ NULL, 0, NULL, NULL, NULL, -1, NULL, NULL },
	};
	int nargs = (int)(sizeof args / sizeof args[0]) - 1;
	status = shadow_server_parse_command_line(server, nargs, args, table);
	free(a_port);
	free(a_bind);
	free(a_sam);
	free(a_mon);
	if (status < 0) {
		fprintf(stderr, "spark-rdp: bad options (%d)\n", status);
		status = 2;
		goto out;
	}

	server->ConfigPath = strdup(dir);
	if (!server->ConfigPath || shadow_server_init(server) < 0) {
		fprintf(stderr, "spark-rdp: could not start (certificate in %s/shadow?)\n", dir);
		status = 1;
		goto out;
	}
	if (shadow_server_start(server) < 0) {
		fprintf(stderr, "spark-rdp: could not listen on %s:%ld\n", address, port);
		status = 1;
		goto out;
	}
	WaitForSingleObject(server->thread, INFINITE);
	DWORD code = 0;
	status = GetExitCodeThread(server->thread, &code) ? (int)code : 1;

out:
	if (server) {
		shadow_server_uninit(server);
		shadow_server_free(server);
	}
	unlink(sam);
	free(sam);
	if (W.display)
		wl_display_disconnect(W.display);
	return status;
}
