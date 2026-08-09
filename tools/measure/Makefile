CFLAGS = -O2 -Wall -Wextra -std=c99
LIBS_PROBE = $(shell pkg-config --libs x11 xext xtst)
LIBS_X11   = $(shell pkg-config --libs x11 xext)

all: fnprobe fnres fnsynth

fnprobe: fnprobe.c
	$(CC) $(CFLAGS) -o $@ $< $(LIBS_PROBE)

fnres: fnres.c
	$(CC) $(CFLAGS) -o $@ $< $(LIBS_X11)

fnsynth: fnsynth.c
	$(CC) $(CFLAGS) -o $@ $< $(shell pkg-config --libs x11)

clean:
	rm -f fnprobe fnres fnsynth
