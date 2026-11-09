#!/usr/bin/env bash
# Local smoke test for page-change-monitor (no GitHub runner needed).
# Hits the live Oracle free tier: 3 checks total.
set -uo pipefail
cd "$(dirname "$0")/.."

fail=0

# 1. baseline + unchanged
INPUT_URLS="https://example.com/" python3 monitor.py > /tmp/pcm1.txt || fail=1
grep -q "example.com" /tmp/pcm1.txt && echo "PASS baseline recorded" || { echo "FAIL baseline"; fail=1; }

INPUT_URLS="https://example.com/" python3 monitor.py > /tmp/pcm2.txt || fail=1
grep -q "unchanged" /tmp/pcm2.txt && echo "PASS second pass unchanged" || { echo "FAIL unchanged"; fail=1; }

# 2. change detection + fail-on-change gate (httpbin returns a new uuid per request)
INPUT_URLS="https://httpbin.org/uuid" python3 monitor.py > /dev/null 2>&1
INPUT_URLS="https://httpbin.org/uuid" INPUT_FAIL_ON_CHANGE=true python3 monitor.py > /tmp/pcm3.txt
rc=$?
[ "$rc" = "1" ] && echo "PASS fail-on-change exits 1" || { echo "FAIL fail-on-change rc=$rc"; fail=1; }
grep -q "changed" /tmp/pcm3.txt && echo "PASS change reported" || { echo "FAIL change report"; fail=1; }

# 3. url-file parsing (no network: empty file must error out cleanly)
: > /tmp/empty.txt
INPUT_URLS_FILE=/tmp/empty.txt python3 monitor.py > /dev/null 2>&1
[ "$?" = "2" ] && echo "PASS empty input exits 2" || { echo "FAIL empty input"; fail=1; }

echo "---"
[ "$fail" = "0" ] && echo "ALL PASS" || echo "FAILURES"
exit $fail
