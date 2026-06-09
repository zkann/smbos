#!/bin/bash
# smbos SessionStart hook
# Injects the SOP protocol and the current SOP index into session context.
# SOP directory resolution: $SOP_DIR > ./sops > ~/sops

PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ -n "$SOP_DIR" ] && [ -d "$SOP_DIR" ]; then
  dir="$SOP_DIR"
elif [ -d "./sops" ]; then
  dir="$(pwd)/sops"
elif [ -d "$HOME/sops" ]; then
  dir="$HOME/sops"
else
  echo "smbos plugin is installed but no SOP directory exists yet (checked \$SOP_DIR, ./sops, ~/sops). If the user does a repeatable business task or asks about SOPs, suggest /sop-init (which can seed a starter pack for their business type) or /sop-import (which converts existing process docs). Starter library: $PLUGIN_ROOT/library"
  exit 0
fi

# Count SOPs by maturity for bootstrap detection
sop_files=$(find "$dir" -name '*.md' ! -name 'INDEX.md' ! -name '_template.md' ! -path '*/archive/*' 2>/dev/null)
total=0
mature=0
if [ -n "$sop_files" ]; then
  total=$(printf '%s\n' "$sop_files" | grep -c .)
  mature=$(printf '%s\n' "$sop_files" | xargs grep -l -E '^status: *(active|trusted)' 2>/dev/null | grep -c .)
fi

echo "## SOP system active (smbos plugin)"
echo ""
echo "SOP directory: $dir (SOPs: $total total, $mature active or trusted)"
echo "Starter library: $PLUGIN_ROOT/library"
echo ""
cat <<'EOF'
SOPs are the user's documented way of doing recurring tasks. They override your defaults. Follow this protocol for the whole session:

1. MATCH. Before starting any multi-step or business-process task, scan the index below. If an SOP matches, read its full file and follow it. Tell the user which SOP you are using (id, version, status).
2. PERSONALIZE DRAFTS. An SOP with status: draft has never been verified by a real run. Before following one, resolve its [personalize: ...] slots by asking the user, save the answers into the file, then proceed. Personalize only the slots this run actually touches; the rest can wait.
3. FOLLOW THEIR WAY. The "My way" section of an SOP beats your default approach, even when your default seems better. If you think the SOP is wrong, say so and ask; do not silently override it.
4. DEVIATE TRANSPARENTLY. If a step cannot apply, say so in the moment and remember the deviation for step 5.
5. LEARN. After finishing an SOP-guided task: update frontmatter (last_used, runs; clean_runs +1 if there were no corrections or deviations, else reset clean_runs to 0). If there were deviations or user corrections, propose a specific edit as a before/after diff. Apply only with approval, bump the version, and add a dated changelog line saying what changed and why. If the user declines but the observation matters, offer to record it under "Notes for next revision".
6. PROMOTE. After a draft completes its first real run, set status: active. When an active SOP reaches clean_runs of 3 or more, set status: trusted. Any approved content edit resets clean_runs to 0 and returns a trusted SOP to active.
7. IMPLICIT FEEDBACK. Treat these as SOP feedback even when the user does not phrase them as such: mid-task corrections, re-asking a request in different words, editing your output afterward, telling you to skip a step. Fold them into update proposals (step 5) or trigger-phrase improvements.

Commands: /sop-init, /sop-new, /sop-import, /sop-run, /sop-update, /sop-list, /sop-review. The user never needs to memorize these; plain requests ("save this as an SOP", "show my SOPs") route to the same flows.
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
echo ""
echo "### SOP index"
if [ -f "$dir/INDEX.md" ]; then
  cat "$dir/INDEX.md"
else
  echo "(INDEX.md is missing. Offer to rebuild it with /sop-list.)"
fi
