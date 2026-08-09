/* fnres -- report the probe's own sampling resolution.
 *
 * Every latency figure fnprobe produces is quantised by how long one capture-and-compare
 * cycle takes: a change can only be noticed at the next sample. Publishing latencies
 * without publishing this number would be presenting a measurement without its error bar.
 */

#define _POSIX_C_SOURCE 200809L
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <X11/extensions/XShm.h>
#include <sys/ipc.h>
#include <sys/shm.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static double now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}

int main(int argc, char **argv) {
    if (argc < 2) { fprintf(stderr, "usage: fnres <window-id> [iterations]\n"); return 2; }
    Window win = (Window)strtoul(argv[1], NULL, 0);
    int iters = argc > 2 ? atoi(argv[2]) : 200;

    Display *dpy = XOpenDisplay(NULL);
    if (!dpy) { fprintf(stderr, "fnres: cannot open display\n"); return 2; }

    XWindowAttributes wa;
    if (!XGetWindowAttributes(dpy, win, &wa)) { fprintf(stderr, "fnres: bad window\n"); return 2; }
    int rx, ry; Window ignored;
    XTranslateCoordinates(dpy, win, wa.root, 0, 0, &rx, &ry, &ignored);

    /* Shared-memory capture: the server writes pixels straight into our segment instead of
     * marshalling them through the socket. */
    XShmSegmentInfo shm;
    XImage *img = XShmCreateImage(dpy, wa.visual, (unsigned)wa.depth, ZPixmap, NULL, &shm,
                                  (unsigned)wa.width, (unsigned)wa.height);
    if (!img) { fprintf(stderr, "fnres: XShmCreateImage failed\n"); return 2; }
    shm.shmid = shmget(IPC_PRIVATE, (size_t)img->bytes_per_line * (size_t)img->height, IPC_CREAT | 0600);
    shm.shmaddr = img->data = shmat(shm.shmid, NULL, 0);
    shm.readOnly = False;
    XShmAttach(dpy, &shm);
    XSync(dpy, False);

    size_t nbytes = 0;
    unsigned char *prev = NULL;
    double *samples = calloc((size_t)iters, sizeof(double));

    for (int i = 0; i < iters; i++) {
        double t0 = now_ms();
        XShmGetImage(dpy, wa.root, img, rx, ry, AllPlanes);
        size_t need = (size_t)img->bytes_per_line * (size_t)img->height;
        if (nbytes < need) { prev = realloc(prev, need); nbytes = need; }
        unsigned long diff = 0;
        for (size_t b = 0; b < need; b += 64) if (prev[b] != (unsigned char)img->data[b]) diff++;
        memcpy(prev, img->data, need);
        (void)diff;
        samples[i] = now_ms() - t0;
    }

    /* Discard the first sample: it includes the first allocation. */
    int n = iters - 1;
    double *s = samples + 1;
    for (int i = 0; i < n; i++)
        for (int j = i + 1; j < n; j++)
            if (s[j] < s[i]) { double t = s[i]; s[i] = s[j]; s[j] = t; }

    printf("window\t%dx%d\n", wa.width, wa.height);
    printf("samples\t%d\n", n);
    printf("min_ms\t%.4f\n", s[0]);
    printf("median_ms\t%.4f\n", s[n / 2]);
    printf("p95_ms\t%.4f\n", s[(int)(n * 0.95)]);
    printf("max_ms\t%.4f\n", s[n - 1]);
    return 0;
}
