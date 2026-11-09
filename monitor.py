#!/usr/bin/env python3
"""page-change-monitor: detect web page changes in CI.

State lives on the SaltCrate Oracle server (keyed by URL), so nothing is
committed to your repository, no cache is needed, and two workflows watching
the same URL share state.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

FREE_HEADER = {"X-Oracle-Free": "1"}


def env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def parse_urls() -> list[str]:
    raw = env("INPUT_URLS")
    if not raw:
        path = env("INPUT_URLS_FILE")
        if path:
            with open(path, encoding="utf-8") as fh:
                raw = "\n".join(
                    line.split("#", 1)[0] for line in fh.read().splitlines()
                )
    out, seen = [], set()
    for chunk in raw.replace(",", "\n").splitlines():
        url = chunk.strip()
        if not url or url in seen:
            continue
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        seen.add(url)
        out.append(url)
    return out


def post_json(url: str, path: str, body: dict, headers: dict, timeout: int) -> tuple[int, Any]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url.rstrip("/") + path, data=data, method="POST",
        headers={"Content-Type": "application/json", **headers},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            return exc.code, json.loads(raw or "{}")
        except json.JSONDecodeError:
            return exc.code, {"raw": raw[:400]}
    except Exception as exc:  # noqa: BLE001 - network failures are per-URL, not fatal
        return 0, {"error": f"{type(exc).__name__}: {exc}"}


def github_issue(repo: str, token: str, title: str, body: str) -> str:
    api = f"https://api.github.com/repos/{repo}/issues"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    # Reuse an existing open issue with the same title instead of spamming new ones.
    search = urllib.request.Request(
        api + "?state=open&per_page=50", headers=headers, method="GET"
    )
    try:
        with urllib.request.urlopen(search, timeout=30) as resp:
            for issue in json.loads(resp.read().decode()):
                if issue.get("title") == title and "pull_request" not in issue:
                    return f"issue #{issue['number']} updated"
    except Exception:  # noqa: BLE001 - fall through to creation
        pass
    payload = json.dumps({"title": title, "body": body}).encode()
    req = urllib.request.Request(api, data=payload, method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return f"issue #{json.loads(resp.read().decode())['number']} created"


def set_output(name: str, value: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"{name}<<EOF\n{value}\nEOF\n")


def main() -> int:
    urls = parse_urls()
    if not urls:
        print("::error::no URLs given (set `urls:` or `urls-file:`)")
        return 2

    base = env("INPUT_ORACLE_URL", "https://oracle.saltcrate.com")
    key = env("INPUT_ORACLE_KEY")
    timeout = int(env("INPUT_TIMEOUT", "30") or 30)
    changes_only = env("INPUT_REPORT_CHANGES_ONLY").lower() == "true"
    fail_on_change = env("INPUT_FAIL_ON_CHANGE").lower() == "true"

    headers = dict(FREE_HEADER)
    if key:
        headers.pop("X-Oracle-Free", None)
        headers["Authorization"] = f"Bearer {key}"

    changed: list[str] = []
    failed: list[str] = []
    rows: list[tuple[str, str, str]] = []  # url, status, detail

    for url in urls:
        code, out = post_json(base, "/check_change", {"url": url}, headers, timeout)
        if code == 402:
            detail = out.get("detail") or out.get("error") or "free tier exhausted"
            failed.append(url)
            rows.append((url, "paywall", str(detail)[:160]))
            continue
        if code >= 300 or code == 0:
            failed.append(url)
            rows.append((url, "error", json.dumps(out)[:160]))
            continue
        status = str(out.get("status", "unknown"))
        if status == "changed":
            changed.append(url)
            detail = f"{out.get('chars', '?')} chars, {out.get('delta_chars', '?')} delta"
        elif status == "new":
            detail = f"baseline recorded ({out.get('chars', '?')} chars)"
        elif status == "error":
            failed.append(url)
            status, detail = "error", str(out.get("error"))[:160]
        else:
            detail = f"unchanged ({out.get('chars', '?')} chars)"
        rows.append((url, status, detail))

    # ---- step summary -------------------------------------------------------
    lines = ["", "## Page change monitor", "",
             f"Checked **{len(urls)}** · changed **{len(changed)}** · failed **{len(failed)}**", "",
             "| Page | Status | Detail |", "|---|---|---|"]
    for url, status, detail in rows:
        icon = {"changed": "🔴", "new": "🆕", "unchanged": "✅", "error": "⚠️", "paywall": "💳"}.get(status, "•")
        lines.append(f"| {url} | {icon} {status} | {detail} |")
    summary = "\n".join(lines)
    print(summary)
    sp = os.environ.get("GITHUB_STEP_SUMMARY")
    if sp:
        with open(sp, "a", encoding="utf-8") as fh:
            fh.write(summary + "\n")

    set_output("changed", "\n".join(changed))
    set_output("changed_count", str(len(changed)))
    set_output("checked_count", str(len(urls)))
    set_output("failed", "\n".join(failed))

    for url in changed:
        print(f"::warning title=Page changed::{url}")

    # ---- optional issue ----------------------------------------------------
    if changed and env("INPUT_CREATE_ISSUE").lower() == "true":
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        token = os.environ.get("GITHUB_TOKEN", "")
        if repo and token:
            title = f"[page-change-monitor] {len(changed)} page(s) changed"
            body = "Detected by `page-change-monitor` (SaltCrate Oracle).\n\n" + "\n".join(
                f"- [ ] {u}" for u in changed
            ) + f"\n\nRun: {os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{repo}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
            try:
                print(github_issue(repo, token, title, body))
            except Exception as exc:  # noqa: BLE001
                print(f"::warning::could not open issue: {exc}")

    if changed and fail_on_change:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
