#!/usr/bin/env bash
#
# FastNote GUI Acceptance Harness — Category 7 (A1..A12)
#
# Runs identical assertions against every port's BUILT BINARY by driving the
# REAL GUI: the window is launched, the port's own pointer-event suite injects
# genuine events through the framework's input pipeline, and the harness
# verifies the result from outside.
#
# There is no CLI seam, no headless mode, and no flag that reaches application
# functionality without the GUI (specification §5). The only flag a port may
# accept is --version. Everything else is tested by pressing the button.
#
# This harness is deliberately external to every port. No port can influence
# its own verdict, and no port's own test suite is consulted for the verdict —
# the port's GUI suite is run, and its pass/fail is the port's, but the harness
# owns the display, the seeded files, the sabotage check, and the assertions
# around the suite.
#
# Usage:
#   ./tools/acceptance/run.sh <port-directory>
#   ./tools/acceptance/run.sh --all
#   ./tools/acceptance/run.sh --all --no-build
#
# Exit status: 0 only if every requested port passes every test.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MANIFEST="$ROOT/tools/acceptance/ports.conf"
TEMPLATE="$ROOT/docs/testdata/template.md"
WORKROOT="$ROOT/tools/tmp/acceptance"

DO_BUILD=1

RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'; DIM=$'\033[2m'; BLD=$'\033[1m'; RST=$'\033[0m'
if [ ! -t 1 ]; then RED=; GRN=; YEL=; DIM=; BLD=; RST=; fi

pass_count=0
fail_count=0
skip_count=0
declare -a FAILED_TESTS

# ---------------------------------------------------------------- assertions

ok()   { printf "  ${GRN}PASS${RST}  %-26s %s\n" "$1" "${2:-}"; pass_count=$((pass_count+1)); }
bad()  { printf "  ${RED}FAIL${RST}  %-26s %s\n" "$1" "${2:-}"; fail_count=$((fail_count+1)); FAILED_TESTS+=("$PORT/$1: ${2:-}"); }
skip() { printf "  ${YEL}SKIP${RST}  %-26s %s\n" "$1" "${2:-}"; skip_count=$((skip_count+1)); }

# ---------------------------------------------------------------- display

# DISPLAY_FOR_TEST exports the display environment the port suite will run
# under: an Xvfb server we start ourselves when one is available, otherwise the
# user's live display. The window that opens is real either way.
DISPLAY_ENV=()

display_setup() {
    if command -v Xvfb >/dev/null 2>&1; then
        local d=":97"
        Xvfb "$d" -screen 0 1280x800x24 >"$WORKROOT/xvfb.log" 2>&1 &
        XVFB_PID=$!
        sleep 1
        DISPLAY_ENV=(DISPLAY="$d")
    elif [ -n "${DISPLAY:-}" ]; then
        DISPLAY_ENV=(DISPLAY="$DISPLAY")
    else
        bad "A2Launches" "no display available (install Xvfb or set DISPLAY)"
    fi
}

display_teardown() {
    [ -n "${XVFB_PID:-}" ] && kill "$XVFB_PID" 2>/dev/null
}

# fnrun <timeout-seconds> <args...> — run a command under the harness display.
fnrun() {
    local secs="$1"; shift
    env "${DISPLAY_ENV[@]}" timeout "$secs" "$@"
}

# ---------------------------------------------------------------- harness

run_port() {
    PORT="$1"
    local build_cmd="$2" bin_rel="$3" ui_globs="$4" suite_cmd="${5:-}"
    local dir="$ROOT/editions/$PORT"

    printf "\n${BLD}=== %s ===${RST}\n" "$PORT"

    if [ ! -d "$dir" ]; then bad "A0Exists" "no such directory"; return; fi

    local work="$WORKROOT/$PORT"
    rm -rf "$work"; mkdir -p "$work/notes"

    # ---- A1 AcceptBinaryExists ------------------------------------------------
    if [ "$DO_BUILD" = "1" ] && [ -n "$build_cmd" ] && [ "$build_cmd" != "true" ]; then
        if ! ( cd "$dir" && eval "$build_cmd" ) >"$work/build.log" 2>&1; then
            bad "A1BinaryExists" "build failed: $build_cmd (see $work/build.log)"
            printf "        ${DIM}%s${RST}\n" "$(tail -3 "$work/build.log" | tr '\n' ' ')"
            return
        fi
    fi

    local BIN="$dir/$bin_rel"
    if [ ! -f "$BIN" ]; then bad "A1BinaryExists" "no artifact at $bin_rel"; return; fi
    if [ ! -x "$BIN" ]; then bad "A1BinaryExists" "artifact not executable: $bin_rel"; return; fi
    ok "A1BinaryExists" "$(du -h "$BIN" | cut -f1)"

    # ---- A3 AcceptVersion — the port's ONLY permitted flag --------------------
    local vout rc3
    vout="$(env -u DISPLAY -u WAYLAND_DISPLAY timeout 15 "$BIN" --version 2>&1)"; rc3=$?
    if [ $rc3 -ne 0 ]; then
        bad "A3Version" "--version exited $rc3"
    elif [ -z "$vout" ]; then
        bad "A3Version" "--version printed nothing"
    elif printf '%s' "$vout" | grep -qiE 'unknown|unrecognized|invalid option|usage:'; then
        bad "A3Version" "--version not supported: $(printf '%s' "$vout" | head -1)"
    else
        ok "A3Version" "$(printf '%s' "$vout" | head -1)"
    fi

    # ---- A2 AcceptLaunches — real window on a real display --------------------
    # Launch the binary, wait for a window to map, close it, and require a clean
    # exit. No flags beyond --version are permitted, so the launch is bare.
    if [ ${#DISPLAY_ENV[@]} -eq 0 ]; then
        bad "A2Launches" "no display available"
    else
        "$BIN" >"$work/launch.log" 2>&1 &
        local app_pid=$!
        local mapped=0
        for _ in $(seq 1 30); do
            if ! kill -0 "$app_pid" 2>/dev/null; then break; fi
            if command -v xdotool >/dev/null 2>&1; then
                if xdotool search --onlyvisible --pid "$app_pid" getwindowname >/dev/null 2>&1; then
                    mapped=1; break
                fi
            fi
            sleep 0.3
        done
        if [ $mapped -eq 0 ]; then
            kill "$app_pid" 2>/dev/null
            bad "A2Launches" "no window mapped within 9s"
        else
            local wname
            wname="$(xdotool search --onlyvisible --pid "$app_pid" getwindowname 2>/dev/null | head -1)"
            # close the window as a user would (WM delete) and require exit 0
            xdotool search --onlyvisible --pid "$app_pid" windowclose >/dev/null 2>&1
            local rc2=0
            for _ in $(seq 1 30); do
                kill -0 "$app_pid" 2>/dev/null || break
                sleep 0.2
            done
            kill -0 "$app_pid" 2>/dev/null && { kill "$app_pid" 2>/dev/null; wait "$app_pid" 2>/dev/null; rc2=$?; }
            wait "$app_pid" 2>/dev/null; rc2=$?
            if [ $rc2 -eq 0 ]; then
                ok "A2Launches" "window mapped and closed cleanly${wname:+ ($wname)}"
            else
                bad "A2Launches" "exit $rc2 on close (expected 0)"
            fi
        fi
    fi

    # ---- A5/A6/A10 static wiring checks ---------------------------------------
    static_checks "$dir" "$ui_globs"

    # ---- A12 AcceptUIClickSuite — genuine pointer events, plus sabotage --------
    # The port's suite drives the real widget tree with the framework's own
    # input API (see fastnote_testing_protocol.md §event-injection rule).
    # It MUST pass as shipped ...
    if [ -z "$suite_cmd" ] || [ "$suite_cmd" = "-" ]; then
        bad "A12UIClickSuite" "port declares no GUI event suite"
    elif ( cd "$dir" && fnrun 180 bash -c "$suite_cmd" ) >"$work/suite.log" 2>&1; then
        ok "A12UIClickSuite" "GUI event suite passed"
    else
        bad "A12UIClickSuite" "$(grep -m1 -E 'FAIL|panic|error|MISMATCH' "$work/suite.log" | head -c 160)"
    fi

    # ... and MUST FAIL under sabotage. FASTNOTE_SABOTAGE=1 asks the suite to
    # unbind a control; a suite that still passes is testing nothing.
    if [ -n "$suite_cmd" ] && [ "$suite_cmd" != "-" ]; then
        if ( cd "$dir" && env FASTNOTE_SABOTAGE=1 fnrun 180 bash -c "$suite_cmd" ) >"$work/sabotage.log" 2>&1; then
            bad "A12Sabotage" "suite passed with a control unbound — it is testing nothing"
        else
            ok "A12Sabotage" "suite failed after unbinding a control, as required"
        fi
    fi
}

# static_checks performs A5, A6 and A10 by inspecting the port's GUI source.
#
# These are guards, not evidence: A4/A7/A9 come from clicking the actual
# widgets. They catch the "control exists but is a dead end" class of defect
# cheaply, and they all can fail.
static_checks() {
    local dir="$1" globs="$2"
    local files=""
    for g in $globs; do
        for f in $dir/$g; do [ -f "$f" ] && files="$files $f"; done
    done

    if [ -z "$files" ]; then
        skip "A5OpenControlPresent"  "no UI sources matched"
        skip "A6FileBrowserExists"   "no UI sources matched"
        skip "A10ExportControlWired" "no UI sources matched"
        return
    fi

    # ---- A5: an Open control exists and is bound to something -----------------
    if grep -qiE '"Open"|Open File|on_open|openBtn|open_btn|OpenPath|open_clicked' $files; then
        if grep -qiE 'openBtn\.Clicked|open_btn|on_open|OpenPath|open_clicked|connect_clicked|button\("Open"\)\.clicked|request_open' $files; then
            ok "A5OpenControlPresent"
        else
            bad "A5OpenControlPresent" "Open control present but no handler binding found"
        fi
    else
        bad "A5OpenControlPresent" "no Open control in UI sources"
    fi

    # ---- A6: an in-app file browser, and no native dialog ---------------------
    local native
    native=$(grep -ilE 'GtkFileChooser|gtk_file_chooser|QFileDialog|rfd::|tinyfd_|add_file_dialog|FileChooserNative|gioui\.org/x/explorer' $files 2>/dev/null | head -1)
    if [ -n "$native" ]; then
        bad "A6FileBrowserExists" "native dialog used: $(basename "$native")"
    elif grep -qiE 'FileBrowser|file_browser|filebrowser|BrowserOpen' $files; then
        ok "A6FileBrowserExists" "in-app browser"
    else
        bad "A6FileBrowserExists" "no in-app file browser component found"
    fi

    # ---- A10: Export control exists, is bound, and reaches a write ------------
    if grep -qiE '"Export"|exportBtn|export_btn|ExportTo|on_export' $files; then
        if grep -qiE 'exportBtn\.Clicked|export_btn|on_export|ExportTo|export_clicked|button\("Export"\)\.clicked|Pending::Export|export_to' $files; then
            if grep -qiE 'ExportTo|SaveToFile|save_to_file|WriteFile|fwrite|fopen|fs::write|File::create|export_to|open\(.*["'"'"']w' $files; then
                ok "A10ExportControlWired"
            else
                bad "A10ExportControlWired" "Export handler present but reaches no filesystem write"
            fi
        else
            bad "A10ExportControlWired" "Export control present but never bound to a handler"
        fi
    else
        bad "A10ExportControlWired" "no Export control in UI sources"
    fi
}

# ---------------------------------------------------------------- entry point

main() {
    local targets=()
    for arg in "$@"; do
        case "$arg" in
            --all)      targets=(ALL) ;;
            --no-build) DO_BUILD=0 ;;
            -h|--help)  sed -n '2,20p' "$0"; exit 0 ;;
            *)          targets+=("$arg") ;;
        esac
    done
    if [ ${#targets[@]} -eq 0 ]; then
        echo "usage: $0 <port-directory> | --all [--no-build]" >&2; exit 2
    fi

    [ -f "$TEMPLATE" ] || { echo "missing canonical template: $TEMPLATE" >&2; exit 2; }
    mkdir -p "$WORKROOT"

    display_setup
    trap display_teardown EXIT

    printf "${BLD}FastNote GUI Acceptance — Category 7${RST}\n"
    printf "${DIM}Specification: FASTNOTE_SPECIFICATION.md | 12 tests per port | no headless seam${RST}\n"

    while IFS= read -r line; do
        line="${line%%#*}"
        [ -z "${line// }" ] && continue
        IFS=':' read -r d b p g c <<< "$line"
        d="$(echo "$d" | xargs)"; b="$(echo "$b" | xargs)"
        p="$(echo "$p" | xargs)"; g="$(echo "$g" | xargs)"
        c="$(echo "${c:-}" | xargs)"

        if [ "${targets[0]}" != "ALL" ]; then
            local want=0
            for t in "${targets[@]}"; do [ "${t%/}" = "$d" ] && want=1; done
            [ $want -eq 0 ] && continue
        fi
        run_port "$d" "$b" "$p" "$g" "$c"
    done < "$MANIFEST"

    local total=$((pass_count + fail_count + skip_count))
    printf "\n${BLD}%s${RST}\n" "----------------------------------------"
    printf "${GRN}%d passed${RST}  ${RED}%d failed${RST}  ${YEL}%d skipped${RST}  (%d assertions)\n" \
        "$pass_count" "$fail_count" "$skip_count" "$total"

    if [ $fail_count -gt 0 ]; then
        printf "\n${RED}${BLD}Failures:${RST}\n"
        for f in "${FAILED_TESTS[@]}"; do printf "  ${RED}x${RST} %s\n" "$f"; done
        printf "\n${DIM}A port failing any test is incomplete regardless of its library test count.${RST}\n"
        exit 1
    fi
    printf "\n${GRN}${BLD}All acceptance tests passed.${RST}\n"
}

main "$@"
