#!/usr/bin/env bash
#
# Can a user actually type into each edition?
#
# This is the question the acceptance suite cannot answer. A13 drives the action layer --
# fn_app_insert_text and friends -- so it passes whether or not a keystroke ever reaches
# the text widget. Two editions were found rendering correctly, accepting button clicks,
# and silently ignoring the keyboard, with a full green board.
#
# Here the binary is launched, a real click is put in the editor pane, real characters are
# typed through XTEST, and the file on disk is read back. Nothing else counts.
#
# Usage: tools/measure/typecheck.sh [edition ...]

set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK="$ROOT/tools/tmp/typecheck"

MARK="TYPEDBYHAND"

# name : directory : launch command : x,y to click inside the editor
#
# The click point is where that edition draws its editor at the size the window manager
# gives it. Where an edition publishes a control map the point is read from it instead.
EDITIONS="
go_gio:fastnote_go_gio_ed:./fastnote-gio
go_fyne:fastnote_go_fyne_ed:./fastnotes
c_gtk4:fastnote_c_gtk4_ed:./fastnote
c_nuklear:fastnote_c_nuklear_ed:./fastnote
c_raygui:fastnote_c_raygui_ed:./fastnote
rust_gtk4:fastnote_rust_gtk4_ed:./target/release/fastnote-gtk4
rust_egui:fastnote_rust_egui_ed:./target/release/fastnote-egui
rust_slint:fastnote_rust_slint_ed:./target/release/fastnote-slint
python_gtk4:fastnote_python_gtk4_ed:./run.sh
python_pyqt6:fastnote_python_pyqt6_ed:./run.sh
python_pyside6:fastnote_python_pyside6_ed:./run.sh
python_dearpygui:fastnote_python_dearpygui_ed:./run.sh
"

want="${*:-}"

# Shut an edition down and refuse to continue until its window is really gone. A leftover
# window silently receives the next edition's clicks and keystrokes.
stop_run() {
    local launcher="$1" pgid="$2" win="$3"
    [ -n "$pgid" ] && kill -TERM "-$pgid" 2>/dev/null
    kill "$launcher" 2>/dev/null
    wait "$launcher" 2>/dev/null

    for _ in $(seq 1 40); do
        [ -n "$win" ] && xdotool getwindowname "$win" >/dev/null 2>&1 || break
        sleep 0.1
    done
    [ -n "$pgid" ] && kill -KILL "-$pgid" 2>/dev/null
    sleep 0.3
}

# Nothing of ours may be running when the sweep starts, for the same reason.
if pgrep -f -- "--notes-dir" >/dev/null 2>&1; then
    echo "error: a FastNote process is already running; the results would be meaningless" >&2
    pgrep -af -- "--notes-dir" | head -5 >&2
    exit 2
fi

printf "%-17s %-9s %-9s %-9s %s\n" EDITION WINDOW CLICKED TYPED "RESULT"
printf -- "------------------------------------------------------------------\n"

for row in $EDITIONS; do
    name="${row%%:*}"; rest="${row#*:}"
    dir="${rest%%:*}"; cmd="${rest#*:}"
    [ -n "$want" ] && ! grep -qw "$name" <<<"$want" && continue

    work="$WORK/$name"
    rm -rf "$work"; mkdir -p "$work/notes"
    printf '# Doc\n\nORIGINAL\n' > "$work/notes/doc.md"

    before=$(xdotool search --name "FastNote" 2>/dev/null | tr '\n' ' ')

    # Launched with setsid so the whole thing sits in its own process group.
    #
    # A subshell was used here before, and killing it left the application running: four
    # orphaned windows accumulated, later editions typed into stale windows belonging to
    # earlier ones, and the run reported failures for editions that work. Killing the
    # group is the only way to be sure nothing survives.
    ( cd "$ROOT/editions/$dir" && \
      exec setsid env \
        FASTNOTE_CONFIG_DIR="$work/cfg" \
        FASTNOTE_CONTROL_MAP="$work/map.tsv" \
        FASTNOTE_READY_FILE="$work/ready" \
        $cmd --notes-dir "$work/notes" --open "$work/notes/doc.md" \
        >"$work/out.log" 2>&1 ) &
    launcher=$!
    sleep 0.3
    # The process group leader is the setsid child, not $launcher.
    pgid=$(ps -o pgid= -p "$launcher" 2>/dev/null | tr -d ' ')

    # Wait for a window that was not there before.
    # Pick the real document window.
    #
    # Matching any window whose name contains "FastNote" also matched the toolkit's own
    # hidden helper window, whose geometry is 1x1: the click point was computed from that
    # and landed nowhere, so a working editor was reported as ignoring the keyboard.
    # A window is only accepted if it is viewable and larger than a token size.
    win=""
    for _ in $(seq 1 150); do
        for w in $(xdotool search --name "FastNote" 2>/dev/null); do
            grep -q " $w " <<<" $before " && continue
            g=$(xdotool getwindowgeometry "$w" 2>/dev/null | grep -oE '[0-9]+x[0-9]+' | tail -1)
            [ -z "$g" ] && continue
            [ "${g%x*}" -lt 200 ] && continue
            [ "${g#*x}" -lt 200 ] && continue
            win="$w"; break
        done
        [ -n "$win" ] && break
        sleep 0.1
    done

    # Where an edition signals readiness, wait for it: the window is mapped before its
    # layout settles, and clicking during that gap lands on a control that has not
    # reached its final position yet.
    if [ -n "$win" ]; then
        for _ in $(seq 1 100); do
            [ -f "$work/ready" ] && break
            sleep 0.1
        done
    fi

    if [ -z "$win" ]; then
        printf "%-17s %-9s %-9s %-9s %s\n" "$name" "no" "-" "-" "no window appeared"
        stop_run "$launcher" "$pgid" ""
        continue
    fi
    sleep 1.5
    xdotool windowactivate --sync "$win" 2>/dev/null; sleep 0.4

    # Where to click: the edition's own control map if it publishes one, else the middle
    # of the window, which is inside the editor pane in every layout here.
    geom=$(xdotool getwindowgeometry "$win" | grep -oE '[0-9]+x[0-9]+' | tail -1)
    ww="${geom%x*}"; wh="${geom#*x}"
    # Where to click. An edition that publishes a control map is believed; the fallback
    # of "a third of the way across" is a guess that lands on the sidebar or the preview
    # depending on the layout, and produced false failures for editions whose editor is
    # simply somewhere else.
    #
    # The map may be written slightly after the window appears, so it is waited for.
    for _ in $(seq 1 60); do
        [ -s "$work/map.tsv" ] && grep -q '^editor' "$work/map.tsv" 2>/dev/null && break
        sleep 0.1
    done

    cx=$(( ww / 3 )); cy=$(( wh / 2 )); aim="guess"
    if grep -q '^editor' "$work/map.tsv" 2>/dev/null; then
        line=$(awk -F'\t' '$1=="editor"{print $2+$4/2"\t"$3+$5/2}' "$work/map.tsv" | head -1)
        if [ -n "$line" ]; then
            cx=$(cut -f1 <<<"$line"); cy=$(cut -f2 <<<"$line"); aim="map"
        fi
    fi

    # Everything goes to the focused window rather than being posted to a window id.
    # `xdotool key --window` sends a synthetic event that many toolkits deliberately
    # ignore, so a working editor looked broken: by hand, with the window activated
    # first, the same edition typed and saved correctly.
    xdotool mousemove --window "$win" "${cx%.*}" "${cy%.*}" click 1 2>/dev/null
    sleep 0.6
    # If the click did not leave this window focused, the keystrokes below would go
    # somewhere else entirely and the verdict would be meaningless.
    if [ "$(xdotool getwindowfocus 2>/dev/null)" != "$win" ]; then
        xdotool windowactivate --sync "$win" 2>/dev/null
        sleep 0.4
    fi
    xdotool type --delay 60 "$MARK" 2>/dev/null
    sleep 1.0

    dirty_title=$(xdotool getwindowname "$win" 2>/dev/null)
    if [ -n "${TYPECHECK_DEBUG:-}" ]; then
        echo "   [dbg] win=$win click=(${cx%.*},${cy%.*}) via=$aim geom=$geom" >&2
        echo "   [dbg] focused=$(xdotool getwindowfocus 2>/dev/null) title=[$dirty_title]" >&2
    fi

    # Save, then read the disk. The file is the only witness a repaint cannot fake.
    xdotool key ctrl+s 2>/dev/null
    sleep 1.5

    # Two independent witnesses: the dirty marker appearing in the title proves the
    # keystrokes reached the document, and the file proves the save wrote them out. An
    # edition can pass the first and fail the second, and the two failures are different
    # bugs, so they are reported separately.
    typed="no"; result="keystrokes never reached the document"
    if grep -q "$MARK" "$work/notes/doc.md" 2>/dev/null; then
        typed="yes"; result="ok"
    elif [[ "$dirty_title" == \** ]]; then
        typed="yes"; result="typed, but Ctrl+S did not save"
    fi

    [ "$aim" = "guess" ] && result="$result (aim guessed: no control map)"
    printf "%-17s %-9s %-9s %-9s %s\n" "$name" "yes" "yes" "$typed" "$result"

    stop_run "$launcher" "$pgid" "$win"
done
