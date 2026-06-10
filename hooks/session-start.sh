#!/bin/bash
# SmbOS SessionStart hook
# Injects the SOP protocol and the current SOP index(es) into session context.
# Home library: $SOP_DIR > ~/sops. Project layer: ./sops (shadows/extends home).

PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

home_dir=""
proj_dir=""
if [ -n "$SOP_DIR" ] && [ -d "$SOP_DIR" ]; then
  home_dir="$SOP_DIR"
elif [ -d "$HOME/sops" ]; then
  home_dir="$HOME/sops"
fi
if [ -d "./sops" ]; then
  proj_dir="$(pwd)/sops"
fi
if [ -n "$proj_dir" ] && [ "$proj_dir" = "$home_dir" ]; then
  proj_dir=""
fi

if [ -z "$home_dir" ] && [ -z "$proj_dir" ]; then
  echo "smbos plugin is installed but no SOP directory exists yet (checked \$SOP_DIR, ./sops, ~/sops). If the user does a repeatable business task or asks about SOPs, suggest /sop-init (which can seed a starter pack for their business type) or /sop-import (which converts existing process docs). Starter library: $PLUGIN_ROOT/library"
  exit 0
fi

list_sops() {
  find "$1" -name '*.md' ! -name 'INDEX.md' ! -name '_template.md' ! -path '*/archive/*' 2>/dev/null
}
sop_files=""
[ -n "$home_dir" ] && sop_files="$(list_sops "$home_dir")"
if [ -n "$proj_dir" ]; then
  sop_files="$(printf '%s\n%s' "$sop_files" "$(list_sops "$proj_dir")" | grep -v '^$')"
fi

total=0
mature=0
if [ -n "$sop_files" ]; then
  total=$(printf '%s\n' "$sop_files" | grep -c .)
  mature=$(printf '%s\n' "$sop_files" | xargs grep -l -E '^status: *(active|trusted)' 2>/dev/null | grep -c .)
fi

echo "## SOP system active (smbos plugin)"
echo ""
if [ -n "$proj_dir" ] && [ -n "$home_dir" ]; then
  echo "SOP libraries: home $home_dir + project $proj_dir (project layer shadows/extends home by id). SOPs: $total total, $mature active or trusted."
elif [ -n "$proj_dir" ]; then
  echo "SOP directory: $proj_dir (project-local; no home library found). SOPs: $total total, $mature active or trusted."
else
  echo "SOP directory: $home_dir (SOPs: $total total, $mature active or trusted)"
fi
echo "Starter library: $PLUGIN_ROOT/library"
echo ""
cat <<'EOF'
SOPs are the user's documented way of doing recurring tasks. They override your defaults. Follow this protocol for the whole session:

1. MATCH. Before starting any multi-step or business-process task, scan the index below. If an SOP matches, read its full file and follow it. Tell the user which SOP you are using (id, version, status).
2. PERSONALIZE DRAFTS. An SOP with status: draft has never been verified by a real run. Before following one, resolve its [personalize: ...] slots by asking the user, save the answers into the file, then proceed. Personalize only the slots this run actually touches; the rest can wait.
3. COMPOSE. SOPs nest. A step containing [[sop:some-id]] means: read that SOP and execute it inline as a sub-run, with its own metadata updates, deviations, and edit proposals (which go to the sub-SOP, not the parent). Frontmatter "needs:" lists upstream SOPs whose output this one consumes; if that input is not already in hand, offer to run the upstream SOP first (do not auto-run it). Frontmatter "next:" lists typical successors; offer the next one in a single line when a run completes. If a reference points to a missing SOP or a chain loops, say so and continue sensibly.
4. CONTEXT. One task can vary by project. (a) Variants: a "## Variants" section lists deltas keyed by detectable conditions (e.g. "TypeScript projects (package.json present)"); detect which applies from the workspace before running and announce it; ask once if ambiguous. (b) Overlays: a project-local ./sops SOP with frontmatter "extends: <home-id>" merges over the home SOP: overlay sections replace same-named base sections, except "My way" which appends. Resolution precedence: the user's explicit ask > project overlay (cwd) > variant condition > ask.
5. FOLLOW THEIR WAY. The "My way" section of an SOP beats your default approach, even when your default seems better. If you think the SOP is wrong, say so and ask; do not silently override it.
6. DEVIATE TRANSPARENTLY. If a step cannot apply, say so in the moment and remember the deviation for step 7.
7. LEARN. After finishing an SOP-guided task: update frontmatter (last_used, runs; clean_runs +1 if there were no corrections or deviations, else reset clean_runs to 0). If there were deviations or user corrections, propose a specific edit as a before/after diff. Before proposing, ask whether each correction is UNIVERSAL or PROJECT-SPECIFIC: universal edits go to the base/home SOP; project-specific ones go to the overlay or variant section (create the overlay if needed). Apply only with approval, bump the version, and add a dated changelog line saying what changed and why. If the user declines but the observation matters, offer to record it under "Notes for next revision".
8. PROMOTE. After a draft completes its first real run, set status: active. When an active SOP reaches clean_runs of 3 or more, set status: trusted. Any approved content edit resets clean_runs to 0 and returns a trusted SOP to active. Sub-runs count for the sub-SOP's promotion too.
9. IMPLICIT FEEDBACK. Treat these as SOP feedback even when the user does not phrase them as such: mid-task corrections, re-asking a request in different words, editing your output afterward, telling you to skip a step. Fold them into update proposals (step 7) or trigger-phrase improvements.

PLAIN WORDS. When talking to the user, render system state in plain language: schedules as "every Monday at 8:57 AM" (never cron syntax), trigger sources as "its schedule" / "a Linear event" (never "source: cron"), failures as what happened plus one suggested fix (never raw API errors). Spec syntax belongs in files, not conversation. Mention overlays/variants as "the version for this project" / "the TypeScript way" unless the user uses the technical terms first.

Commands: /sop-init, /sop-new, /sop-import, /sop-run, /sop-update, /sop-list, /sop-review, /sop-dashboard (visual library view in the browser), /sop-triggers (schedules, automation, costs), /sop-connect (Claude Desktop), /sop-work (track multi-stage work in progress). The user never needs to memorize these; plain requests ("save this as an SOP", "show my SOPs", "what has automation cost") route to the same flows.
EOF
echo ""
if [ "$mature" -lt 5 ]; then
  cat <<'EOF'
BOOTSTRAP MODE (fewer than 5 active SOPs). The library is young, so capture aggressively:
- Offer to save an SOP after EVERY completed multi-step task that could plausibly recur, not once per session.
- When the user requests a task type you have seen before in this session or library gaps make it obvious ("second invoice this week, no SOP"), name the gap.
- If the library is empty or mostly drafts, suggest /sop-init starter packs or /sop-import for existing process docs, once.
EOF
else
  echo "CAPTURE (steady state): after completing a multi-step task that is likely to recur and has NO matching SOP, offer once per session to save it via the /sop-new flow."
fi
if [ "$total" -gt 0 ]; then
  has_runs=$(printf '%s\n' "$sop_files" | xargs grep -l -E '^runs: [1-9]' 2>/dev/null | grep -c .)
  if [ "$has_runs" -eq 0 ]; then
    echo ""
    echo "GETTING GOING: the library has $total SOP(s) but none has been used yet. If a natural moment arises this session (the user starts a task an SOP covers), point out that doing it together verifies the SOP and unlocks automation for it. One gentle mention at most."
  fi
fi
pending=0
if [ -n "$sop_files" ]; then
  pending=$(printf '%s\n' "$sop_files" | xargs grep -h 'via dashboard' 2>/dev/null | grep -c .)
fi
if [ "$pending" -gt 0 ]; then
  echo ""
  echo "PENDING DASHBOARD SUGGESTIONS: $pending note(s) tagged 'via dashboard' are waiting in 'Notes for next revision' sections. Early in this session, offer to review them and fold them into SOP edits through the normal diff/approval flow (remove each note once folded in)."
fi
parked=0
approved=0
for pdir in "$home_dir/pending" "$proj_dir/pending"; do
  [ -d "$pdir" ] || continue
  n=$(grep -l '^status: pending' "$pdir"/*.md 2>/dev/null | grep -c .)
  parked=$((parked + n))
  a=$(grep -l '^status: approved' "$pdir"/*.md 2>/dev/null | grep -c .)
  approved=$((approved + a))
done
if [ "$approved" -gt 0 ]; then
  echo ""
  echo "APPROVED ACTIONS TO EXECUTE: $approved parked run(s) have status: approved (the owner approved them from chat/Desktop, where actions cannot execute). Early in this session: execute each approved action exactly as written in its pending file, confirm completion to the owner, then set the file's status to done (or delete it)."
fi
if [ "$parked" -gt 0 ]; then
  echo ""
  echo "TRIGGERED RUNS AWAITING APPROVAL: $parked parked run(s) in the SOP pending/ directory. Early in this session, walk the owner through each one: show the prepared work and the proposed action, get an approve/discard decision, complete approved actions, then set the file's status to approved or discarded (or delete it)."
fi
cwd="$(pwd)"
queued_here=0
elsewhere_list=""
for qdir in "$home_dir/queue" "$proj_dir/queue"; do
  [ -d "$qdir" ] || continue
  for f in "$qdir"/*.md; do
    [ -f "$f" ] || continue
    grep -q '^status: queued' "$f" || continue
    proj=$(grep -m1 '^project:' "$f" | sed 's/^project:[[:space:]]*//')
    if [ -z "$proj" ] || [ "$proj" = "$cwd" ]; then
      queued_here=$((queued_here + 1))
    else
      elsewhere_list="$elsewhere_list$proj
"
    fi
  done
done
if [ "$queued_here" -gt 0 ]; then
  echo ""
  echo "OWNER-QUEUED TASKS FOR THIS SESSION: $queued_here task(s) the owner queued (from the dashboard) to do together, that belong in this folder or are project-agnostic. Early in this session, offer to start: for each matching queue/ file, read its sop id and any owner notes, then run that SOP interactively (this is also how drafts get verified and promoted). When one finishes, set the queue file's status to done (or delete the file)."
fi
if [ -n "$elsewhere_list" ]; then
  folders=$(printf '%s' "$elsewhere_list" | grep -v '^$' | sort -u | xargs -n1 basename 2>/dev/null | paste -sd ', ' -)
  echo ""
  echo "QUEUED TASKS FOR OTHER PROJECTS: the owner has queued task(s) tied to a different folder than this one ($folders). Do NOT run them here. If the user asks about them, tell them to open Claude Code in that folder; this session is the wrong place for project-specific work."
fi
inflight_here=""
for wd in "$home_dir/work" "$proj_dir/work"; do
  [ -d "$wd" ] || continue
  for f in "$wd"/*.md; do
    [ -f "$f" ] || continue
    grep -q '^status: done' "$f" && continue
    wproj=$(grep -m1 '^project:' "$f" | sed 's/^project:[[:space:]]*//')
    [ -n "$wproj" ] && [ "$wproj" != "$cwd" ] && continue
    title=$(grep -m1 '^title:' "$f" | sed 's/^title:[[:space:]]*//')
    stage=$(grep -m1 '^stage:' "$f" | sed 's/^stage:[[:space:]]*//')
    st=$(grep -m1 '^status:' "$f" | sed 's/^status:[[:space:]]*//')
    flag=""; [ "$st" = "blocked" ] && flag=" (BLOCKED)"
    inflight_here="$inflight_here  - $title: at stage '$stage'$flag
"
  done
done
if [ -n "$inflight_here" ]; then
  echo ""
  echo "WORK IN PROGRESS (multi-stage items active in this folder or unscoped):"
  printf '%s' "$inflight_here"
  echo "If the user picks one up, follow its workflow SOP for the current stage, then advance it (work.py advance) and log what happened. Surface blocked items so they don't stall silently."
fi
if [ -n "$proj_dir" ] && [ -f "$proj_dir/INDEX.md" ]; then
  echo ""
  echo "### Project SOP index ($proj_dir; shadows/extends home by id)"
  cat "$proj_dir/INDEX.md"
fi
if [ -n "$home_dir" ]; then
  echo ""
  echo "### SOP index ($home_dir)"
  if [ -f "$home_dir/INDEX.md" ]; then
    cat "$home_dir/INDEX.md"
  else
    echo "(INDEX.md is missing. Offer to rebuild it with /sop-list.)"
  fi
fi
