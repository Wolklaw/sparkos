# spark-rdp: the RDP server behind Spark Connect's "Take control" in the Spark compositor session.
# FreeRDP's shadow server with a spark-compositor backend: wlr-screencopy for the picture,
# wlr-virtual-pointer and zwp-virtual-keyboard for input. spark-share starts it.
CC      ?= gcc
PREFIX  ?= /usr
WLRP     = /usr/share/wlr-protocols/unstable
WP       = /usr/share/wayland-protocols
PKGS     = wayland-client xkbcommon freerdp-shadow3 freerdp-server3 freerdp3 winpr3
CFLAGS  ?= -O2
CFLAGS  += -Wall -Wextra -Werror -std=gnu11 -D_FORTIFY_SOURCE=3 -fstack-protector-strong \
           -Wno-unused-parameter -Wno-missing-field-initializers -Wno-deprecated-declarations -I. \
           $(shell pkg-config --cflags $(PKGS))
LIBS     = $(shell pkg-config --libs $(PKGS)) -lpthread

PROTOS   = screencopy vptr vkbd xdg-output
screencopy_XML = $(WLRP)/wlr-screencopy-unstable-v1.xml
vptr_XML       = $(WLRP)/wlr-virtual-pointer-unstable-v1.xml
vkbd_XML       = virtual-keyboard-unstable-v1.xml
xdg-output_XML = $(WP)/unstable/xdg-output/xdg-output-unstable-v1.xml

HEADERS  = $(PROTOS:%=%-protocol.h)
SOURCES  = $(PROTOS:%=%-protocol.c)

all: spark-rdp

%-protocol.h:
	wayland-scanner client-header $($*_XML) $@
%-protocol.c:
	wayland-scanner private-code $($*_XML) $@

spark-rdp: spark-rdp.c $(HEADERS) $(SOURCES)
	$(CC) $(CFLAGS) -o $@ spark-rdp.c $(SOURCES) $(LIBS)

install: spark-rdp
	install -Dm755 spark-rdp $(DESTDIR)$(PREFIX)/libexec/spark-rdp

clean:
	rm -f spark-rdp $(HEADERS) $(SOURCES)

.PHONY: all install clean
