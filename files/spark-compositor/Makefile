# Spark compositor, built on wlroots 0.19 (Fedora package wlroots0.19-devel).
#   make            builds ./spark-compositor
#   make install DESTDIR=/x PREFIX=/usr
# Protocol headers are generated here from wayland-protocols and wlr-protocols; nothing is
# vendored. Same warning flags as the image's other compiled piece (sparkos-capslock).
CC      ?= gcc
PREFIX  ?= /usr
PKGS     = wlroots-0.19 wayland-server xkbcommon libinput pixman-1
WP       = $(shell pkg-config --variable=pkgdatadir wayland-protocols)
WLRP     = /usr/share/wlr-protocols/unstable
CFLAGS  ?= -O2
CFLAGS  += -Wall -Wextra -Werror -std=gnu11 -D_FORTIFY_SOURCE=3 -fstack-protector-strong \
           -DWLR_USE_UNSTABLE -Wno-unused-parameter -I. $(shell pkg-config --cflags $(PKGS))
LIBS     = $(shell pkg-config --libs $(PKGS)) -lm

PROTO_H  = xdg-shell-protocol.h cursor-shape-v1-protocol.h tearing-control-v1-protocol.h \
           ext-image-copy-capture-v1-protocol.h pointer-constraints-unstable-v1-protocol.h \
           content-type-v1-protocol.h color-management-v1-protocol.h tablet-v2-protocol.h \
           wlr-layer-shell-unstable-v1-protocol.h wlr-output-power-management-unstable-v1-protocol.h

all: spark-compositor

xdg-shell-protocol.h: $(WP)/stable/xdg-shell/xdg-shell.xml
	wayland-scanner server-header $< $@
cursor-shape-v1-protocol.h: $(WP)/staging/cursor-shape/cursor-shape-v1.xml
	wayland-scanner server-header $< $@
tearing-control-v1-protocol.h: $(WP)/staging/tearing-control/tearing-control-v1.xml
	wayland-scanner server-header $< $@
ext-image-copy-capture-v1-protocol.h: $(WP)/staging/ext-image-copy-capture/ext-image-copy-capture-v1.xml
	wayland-scanner server-header $< $@
pointer-constraints-unstable-v1-protocol.h: $(WP)/unstable/pointer-constraints/pointer-constraints-unstable-v1.xml
	wayland-scanner server-header $< $@
content-type-v1-protocol.h: $(WP)/staging/content-type/content-type-v1.xml
	wayland-scanner server-header $< $@
color-management-v1-protocol.h: $(WP)/staging/color-management/color-management-v1.xml
	wayland-scanner server-header $< $@
tablet-v2-protocol.h: $(WP)/stable/tablet/tablet-v2.xml
	wayland-scanner server-header $< $@
wlr-layer-shell-unstable-v1-protocol.h: $(WLRP)/wlr-layer-shell-unstable-v1.xml
	wayland-scanner server-header $< $@
wlr-output-power-management-unstable-v1-protocol.h: $(WLRP)/wlr-output-power-management-unstable-v1.xml
	wayland-scanner server-header $< $@

spark-compositor: spark-compositor.c $(PROTO_H)
	$(CC) $(CFLAGS) -o $@ spark-compositor.c $(LIBS)

install: spark-compositor
	install -Dm755 spark-compositor $(DESTDIR)$(PREFIX)/bin/spark-compositor

clean:
	rm -f spark-compositor $(PROTO_H)

.PHONY: all install clean
