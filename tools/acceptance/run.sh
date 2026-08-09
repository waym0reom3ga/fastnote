#!/usr/bin/env bash
#
# FastNote GUI Acceptance Harness — Category 7 (A1..A12)
#
# Runs identical assertions against every port's BUILT BINARY via the CLI control seam
# defined in FASTNOTE_SPECIFICATION.md section 5.
#
# This harness is deliberately external to every port. No port can influence its own
# verdict, and no port's own test suite is consulted. Library tests (Categories 1-6) are
# out of scope here: they were passing at 35/35 across the board while no port could open
# a file, which is the reason this harness exists.
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

MARKER="MARKER-A12-1f3d9c"
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

# assert_file_contains <test> <file> <needle> <description>
assert_file_contains() {
    local test="$1" file="$2" needle="$3" desc="$4"
    if [ ! -f "$file" ]; then bad "$test" "$desc: file not created: $file"; return 1; fi
    if [ ! -s "$file" ]; then bad "$test" "$desc: file is empty: $file"; return 1; fi
    if ! grep -qF -- "$needle" "$file"; then
        bad "$test" "$desc: '$needle' absent from $(basename "$file")"; return 1
    fi
    return 0
}

# ---------------------------------------------------------------- invocation

# fnrun <timeout-seconds> <args...>
#
# Every invocation is bounded and stripped of DISPLAY/WAYLAND_DISPLAY. The harness must
# never open a window: a port that blocks waiting for a display in headless mode is
# violating specification 5.3 and should fail rather than hang the suite.
fnrun() {
    local secs="$1"; shift
    env -u DISPLAY -u WAYLAND_DISPLAY timeout "$secs" "$@"
}

# ---------------------------------------------------------------- harness

run_port() {
    PORT="$1"
    local build_cmd="$2" bin_rel="$3" ui_globs="$4" click_cmd="${5:-}"
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

    # ---- CLI seam probe -------------------------------------------------------
    # A binary that accepts a nonsense flag and exits 0 has no argument parsing, so every
    # subsequent CLI assertion would pass vacuously. Detect that before trusting anything.
    # Observed in practice: a port printed "Unknown option --version" and exited 0, which
    # satisfied a naive "--version produced output" check.
    local seam=1
    if fnrun 15 "$BIN" --fnprobe-xyzzy-should-not-exist >/dev/null 2>&1; then
        seam=0
    fi

    # ---- A2 AcceptVersion -----------------------------------------------------
    local vout rc2
    vout="$(fnrun 15 "$BIN" --version 2>&1)"; rc2=$?
    if [ $seam -eq 0 ]; then
        bad "A2Version" "no CLI seam: binary ignores unknown flags and exits 0"
    elif [ $rc2 -ne 0 ]; then
        bad "A2Version" "--version exited $rc2"
    elif [ -z "$vout" ]; then
        bad "A2Version" "--version printed nothing"
    elif printf '%s' "$vout" | grep -qiE 'unknown|unrecognized|invalid option|usage:'; then
        bad "A2Version" "--version not supported: $(printf '%s' "$vout" | head -1)"
    else
        ok "A2Version" "$(printf '%s' "$vout" | head -1)"
    fi

    # ---- A3 AcceptSelfTest ----------------------------------------------------
    if [ $seam -eq 0 ]; then
        bad "A3SelfTest" "no CLI seam: --selftest cannot be distinguished from a no-op"
    elif fnrun 30 "$BIN" --notes-dir "$work/notes" --selftest >"$work/selftest.log" 2>&1; then
        ok "A3SelfTest"
    else
        bad "A3SelfTest" "$(tail -1 "$work/selftest.log")"
    fi

    # ---- A4 AcceptHeadlessNoDisplay -------------------------------------------
    # Must not require a display server, and must not hang waiting for one.
    if [ $seam -eq 0 ]; then
        bad "A4HeadlessNoDisplay" "no CLI seam: --headless is not honoured"
    elif fnrun 20 "$BIN" --headless --notes-dir "$work/notes" --version >/dev/null 2>&1; then
        ok "A4HeadlessNoDisplay"
    else
        local rc=$?
        if [ $rc -eq 124 ]; then bad "A4HeadlessNoDisplay" "timed out: blocked on a display"
        else bad "A4HeadlessNoDisplay" "exit $rc without DISPLAY"; fi
    fi

    # ---- A5 AcceptOpenArbitraryFile -------------------------------------------
    # The seeded file lives OUTSIDE the notes directory. A port that only scans its notes
    # directory -- which is every port at the time this harness was written -- fails here.
    local outside="$work/outside"; mkdir -p "$outside"
    local far="$outside/far_away_document.md"
    printf '# Far Away Document\n\nUNIQUE-OUTSIDE-CONTENT-8842\n' > "$far"

    if fnrun 30 "$BIN" --headless --notes-dir "$work/notes" \
            --open "$far" --export "$work/a5.html" >"$work/a5.log" 2>&1; then
        assert_file_contains A5OpenArbitraryFile "$work/a5.html" \
            "UNIQUE-OUTSIDE-CONTENT-8842" "opened file outside notes dir" \
            && ok "A5OpenArbitraryFile"
    else
        bad "A5OpenArbitraryFile" "$(tail -1 "$work/a5.log")"
    fi

    # ---- A6/A7/A11 static wiring checks ---------------------------------------
    static_checks "$dir" "$ui_globs"

    # ---- A13 AcceptUIClickTests -----------------------------------------------
    # The CLI seam proves the logic works. It cannot prove the BUTTONS work: a port could
    # satisfy every test above while its toolbar is inert. This was the original failure of
    # this project and it recurred once during the reference implementation's own
    # development -- the Open button rendered, the CLI passed, and clicking did nothing.
    #
    # Each port must therefore ship tests that inject real pointer events into its widget
    # tree and assert on the result. The command is declared per port in ports.conf.
    if [ -z "$click_cmd" ] || [ "$click_cmd" = "-" ]; then
        bad "A13UIClickTests" "port declares no UI click test command"
    elif ( cd "$dir" && eval "$click_cmd" ) >"$work/click.log" 2>&1; then
        local n
        n=$(grep -cE '^(--- )?(ok|PASS|test result: ok)' "$work/click.log" 2>/dev/null)
        ok "A13UIClickTests" "real pointer events injected"
    else
        bad "A13UIClickTests" "$(grep -m1 -E 'FAIL|panic|error' "$work/click.log" | head -c 120)"
    fi

    # ---- A8 AcceptEditSave ----------------------------------------------------
    local a8_ok=0
    local editdoc="$work/notes/edit_target.md"
    cp "$TEMPLATE" "$editdoc"
    local before_size; before_size=$(stat -c%s "$editdoc")

    if fnrun 30 "$BIN" --headless --notes-dir "$work/notes" \
            --open "$editdoc" --insert "$MARKER" --save >"$work/a8.log" 2>&1; then
        local after_size; after_size=$(stat -c%s "$editdoc")
        if ! grep -qF "$MARKER" "$editdoc"; then
            bad "A8EditSave" "marker not persisted to disk"
        elif [ "$after_size" -le "$before_size" ]; then
            bad "A8EditSave" "file did not grow ($before_size -> $after_size)"
        else
            a8_ok=1
            ok "A8EditSave" "${before_size}B -> ${after_size}B"
        fi
    else
        bad "A8EditSave" "$(tail -1 "$work/a8.log")"
    fi

    # ---- A9 AcceptDirtyState --------------------------------------------------
    # Editing without --save must leave the file untouched on disk.
    local dirtydoc="$work/notes/dirty_target.md"
    cp "$TEMPLATE" "$dirtydoc"
    local dirty_before; dirty_before=$(md5sum "$dirtydoc" | cut -d' ' -f1)
    fnrun 30 "$BIN" --headless --notes-dir "$work/notes" \
        --open "$dirtydoc" --insert "UNSAVED-EDIT" >"$work/a9.log" 2>&1
    local dirty_after; dirty_after=$(md5sum "$dirtydoc" | cut -d' ' -f1)
    # Guarded by the A8 result: "the file did not change" is only evidence of correct dirty
    # handling if the port is capable of writing the file at all. A port that does nothing
    # would otherwise pass this test for the wrong reason.
    if [ $seam -eq 0 ]; then
        bad "A9DirtyState" "no CLI seam: cannot distinguish restraint from inaction"
    elif [ "$a8_ok" -ne 1 ]; then
        bad "A9DirtyState" "inconclusive: A8 could not write the file in the first place"
    elif [ "$dirty_before" = "$dirty_after" ]; then
        ok "A9DirtyState" "unsaved edit not written"
    else
        bad "A9DirtyState" "edit reached disk without --save"
    fi

    # ---- A10 AcceptExportHTMLFile ---------------------------------------------
    local exdoc="$work/notes/export_target.md"
    cp "$TEMPLATE" "$exdoc"
    local exout="$work/a10.html"
    if fnrun 30 "$BIN" --headless --notes-dir "$work/notes" \
            --open "$exdoc" --export "$exout" >"$work/a10.log" 2>&1; then
        local missing=""
        for token in "DOCTYPE" "<html" "<style" "<title"; do
            grep -qiF -- "$token" "$exout" 2>/dev/null || missing="$missing $token"
        done
        if [ ! -s "$exout" ]; then
            bad "A10ExportHTMLFile" "no file written to $exout"
        elif [ -n "$missing" ]; then
            bad "A10ExportHTMLFile" "not a standalone document, missing:$missing"
        elif ! grep -qF "FastNote Acceptance Template" "$exout"; then
            bad "A10ExportHTMLFile" "document content absent from export"
        else
            ok "A10ExportHTMLFile" "$(stat -c%s "$exout")B"
        fi
    else
        bad "A10ExportHTMLFile" "$(tail -1 "$work/a10.log")"
    fi

    # ---- A12 AcceptE2EWorkflow -- the primary test ----------------------------
    # open template -> edit -> save -> export, all through the application.
    local e2e="$work/notes/e2e_document.md"
    cp "$TEMPLATE" "$e2e"
    local e2eout="$work/a12.html"
    if fnrun 60 "$BIN" --headless --notes-dir "$work/notes" \
            --open "$e2e" \
            --insert "

## Inserted By Acceptance

$MARKER
" \
            --save --export "$e2eout" >"$work/a12.log" 2>&1; then
        local e2e_ok=1
        grep -qF "$MARKER" "$e2e"      || { bad "A12E2EWorkflow" "marker missing from saved .md"; e2e_ok=0; }
        if [ $e2e_ok -eq 1 ]; then
            [ -s "$e2eout" ]                                    || { bad "A12E2EWorkflow" "export file missing/empty"; e2e_ok=0; }
        fi
        if [ $e2e_ok -eq 1 ]; then
            grep -qF "$MARKER" "$e2eout"                        || { bad "A12E2EWorkflow" "marker missing from export"; e2e_ok=0; }
        fi
        if [ $e2e_ok -eq 1 ]; then
            grep -qF "FastNote Acceptance Template" "$e2eout"   || { bad "A12E2EWorkflow" "original template heading lost"; e2e_ok=0; }
        fi
        [ $e2e_ok -eq 1 ] && ok "A12E2EWorkflow" "template -> edit -> save -> export"
    else
        bad "A12E2EWorkflow" "$(tail -1 "$work/a12.log")"
    fi
}

# static_checks performs A6, A7 and A11 by inspecting the port's GUI source.
#
# These exist because a CLI-driven test cannot distinguish "the button works" from "the CLI
# has a private copy of the logic". Three properties are checked in sequence, all of which
# have been observed missing in this project:
#   constructed -> placed in a container -> bound to a handler.
# Checking only the first two would have passed rust_gtk4, whose Export button is created,
# packed, and never connected to anything.
static_checks() {
    local dir="$1" globs="$2"
    local files=""
    for g in $globs; do
        for f in $dir/$g; do [ -f "$f" ] && files="$files $f"; done
    done

    if [ -z "$files" ]; then
        skip "A6OpenControlPresent"  "no UI sources matched"
        skip "A7FileBrowserExists"   "no UI sources matched"
        skip "A11ExportControlWired" "no UI sources matched"
        return
    fi

    # ---- A6: an Open control exists and is bound to something -----------------
    if grep -qiE '"Open"|Open File|on_open|openBtn|open_btn|OpenPath|open_clicked' $files; then
        # Retained-mode toolkits bind a handler by name; immediate-mode ones (egui,
        # nuklear, raygui) express the binding as `if button(...).clicked() { ... }`, which
        # the original pattern list could not see.
        if grep -qiE 'openBtn\.Clicked|open_btn|on_open|OpenPath|open_clicked|connect_clicked|button\("Open"\)\.clicked|request_open' $files; then
            ok "A6OpenControlPresent"
        else
            bad "A6OpenControlPresent" "Open control present but no handler binding found"
        fi
    else
        bad "A6OpenControlPresent" "no Open control in UI sources"
    fi

    # ---- A7: an in-app file browser, and no native dialog ---------------------
    local native
    native=$(grep -ilE 'GtkFileChooser|gtk_file_chooser|QFileDialog|rfd::|tinyfd_|add_file_dialog|FileChooserNative|gioui\.org/x/explorer' $files 2>/dev/null | head -1)
    if [ -n "$native" ]; then
        bad "A7FileBrowserExists" "native dialog used: $(basename "$native") (spec 3.1 prohibits this)"
    elif grep -qiE 'FileBrowser|file_browser|filebrowser|BrowserOpen' $files; then
        ok "A7FileBrowserExists" "in-app browser"
    else
        bad "A7FileBrowserExists" "no in-app file browser component found"
    fi

    # ---- A11: Export control exists, is bound, and reaches a write ------------
    if grep -qiE '"Export"|exportBtn|export_btn|ExportTo|on_export' $files; then
        if grep -qiE 'exportBtn\.Clicked|export_btn|on_export|ExportTo|export_clicked|button\("Export"\)\.clicked|Pending::Export|export_to' $files; then
            # Filesystem writes, across the languages in this comparison: Go's
            # os.WriteFile, C's fwrite/fopen, Python's open(...,'w'), and Rust's
            # fs::write / File::create. The Rust idioms were missing, so a correctly
            # wired Rust port was reported as reaching no write.
            if grep -qiE 'ExportTo|SaveToFile|save_to_file|WriteFile|fwrite|fopen|fs::write|File::create|export_to|open\(.*["'"'"']w' $files; then
                ok "A11ExportControlWired"
            else
                bad "A11ExportControlWired" "Export handler present but reaches no filesystem write"
            fi
        else
            bad "A11ExportControlWired" "Export control present but never bound to a handler"
        fi
    else
        bad "A11ExportControlWired" "no Export control in UI sources"
    fi
}

# ---------------------------------------------------------------- entry point

main() {
    local targets=()
    for arg in "$@"; do
        case "$arg" in
            --all)      targets=(ALL) ;;
            --no-build) DO_BUILD=0 ;;
            -h|--help)  sed -n '2,22p' "$0"; exit 0 ;;
            *)          targets+=("$arg") ;;
        esac
    done
    if [ ${#targets[@]} -eq 0 ]; then
        echo "usage: $0 <port-directory> | --all [--no-build]" >&2; exit 2
    fi

    [ -f "$TEMPLATE" ] || { echo "missing canonical template: $TEMPLATE" >&2; exit 2; }
    mkdir -p "$WORKROOT"

    printf "${BLD}FastNote GUI Acceptance — Category 7${RST}\n"
    printf "${DIM}Specification: FASTNOTE_SPECIFICATION.md | 13 tests per port${RST}\n"

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
