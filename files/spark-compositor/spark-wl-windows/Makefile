# spark-wl-windows: the Spark shell's window list in the Spark compositor session.
# Reads zwlr_foreign_toplevel_manager_v1 and prints the windows as one JSON line per change;
# takes "activate|minimize|unminimize|close|maximize|unmaximize ID" lines on stdin.
CC      ?= gcc
PREFIX  ?= /usr
WLRP     = /usr/share/wlr-protocols/unstable
CFLAGS  ?= -O2
CFLAGS  += -Wall -Wextra -Werror -std=gnu11 -D_FORTIFY_SOURCE=3 -fstack-protector-strong \
           -Wno-unused-parameter -I. $(shell pkg-config --cflags wayland-client)
LIBS     = $(shell pkg-config --libs wayland-client)
XML      = $(WLRP)/wlr-foreign-toplevel-management-unstable-v1.xml

all: spark-wl-windows

ftl-protocol.h: $(XML)
	wayland-scanner client-header $< $@
ftl-protocol.c: $(XML)
	wayland-scanner private-code $< $@

spark-wl-windows: spark-wl-windows.c ftl-protocol.h ftl-protocol.c
	$(CC) $(CFLAGS) -o $@ spark-wl-windows.c ftl-protocol.c $(LIBS)

install: spark-wl-windows
	install -Dm755 spark-wl-windows $(DESTDIR)$(PREFIX)/libexec/spark-wl-windows

clean:
	rm -f spark-wl-windows ftl-protocol.h ftl-protocol.c

.PHONY: all install clean
