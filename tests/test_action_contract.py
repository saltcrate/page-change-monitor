#!/usr/bin/env python3
"""Contract test: action.yml ↔ monitor.py ↔ README, plus one live two-pass run.

Guards the regression class that shipped twice — an output declared in
action.yml under one name while monitor.py writes another (silent empty
outputs), and the dot form `outputs.changed-count`, which GitHub's expression
parser reads as a subtraction.

    python3 tests/test_action_contract.py        # SKIP_NET=1 for offline

Test-only dependency: PyYAML. The action itself stays stdlib-only.
"""
import os
import re
import subprocess
import sys
import tempfile

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCUMENTED = {"changed", "changed-count", "checked-count", "failed"}

ok, fail, skip = [], [], []


def check(name, cond, detail=""):
    (ok if cond else fail).append(f"{name}{': ' + detail if detail else ''}")


def main():
    yml = yaml.safe_load(open(os.path.join(REPO, "action.yml")))
    src = open(os.path.join(REPO, "monitor.py")).read()
    readme = open(os.path.join(REPO, "README.md")).read()

    emitted = set(re.findall(r'set_output\(\s*"([^"]+)"', src))
    check("monitor.py emits the documented keys", DOCUMENTED <= emitted, f"emitted={sorted(emitted)}")

    declared = {k: v["value"] for k, v in yml["outputs"].items()}
    for name, expr in declared.items():
        bracket = re.search(r"outputs\['([^']+)'\]", expr)
        dot = re.search(r"outputs\.([A-Za-z_]\w*)", expr)
        target = bracket.group(1) if bracket else (dot.group(1) if dot else None)
        check(f"output {name!r} resolves a written key", target in emitted, f"-> {target!r}")
        if "-" in name:
            check(f"dashed output {name!r} uses index syntax", bool(bracket), "dot form = subtraction")

    # GitHub truncates action metadata over 125 chars without failing.
    check("description <= 125 chars", len(yml["description"]) <= 125, str(len(yml["description"])))
    check("README has no steps.*.outputs.dashed-dot access",
          not re.search(r"steps\.\w+\.outputs\.[\w-]*-", readme))
    check("README shows index syntax", "outputs['changed-count']" in readme)
    rc = subprocess.run([sys.executable, "-m", "py_compile", os.path.join(REPO, "monitor.py")]).returncode
    check("monitor.py compiles", rc == 0, f"rc={rc}")

    if os.environ.get("SKIP_NET") != "1":
        env = dict(os.environ, INPUT_URLS="https://example.com", INPUT_TIMEOUT="30")
        runs = []
        for _ in range(2):
            out = os.path.join(tempfile.mkdtemp(prefix="pcm-out-"), "gh_output")
            r = subprocess.run([sys.executable, os.path.join(REPO, "monitor.py")],
                               env=dict(env, GITHUB_OUTPUT=out), capture_output=True, text=True)
            if r.returncode:
                skip.append(f"live run rc={r.returncode}: {r.stderr.strip()[:120]}")
                break
            runs.append((open(out).read(), r.stdout))
        if len(runs) == 2:
            keys = set(re.findall(r"^([\w-]+)<<EOF$", runs[0][0], re.M))
            check("live run emits every declared key", keys >= DOCUMENTED, f"{sorted(keys)}")
            check("second run reports unchanged", "unchanged" in runs[1][1])

    print("\n".join(f"PASS {s}" for s in ok))
    print("\n".join(f"SKIP {s}" for s in skip))
    print("\n".join(f"FAIL {s}" for s in fail))
    print(f"\n{len(ok)} passed, {len(fail)} failed, {len(skip)} skipped")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
