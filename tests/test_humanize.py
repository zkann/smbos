from humanize import humanize_cron, humanize_failure, humanize_source, humanize_spec


def test_cron_shapes():
    assert humanize_spec("cron(57 8 * * 1)", "cron") == "every Monday at 8:57 AM"
    assert humanize_spec("cron(53 7 * * *)", "cron") == "every day at 7:53 AM"
    assert humanize_spec("cron(0 9 1 * *)", "cron") == "monthly on day 1 at 9:00 AM"
    assert humanize_spec("cron(30 17 * * 1-5)", "cron") == "every weekday at 5:30 PM"
    assert humanize_cron("0 13 * * 0") == "every Sunday at 1:00 PM"


def test_no_raw_cron_leak():
    for spec in ["cron(57 8 * * 1)", "cron(53 7 * * *)", "cron(30 17 * * 1-5)"]:
        assert "cron(" not in humanize_spec(spec, "cron")


def test_event_specs():
    out = humanize_spec("linear.issue.created[label=bug]", "event")
    assert out == "when a Linear issue created happens (label=bug)"
    assert humanize_spec("slack.message[#support]", "event").startswith("when a Slack message")


def test_garbage_passes_through():
    assert humanize_spec("garbage", None) == "garbage"
    assert humanize_cron("cron(not a real spec)") == "cron(not a real spec)"


def test_sources():
    assert humanize_source("cron") == "its schedule"
    assert humanize_source("manual") == "a manual test"
    assert humanize_source("somethingelse") == "a somethingelse event"


def test_failure_mapping():
    plain, action = humanize_failure("API Error: OAuth token has expired")
    assert "logged in" in plain and "log in" in action
    plain, _ = humanize_failure("monthly budget reached ($21 of $20)")
    assert "spending cap" in plain
    plain, _ = humanize_failure("timeout after 900s")
    assert "took too long" in plain
    plain, action = humanize_failure("status is 'draft'; only active/trusted SOPs run unattended")
    assert "hasn't been done" in plain
    plain, action = humanize_failure("some weird thing")
    assert "unexpected error" in plain and "some weird thing" in action


def test_unrecorded_changes_failure_is_plain():
    plain, action = humanize_failure("unrecorded changes since the last saved version")
    assert "outside the normal save flow" in plain
    assert "review the changes" in action
