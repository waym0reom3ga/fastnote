/* fnprobe -- interaction latency probe for the FastNote comparison.
 *
 * Measures the interval a user actually experiences: from the instant a synthetic input
 * event is handed to the X server, to the instant the window's pixels change in response.
 * Both ends are real. The click is delivered through XTEST, so it enters the same event
 * queue a mouse produces and the application cannot tell the difference. The pixel change
 * is observed by reading the window's contents directly.
 *
 * Why not measure inside the application: an in-process timer stops when the handler
 * returns, which is before layout, compositing and presentation have happened. That number
 * flatters every toolkit, and flatters the ones that defer work the most. The number here
 * includes everything the user waits for.
 *
 * Why not ImageMagick: spawning `import` costs ~23 ms on this machine, the same order as
 * the intervals being measured. A plain XGetImage of the whole window is barely better at
 * ~21 ms, because the pixels are marshalled through the X socket. Capturing into a shared
 * memory segment instead costs ~1.9 ms median, so the instrument is an order of magnitude
 * finer than the signal. fnres reports the figure for the machine in use, and it is
 * published alongside the latencies as their resolution.
 *
 * Usage:
 *   fnprobe --window <id> --settle <ms> click <x> <y>
 *   fnprobe --window <id> --settle <ms> key <keysym>
 *   fnprobe --window <id> --settle <ms> type <string>
 *   fnprobe --window <id> baseline
 *
 * Prints one line of TSV to stdout: event<TAB>latency_ms<TAB>changed_px
 * Exit status 0 when a change was observed, 3 when the timeout expired with no change.
 */

#define _POSIX_C_SOURCE 200809L
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <X11/extensions/XTest.h>
#include <X11/extensions/XShm.h>
#include <sys/ipc.h>
#include <sys/shm.h>
#include <X11/keysym.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <time.h>
#include <unistd.h>

static double now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}

/* A downsampled fingerprint of the window: every step'th pixel, summed per channel.
 * Comparing full frames would make the probe itself the slow part; a stride of 4 still
 * notices a single repainted button. */
/* A capturer holds a shared-memory image bound to one screen region. */
typedef struct {
    Display *dpy;
    Window root;
    int x, y, w, h;
    XImage *img;
    XShmSegmentInfo shm;
    unsigned char *prev;
    size_t nbytes;
} capturer_t;

static int cap_init(capturer_t *c, Display *dpy, Window root, Visual *vis, int depth,
                    int x, int y, int w, int h) {
    memset(c, 0, sizeof(*c));
    c->dpy = dpy; c->root = root; c->x = x; c->y = y; c->w = w; c->h = h;

    c->img = XShmCreateImage(dpy, vis, (unsigned)depth, ZPixmap, NULL, &c->shm,
                             (unsigned)w, (unsigned)h);
    if (!c->img) return -1;

    c->nbytes = (size_t)c->img->bytes_per_line * (size_t)c->img->height;
    c->shm.shmid = shmget(IPC_PRIVATE, c->nbytes, IPC_CREAT | 0600);
    if (c->shm.shmid < 0) return -1;
    c->shm.shmaddr = c->img->data = shmat(c->shm.shmid, NULL, 0);
    c->shm.readOnly = False;
    if (!XShmAttach(dpy, &c->shm)) return -1;
    XSync(dpy, False);

    /* Marked for destruction now, so the segment goes away even if we crash. */
    shmctl(c->shm.shmid, IPC_RMID, NULL);

    c->prev = malloc(c->nbytes);
    return c->prev ? 0 : -1;
}

static void cap_snapshot(capturer_t *c) {
    XShmGetImage(c->dpy, c->root, c->img, c->x, c->y, AllPlanes);
    memcpy(c->prev, c->img->data, c->nbytes);
}

/* Capture again and report how many sampled bytes differ from the stored snapshot.
 *
 * Every 4th byte is examined -- one per pixel at 32bpp. A coarser stride was tried first
 * and it missed real events: clearing a dirty marker from a title bar changes only a
 * handful of pixels, and at a stride of 64 those fell between samples, so roughly half
 * the save timings were recorded as "nothing happened". A measurement that silently
 * ignores small repaints is worse than a slow one.
 *
 * The cost is a full pass over the captured bytes rather than a sixteenth of one, which
 * is still far below the capture itself; fnres reports the resulting cycle time. */
static unsigned long cap_diff(capturer_t *c) {
    XShmGetImage(c->dpy, c->root, c->img, c->x, c->y, AllPlanes);
    const unsigned char *cur = (const unsigned char *)c->img->data;
    unsigned long n = 0;
    for (size_t i = 0; i < c->nbytes; i += 4) {
        if (cur[i] != c->prev[i]) n++;
    }
    return n;
}

static void cap_free(capturer_t *c) {
    if (c->img) {
        XShmDetach(c->dpy, &c->shm);
        XDestroyImage(c->img);
        shmdt(c->shm.shmaddr);
    }
    free(c->prev);
}

static void usage(void) {
    fprintf(stderr,
        "usage: fnprobe --window <id> [--settle ms] [--timeout ms] <action>\n"
        "  actions: click <x> <y> | key <keysym> | type <text> | baseline\n");
}

int main(int argc, char **argv) {
    Window win = 0;
    int settle_ms = 400;
    int timeout_ms = 5000;
    int argi = 1;

    while (argi < argc && strncmp(argv[argi], "--", 2) == 0) {
        if (strcmp(argv[argi], "--window") == 0 && argi + 1 < argc) {
            win = (Window)strtoul(argv[++argi], NULL, 0);
        } else if (strcmp(argv[argi], "--settle") == 0 && argi + 1 < argc) {
            settle_ms = atoi(argv[++argi]);
        } else if (strcmp(argv[argi], "--timeout") == 0 && argi + 1 < argc) {
            timeout_ms = atoi(argv[++argi]);
        } else {
            usage();
            return 2;
        }
        argi++;
    }
    if (!win || argi >= argc) { usage(); return 2; }

    const char *action = argv[argi++];

    Display *dpy = XOpenDisplay(NULL);
    if (!dpy) { fprintf(stderr, "fnprobe: cannot open display\n"); return 2; }

    int event_base, error_base, major, minor;
    if (!XTestQueryExtension(dpy, &event_base, &error_base, &major, &minor)) {
        fprintf(stderr, "fnprobe: XTEST unavailable; cannot inject real input\n");
        return 2;
    }

    XWindowAttributes wa;
    if (!XGetWindowAttributes(dpy, win, &wa)) {
        fprintf(stderr, "fnprobe: no such window 0x%lx\n", win);
        return 2;
    }
    int w = wa.width, h = wa.height;

    /* Where the window sits on the root, so captures read the visible pixels. */
    int root_x, root_y; Window ignored;
    XTranslateCoordinates(dpy, win, wa.root, 0, 0, &root_x, &root_y, &ignored);

    if (!XShmQueryExtension(dpy)) {
        fprintf(stderr, "fnprobe: MIT-SHM unavailable; capture would be too slow to trust\n");
        return 2;
    }

    capturer_t cap;
    if (cap_init(&cap, dpy, wa.root, wa.visual, wa.depth, root_x, root_y, w, h) != 0) {
        fprintf(stderr, "fnprobe: cannot set up shared-memory capture\n");
        return 2;
    }

    /* Let any residual animation finish, so the change we time is the one we caused. */
    struct timespec settle = { settle_ms / 1000, (settle_ms % 1000) * 1000000L };
    nanosleep(&settle, NULL);

    cap_snapshot(&cap);

    if (strcmp(action, "baseline") == 0) {
        /* Measure the probe's own noise floor: no input, just two captures. A non-zero
         * result here means the window changes on its own (a cursor blink, say) and the
         * latency figures for it need treating with suspicion. */
        nanosleep(&settle, NULL);
        printf("baseline\t0.000\t%lu\n", cap_diff(&cap));
        cap_free(&cap);
        return 0;
    }

    /* Deliver the input, then start the clock. The ordering matters: XFlush is what hands
     * the event to the server, so the interval begins there and includes the server's own
     * dispatch, which the user also waits through. */
    double t0;
    if (strcmp(action, "click") == 0) {
        if (argi + 1 >= argc) { usage(); return 2; }
        int x = atoi(argv[argi]), y = atoi(argv[argi + 1]);
        /* Coordinates are window-relative; translate to root for XTEST. */
        int rx, ry; Window child;
        XTranslateCoordinates(dpy, win, wa.root, x, y, &rx, &ry, &child);

        XTestFakeMotionEvent(dpy, wa.screen ? XScreenNumberOfScreen(wa.screen) : 0, rx, ry, 0);
        XFlush(dpy);
        nanosleep(&(struct timespec){0, 30 * 1000000L}, NULL);

        t0 = now_ms();
        XTestFakeButtonEvent(dpy, 1, True, 0);
        XTestFakeButtonEvent(dpy, 1, False, 0);
        XFlush(dpy);
    } else if (strcmp(action, "key") == 0) {
        if (argi >= argc) { usage(); return 2; }

        /* Accept "ctrl+s" and "shift+Tab" as well as a bare keysym: an accelerator is
         * exactly the sort of thing worth timing, and the probe previously rejected the
         * only spelling anyone would reach for. */
        char spec[128];
        snprintf(spec, sizeof(spec), "%s", argv[argi]);

        KeyCode mods[4];
        int nmods = 0;
        char *plus;
        char *rest = spec;
        while ((plus = strchr(rest, '+')) != NULL && nmods < 4) {
            *plus = '\0';
            KeySym msym = NoSymbol;
            if (strcasecmp(rest, "ctrl") == 0 || strcasecmp(rest, "control") == 0) {
                msym = XK_Control_L;
            } else if (strcasecmp(rest, "shift") == 0) {
                msym = XK_Shift_L;
            } else if (strcasecmp(rest, "alt") == 0) {
                msym = XK_Alt_L;
            } else {
                msym = XStringToKeysym(rest);
            }
            if (msym == NoSymbol) {
                fprintf(stderr, "fnprobe: unknown modifier '%s'\n", rest);
                return 2;
            }
            mods[nmods++] = XKeysymToKeycode(dpy, msym);
            rest = plus + 1;
        }

        KeySym sym = XStringToKeysym(rest);
        if (sym == NoSymbol) {
            fprintf(stderr, "fnprobe: unknown keysym '%s'\n", rest);
            return 2;
        }
        KeyCode kc = XKeysymToKeycode(dpy, sym);

        t0 = now_ms();
        for (int m = 0; m < nmods; m++) XTestFakeKeyEvent(dpy, mods[m], True, 0);
        XTestFakeKeyEvent(dpy, kc, True, 0);
        XTestFakeKeyEvent(dpy, kc, False, 0);
        for (int m = nmods - 1; m >= 0; m--) XTestFakeKeyEvent(dpy, mods[m], False, 0);
        XFlush(dpy);
    } else if (strcmp(action, "type") == 0) {
        if (argi >= argc) { usage(); return 2; }
        const char *text = argv[argi];

        t0 = now_ms();
        for (const char *p = text; *p; p++) {
            char buf[2] = { *p, 0 };
            KeySym sym = XStringToKeysym(buf);
            if (*p == ' ') sym = XK_space;
            if (sym == NoSymbol) continue;
            KeyCode kc = XKeysymToKeycode(dpy, sym);
            if (!kc) continue;
            XTestFakeKeyEvent(dpy, kc, True, 0);
            XTestFakeKeyEvent(dpy, kc, False, 0);
        }
        XFlush(dpy);
    } else {
        usage();
        return 2;
    }

    /* Poll until the window differs from its pre-input state. */
    double deadline = t0 + timeout_ms;
    unsigned long changed = 0;
    double t_change = -1;

    while (now_ms() < deadline) {
        changed = cap_diff(&cap);
        if (changed > 0) { t_change = now_ms(); break; }
    }

    if (t_change < 0) {
        printf("%s\ttimeout\t0\n", action);
        return 3;
    }
    printf("%s\t%.3f\t%lu\n", action, t_change - t0, changed);

    cap_free(&cap);
    XCloseDisplay(dpy);
    return 0;
}
