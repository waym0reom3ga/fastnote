/* fnsynth -- a target with a known, deliberate response delay.
 *
 * Calibrates fnprobe. A latency tool that has never been pointed at a known quantity is
 * just a number generator: this program repaints its window exactly N milliseconds after a
 * click, so the probe's reading can be compared against the truth. What fnprobe reports
 * minus N is the instrument's overhead, and it should be small and stable.
 *
 * usage: fnsynth <delay-ms>
 */

#define _POSIX_C_SOURCE 200809L
#include <X11/Xlib.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

int main(int argc, char **argv) {
    int delay_ms = argc > 1 ? atoi(argv[1]) : 50;

    Display *dpy = XOpenDisplay(NULL);
    if (!dpy) { fprintf(stderr, "fnsynth: no display\n"); return 2; }

    int screen = DefaultScreen(dpy);
    Window win = XCreateSimpleWindow(dpy, RootWindow(dpy, screen), 0, 0, 400, 300, 0,
                                     BlackPixel(dpy, screen), WhitePixel(dpy, screen));
    XStoreName(dpy, win, "fnsynth");
    XSelectInput(dpy, win, ExposureMask | ButtonPressMask);
    XMapWindow(dpy, win);

    GC gc = XCreateGC(dpy, win, 0, NULL);
    unsigned long colors[2] = { WhitePixel(dpy, screen), BlackPixel(dpy, screen) };
    int state = 0;

    fprintf(stderr, "fnsynth: window 0x%lx, responding after %d ms\n", win, delay_ms);
    fflush(stderr);

    for (;;) {
        XEvent ev;
        XNextEvent(dpy, &ev);
        if (ev.type == Expose) {
            XSetForeground(dpy, gc, colors[state]);
            XFillRectangle(dpy, win, gc, 0, 0, 400, 300);
            XFlush(dpy);
        } else if (ev.type == ButtonPress) {
            /* The whole point: a precisely known interval before anything changes. */
            struct timespec ts = { delay_ms / 1000, (delay_ms % 1000) * 1000000L };
            nanosleep(&ts, NULL);
            state ^= 1;
            XSetForeground(dpy, gc, colors[state]);
            XFillRectangle(dpy, win, gc, 0, 0, 400, 300);
            XFlush(dpy);
            XSync(dpy, False);
        }
    }
    return 0;
}
