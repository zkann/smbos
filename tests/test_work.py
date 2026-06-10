import subprocess
import sys

from conftest import SCRIPTS

SCRIPT = SCRIPTS / "work.py"


def run(args, library):
    import os
    env = dict(os.environ)
    env["SOP_DIR"] = str(library)
    return subprocess.run([sys.executable, str(SCRIPT)] + args,
                          capture_output=True, text=True, env=env, timeout=30)


def test_lifecycle(library):
    out = run(["new", "Add SSO", "--stages", "plan,build,review,ship"], library).stdout
    assert "at stage 'plan'" in out
    assert "now at 'build'" in run(["advance", "add-sso", "branch cut"], library).stdout
    assert "blocked" in run(["block", "add-sso", "waiting on review"], library).stdout
    listed = run(["list"], library).stdout
    assert "[BLOCKED]" in listed and "[build]" in listed and "✓plan" in listed
    run(["unblock", "add-sso"], library)
    run(["stage", "add-sso", "ship", "skipped review"], library)
    assert "done" in run(["done", "add-sso"], library).stdout
    assert "No work in progress" in run(["list"], library).stdout
    assert "Add SSO" in run(["list", "--all"], library).stdout
    body = (library / "work" / "add-sso.md").read_text()
    assert "branch cut" in body and "skipped review" in body


def test_advance_past_last_stage(library):
    run(["new", "Tiny", "--stages", "only"], library)
    out = run(["advance", "tiny"], library).stdout
    assert "last stage" in out


def test_duplicate_titles_get_unique_ids(library):
    run(["new", "Same title"], library)
    run(["new", "Same title"], library)
    out = run(["list"], library).stdout
    assert out.count("Same title") == 2
