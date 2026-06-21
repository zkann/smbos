# jobs.d: recurring-job specs

Each `*.json` here declares one recurring job that `scripts/jobs.py sync` compiles into a tagged
crontab line. This directory holds **public** jobs shipped with the plugin; **private** jobs live in
a local `<sop_dir>/jobs.d` (e.g. `~/sops/jobs.d`) that `sync` also reads and that never enters this
repo. A local spec overrides a public one of the same name.

Spec format:

```json
{
  "name": "my-job",
  "kind": "job",
  "schedule": "30 8 * * *",
  "command": "/usr/bin/python3 /abs/path/script.py >/dev/null 2>&1",
  "enabled": true,
  "liveness_file": "/abs/path/the-job-writes-on-success.json",
  "max_age_minutes": 1560
}
```

- **name**: `[a-z0-9-]`; used verbatim in the cron tag and (for a keychain job) the launchctl label.
- **kind**: `job` (a plain cron line running `command`) or `keychain-job` (a cron line that
  `launchctl kickstart`s the existing GUI agent `com.smbos.<name>`, the workaround for cron not being
  able to read the login keychain).
- **schedule**: a literal cron timing field (`30 8 * * *`) or an `@hourly`/`@daily`/`@weekly` shortcut.
- **command**: `job` only; a self-contained shell command (cron's environment is minimal, so bake in
  absolute paths and any needed `SMBOS_*` vars).
- **enabled**: optional, default `true`.
- **liveness_file**: optional; a path or glob the job writes (or touches) on a successful run. The
  newest matching file's mtime is the job's last-run, which the dashboard's **System view** reads to show
  each job's health (green when fresh, amber when stale). Omit it and the job shows as health "unknown".
- **max_age_minutes**: optional; how stale `liveness_file` may get before the System view flags the job.
  Defaults to 90 for a `keychain-job` (hourly-ish) and ~1 day for a `job`.

Run `python3 scripts/jobs.py sync` from a **Terminal**: writing the crontab needs Full Disk Access,
which the dashboard process doesn't have. `sync` is idempotent, claims the legacy smbos cron tags, and
preserves every non-smbos crontab line. **Out of scope:** always-on launchd services (the
dashboard/tray/desktop agents) are managed by the cutover installers, not here.
