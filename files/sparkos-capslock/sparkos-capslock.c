/*
 * sparkos-capslock: Caps Lock turns on and off when it's pressed, like on Windows.
 *
 * Linux turns Caps Lock off when the key is released. If you tap Caps Lock to turn it off and
 * start the next letter before your finger is fully off the key, that letter still comes out in
 * capitals. This program sits between one physical keyboard and the desktop and changes one thing:
 * when Caps Lock goes down it sends a whole Caps Lock press and release at once, and it drops the
 * key's own release (and its repeats). Every other event, keys, mouse movement and scrolling on
 * keyboards that have them, passes through unchanged.
 *
 * How: it opens the keyboard, makes a copy of it with uinput (same name, IDs and capabilities),
 * takes the keyboard for itself (EVIOCGRAB) and writes its events to the copy. The desktop reads
 * the copy. Caps Lock's light is set on the copy and passed back to the keyboard. If this program
 * stops or crashes, the grab and the copy go away and the keyboard works the Linux way again.
 *
 * Usage: sparkos-capslock /dev/input/eventN   (run by sparkos-capslock@eventN.service, which
 * udev starts for each physical keyboard: /usr/lib/udev/rules.d/80-sparkos-capslock.rules)
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/input.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>

#include <libevdev/libevdev.h>
#include <libevdev/libevdev-uinput.h>

#define BIT_IS_SET(arr, bit) ((arr)[(bit) / 8] & (1u << ((bit) % 8)))

static volatile sig_atomic_t stop;

static void on_signal(int sig)
{
	(void)sig;
	stop = 1;
}

/* Keys passed to the copy as pressed and not yet released, to release them after lost events. */
static unsigned char down[KEY_CNT];

static int emit(struct libevdev_uinput *ui, unsigned int type, unsigned int code, int value)
{
	int rc = libevdev_uinput_write_event(ui, type, code, value);
	if (rc < 0)
		fprintf(stderr, "writing to the copy failed: %s\n", strerror(-rc));
	return rc;
}

/* Waits (up to 3 s) until no key is held, so no key is left pressed on the desktop's side when
 * the keyboard is taken over (its release would go to the copy, which never saw the press). */
static void wait_for_keys_up(int fd)
{
	unsigned char keys[KEY_CNT / 8 + 1];
	struct timespec pause = { 0, 20 * 1000 * 1000 };

	for (int i = 0; i < 150; i++) {
		int held = 0;

		memset(keys, 0, sizeof keys);
		if (ioctl(fd, EVIOCGKEY(sizeof keys), keys) < 0)
			return;
		for (size_t b = 0; b < sizeof keys; b++)
			held |= keys[b];
		if (!held)
			return;
		nanosleep(&pause, NULL);
	}
}

/* After lost events (SYN_DROPPED): release on the copy every key that's no longer held. */
static void resync(int fd, struct libevdev_uinput *ui)
{
	unsigned char keys[KEY_CNT / 8 + 1];
	int sent = 0;

	memset(keys, 0, sizeof keys);
	if (ioctl(fd, EVIOCGKEY(sizeof keys), keys) < 0)
		return;
	for (unsigned int code = 0; code < KEY_CNT; code++) {
		if (down[code] && !BIT_IS_SET(keys, code)) {
			emit(ui, EV_KEY, code, 0);
			down[code] = 0;
			sent = 1;
		}
	}
	if (sent)
		emit(ui, EV_SYN, SYN_REPORT, 0);
}

int main(int argc, char **argv)
{
	struct libevdev *dev = NULL;
	struct libevdev_uinput *ui = NULL;
	struct sigaction sa;
	int fd, uifd, rc;
	int skipping = 0; /* after SYN_DROPPED, until the next SYN_REPORT */

	if (argc != 2) {
		fprintf(stderr, "usage: %s /dev/input/eventN\n", argv[0]);
		return 2;
	}

	memset(&sa, 0, sizeof sa);
	sa.sa_handler = on_signal;
	sigaction(SIGTERM, &sa, NULL);
	sigaction(SIGINT, &sa, NULL);
	sigaction(SIGHUP, &sa, NULL);

	fd = open(argv[1], O_RDWR | O_NONBLOCK | O_CLOEXEC);
	if (fd < 0) {
		fprintf(stderr, "%s: %s\n", argv[1], strerror(errno));
		return 1;
	}

	rc = libevdev_new_from_fd(fd, &dev);
	if (rc < 0) {
		fprintf(stderr, "%s: %s\n", argv[1], strerror(-rc));
		return 1;
	}

	if (!libevdev_has_event_code(dev, EV_KEY, KEY_CAPSLOCK)) {
		printf("%s (%s) has no Caps Lock key; left alone\n", argv[1], libevdev_get_name(dev));
		return 0;
	}

	/* Keyboards with force feedback don't exist in practice; a copy that offered it would make
	 * a program that uploads an effect wait for this one. */
	libevdev_disable_event_type(dev, EV_FF);

	wait_for_keys_up(fd);

	rc = libevdev_uinput_create_from_device(dev, LIBEVDEV_UINPUT_OPEN_MANAGED, &ui);
	if (rc < 0) {
		fprintf(stderr, "%s: can't make the copy: %s\n", argv[1], strerror(-rc));
		return 1;
	}
	uifd = libevdev_uinput_get_fd(ui);
	fcntl(uifd, F_SETFL, fcntl(uifd, F_GETFL) | O_NONBLOCK);

	if (ioctl(fd, EVIOCGRAB, (void *)1) < 0) {
		/* Another program (a remapper the user installed) already has it: leave it to them. */
		printf("%s (%s) is taken by another program (%s); left alone\n",
		       argv[1], libevdev_get_name(dev), strerror(errno));
		libevdev_uinput_destroy(ui);
		return 0;
	}

	printf("%s (%s): Caps Lock toggles when pressed; the desktop reads %s\n",
	       argv[1], libevdev_get_name(dev), libevdev_uinput_get_devnode(ui));
	fflush(stdout);

	while (!stop) {
		struct pollfd pfd[2] = { { fd, POLLIN, 0 }, { uifd, POLLIN, 0 } };
		struct input_event evs[64];
		ssize_t n;

		if (poll(pfd, 2, -1) < 0) {
			if (errno == EINTR)
				continue;
			perror("poll");
			break;
		}

		if (pfd[0].revents & (POLLERR | POLLHUP | POLLNVAL)) {
			printf("%s is gone\n", argv[1]);
			break;
		}

		if (pfd[0].revents & POLLIN) {
			n = read(fd, evs, sizeof evs);
			if (n < 0) {
				if (errno == EAGAIN || errno == EINTR)
					continue;
				if (errno == ENODEV) {
					printf("%s is gone\n", argv[1]);
					break;
				}
				perror("read");
				break;
			}

			for (size_t i = 0; i < (size_t)n / sizeof *evs; i++) {
				const struct input_event *ev = &evs[i];

				if (skipping) {
					if (ev->type == EV_SYN && ev->code == SYN_REPORT) {
						skipping = 0;
						resync(fd, ui);
					}
					continue;
				}

				if (ev->type == EV_SYN && ev->code == SYN_DROPPED) {
					skipping = 1;
					continue;
				}

				if (ev->type == EV_KEY) {
					/* Repeats: the copy makes its own (the kernel repeats for every
					 * device that has EV_REP), so passing these on would double them. */
					if (ev->value == 2)
						continue;

					if (ev->code == KEY_CAPSLOCK) {
						/* The whole press now; the key's own release is dropped. */
						if (ev->value == 1) {
							emit(ui, EV_KEY, KEY_CAPSLOCK, 1);
							emit(ui, EV_SYN, SYN_REPORT, 0);
							emit(ui, EV_KEY, KEY_CAPSLOCK, 0);
							emit(ui, EV_SYN, SYN_REPORT, 0);
						}
						continue;
					}

					if (ev->code < KEY_CNT)
						down[ev->code] = ev->value ? 1 : 0;
				}

				emit(ui, ev->type, ev->code, ev->value);
			}
		}

		if (pfd[1].revents & POLLIN) {
			/* What the desktop sets on the copy: the lights (Caps Lock, Num Lock...) go to
			 * the keyboard. */
			n = read(uifd, evs, sizeof evs);
			for (size_t i = 0; n > 0 && i < (size_t)n / sizeof *evs; i++) {
				if (evs[i].type == EV_LED) {
					struct input_event led[2];

					memset(led, 0, sizeof led);
					led[0].type = EV_LED;
					led[0].code = evs[i].code;
					led[0].value = evs[i].value;
					led[1].type = EV_SYN;
					led[1].code = SYN_REPORT;
					if (write(fd, led, sizeof led) < 0 && errno == ENODEV)
						stop = 1;
				}
			}
		}
	}

	/* Removing the copy releases any key still held on it. */
	libevdev_uinput_destroy(ui);
	ioctl(fd, EVIOCGRAB, (void *)0);
	libevdev_free(dev);
	close(fd);
	return 0;
}
