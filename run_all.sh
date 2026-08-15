#!/usr/bin/env bash
# FastNote — full build, test, and report pipeline.
#
# Usage:
#   ./run_all.sh                    # everything
#   ./run_all.sh --build-only       # build all editions, no tests
#   ./run_all.sh --test-only        # skip builds, run tests on existing binaries
#   ./run_all.sh --edition go_gio   # one edition only
#   ./run_all.sh --skip-build       # alias for --test-only
#   ./run_all.sh --no-display       # skip GUI tests (A03-A09, A13), run A02 + static only
#
# Outputs:
#   tools/tmp/qa/report.md          — markdown capability matrix + failures
#   tools/tmp/qa/report.json        — machine-readable results
#   tools/tmp/qa/binary_sizes.csv   — edition, path, bytes, human
#   docs/benchmark-report.html      — comparative tableau (if --measure)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$SCRIPT_DIR"
EDITIONS_DIR="$ROOT/editions"
QA="$ROOT/tools/qa/suite.py"
REPORT_PY="$ROOT/tools/measure/gen_report.py"
WORK="$ROOT/tools/tmp/qa"
SIZES_CSV="$WORK/binary_sizes.csv"
REPORT_MD="$WORK/report.md"
REPORT_JSON="$WORK/report.json"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

# ── arg parse ──────────────────────────────────────────────────────────
BUILD=true
TEST=true
MEASURE=false
EDITIONS=()
CASES=""
NO_DISPLAY=false
JUNIT=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --build-only)   TEST=false; shift ;;
        --test-only|--skip-build) BUILD=false; shift ;;
        --measure)      MEASURE=true; shift ;;
        --no-display)   NO_DISPLAY=true; shift ;;
        --edition)      EDITIONS+=("$2"); shift 2 ;;
        --case)         CASES="$2"; shift 2 ;;
        --junit)        JUNIT="$2"; shift 2 ;;
        -h|--help)
            sed -n '2,/^$/{ s/^# //; p }' "$0"
            exit 0
            ;;
        *) echo "unknown flag: $1" >&2; exit 2 ;;
    esac
done

mkdir -p "$WORK"

# ── edition list ───────────────────────────────────────────────────────
ALL_EDITIONS=(
    go_gio go_fyne go_gtk4 go_wails3
    c_gtk4 c_nuklear c_raygui
    rust_gtk4 rust_egui rust_slint
    python_gtk4 python_pyqt6 python_pyside6 python_dearpygui
)

if [[ ${#EDITIONS[@]} -gt 0 ]]; then
    TARGETS=("${EDITIONS[@]}")
else
    TARGETS=("${ALL_EDITIONS[@]}")
fi

# ── manifest lookup: edition → (dir, build_cmd, binary_path) ──────────
declare -A ED_DIR ED_BUILD ED_BIN
eval "$(python3 -c "
import sys; sys.path.insert(0, '$ROOT/tools/qa')
from fastnote_qa.manifest import EDITIONS
for name, (d, build, binary, title, event) in EDITIONS.items():
    print(f'ED_DIR[{name}]={d}')
    print(f'ED_BUILD[{name}]=\"{build}\"')
    print(f'ED_BIN[{name}]={binary}')
")"

# ── phase 1: build ─────────────────────────────────────────────────────
build_edition() {
    local name=$1
    local dir="$EDITIONS_DIR/${ED_DIR[$name]}"
    local cmd="${ED_BUILD[$name]}"
    local bin="$EDITIONS_DIR/${ED_DIR[$name]}/${ED_BIN[$name]}"

    if [[ "$cmd" == "true" ]]; then
        echo -e "  ${YELLOW}SKIP${NC}  $name (launcher, nothing to build)"
        return 0
    fi

    if [[ -f "$bin" ]] && [[ "${FORCE_BUILD:-}" != "1" ]]; then
        echo -e "  ${GREEN}OK${NC}    $name (already built)"
        return 0
    fi

    echo -ne "  BUILD $name ... "
    local log="$WORK/build_${name}.log"
    if timeout 600 bash -lc "$cmd" >"$log" 2>&1; then
        if [[ -f "$bin" ]]; then
            echo -e "${GREEN}OK${NC}"
            return 0
        else
            echo -e "${RED}FAIL${NC} (no artifact at $bin)"
            return 1
        fi
    else
        echo -e "${RED}FAIL${NC} (see $log)"
        return 1
    fi
}

if [[ "$BUILD" == "true" ]]; then
    echo -e "${BOLD}=== Phase 1: Build ===${NC}"
    BUILD_FAILS=0
    for ed in "${TARGETS[@]}"; do
        build_edition "$ed" || ((BUILD_FAILS++)) || true
    done
    echo ""
fi

# ── phase 2: collect binary sizes ──────────────────────────────────────
echo -e "${BOLD}=== Phase 2: Binary sizes ===${NC}"
echo "edition,path,bytes,human" > "$SIZES_CSV"
for ed in "${TARGETS[@]}"; do
    dir="$EDITIONS_DIR/${ED_DIR[$ed]}"
    binpath="$dir/${ED_BIN[$ed]}"
    if [[ -f "$binpath" ]]; then
        bytes=$(stat -c%s "$binpath")
        if (( bytes >= 1048576 )); then
            human="$(echo "scale=1; $bytes / 1048576" | bc) MB"
        else
            human="$(echo "scale=0; $bytes / 1024" | bc) KB"
        fi
        echo "$ed,${ED_BIN[$ed]},$bytes,$human" >> "$SIZES_CSV"
        printf "  %-18s %10s  %s\n" "$ed" "$human" "${ED_BIN[$ed]}"
    else
        echo "$ed,${ED_BIN[$ed]},0,MISSING" >> "$SIZES_CSV"
        echo -e "  ${RED}MISS${NC} $ed  ${ED_BIN[$ed]}"
    fi
done
echo ""

# ── phase 3: run QA suite ──────────────────────────────────────────────
if [[ "$TEST" == "true" ]]; then
    echo -e "${BOLD}=== Phase 3: QA tests ===${NC}"

    QA_ARGS=()
    if [[ ${#TARGETS[@]} -eq ${#ALL_EDITIONS[@]} ]]; then
        QA_ARGS+=(--all)
    else
        for ed in "${TARGETS[@]}"; do
            QA_ARGS+=(--edition "$ed")
        done
    fi
    if [[ -n "$CASES" ]]; then
        QA_ARGS+=(--case "$CASES")
    fi
    if [[ -n "$JUNIT" ]]; then
        QA_ARGS+=(--junit "$JUNIT")
    fi

    python3 "$QA" "${QA_ARGS[@]}" 2>&1
    QA_EXIT=$?
    echo ""
else
    QA_EXIT=0
fi

# ── phase 4: generate JSON report ──────────────────────────────────────
echo -e "${BOLD}=== Phase 4: Reports ===${NC}"

python3 -c "
import json, sys
sys.path.insert(0, '$ROOT/tools/qa')
from fastnote_qa.results import Store, report_markdown, report_json

store = Store('$WORK/results.db')
rows = store.latest_rows()
if rows:
    md = report_markdown(rows)
    with open('$REPORT_MD', 'w') as f:
        f.write(md)
    print(f'  Markdown: $REPORT_MD')

    # JSON with binary sizes merged
    sizes = {}
    try:
        with open('$SIZES_CSV') as f:
            for line in f.readlines()[1:]:
                parts = line.strip().split(',')
                if len(parts) >= 4 and parts[2] != '0':
                    sizes[parts[0]] = {'bytes': int(parts[2]), 'human': parts[3]}
    except: pass

    by_edition = {}
    for edition, case_id, status, detail, seconds in rows:
        by_edition.setdefault(edition, {})[case_id] = {
            'status': status, 'detail': detail, 'seconds': seconds}
    for ed in by_edition:
        by_edition[ed]['binary_size'] = sizes.get(ed, {})

    with open('$REPORT_JSON', 'w') as f:
        json.dump({'editions': by_edition, 'sizes': sizes}, f, indent=2)
    print(f'  JSON:     $REPORT_JSON')
else:
    print('  No QA results found in database')
" 2>&1

# ── phase 5: capability matrix summary ─────────────────────────────────
echo ""
echo -e "${BOLD}=== Capability Matrix ===${NC}"
python3 -c "
import sys
sys.path.insert(0, '$ROOT/tools/qa')
from fastnote_qa.results import Store

store = Store('$WORK/results.db')
matrix = store.per_edition_latest()
cases = ['a01','a02','a03','a04','a05','a06','a07','a08','a09','a10','a11','a12','a13','a14']

# header
print(f'  {\"edition\":<18}', end='')
for c in cases:
    print(f'{c.upper():>5}', end='')
print(f'  {\"pass\":>5}')
print('  ' + '─' * (18 + 5 * len(cases) + 6))

for ed in sorted(matrix):
    cs = matrix[ed]
    passed = sum(1 for c in cases if cs.get(c) == 'PASS')
    print(f'  {ed:<18}', end='')
    for c in cases:
        s = cs.get(c, '-')
        mark = {'PASS': '✓', 'FAIL': '✗', 'PARTIAL': '◐', 'SKIP': '○'}.get(s, '?')
        print(f'{mark:>5}', end='')
    print(f'  {passed:>4}/{len(cases)}')
" 2>&1

echo ""
echo -e "${BOLD}=== Done ===${NC}"
echo "  report.md:      $REPORT_MD"
echo "  report.json:    $REPORT_JSON"
echo "  binary_sizes:   $SIZES_CSV"

exit $QA_EXIT
