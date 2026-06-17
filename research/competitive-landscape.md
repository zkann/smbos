# SmbOS Competitive Landscape

SmbOS is a Claude Code plugin: an SOP manager for a technical solo operator. Plain-markdown SOPs in `~/sops`, a SessionStart hook that injects an SOP-following protocol, a local live-mirror dashboard (FastAPI + SSE + single-file JS) showing "On your plate / In flight / Coming up / Recent runs / Procedures / Settings", a do-loop (task lands on plate, human picks it up, a primed Claude Code session opens, completion reports back), an MCP stdio server, an importer, and cron-based scheduling. This report maps the surrounding market across seven categories and locates SmbOS inside it.

The headline finding: the market has independently converged on SmbOS's exact architecture (local control plane, plain-markdown procedures, durable pause/resume, command-center board), so the bet is validated rather than novel. The plumbing is commoditized and often free. The competition has moved to trust, and trust is bought with three things: legibility (an inspectable record of what an agent actually did), graduated control (per-task approval, not a global on/off), and cost transparency (per-run spend, hard stops). SmbOS's defensible moat is not the dashboard or the session plumbing; it is the SOP layer (the scoping discipline every autonomous tool makes users reinvent per task) plus the plain-language operating model for a non-babysitting solo owner.

---

## 1. AI DevOps / agent-ops platforms (the closest analogues)

### aidevops (aidevops.sh)
- **One-liner:** Open-source CLI framework that turns OpenCode/Claude Code into a self-supervising DevOps team running missions across code, infra, and business ops.
- **How it works:** Bash + TypeScript (Bun) on top of OpenCode/Claude Code. A "Pulse supervisor" runs every 2 minutes via launchd as an LLM-driven manager: checks capacity (a circuit breaker sizes worker slots from available RAM), merges green PRs, dispatches workers to stuck PRs, advances missions, triages findings, syncs TODOs to GitHub issues. Work is Mission to Milestone to Feature to Worker; each worker runs in an isolated git worktree; agents coordinate through a SQLite WAL "mailbox" (registry with role/branch/heartbeat, inbox/outbox, broadcasts). Mission state persists as JSON committed to the repo so any session resumes. Budget is an append-only cost ledger that routes cheap work to small models and pauses missions at an 80% spend threshold. Destructive ops (force-push, prod deploy, DROP DATABASE) require cross-provider verification by a second AI.
- **Value prop:** Closes the gap between "the model can probably do this" and "the work is done, verified, safe, and worth the cost" for a solo operator, running 24/7 with minimal babysitting.
- **Key features:** Pulse 2-minute autonomous loop; missions persisted as repo JSON; parallel worktrees; SQLite mailbox; budget ledger with 80% pause; stuck-worker "struggle ratio" (messages/commits >30 struggling, >50 thrashing, kills workers 3h+ with no PR); multi-model verification gate; named runners with own memory namespace; 90+ slash commands, 2050+ subagent files, 30+ integrations.
- **Tech stack:** Bash + TS/Bun, MCP servers, SQLite (WAL), launchd. OSS (MIT), ~270 stars.
- **Pricing:** Free; user pays model/API costs (Claude Max ~$200/mo discussed, cheaper-model routing as mitigation).
- **Feedback:** Enthusiastic small-audience reception; users like that OSS lets them "ask the AI what it all does and whether it's safe." But ~270 stars is modest, and the kitchen-sink scope (90+ commands, 2050+ subagent files) plus hype-heavy copy ("SOTA everything", "100x superpowers") is a clear complexity/credibility risk.
- **vs SmbOS:** Nearly identical persona and the single closest analogue. aidevops is more autonomous and more sprawling; SmbOS is more legible and human-gated. Most borrowable: the Pulse pattern (an LLM "manager pass" that decides what to surface on the plate instead of the human polling), the struggle-ratio heuristic to flag a thrashing in-flight session, budget-as-plain-language-surface with an 80% pause, and the cross-provider verification gate before irreversible actions. SmbOS should resist aidevops's kitchen-sink scope; its plain-language discipline is the counter-positioning.

### Devin / Devin Desktop (Cognition)
- **One-liner:** Cloud autonomous "AI software engineer" plus a desktop "command center" for coordinating fleets of local and cloud agents.
- **How it works:** Assign a task via Slack/web/API; each task spins up a sandboxed VM (editor, terminal, browser); the agent plans, codes, runs CI, opens a PR. Devin Desktop (June 2026) is the management layer: an editor plus a dashboard coordinating agents across projects, with "Spaces" (group agents by project, share context across sessions/PRs/files), read/unread indicators (orange dot, clears on open), one-click "start a new session with this prompt", and "Devin Local". It implements the open Agent Client Protocol (ACP) so Codex/Claude Agent/OpenCode run in the same center; an Agent Router auto-directs tasks to the cheapest agent. Billed in ACUs (~15 min of work each).
- **Value prop:** Offload well-scoped tasks and supervise a fleet from one governed center rather than driving each agent by hand.
- **Key features:** Spaces; read/unread orange dots; ACP interop; Agent Router; ACU metering with per-task cost; up to 10 concurrent sessions (Core) / unlimited (Team); VPC + SAML/OIDC enterprise.
- **Tech stack:** Cloud, per-task sandboxed VMs, closed source. Reports 67% PR merge rate (up from 34%); ~89% of its own commits.
- **Pricing:** Core pay-as-you-go from $20 (ACUs $2.25 each); Team $500/mo (250 ACUs at $2.00); Enterprise custom.
- **Feedback:** Great on narrowly-scoped ~1-hour tasks ($2-10 each); a full-stack task consumed ~20 ACUs ($40) with zero usable output, stuck looping on linter errors ("we would not have kept them on the team"). Early Answer.AI trial logged 14 failures / 3 successes across 20 tasks. No long-term memory across sessions; introduces tech debt.
- **vs SmbOS:** Positioned upmarket, but the command-center UX is directly relevant. Borrow: read/unread dots for the In-flight list, Spaces (group runs by client/project), ACU-style per-task cost on Recent runs, one-click re-run a prior plate task. The hard lesson (agents shine on ~1-hour tasks, fail on sprawling ones) is SmbOS's wedge: SOPs enforce narrow framing by design.

### Cline CLI 2.0 + Cline Kanban
- **One-liner:** Open-source terminal coding agent that becomes a local control plane, with a browser Kanban board running many CLI agents in parallel, each in its own git worktree.
- **How it works:** CLI 2.0 (Feb 2026) brings long-running and parallel headless work with a review path. Oversight is tunable: `-y` YOLO auto-approves; otherwise approve per step or shift+tab to set auto-approve; an approval-hooks system gates every tool call with a script (allow reads, require approval on writes, block prod); `CLINE_COMMAND_PERMISSIONS` restricts shell commands. `cline schedule create` runs cron agents; "Zen mode" backgrounds a task. Cline Kanban (`cline --kanban`, localhost:3484) is a local web app: cards run many agents in parallel, each in an ephemeral worktree + terminal; review a diff scoped to message ranges (not one blob), comment inline and feedback routes back to the agent; linked cards auto-start when a predecessor lands.
- **Value prop:** Make parallel, long-running, partly-autonomous work legible and reviewable from one local board without vendor lock-in or cloud.
- **Key features:** Kanban of agent cards; per-card worktree + terminal; message-range-scoped diffs with inline line comments routed back; dependency chains; tunable oversight ladder; script-gated approval hooks; cron + Zen background; BYOK local + hosted.
- **Tech stack:** Open-source Cline SDK runtime; localhost board; git worktrees; cron. Free CLI (free Kimi K2.5/M2.5 at launch).
- **Pricing:** Free/OSS; BYOK.
- **Feedback:** Builders called it the likely default multi-agent interface for tackling the two real bottlenecks (inference-bound waiting, merge-conflict-heavy parallelism). The per-card worktree + scoped diff + inline review combo drew strong praise; the control-plane framing resonated.
- **vs SmbOS:** The Kanban columns map almost 1:1 onto SmbOS's plate. Most borrowable: scoped diffs with inline comments routed back to the agent (legible + correctable in-flight work), the tunable oversight ladder (graduated trust vs binary launch-permission), approval hooks as a concrete guardrail, dependency chains for multi-stage SOP work (plan to build to review to ship auto-advancing).

### Charm Crush
- **One-liner:** Polished single-binary terminal coding agent (OpenCode successor) with multi-provider model switching, LSP context, MCP extensibility.
- **How it works:** Single Go binary on Charm's Bubble Tea TUI. CLI to AgentCoordinator to a SessionAgent backed by a "fantasy" multi-provider abstraction. BYOK across ~7 providers with mid-session model switching that preserves context. Pulls context via LSP, tools via MCP, project config via `CRUSH.md`. A single interactive agent, not a supervisor.
- **Value prop:** The prettiest, most enjoyable terminal agent with serious provider flexibility in one portable binary.
- **Key features:** Cross-platform single binary; Bubble Tea TUI with inline highlighting and clear diff windows; mid-session model switching; LSP context; MCP.
- **Tech stack:** Go + Bubble Tea, LSP + MCP, BYOK, OSS.
- **Pricing:** Free/OSS; BYOK.
- **Feedback:** "Ridiculously pretty", "most enjoyable to use so far". But concrete gripes: no chat history, broken copy/paste, crashes on Ctrl+C, can't mix models, requires API keys not Pro sub, weaker planning than Claude Code, and it drops "unexplained junk binary files" and a low-value default `CRUSH.md`. Drifts on multi-day refactors spanning 50+ files.
- **vs SmbOS:** Single-agent, no orchestration; relevance is the lessons. Polish-as-trust (clear diffs drive adoption) reinforces SmbOS's screenshot-QA rule. The junk-file/empty-config complaint is a direct warning: never litter the repo, keep generated SOP/config files high-value from creation. The 50+-file drift reinforces the narrow-SOP bias.

### Agent observability (Langfuse, AgentOps, LangSmith, Laminar, Sentry, Arize)
- **One-liner:** The AIOps layer: dashboards that trace agent runs, model calls, tokens, cost, and tool invocations, increasingly on OpenTelemetry gen_ai conventions.
- **How it works:** Instrument an agent (Vercel AI SDK, OpenAI Agents SDK, LangGraph) and the platform captures each run as nested spans (model calls, tool calls, latency, tokens, cost), grouped by session/user, often near-zero-code. Monitors and evaluates; does not dispatch or supervise.
- **Value prop:** Make autonomous behavior legible and debuggable after the fact.
- **Key features:** Trace-per-run nested spans; session/user grouping; pre-built dashboards; OTel gen_ai standard; eval harness + prompt versioning; auto-instrumentation.
- **Tech stack:** OTel-based; Langfuse and several self-hostable/OSS; SDK integrations.
- **Pricing:** Varies (Langfuse OSS + cloud tiers; LangSmith/Arize/Datadog commercial; Sentry usage-based).
- **Feedback:** Langfuse favored for prompt iteration + evals and being self-hostable; the space is crowded and fragmenting, with OTel gen_ai cited as the consolidating standard.
- **vs SmbOS:** Complementary, not competitive. Borrow the trace-per-run data model for Recent runs (steps, tool calls, duration, cost in plain language), session/SOP grouping, and a lightweight eval signal ("did this run meet the SOP's acceptance criteria?") to strengthen the completion-reports-back step beyond binary done/not-done. Standardizing on OTel gen_ai would let the dashboard later ingest from any runtime.

---

## 2. Autonomous + assistive coding agents

### OpenHands (formerly OpenDevin, All Hands AI)
- **One-liner:** Open-source autonomous SE platform with a tiny event-driven core, runnable fully local or as persistent cloud agents.
- **How it works:** CodeAct core: a stateless Agent emits Actions; a Conversation runs the loop and stores an append-only EventLog; a Workspace (local process or Docker) executes Actions and returns Observations; LiteLLM gives provider portability. Every action/observation is an immutable event enabling deterministic replay, pause/resume, debugging. Tasks enter from GitHub/Slack/PagerDuty/CI/manual. Supports microagents and parallel agents.
- **Value prop:** A fully inspectable, self-hostable autonomous agent with no lock-in.
- **Key features:** Append-only EventLog (replay + pause/resume); swappable local-Docker vs cloud sandbox; microagents; multi-entry intake; Agent Canvas; budget/RBAC/audit (enterprise).
- **Tech stack:** OSS (MIT), Python core, LiteLLM, Docker. Model-agnostic.
- **Pricing:** Free/OSS; cloud and enterprise tiers.
- **Feedback:** The tiny-core event-stream architecture is praised as flexible; the immutable log makes runs debuggable and replayable (a trust win). Docker-sandbox setup and operational complexity are a barrier for casual users.
- **vs SmbOS:** Strongest borrowable pattern in the cluster: an append-only event log per run. Recent runs and In flight would be far more trustworthy backed by a replayable immutable stream than a status field. Multi-entry intake maps to SmbOS triggers; microagents map to SOP-scoped primed sessions.

### Aider
- **One-liner:** Terminal-based, git-native AI pair programmer that maps the whole repo and commits every edit as its own diff.
- **How it works:** A Coder coordinates LLM, filesystem, and git: instruction to edit blocks to file apply to git commit. A compact "repo map" gives whole-codebase context. Git-native: every edit is a commit. Architect mode separates planning from editing. Model-agnostic incl. local.
- **Value prop:** Lightweight, transparent AI coding where git is the safety net and audit log.
- **Key features:** Repo map; one commit per edit; architect/edit split; massive model flexibility incl. local; terminal-first.
- **Tech stack:** OSS (Apache 2.0), Python; git as persistence/audit.
- **Pricing:** Free/OSS; model cost only (or $0 local).
- **Feedback:** "The tool to benchmark against"; the author dogfoods it on aider's own ~30k-line codebase. "Glimpse into the future of coding."
- **vs SmbOS:** Git-as-audit-log is the cleanest trust mechanism in the cluster. SmbOS could make every run produce a discrete, reviewable, revertable commit so Recent runs maps 1:1 to git history the user already trusts. The architect/edit split reinforces a Prepare-before-Run step.

### Cline (IDE agent)
- **One-liner:** Open-source VS Code agent with a strict Plan/Act split and per-step human approval on every edit and command.
- **How it works:** Plan mode is read-only (explores, asks, proposes, changes nothing). Act mode executes step by step, surfacing each edit as a diff and each command as a preview you approve/reject. Ops are risk-classified (safe reads auto-approve; rm/DROP TABLE always require approval; YOLO disables guardrails). A shadow git repo checkpoints after each tool use (restore files / messages / both). `/newtask` distills the conversation and starts a fresh context. Live token + cost display with a "Spend Limit Reached" guard.
- **Value prop:** Autonomous capability with safety dials maxed: plan first, approve every change, roll back anything, never get a surprise bill.
- **Key features:** Plan/Act split; per-step risk-classified approval; shadow-git checkpoints; `/newtask` handoff; live cost + hard spend limit; MCP marketplace.
- **Tech stack:** OSS (Apache 2.0), VS Code extension + SDK/CLI; BYOK or Cline Provider.
- **Pricing:** Free OSS; BYOK (~$0.01-0.10/task) or pay-as-you-go.
- **Feedback:** Plan/Act "prevents the AI-rewrote-half-my-project failure mode"; per-step approval and full OSS auditability are the repeatedly-cited trust features.
- **vs SmbOS:** The richest trust template here. Plan/Act maps onto Prepare to Run (make Prepare an explicit read-only state the human reviews). Risk-classified approval is the strongest argument for graduating launch-permission per-SOP. Shadow-git checkpoints = a concrete one-click "undo this run" on Recent runs. Live cost + hard stop is exactly what Settings budget should enforce, in plain language. `/newtask` is a clean template for the completion report.

### Cursor (Agent Mode + Background/Cloud Agents)
- **One-liner:** AI-native editor turned agent-first control center running parallel cloud agents that each open a PR.
- **How it works:** In-editor Agent Mode does multi-file edits; Background/Cloud Agents clone into a fresh Ubuntu VM, work on a branch, push a PR. "Computer Use" (Feb 2026) gives each agent a desktop+browser to visually verify UI. The Agents Window lists every running agent (task, repo, local-vs-cloud), where you click in to see history + diffs, redirect, review branches, and merge.
- **Value prop:** One panel to dispatch, watch, redirect, and merge many parallel autonomous agents.
- **Key features:** Agents Window; parallel cloud agents to PRs; Computer Use visual verification; Slack/web dispatch; click-in to inspect/redirect/merge.
- **Tech stack:** Closed-source VS Code fork; isolated cloud VMs; frontier models + Composer.
- **Pricing:** Pro+ subscription + cloud-agent compute usage.
- **Feedback:** Pushback that agent-first abandons the IDE identity; constant context-switching to review agent code "is mentally taxing and kills flow state." Users want diffs grouped by which agent produced them (provenance gap).
- **vs SmbOS:** The Agents Window is the closest analog to In flight. Borrow its columns (task, target, local-vs-cloud, live status) and click-through to history+diffs; let the human redirect a running session (a mid-flight verb beyond put-back/done/dismiss); tag every run with which SOP produced it. The flow-state complaint validates SmbOS's consolidated, plain-language framing over scattering across IDE+Slack+dashboard.

### Roo Code
- **One-liner:** Open-source VS Code "team of AI agents" with permission-scoped modes (Code, Architect, Ask, Debug, Custom) an orchestrator delegates between.
- **How it works:** Each mode has its own prompting and tool/permission set (Architect is read-only by design). An Orchestrator delegates subtasks to the right mode. Per-action permission prompts by default; opt-in Auto-Approve.
- **Value prop:** A configurable in-editor dev team where each role has scoped permissions, so you dial autonomy per task type.
- **Key features:** Permission-scoped modes; orchestrator delegation; custom modes; opt-in Auto-Approve; MCP.
- **Tech stack:** OSS, VS Code, model-agnostic, BYOK.
- **Pricing:** Free OSS; model cost only.
- **Feedback:** The mode system + read-only Architect guardrail keep complex tasks organized; the configurability has a learning curve, and Auto-Approve can run long.
- **vs SmbOS:** Permission-scoped modes are a strong model for SOPs: each SOP could declare its capability scope (read-only audit vs file-writing vs external/destructive) and the plate enforces it, safer than one global toggle. The Auto-Approve-runs-long warning argues for pairing any auto-run with a budget/time tripwire.

### Factory.ai (Droids)
- **One-liner:** Role-specialized "Droids" running long-horizon "Missions" across terminal, IDE, and web to ship mergeable PRs.
- **How it works:** Four Droids (Code, Knowledge, Reliability, Product). Missions: describe a business outcome and watch Droids plan, execute, verify over hours/days, across web/IDE/CLI/Slack. Output is PRs for review.
- **Value prop:** Describe an outcome, not steps; specialized agents coordinate across your toolchain to deliver review-ready work.
- **Key features:** Role-specialized Droids; outcome-described multi-Droid Missions with verify; cross-surface; CLI for CI/CD; PR-as-deliverable.
- **Tech stack:** Closed-source cloud; token billing; BYOK option.
- **Pricing:** Free BYOK; Pro $20; Plus $100; Max $200; Enterprise custom.
- **Feedback:** Code quality needs "significant manual cleanup"; token consumption is a "blackhole" causing budget overruns; "powerful but uneven, depends on scoping."
- **vs SmbOS:** Role-specialized Droids = SmbOS's library of named, purpose-built SOPs ("pick the right specialist" is more legible to a solo operator). The token-blackhole complaint validates the budget setting as a differentiator, but it must show real-time spend and hard-stop. Cross-surface is a both-sides lesson: SmbOS's value is being the one local center, not fragmenting the user.

### Sourcegraph Amp
- **One-liner:** Frontier terminal/editor agent with shareable Threads, autonomous subagents, an Oracle reasoning model, billed pure pass-through.
- **How it works:** Three modes (deep/smart/rush). Work happens in Threads (persistent, savable, resumable, shareable). The main agent spawns Subagents (isolated context windows) for parallel parts and can auto-invoke the Oracle (high-reasoning model) for debugging/review without spending the main thread's tokens. Granular thread visibility (private to public link). CLI shows real-time tool execution and expandable thinking blocks.
- **Value prop:** A high-autonomy agent whose work is a shareable, inspectable artifact, paying only raw model cost.
- **Key features:** Threads; granular visibility + public links; subagents with isolated context; Oracle on a separate budget; expandable tool/thinking view; no-markup credit billing ($5 min).
- **Tech stack:** Commercial (Sourcegraph); CLI + editor; Threads on Sourcegraph servers; multi-model.
- **Pricing:** No subscription; credits at raw LLM cost, zero markup; Enterprise +50%.
- **Feedback:** Writes 70-80% of code for active users; the Oracle auto-second-opinion on its own context is the standout. But pay-per-use makes cost feel unpredictable for exploratory use.
- **vs SmbOS:** Threads-as-shareable-artifact is the best legibility idea here: make each run a persistent, linkable thread with full tool calls so Recent runs becomes a library of inspectable artifacts. A public link lets a founder share a completed run as proof/handoff to a client. The Oracle pattern (auto-escalate hard sub-problems to a stronger model on a separate budget) keeps routine runs cheap. Real-time expandable tool view is exactly what In flight should stream over SSE (collapsed by default).

---

## 3. Agent orchestration, multi-session managers, autonomous loops

### Conductor (Melty Labs)
- **One-liner:** Free Mac app running parallel Claude Code / Codex / Cursor agents, each in its own git worktree, with a unified monitor/diff/merge dashboard.
- **How it works:** Each task gets a worktree + branch + terminal + diff + review path; a central dashboard shows all sessions. Checkpoints + rollback; a multi-model "race" mode (several agents attempt the same task, pick the winner). Uses existing Claude auth; clones the repo via GitHub OAuth.
- **Value prop:** Turns "babysit one terminal" into "delegate N scoped tasks and review them like PRs." "The skill isn't coding faster. It's knowing what can happen simultaneously."
- **Key features:** Per-task workspace; unified dashboard; checkpoints + rollback; multi-model race; free.
- **Tech stack:** Native macOS (Apple Silicon), worktrees, GitHub-OAuth clone, closed source. YC S24.
- **Pricing:** Free app; BYO subscription.
- **Feedback:** OAuth asks for full read-write to the entire GitHub account (no fine-grained scopes), drawing backlash. Parallel execution is fast (4 bugs in ~10 min), but worktrees exclude untracked files (.env, node_modules) so each needs bootstrapping, 4 agents = 4x tokens, new workspaces have "context amnesia", and "4 parallel agents = 4x as many bugs to catch."
- **vs SmbOS:** The "each task = workspace + branch + terminal + diff + review" framing is the cleanest legible-unit model. Borrow checkpoints + rollback as "undo this run". The .env-bootstrapping pain warns the Prepare step should capture the environment/secrets a run needs. "Context amnesia per new workspace" is exactly what the SOP-injection hook solves: lean into it. The full-account-OAuth backlash is a positioning lesson: local-first / minimal-scope is a trust advantage.

### Sculptor (Imbue)
- **One-liner:** Mac app running parallel Claude Code agents in isolated Docker containers, with one-click "Pairing Mode" to pull any agent's work into your local repo and IDE.
- **How it works:** Each agent runs in its own Docker container (not a worktree), safe parallel execution with no per-agent dependency reinstalls. Pairing Mode bidirectionally syncs a container agent into your local repo so the agent sees your edits live and you test in your IDE before committing. Merge auto-flags conflicts; beta "Suggestions" flags issues; roadmap "Instruction audits" check output against your plaintext rules.
- **Value prop:** Run multiple agents safely in parallel and quickly verify their changes; container isolation bounds blast radius, Pairing Mode collapses sandbox-vs-real-workflow.
- **Key features:** Per-agent container isolation; Pairing Mode; persistent session history; auto-flagged conflicts; beta Suggestions + planned Instruction audits.
- **Tech stack:** macOS + Docker, local execution, closed source. Imbue.
- **Pricing:** Not public; BYO Claude.
- **Feedback:** Direction came from Claude Code users explicitly asking for safe parallel agents and fast verification (strong PMF signal). But the trust features that matter most (Suggestions, Instruction audits) are beta/roadmap; verification is still manual today.
- **vs SmbOS:** "Instruction audits" (check output against plaintext rules) is the killer idea: SmbOS SOPs ARE plaintext rules, so a post-run "did this run follow its SOP?" audit is a natural, differentiated Recent-runs feature SmbOS is uniquely positioned to ship. Pairing Mode is a richer "pick up": a "take over this in-flight session locally" button. Container isolation is the trust story for any unattended/scheduled SOP.

### Vibe Kanban (Bloop AI)
- **One-liner:** Open-source self-hosted Kanban board for orchestrating CLI coding agents: write a ticket, assign an agent, it runs in an isolated worktree, you review the diff and merge from the board.
- **How it works:** `npx vibe-kanban`. Board (To Do, In Progress, In Review, Done) plus a live agent-interaction pane streaming reasoning, commands, file ops, and MCP tool calls in real time. Assign a task to a saved agent profile (Claude Code, Codex, Gemini, OpenCode, Amp, Cursor CLI); it runs in a worktree with permission-skipping flags on by default. Review the diff, comment back to the agent, or reject and re-attempt with a different agent. On accept it rebases, merges, cleans up. "Open in IDE" opens the worktree.
- **Value prop:** Fixes the "working synchronously with one agent leads to distraction and doomscrolling" problem with async board-based oversight and a clear review gate.
- **Key features:** Kanban with explicit In-Review gate; real-time streaming pane; per-task worktree with auto rebase+merge; comment-back + reject-to-new-attempt; multi-agent profiles; single-command self-host.
- **Tech stack:** Local web app, npx-launched, GitHub-connected, worktrees. OSS.
- **Pricing:** Free/OSS (announced sunsetting; community-maintained).
- **Feedback:** The explicit review gate resonated; but it overlaps Cursor's Agents UI in a crowded field ("why this over X"), and permission-skipping ON by default is a YOLO safety concern for a tool that merges to main.
- **vs SmbOS:** The columns map almost 1:1 onto SmbOS's vocabulary, and the explicit "In Review" gate (a distinct state between in flight and done so completed-but-unverified work doesn't silently land) is the borrowable upgrade. Comment-back + reject-to-new-attempt is a great human-in-the-loop primitive (reply to a run to re-run with a tweak). The real-time streaming pane is the legibility gold standard for the SSE mirror. Permission-skipping-by-default is the anti-pattern to avoid.

### Claude Squad
- **One-liner:** Terminal TUI manager for multiple agents, each in its own tmux session + git worktree, with optional background auto-accept.
- **How it works:** A Go TUI (`cs`); each instance = tmux session + worktree. Keys drive new/attach/commit+push/pause/resume/kill, with a diff/preview toggle. `--autoyes` runs background YOLO. Configurable launch profiles drive Claude Code, Codex, Gemini, Aider, OpenCode, Amp.
- **Value prop:** For terminal-dwellers hitting "session sprawl", one TUI to spawn, attach, diff, pause/resume, and push N isolated sessions.
- **Key features:** Single TUI over N agents (tmux + worktree); pause/resume; background auto-accept; in-TUI diff; commit+push from TUI; multi-agent profiles.
- **Tech stack:** Go TUI, tmux + worktrees + gh, fully local. OSS (~7.8k stars).
- **Pricing:** Free/OSS; BYO agent.
- **Feedback:** Strong adoption among terminal-native users (the canonical DIY tmux+worktree pattern productized); `--autoyes` is a known footgun (no review gate).
- **vs SmbOS:** Validates the persona: even terminal-natives want one pane making parallel/queued sessions legible. Borrow pause/resume as explicit states ("paused, waiting on you" vs "actively running", maps to the inflight-session-liveness branch) and named launch profiles (an SOP declares model/flags/permissions it launches with).

### Ralph loop (Geoffrey Huntley)
- **One-liner:** A technique: run an agent in a bare `while` loop, feeding the same prompt + spec each iteration, one task per loop with a fresh context window.
- **How it works:** `while :; do cat PROMPT.md | claude-code ; done`. Each iteration starts a fresh instance, reads a fixed stack (`@fix_plan.md`, `@specs/*`, `@AGENT.md`, `PROMPT.md`), does ONE atomic task, commits only if tests pass. The non-obvious insight is the deliberate context reset. Subagents handle expensive work; specs live external; prompt-level guardrails (search before assuming, no placeholders, run tests immediately, leave notes).
- **Value prop:** Cheap, dumb, durable autonomy: orchestration reframed as a loop + a good spec + a context reset.
- **Key features:** One task per loop + fresh context; external spec/plan as durable state; tests-pass-before-commit; subagents-as-workers; prompt-level guardrails.
- **Tech stack:** Bash + a coding CLI + markdown + git.
- **Pricing:** Free pattern.
- **Feedback:** Real overnight throughput when spec + test loop are solid; but "no way I'd use Ralph in an existing codebase" and "no way this is possible without senior expertise"; failure modes are placeholders, non-deterministic search, and waking to a broken codebase.
- **vs SmbOS:** The "fresh context + injected spec every iteration" IS SmbOS's SessionStart-hook model: independent validation that priming each run from external markdown beats long sessions. `fix_plan.md` / specs / `AGENT.md` map to plate / SOP / CLAUDE.md. "One task per loop, tests-pass-before-commit" is the safest contract for unattended cron SOPs. The greenfield-only caveat says scope unattended SOPs to well-defined, verifiable, low-blast-radius work.

### Terragon / Terry (shut down Jan 2026)
- **One-liner:** Cloud fleet of background Claude Code agents you assign from anywhere; each runs in a remote sandbox and opens a PR, with a `terry` CLI to pull a cloud session down locally.
- **How it works:** Remote sandboxed container per task; PR as the reviewable unit; async assignment from mobile; `terry` for cloud-to-local takeover. Now an OSS snapshot; Claude Code Web is the successor.
- **Value prop:** Async fire-and-forget work producing reviewable PRs, with a clean local-takeover escape hatch.
- **Key features:** Cloud sandbox per task; PR deliverable; mobile async assignment; cloud-to-local takeover; parallel background fleet.
- **Tech stack:** Cloud sandboxes + PR output + local CLI bridge. Now OSS.
- **Pricing:** Was paid SaaS; now free OSS snapshot (defunct).
- **Feedback:** The "background agent, terminal closed" pitch landed. But it shut down: Anthropic shipping Claude Code Web ate the wedge. "Thin cloud-wrappers over Claude Code get eaten by the platform vendor."
- **vs SmbOS:** PR-as-reviewable-unit and cloud-to-local takeover are borrowable. The strategic caution is the most important takeaway: Terragon died because it was a thin wrapper Anthropic could replace. SmbOS's defensibility must be the SOP library + plain-language operating model, NOT re-implementing session plumbing.

### container-use (Dagger)
- **One-liner:** Open-source MCP server giving each agent a containerized, git-branched environment, with a full command/log audit trail and a drop-into-terminal escape hatch.
- **How it works:** An MCP server you add to any MCP agent. Each agent gets a fresh Dagger container in its own git branch; every change is auto-committed (a complete git audit trail). It records the full command history and logs of what agents actually did ("not just what they claim"); you can drop into any agent's terminal to inspect or take over.
- **Value prop:** Infrastructure-layer trust + isolation: many agents safely, plus an honest replayable record.
- **Key features:** Per-agent container + branch; auto-commit audit trail; full command/log history; drop-into-terminal takeover; MCP; discard-failures-instantly.
- **Tech stack:** MCP stdio + Dagger + git worktrees. OSS.
- **Pricing:** Free/OSS.
- **Feedback:** "Containing agent chaos" resonates with teams burned by unverifiable claims. But the Docker/Dagger dependency adds setup overhead vs simple worktrees.
- **vs SmbOS:** "Record what the agent actually did, not what it claims" is the single strongest trust feature in this cluster. Recent runs should store the real command/tool-call log so "completed" is verifiable, not asserted. It's an MCP server like SmbOS's own, suggesting SmbOS could expose run-isolation/audit as MCP resources.

### GSD + Backlog.md (markdown spec-driven planners)
- **One-liner:** Markdown-native, git-stored planning systems: GSD runs define/build/ship milestone cycles as a Claude Code plugin; Backlog.md turns any repo into a markdown kanban treating AI agents as first-class.
- **How it works:** GSD: interview to research-agent fan-out to v1/v2/out-of-scope to phased roadmap to wave-based execution; state persists in `.planning/` markdown across context resets; pause/resume/progress/debug commands. Backlog.md: tasks/docs/decisions as markdown + YAML in-repo (every change a commit), instant terminal kanban + web UI, AGENTS.md instruction files for predictable structured output.
- **Value prop:** Make the plan itself durable, versioned, plain-text, and agent-readable, surviving context resets and living in git.
- **Key features:** Markdown + YAML in git, every change a commit; GSD milestone/phase cycles with state-across-resets; Backlog.md terminal kanban + web UI; AGENTS.md structured contracts; resume/pause/progress.
- **Tech stack:** Plain markdown + YAML in git; Backlog.md zero-config CLI + web UI; GSD plugin/skills. OSS.
- **Pricing:** Both free/OSS.
- **Feedback:** "Markdown-native, 100% private and offline, lives inside your repo" is the loved property; AGENTS.md as a structured contract is the differentiator. But the ceremony is "great for big projects, overkill for a quick fix."
- **vs SmbOS:** SmbOS's closest philosophical cousins. Backlog.md's "every change is a git commit" gives a model for versioning runs and plate changes. AGENTS.md = the SessionStart SOP-injection; borrow the structured completion-report contract. The "terminal kanban + web UI from the same plain files" pattern validates dashboard-over-markdown and suggests a terminal view of the plate. The "overkill for small tasks" critique is a direct warning: keep a lightweight quick-run path.

---

## 4. Agent inbox / human-in-the-loop control surfaces

### LangChain Agent Inbox
- **One-liner:** Open-source React inbox for reviewing and responding to human-in-the-loop interrupts from LangGraph agents.
- **How it works:** A LangGraph agent calls `interrupt()` with a HumanInterrupt payload, checkpointing graph state and pausing. The Inbox polls for outstanding interrupts and renders each with a markdown description + an action_request; the human resolves with one of four HumanResponse actions and the graph resumes.
- **Value prop:** A ready-made review surface for any LangGraph agent; the four-action vocabulary is a clean handoff contract.
- **Key features:** Accept / Edit / Respond / Ignore; per-interrupt config flags declaring which actions are valid; markdown description per item; checkpoint-resumable; multi-deployment.
- **Tech stack:** TypeScript, React/Next/Tailwind, MIT; tightly coupled to LangGraph/LangSmith.
- **Pricing:** Free/OSS; pay for LangGraph/LangSmith infra.
- **Feedback:** (Framework-coupled; the four-action contract is the widely-copied takeaway.)
- **vs SmbOS:** Adopt the explicit per-task action contract: each plate item declares which actions are valid (pick up / queue / dismiss / edit-and-run), like HumanInterrupt.config. The Edit action is the trust unlock: let the human modify the agent's proposed args/plan BEFORE it runs (Prepare exposes parameters as editable fields). Every card should carry a markdown "why this is here / what it'll do" blurb.

### HumanLayer (SDK + CodeLayer + Agent Control Plane)
- **One-liner:** YC-backed HITL layer that began as a Slack/email approval SDK and became CodeLayer, a local Tauri desktop control surface orchestrating parallel Claude Code sessions.
- **How it works:** SDK: wrap risky tools with `@require_approval`, expose `@human_as_tool`; calls pause and route over Slack/email; adds routing, escalations, timeouts, and learned auto-approvals. CodeLayer (Apache-2.0): an `hld` Go daemon owning session lifecycle, persisting to SQLite, running Claude Code, exposing REST; a Tauri/React keyboard-first desktop UI; a TS CLI. "MULTICLAUDE" runs many sessions across worktrees + remote workers. Agent Control Plane is a Kubernetes-CRD scheduler with an AwaitingHumanApproval phase.
- **Value prop:** Run agents headless and still gate the few risky steps through a human, over the channels they already use or a fast local surface.
- **Key features:** `@require_approval` / `@human_as_tool`; Slack/email routing + escalations + timeouts; learned auto-approvals; CodeLayer local daemon + SQLite + REST + Tauri UI + CLI; ACP CRD scheduler.
- **Tech stack:** SDK Python/TS + cloud API; CodeLayer Go + Tauri/React + SQLite + REST (Apache-2.0, ~11k stars). Mix of OSS and hosted.
- **Pricing:** SDK free Starter ~1,000 ops/mo then pay-as-you-go (~$20/200 ops drew pushback); CodeLayer/ACP open source.
- **Feedback:** Pricing attacked ("not complicated to make... any competition would wipe out your pricing"). Automation-bias risk raised ("if the agent usually works, the human rubber-stamps and never catches the risky 5%"). CodeLayer praised by users ("shipping one banger PR after the other", "+50% productivity"). But a critical review called the context-engineering framework "mostly vapor... CodeLayer isn't available" (features marketed ahead of GA).
- **vs SmbOS:** CodeLayer is a near-mirror of SmbOS (local daemon + SQLite + REST + desktop center + CLI orchestrating Claude Code across worktrees) and validates the bet, including the launchd/daemon-liveness and session-lifecycle problems SmbOS is fighting. Borrow learned auto-approvals (graduate launch-permission to per-SOP learned trust, e.g., "approved this invoice-send 8 times, auto-run under $X"). Route "waiting for you" to Slack/email/push. Surface what CHANGED vs the last approved run, not just "approve?" The "mostly vapor" review is a warning: keep Run/Queue/Prepare honest about what actually executes.

### Inngest AgentKit (+ Inngest durable platform)
- **One-liner:** Open-source TS multi-agent framework on durable execution, where HITL is `step.waitForEvent()` pausing a workflow for hours/days with no cron or DB hacks.
- **How it works:** Agents compose into Networks coordinated by a Router (rule-based or LLM); shared Network State. Runs on durable execution: every step checkpointed; `step.waitForEvent()` pauses indefinitely and resumes on the matching event with state intact. The Dev Server traces every run with full logs and per-step I/O.
- **Value prop:** "Pause an autonomous workflow for a human, possibly for days, then resume exactly where it left off" as a one-liner, plus a free run-inspection dashboard.
- **Key features:** `waitForEvent` indefinite pause; durable checkpointed steps; Networks + Router; Dev Server per-step traces; multi-LLM + MCP.
- **Tech stack:** TS (@inngest/agent-kit), OSS, on Inngest durable engine (cloud or self-host).
- **Pricing:** Library free; platform usage-based.
- **Feedback:** Positions durable steps as what makes production agents debuggable; often compared head-to-head with Trigger.dev.
- **vs SmbOS:** `waitForEvent()` is the clean mental model for "pick up later" / scheduled-then-gated runs (sit in "in flight, awaiting you" for days, resume primed, zero cost while waiting). The Dev Server run-trace is exactly the legibility Recent runs needs. The deterministic-vs-LLM router distinction maps to SmbOS triggers: label how a task got on the plate (cron/inbox verdict vs an LLM deciding "this needs you").

### gotoHuman
- **One-liner:** Cloud platform-agnostic agent inbox: a no-code review-form builder plus async webhook loop so any agent can request human approval/editing.
- **How it works:** Agent requests a review (SDK/HTTP/MCP/n8n); it appears in a web inbox routed to an assignee. Reviews render from no-code templates (typed fields + controls). Reviewers approve, edit in-place, or regenerate with an edited prompt, comparing versions via artifact versioning. Decision returns via webhook; decisions accumulate as "Agent Memory."
- **Value prop:** Design a review form, drop a webhook, get a polished team inbox with editing, versioning, routing, and a learning dataset, on any framework.
- **Key features:** No-code per-review-type templates with typed fields; in-place edit + regenerate-with-edited-prompt; artifact versioning; team inbox + Slack/email; broad integrations; Agent Memory.
- **Tech stack:** Cloud SaaS (EU, GDPR); SDKs + MCP + webhooks. Not OSS/local.
- **Pricing:** Usage-based; tiers not fully published.
- **Feedback:** (The per-task-type review template is the standout.)
- **vs SmbOS:** Per-task-type review templates: let a SOP define the exact fields/controls a human sees when picking up that task (an invoice SOP shows amount + recipient as editable fields with Approve). Artifact versioning supports "show what changed." Agent Memory maps to feeding pick-up/dismiss/edit history back into SOPs via sop-update. Its explicit "Agent Inbox" naming shows the inbox metaphor is category-standard; SmbOS's "On your plate" is the warmer version.

### Vercel AI SDK 6 (HITL tool approval)
- **One-liner:** The most-copied HITL primitive: a `needsApproval` flag on a tool plus `addToolResult` to send the human's decision back and resume the loop.
- **How it works:** `needsApproval: true | (input) => boolean` intercepts the tool call instead of executing it; the frontend renders a confirm card; the user's decision via `addToolResult` resumes the loop. Pairs with the Workflow SDK for long waits.
- **Value prop:** The minimum-viable HITL contract: one boolean (or input-predicate) to gate a tool, render-as-a-card, one call to resume.
- **Key features:** Per-tool or per-input gating; tool calls as confirm cards; store preferences to auto-approve; durable-workflow pairing.
- **Tech stack:** TS, AI SDK 6 + useChat, React/Next. OSS.
- **Pricing:** Free/OSS.
- **Feedback:** The input-predicate form (gate only risky inputs, not the whole tool) is the elegant bit.
- **vs SmbOS:** The input-predicate gate is the cleanest answer to binary launch-permission: gate a SOP run only when args cross a threshold (budget over $X, external recipient, production target). Plate items ARE these confirm cards: keep the proposed action's concrete args visible so approval is informed.

### ServiceNow AI Control Tower (enterprise control-tower pattern)
- **One-liner:** The enterprise framing: a centralized governance console over all agent activity with policy-gated approvals, identity, and auditability via MCP/Action Fabric.
- **How it works:** A governance plane above all agents; requests go to a human only when policy says so; "progressive delegation" expands autonomy as the user's approval history builds trust; Action Fabric exposes governed workflows to any external agent over MCP.
- **Value prop:** Where the category goes upmarket: a governed, audited, identity-aware center where approvals are policy-driven and autonomy is earned.
- **Key features:** Single-pane governance; policy-gated approvals; identity-verified auditable execution; Action Fabric MCP; progressive delegation.
- **Tech stack:** Proprietary enterprise SaaS + MCP. Closed.
- **Pricing:** Enterprise licensing.
- **Feedback:** (Conceptual ceiling of the category, not SmbOS's user.)
- **vs SmbOS:** "Progressive delegation" is the single most transferable idea: start a new SOP requiring approval, expand autonomy automatically as approval history accumulates (the productized version of launch-permission + budget, and the direct counter to automation bias). "Route to a human only when policy says so" reframes the plate: most runs should NOT hit it; the plate should be the policy-defined exception set.

---

## 5. SOP & process-documentation tools

### Process Street
- **One-liner:** Checklist/workflow engine where SOPs are runnable templates with conditional logic, approvals, and automation.
- **How it works:** A template (an SOP as an ordered task list) spawns a checklist instance someone works through; form fields, conditional branching, role assignment, approval steps, due dates, automations (webhooks, scheduled runs) make each run dynamic. The distinction vs doc tools: a procedure is executed and tracked as a live instance.
- **Value prop:** Procedures you actually run and complete, with branching and approval gates, not docs that sit unread.
- **Key features:** Templates to runnable instances; conditional branching; inline approval tasks; scheduled runs + webhooks; run history.
- **Tech stack:** Cloud SaaS + webhooks/API. Closed.
- **Pricing:** Startup ~$100/mo but bills a 5-user minimum even if 2 use it (the loudest complaint).
- **Feedback:** Conditional logic is powerful once learned; pricing (5-seat minimum) and a slow UI are the loudest complaints; advanced users hit a ceiling on complex automation.
- **vs SmbOS:** The closest conceptual cousin: SOP-as-runnable-instance. Run/Queue/Prepare + Recent runs maps 1:1 to template to checklist to history, but agent-executed. Approval tasks INSIDE a run are exactly the HITL gate; conditional branching = SOPs that branch on runtime answers the agent evaluates. The seat-floor resentment is a clean wedge for SmbOS's single-operator no-seat local model.

### Whale (usewhale.io)
- **One-liner:** AI SOP software that captures processes, builds training, and explicitly positions SOPs as the knowledge layer for training AI agents.
- **How it works:** Record/upload a process; "Alice" transcribes it into a numbered SOP with embedded video. SOPs get an owner, approval status, and change log; updates flow through an expert-review cycle before going live. Markets a "Train AI agents" use case: SOPs as grounding context.
- **Value prop:** Your documented processes become both human training AND the trustworthy context that powers your AI agents.
- **Key features:** AI video/voice to SOP; per-SOP owner + approval status + change log; expert-review-before-live; AI tests + auto-assign; "Train AI agents."
- **Tech stack:** Cloud SaaS, token-metered AI. Closed.
- **Pricing:** Per-seat; AI token-metered (a documented gotcha).
- **Feedback:** Claims ~50% faster onboarding, ~70% less documentation time; governance praised. But AI features burn the token allocation fast on paid plans, then become unavailable until reset.
- **vs SmbOS:** The closest strategic competitor to SmbOS's thesis (SOPs as agent grounding context), validating the market, but Whale does it as a cloud add-on; SmbOS does it natively (SessionStart hook + MCP server), a sharper terminal-native execution. Borrow the governance triad (every SOP has owner + approval status + change log) and update-goes-through-review-before-live (drafted changes land on the plate for owner approval before becoming the live SOP an agent follows). Token-metering resentment validates the budget/cost-report feature.

### Scribe
- **One-liner:** Extension that watches you do a task once and auto-generates a step-by-step guide with annotated screenshots.
- **How it works:** Click record, perform the workflow; it captures clicks, writes step text, and grabs/annotates a screenshot per step; desktop apps extend capture to native apps. AI auto-writes titles and auto-blurs PII.
- **Value prop:** Documentation as a byproduct of doing the work once. "Capture, don't author."
- **Key features:** One-pass click capture; auto-redaction; AI titles; desktop capture; embed/share, SOC2.
- **Tech stack:** Browser extension + desktop + cloud. Closed. Freemium.
- **Pricing:** Free tier; Pro ~$23-29/user/mo; Enterprise.
- **Feedback:** Fastest way to document; non-technical staff produce clean guides. But when the UI changes you re-record everything (screenshots go stale); step text captures WHAT not WHY; terminal/command-line output isn't captured; over-eager blur redacts non-sensitive text.
- **vs SmbOS:** Capture-don't-author is directly relevant to the importer. The "WHAT not WHY" complaint is the exact gap SmbOS can win on: a session transcript captures reasoning/decisions, not just clicks. Staleness is Scribe's core weakness: markdown SOPs an agent reads don't break when a button moves. And "terminal not captured" is a literal gap for a terminal-living founder: SmbOS inside Claude Code captures exactly what Scribe can't.

### Trainual / SweetProcess (SOP + training/delegation)
- **One-liner:** Cloud SOP + onboarding platforms turning processes into assigned, trackable training (Trainual is LMS-leaning; SweetProcess is flatter and cheaper).
- **How it works:** Build a content tree of Subjects/Procedures filed by role/department; assign; track viewed/completed/quiz-passed/e-signed. Manager authors, employee acknowledges, dashboard shows progress.
- **Value prop:** One place where every process is documented, assigned, and provably acknowledged. Sells the "business that runs without you" dream.
- **Key features:** Role/department tree + assignment; completion tracking, quizzes, e-signatures; progress dashboards; AI drafting.
- **Tech stack:** Cloud SaaS + mobile. Closed. Per-seat annual.
- **Pricing:** Trainual ~$124/mo (10 users) to $249/mo (20); SweetProcess from ~$99/mo (up to 20).
- **Feedback:** Trainual: clean structured UI and e-signatures praised; "far too expensive for a small business"; heavy customization needed. SweetProcess: easier to start, lighter on training/automation/analytics.
- **vs SmbOS:** The "business runs without you" framing resonates; SmbOS's plate/in-flight model is the agent-executed version. Assignment + acknowledgement is a trust primitive ("this run followed SOP vX, owner approved launch"). SweetProcess's Procedures-chained-into-Processes maps to a multi-stage work item referencing sub-SOPs. The role/department tree is heavy chrome for a solo operator; the flat markdown library is the right counter-positioning.

### Tettra / Slite (AI knowledge base + Q&A)
- **One-liner:** AI KBs that answer questions strictly from your docs with citations and proactively flag stale/duplicate content.
- **How it works:** Author docs; an AI bot answers inline (Tettra in Slack; Slite via "Ask") grounded only in your content with sources, routing to a human or flagging staleness when it can't.
- **Value prop:** Trustworthy cited answers + a KB that maintains its own freshness.
- **Key features:** Cited grounded answers; route-to-human-if-unsure; self-maintaining staleness/duplicate flagging; content owners + verification badges + review cadence.
- **Tech stack:** Cloud SaaS. Closed. (Slite notably has no public API.)
- **Pricing:** Per-seat paid tiers.
- **Feedback:** "Ask" cuts onboarding from a week to "just ask"; verification workflow praised. But no free plan (Tettra), value collapses off Slack; Slite has no developer API.
- **vs SmbOS:** "Answers grounded ONLY in your content, with citations" is the trust bar for agent output: SmbOS runs should be traceable to specific SOP text and escalate to the plate when no SOP covers the task, never improvise silently. Self-maintaining staleness flagging is exactly the sop-review job: make drift/overlap detection proactive on the dashboard. Slite's no-API complaint is instructive: plain markdown + MCP is the opposite, programmable stance.

### Notion-as-SOP
- **One-liner:** Notion databases + templates as a DIY SOP system: flexible and cheap, but static docs with no execution or enforcement.
- **How it works:** SOP templates create a database of procedure pages with role/division views; each page is step content + owner + change-log by convention. No runtime: nothing runs a procedure.
- **Value prop:** A free-form, familiar, cheap home for SOPs.
- **Key features:** Database views by role; huge template marketplace; relate to projects/people; Notion AI.
- **Tech stack:** Cloud SaaS + AI (has an API). Closed.
- **Pricing:** Standard per-seat; templates free/cheap.
- **Feedback:** Flexible no-extra-cost SOP home. But static docs that are easy to over-build and let rot: no execution, no enforced acknowledgement, freshness depends entirely on manual discipline.
- **vs SmbOS:** The DEFAULT SmbOS competes against for technical founders. The wedge: Notion SOPs are inert docs a human must remember to follow; SmbOS SOPs are agent-executable and auto-injected at session start ("your SOPs actually run"). Files-you-own (greppable, version-controllable, AI-editable, no per-seat tax) is a real positioning advantage. (Guidde, an AI-video documentation tool, is a counter-positioning lesson: video is the wrong format for a terminal-living founder and for agent consumption.)

---

## 6. AI automation / agent builders for SMB ops

### Zapier Agents (+ Central)
- **One-liner:** AI teammates that act autonomously across 8,000+ apps from natural-language instructions, with a "Needs action" approval queue.
- **How it works:** Trigger to instructions to tools to action to logged activity. Describe intent; a prompt-optimizer rewrites it; connect apps and data sources (Drive, Notion, Airtable as a KB); pick triggers (on-demand, scheduled, from a Zap, from app events). An LLM decides which tools to call; all runs land in an activity log.
- **Value prop:** Lowest-friction autonomous agent acting across the apps a business already uses, with the largest catalog and a human-approval queue.
- **Key features:** NL agent creation + prompt-optimizer; 8,000+ integrations; data-source KB; "Needs action" queue (info/approval/re-auth); draft-approval before sensitive actions; full activity log.
- **Tech stack:** Cloud-only SaaS, proprietary. No self-host.
- **Pricing:** Usage/credit add-on; Agents called out as meaningfully more expensive than core Zaps.
- **Feedback:** Core automation reliable and easy; Agents "cost quite a bit more"; connections occasionally disconnect without reason (a trust issue for unattended runs).
- **vs SmbOS:** The "Needs action" queue is exactly "On your plate," and it validates splitting plate items by reason (needs-approval vs needs-info vs broken-auth). The prompt-optimizer step: offer to rewrite a captured task into a stronger primed prompt the user can edit. Draft-before-send gating tied to action sensitivity maps to launch-permission.

### Lindy
- **One-liner:** No-code builder for always-on AI "employees" triggered by email/Slack/calendar events.
- **How it works:** Describe an agent in plain English; Lindy generates trigger + actions; event triggers fire a sequence of tool calls. 100+ role templates. Credit-metered per action.
- **Value prop:** Turn a described role into a running always-on assistant in minutes, with templates that make the first agent concrete.
- **Key features:** Conversational generation; 100+ templates; event triggers; 1M-char KB on free tier; packaged phone/lead/notes agents.
- **Tech stack:** Cloud-only proprietary SaaS, LLM-backed.
- **Pricing:** Free 400 credits/mo; Starter $19.99/2,000; Pro $49.99/5,000; Business custom.
- **Feedback:** "Expensive" is the single most common complaint (42 mentions); credit anxiety makes users afraid to experiment. The AI phone agent never worked across rebuilds; an agent "vanished from the dashboard"; the agent "runs off and builds before it has all the info" while burning credits. The no-code builder and templates are praised (4.7).
- **vs SmbOS:** Templates as the cold-start fix: the Procedures library should ship a seeded starter pack so the plate is never empty on day one. Credit anxiety is the cautionary tale: budget should show projected/spent cost per run and warn BEFORE a run blows the budget. "Agent vanished" is a legibility failure SmbOS can beat: every session must stay visible with a clear terminal state, never silently disappear. The "ran off before it had all the info" complaint argues for the primed-session + SOP approach.

### n8n (AI agents)
- **One-liner:** Fair-code, self-hostable visual workflow engine with native LangChain AI nodes, autonomous agents, memory, and vector stores.
- **How it works:** Visual canvas where AI is first-class (70+ AI nodes, native LangChain, persistent memory, vector stores). Self-host via Docker (Postgres/Redis) on a cheap VPS for effectively unlimited executions, or n8n Cloud. Agents call tools mid-workflow; drop to custom code nodes anywhere.
- **Value prop:** Maximum control and lowest marginal cost for technical users: own the infra and data, pay for a VPS not per-task credits.
- **Key features:** Self-host or cloud; 70+ AI nodes + LangChain + memory + vectors; 400+ integrations + custom code; execution-based pricing; source-available; branching/error handling.
- **Tech stack:** Node/TS, Docker (Postgres + Redis), source-available (Sustainable Use License).
- **Pricing:** Self-host free (VPS cost; cited ~12x cheaper than cloud, 80-90% cheaper than Zapier at volume); Cloud execution-metered.
- **Feedback:** Self-hosting is "a developer's dream" (~12x cheaper). But AI chains break mid-reasoning; workflows >15-20 nodes silently stop while showing "success" with partial data written; webhooks fire inconsistently; two max-severity vulns let authenticated users take over the server; self-hosting needs real DevOps.
- **vs SmbOS:** The silent-success-with-partial-data failure is the strongest argument for SmbOS's design: sessions must report a real completion state, and the dashboard must distinguish "reported done" from "went quiet" (the inflight-session-liveness work directly addresses this). Local-first / own-your-data and execution-not-credit cost framing are shared DNA worth leaning into.

### Relay.app
- **One-liner:** Human-in-the-loop automation: build a workflow, drop approval checkpoints anywhere, and a person approves/edits before sensitive steps run.
- **How it works:** Trigger + a readable series of steps. HITL is a native step type: an Approval checkpoint pauses until an assignee approves; AI-step review is a one-toggle route to email/Slack to approve/revise/send-back; data-collection steps send a small form. Assignees notified via interactive Slack/email. All HITL features free on every plan.
- **Value prop:** Automation you can trust with irreversible actions because the human gate is built in, not bolted on.
- **Key features:** Native approval checkpoint; one-toggle human review (approve/revise/send-back); data-collection forms; interactive Slack/email; checklist-style readable workflows.
- **Tech stack:** Cloud SaaS, proprietary. No self-host.
- **Pricing:** Free 200 steps + 500 AI credits; Professional $19/mo; Team $138/mo; HITL free across all tiers.
- **Feedback:** Native HITL approval before sensitive actions beats Gumloop/Bardeen (which rely on full automation or out-of-band review); checklist UI feels simpler than flowcharts. Step-based metering can limit at volume; two meters (steps + AI credits) to track.
- **vs SmbOS:** The sharpest HITL analogue. Steal the "approve / revise / send-back" triad as the action set on a plate approval item: SmbOS has put-back/done/dismiss; the missing verb is "revise and re-run." Make AI-step review a per-procedure toggle (some SOPs auto-run, some always pause), a per-procedure granularity on top of global launch-permission. Interactive Slack/email notifications close the loop when the founder isn't at the dashboard. Checklist-over-flowchart matches SmbOS's ethos: resist turning the dashboard into a node graph.

### Gumloop / Bardeen / Stack AI (rounding out the cluster)
- **Gumloop:** AI-native drag-and-drop node canvas (YC W24, $50M Series B). Tiered model cost made explicit (cheap model = small cost, frontier = big cost) is a transparency pattern SmbOS could echo at the Run/Queue/Prepare choice. Credit consumption hard to predict; Expert-tier nodes burn fast. Usage-not-seat pricing.
- **Bardeen:** "Zapier for your browser", local Chrome-extension automations. Local-execution-as-trust is shared, but the "stops when Chrome closes" ceiling shows the value of a persistent local daemon (SmbOS's launchd/cron approach). The credit "rug-pull" backlash is a warning that pricing/permission changes must be communicated loudly.
- **Stack AI:** Enterprise governance-first agent builder. The eval/guardrail framing (define what "good output" looks like, check against it) could inform how SmbOS verifies a run actually completed its SOP, beyond a self-reported "done." 60-90 day procurement; overkill for a solo operator.

---

## 7. Adjacent surfaces: personal chief-of-staff, runbooks, scheduled agents, local-first dashboards

### Personal "chief of staff" / do-loop planners
- **Motion / Reclaim:** AI auto-schedulers. Motion's auto-scheduler is called a "black box" that "reshuffles in ways that don't feel discerning", trust erosion from acting without explicit approval. The lesson: when a task moves or reorders, show WHY (priority, deadline, budget), never silently. SmbOS's "pick up to launch" gate is the antidote. Reclaim's per-habit "defense aggressiveness" slider maps to how aggressively a scheduled SOP claims time/budget vs yields to ad-hoc plate items.
- **Sunsama:** Guided manual daily planner (morning plan + evening shutdown ritual, a "workload counter" warning over-commitment). Borrow the ritual frame (a daily/session-start digest of plate/in-flight/coming-up + an end-of-session recap) and the workload counter ("today's committed runs vs budget"). Carry-over/defer/snooze validates explicit human triage of carryover. Sunsama's whole bet (humans WANT control, reject silent automation) validates the pick-up gate as a feature. ~$20-25/mo, no free tier (one of the priciest), is the complaint.
- **Akiflow:** Keyboard-first command-bar task consolidator. The always-available Command Bar (alt+space, NL + voice entry) is the single most transferable UX for a terminal-dwelling operator: a global hotkey overlay to capture a task, run/queue a Procedure, or create a cron SOP in plain language ("run invoice-followup every Monday 9am") instead of cron syntax. "Manual re-planning tax on chaotic weeks" warns to offer optional auto-ordering of "Coming up."
- **Cora (by Every):** Autonomous email chief-of-staff (screen, draft-in-your-voice, twice-daily Brief). The "inbox vs feed" reframe is directly transferable: keep "On your plate" strictly act-required and never let it decay into a skim-and-miss feed; a Recent-runs digest is the feed. Cora's risk (important things buried in a digest, trust taking weeks) is the strongest argument for SmbOS's never-auto-handle-silently posture. Draft-but-don't-send (human approves outgoing) is the safe default for any external artifact. $15/mo, Gmail-only.
- **Superhuman:** Power-user email (Split Inbox context streams + AI assist, human stays in control). Split Inbox validates splitting one queue into context lanes to reduce thrash (consider a per-client/project plate lane). Keyboard-first everything: every dashboard action should have a hotkey. Assist-not-autonomous is the deliberate, defensible middle ground SmbOS occupies.

### Runbooks, executable markdown, terminal ops
- **Runme (Stateful):** Plain-markdown docs become interactive executable notebooks (named, individually-runnable cells; shared persistent shell session; one file drives notebook UI + CLI + CI; confirm-before-run default). Borrow: let a single SOP step be "run this one block"; expose intermediate outputs of in-flight sessions; one SOP artifact drives Run/Queue/cron. Anti-bitrot framing validates demand for sop-review, but Runme can't auto-verify SOPs the way a Claude-driven reviewer can. OSS (Apache 2.0).
- **Warp (Workflows, Notebooks, Agent Mode):** AI terminal where parameterized commands (Workflows) and runnable runbooks (Notebooks) feed an embedded agent that asks permission before each command, reads output, and self-corrects. Borrow: typed parameters at Prepare time; the ask-run-observe-correct loop as the trust pattern; saved knowledge (Drive) auto-feeding the agent's context. Its mandatory-login backlash ("I have never uninstalled a program faster") is a cautionary tale: keep SmbOS install/use friction near zero, never gate the core loop behind an account.
- **Rundeck (PagerDuty):** Web console turning ops scripts into safe, parameterized, RBAC-gated, audited self-service Jobs (on-demand / scheduled / alert-triggered). The author-vs-runner boundary with a publish/approval gate maps to SOP status (draft to approved). Three trigger modes for one job is the model SmbOS triggers should match. Heavyweight JVM server + steep learning curve is SmbOS's opening: same value, local and near-zero-setup.
- **Tines:** Visual workflow mixing deterministic + agentic + human-approval steps, with the principle "enrich context BEFORE asking the human, not after." Borrow: a task on the plate should arrive decision-ready (recent runs, relevant files, draft output gathered), not as a bare "approve?"; an approval gate that pauses a run mid-stream for irreversible steps then resumes; the deterministic/agentic/human taxonomy for classifying SOP steps. Free Community Edition, no sales call.
- **Notion/Obsidian runbooks:** Validate the plain-markdown, local-first, git-friendly bet (Obsidian + Execute Code plugin) over cloud wiki lock-in. The universal complaint (copy-pasting commands from a stale doc, "the runbook is lying to you") is the exact pain SmbOS targets. Gap to exploit: these have NO scheduling, NO approval gate, NO orchestration, NO audit ledger; SmbOS's do-loop + plate + cron + recent-runs is the missing layer.

### Scheduled / background agents (cron-for-agents)
- **Claude Code Routines (Scheduled Tasks):** Anthropic's first-party cron-for-agents (cron + webhook + GitHub triggers, combinable; runs server-side with the laptop closed; reuses Claude Code config). The closest first-party analogue to "Coming up" / Recent runs, but cloud and headless. The HN backlash is a direct opening: "I want a commodity, not a platform"; Routines seen as "an unnecessarily complex wrapper around cron/webhooks that could be local", creating lock-in. Plus cost opacity (token burn, caching bugs raising costs 10-20x). SmbOS's local-first, plain-markdown, model-agnostic stance is exactly what that audience says it wants. Borrow combinable triggers and a "routine = saved config" object; surface token/cost burn honestly and show remaining budget plainly. Bundled in paid plans; daily caps (Pro 5, Max 15).
- **Trigger.dev:** OSS durable background-job runtime; Waitpoint tokens pause a run indefinitely at zero idle cost until a human completes the token via callback URL/SDK/React hook. This is the canonical HITL primitive and the model for the plate handoff: a run pauses, sits on the plate, resumes exactly where it left off, no compute burned while waiting. "Idle waiting is free" is reassuring budget framing. Subscribe/stream a background run to the foreground = click an In-flight session to stream live output. Free tier + managed/self-host.
- **ChatGPT Tasks + agent:** Consumer scheduled prompts (push/email delivery) + a computer-use agent. Plain-language scheduling ("every weekday at 7am, your timezone") is the bar to match in "Coming up." Deliver results where the human is (a "here's what got done overnight" push/digest). Avoid the 10-task cap trap: model a schedule as one object with many fire times. Add conditional/skip logic so scheduled runs don't fire pointless work (ChatGPT Tasks' #1 complaint: repetitive useless notifications).
- **Cosine Genie / Devin (background SWE agents):** Delegate a ticket, async report-back, human reviews the PR (the same trust contract as SmbOS's pick-up loop). Borrow "review the artifact, not the work" (every run ends with a concrete reviewable output on the plate, not just "done") and "return-when-blocked" (a specific question on the plate with enough context to answer in one step). Devin's "scheduled chores" framing names recurring upkeep SOPs plainly in "Coming up."

### Local-first command-center dashboards (the most direct surface analogues)
- **Claude Code Agent View (first-party):** A local TUI dispatching/supervising many background Claude Code sessions, state-grouped (Ready for review, Needs input, Working, Completed) with needs-you pinned to top. A supervisor daemon keeps sessions alive without a terminal; state persists on disk; sessions resume after sleep. Peek (Space) shows the blocking question + an editable suggested reply without attaching; two-tier glyphs separate TASK state (color) from PROCESS liveness (shape: alive / exited-but-resumable / sleeping). Haiku-generated one-line row summaries refresh every 15s. PR status is a first-class colored signal. Permission-mode gating refuses unwatched bypass-permission until accepted once. This is the strongest direct mirror of SmbOS's board. Borrow: the two-tier glyph (separate task state from process liveness, directly relevant to the inflight-session-liveness branch); peek + reply without attaching, with a prefilled suggested reply; Haiku one-line "what it's doing right now" summaries; the deliverable as the clickable pickup point; persist state so the dashboard survives restarts and resumes exited sessions ("process exited, resumes on pickup" not a scary "failed").
- **claude-code-command-center (amahpour):** OSS web dashboard with nearly the IDENTICAL stack to SmbOS's (FastAPI + uvicorn + SQLite/FTS5 + a JSONL file-watcher + vanilla JS + xterm.js, hook-event ingestion, WebSocket fan-out). Five session states incl. an explicit "Stale (>5min no activity)" liveness heuristic; per-session cost/token tracking; auto-links Jira/PRs to sessions. This confirms SmbOS's architecture is the right shape and that the differentiator MUST be the SOP/do-loop layer, not the transcript-viewing plumbing. The "Stale >5min" heuristic is directly useful for the liveness work (distinguish "in flight and progressing" from "in flight but stalled").
- **CRM-CLI (crmcli.sh):** Local-first personal CRM (single Go binary, local SQLite/FTS5, MCP server) where you narrate a meeting in natural language and Claude logs the interaction and creates follow-ups, maintaining a per-contact "living dossier." Validates SmbOS's exact bet (plain local files + MCP + an LLM doing the structured work) for the terminal-native solo operator. "Tell Claude what happened, it logs it and creates the next step" is the do-loop in miniature; the living-dossier pattern suggests an auto-maintained "current state / last run notes" block per SOP so a freshly picked-up session is primed without re-reading history.
- **Superpowers (obra/superpowers):** A Claude Code plugin shipping composable markdown "skills" the agent reads before acting, enforcing a gated brainstorm to plan to execute to review pipeline. The strongest direct peer (same delivery vehicle, same plain-markdown-instruction substrate). Confirms "procedures as plain markdown the agent reads before acting" is a proven, loved pattern; SmbOS's edge is the owner-facing dashboard + do-loop + scheduling on top. Gating as trust (block execute until a plan is approved) maps to inserting a plan/approval gate before unattended action; the brainstorm gate produces a human-legible artifact, which the Prepare verb should surface ("what this run will do").
- **Raycast / Homepage / tmux+Zellij (adjacent UX lessons):** Raycast's "search to act" pivot is the SmbOS thesis in launcher form (make SOPs runnable in one gesture; mark which are runnable-by-agent vs reference-only). Its lock-in/closed/cloud/no-BYO-key complaints are precisely SmbOS's differentiators (anti-Raycast positioning: your data is just files). Zellij's persistent always-visible "what mode am I in / what keys are available" bar is the discoverability lesson: never make the operator remember what they can do; surface the available verbs in context on each card. tmux/Zellij session-persistence-across-disconnect is the durability model for In flight.

---

## Summary comparison framing

SmbOS sits at the intersection of three converging clusters: (1) local agent-session command centers (Agent View, command-center, Conductor, Claude Squad), (2) procedures-as-plain-files-plus-LLM (Superpowers, Backlog.md/GSD, Runme, CRM-CLI), and (3) durable HITL control surfaces (Agent Inbox, HumanLayer CodeLayer, Inngest, Trigger.dev, Relay). HumanLayer's CodeLayer is the single closest architectural twin (local Go daemon + SQLite + REST + desktop center + CLI orchestrating Claude Code across worktrees) and fights the same launchd/liveness battle. Whale is the closest thesis competitor (SOPs as agent context) but does it as a cloud add-on. The market has commoditized the plumbing; the open lane is a local-first, plain-markdown, plain-language command center over a solo operator's recurring BUSINESS SOPs (not SRE/SOAR, not enterprise governance, not a thin cloud wrapper) with the do-loop closed: task lands to human picks up to primed session runs to completion reports back, plus scheduling.
---

# Appendix: per-tool detail


## Cluster: AI DevOps / agent-ops platforms (incl. the named example)

_The cluster is converging hard on one shape that SmbOS is squarely inside: a LOCAL control plane that makes parallel, partly-autonomous agent work legible and trustworthy, with git worktrees for isolation and a board/command-center as the human surface. Cline Kanban, aidevops's mission/pulse, and Devin Desktop independently landed on the same primitives, per-task isolation (worktree/VM/Space), a recurring supervisor or board that surfaces what needs the human, scoped diffs for review, and cost/budget metering. Three patterns recur and are the most borrowable for SmbOS: (1) Legibility primitives, read/unread dots (Devin), message-range-scoped diffs with inline comments routed back to the agent (Cline), and trace-per-run dashboards (Langfuse) all answer 'what did this autonomous thing just do, and does it need me?', which is exactly SmbOS's 'In flight' / 'Recent runs' job. (2) Graduated trust, every serious tool offers tunable oversight (Cline's per-step -> shift+tab auto-approve -> YOLO, approval hooks; aidevops's cross-provider verification gate on destructive ops), arguing SmbOS's single launch-permission Setting should become a ladder, and that irreversible actions deserve a hard gate. (3) Budget as a first-class plain-language surface, ACUs (Devin) and aidevops's append-only ledger with an 80%-pause threshold both make spend legible per task; SmbOS's budget Setting should show per-run cost and burn-rate, not tokens. The strongest market signal: the universal real-world complaint (Devin's $40-for-nothing full-stack failures, Crush drifting on 50+ file refactors, aidevops's kitchen-sink scope) is that autonomy fails on sprawling tasks and succeeds on narrow ~1-hour ones. That is SmbOS's wedge: a well-scoped-SOP-per-task model with human pickup and a plain-language plate is the antidote to both the legibility gap and the scope-blowup failure mode that plague every tool here, and SmbOS's plain-words copy + SOP discipline is differentiation none of these terminal/enterprise tools have._

### aidevops (aidevops.sh) - Open-source CLI framework that turns OpenCode/Claude Code into an autonomous, self-supervising DevOps team running missions across code, infra, and business ops.

- **Category:** AI DevOps / agent-ops framework (closest analogue to SmbOS)  
- **URL:** https://aidevops.sh  
- **Relevance:** high  
- **How it works:** Local-first bash + TypeScript (Bun) framework layered on top of OpenCode (and Claude Code). Core loop is a 'Pulse supervisor' that runs every 2 minutes via launchd and acts as an LLM-driven manager: it checks capacity (circuit breaker sizes worker slots from available RAM), merges green PRs, dispatches workers to failing/stuck PRs, advances missions, triages quality findings, and syncs TODOs to GitHub issues. Work is structured Mission -> Milestone -> Feature -> Worker. A user types `/mission "goal"`; it decomposes into milestones + GitHub issues tagged `mission:mNNN`; each worker agent runs in its own isolated git worktree and branch; agents coordinate through a SQLite WAL-mode 'mailbox' (agent registry with role/branch/worktree/heartbeat, inbox/outbox, broadcasts). Mission state persists as JSON committed to the repo so any session can resume. Budget is an append-only cost ledger that routes cheap work to small models and pauses missions at an 80% spend threshold. Critical ops (force-push, prod deploy, DROP DATABASE) require cross-provider verification by a second AI before executing.  
- **Value prop:** Closes the gap between 'the model can probably do this' and 'the work is actually done, verified, safe, and worth the cost' for a solo operator, by giving agents context, routing, git hygiene, budget, observability, and follow-through so they run 24/7 with minimal human babysitting.  
- **Tech/stack:** Bash scripts + TypeScript on Bun; MCP servers; SQLite (WAL) for mailbox; launchd for the pulse cron; local-first CLI coordinating cloud services. OSS, MIT license. ~270 GitHub stars, 50 forks, 20k+ commits. Built primarily on OpenCode, Claude fully supported via OAuth.  
- **Pricing:** Free, open-source (MIT). Model/API costs (OpenAI, Anthropic) are the user's separate expense; forum notes Claude Max ~$200/mo discussed, with cheaper-model routing as the mitigation.  
- **Target user:** Technical solo operators and small teams who 'vibe-code' but find DevOps hard; people who want AI doing real work across code, infra, SEO, marketing without every job becoming a long fragile chat. Nearly identical persona to SmbOS's real user.  
- **Key features:**
    - Pulse supervisor: LLM-driven 2-minute autonomous management loop (merge/fix/dispatch/advance/triage)
    - Missions: high-level goal -> milestones -> features -> GitHub issues, state persisted as JSON in repo
    - Parallel worktrees: one isolated git worktree + branch per worker, no merge conflicts
    - SQLite mailbox: agent registry + inbox/outbox/broadcasts for inter-agent coordination
    - Budget tracker: append-only cost ledger, model-tier routing, 80% pause threshold, /budget-analysis burn-rate report
    - Stuck-worker detection via 'struggle ratio' (messages/commits): >30 = struggling, >50 = thrashing; kills workers 3h+ with no PR
    - Multi-model verification gate on destructive operations
    - Runners: named persistent agent identities with own AGENTS.md + memory namespace; cron-schedulable
    - 90+ slash commands, 12 primary agents, 2050+ subagent markdown files, 30+ service integrations
    - mission-dashboard-helper.sh visual progress tracking; observability plugin logs all LLM requests
    - Skill import system with automatic security scanning (Cisco Skill Scanner, .pth audits)
- **User feedback:**
    - (positive) Cloudron forum thread (forum.cloudron.io/topic/14688): Enthusiastic small-audience reception; users like that being open-source lets them 'ask the AI what it all does and whether it's safe.' One user: 'Wow that's great stuff man.' Cost-consciousness around Claude Max $200/mo was raised, with cheaper-model routing as the answer.
    - (mixed) GitHub repo description / traction (marcusquinn/aidevops): Real but modest traction (~270 stars). Enormous scope (90+ commands, 2050+ subagent files, 30+ integrations, 1480+ helper scripts) reads as powerful to fans but is a clear kitchen-sink/complexity risk; positioning copy ('SOTA everything', '100x developer superpowers', 'money-making magic') is hype-heavy.
- **Borrowable for SmbOS:**
    - The Pulse pattern: a lightweight recurring LLM-driven supervisor loop that triages the plate (merge-ready, stuck, queued, budget) instead of the human polling. SmbOS already has cron + a watchdog; an LLM 'manager pass' that decides what to surface on 'On your plate' is a natural fit.
    - Struggle-ratio heuristic (messages/commits, time-in-flight) to auto-flag a stuck in-flight session and surface it on the plate as 'this one is thrashing, look at it' rather than letting it run silently.
    - Budget as a first-class, plain-language surface: append-only cost ledger + 'pause at 80%' threshold maps directly to SmbOS Settings (budget) and the owner-facing copy. Show burn-rate, not raw tokens.
    - Mission state persisted as committed JSON so any session resumes mid-work, parallels SmbOS's session-liveness/recovery work (put-back / done / dismiss).
    - Cross-provider verification gate before destructive/irreversible actions, a concrete trust mechanism for SmbOS's 'launch permission' setting.
    - Mission -> Milestone -> Feature decomposition as the shape of a multi-stage SOP run (maps to /sop-work's plan/build/review/ship stages).

### Devin / Devin Desktop (Cognition) - Cloud-hosted autonomous 'AI software engineer' plus a desktop 'agent command centre' for coordinating fleets of local and cloud agents across a team's projects.

- **Category:** Enterprise autonomous coding agent + agent command center  
- **URL:** https://devin.ai  
- **Relevance:** high  
- **How it works:** Devin runs as a cloud agent you assign tasks to (via Slack, web, or API); each task spins up an isolated sandboxed VM with editor, terminal, and browser, and the agent plans, codes, runs CI, and opens a PR. Devin Desktop (launched June 2026) is the management layer: a full code editor plus a dashboard 'unified command centre for engineering teams managing fleets of AI agents' coordinating agents across projects, codebases, tasks, and environments. It adds 'Spaces' (group agents by project, share context across sessions/PRs/files/tasks), read/unread indicators (orange dot = unread updates, clears on open), one-click 'Start a new session with this prompt,' and 'Devin Local' (a local agent with subagents). It implements the open Agent Client Protocol (ACP) so third-party agents (Codex, Claude Agent, OpenCode) run inside the same command center with shared Spaces context. An 'Agent Router' (incoming) auto-directs tasks to the cheapest/most-efficient agent. Work is billed in ACUs (~15 min of autonomous work each).  
- **Value prop:** Offload well-scoped engineering tasks to autonomous agents and manage many of them from one governed command center, so a team (or solo operator) supervises a fleet rather than driving each agent by hand.  
- **Tech/stack:** Cloud-hosted, sandboxed per-task VMs; closed source. Desktop app for the command center. ACP as an open interop standard. Reports 67% PR merge rate (up from 34%) and that Devin writes ~89% of its own commits.  
- **Pricing:** Core: pay-as-you-go from $20, ACUs $2.25 each, up to 10 concurrent sessions, unlimited users. Team: $500/mo incl. 250 ACUs at $2.00 (~62.5 hrs/mo), unlimited concurrency. Enterprise: custom, VPC deploy + SSO + governance.  
- **Target user:** Engineering teams and enterprises (regulated industries, data-residency needs); also solo/small via the pay-as-you-go Core plan. Positioned upmarket vs SmbOS but the command-center UX is directly relevant.  
- **Key features:**
    - Devin Desktop: editor + dashboard 'command centre' for local and cloud agents
    - Spaces: group agents by project, share context across sessions/PRs/files/tasks
    - Read/unread session indicators (orange dot) so you can scan a fleet for what changed
    - Agent Client Protocol (ACP): open standard to run third-party agents alongside Devin
    - Agent Router (incoming): auto-route tasks to cheapest/most-efficient agent/model
    - ACU-based metering (~15 min autonomous work per ACU) with per-task cost visibility
    - Up to 10 concurrent sessions (Core) / unlimited (Team); enterprise VPC deploy, SAML/OIDC, teamspace isolation
- **User feedback:**
    - (mixed) frontierai.substack.com 'One month of using Devin': Great at narrowly-scoped ~1-hour tasks (pie chart formatting, API edge case, Redux frontend) costing $2-10 each; disastrous on a full-stack DB+API+frontend task that consumed ~20 ACUs ($40) with zero usable output and got stuck looping on linter errors. Verdict: 'If this was an engineer we'd hired, we would not have kept them on the team.' Larger tasks burn disproportionately more ACUs without being proportionally harder.
    - (negative) The Register (theregister.com, Jan 2025) citing Answer.AI trial: Early testers logged '14 failures and just 3 successes' across 20 tasks; original SWE-bench ~13.86% unassisted. Wide gap between benchmark numbers and real-world satisfaction.
    - (mixed) Stanford / sitepoint production reviews (2025): No long-term memory across sessions; reasoning bounded by context window; introduces technical debt (verbose solutions, redundant null checks, diverges from codebase conventions). Improved materially over 2025-2026 (67% merge rate) but still junior-level for isolated bugs, not full-stack.
- **Borrowable for SmbOS:**
    - Read/unread orange-dot indicators per session: a dead-simple legibility primitive for SmbOS's 'In flight' list, mark a picked-up session that has new output/needs-you and clear it on open.
    - 'Command centre' framing of coordinating many sessions across projects validates SmbOS's dashboard direction; Spaces (shared context grouped by project) maps to grouping SOP runs by client/project.
    - ACU-style metering surfaced per-task ('this run cost X, ~Y minutes of work') for SmbOS's budget/Recent-runs view, in plain language.
    - The hard lesson on scope: agents shine on well-scoped ~1-hour tasks and fail on sprawling ones. SmbOS SOPs should encourage narrow, single-component task framing on the plate, and warn/cap when a run balloons in cost.
    - One-click 'start a new session with this prompt' for re-running a prior plate task is a cheap, high-value affordance for Recent runs.

### Cline CLI 2.0 + Cline Kanban - Open-source terminal coding agent that becomes a local 'agent control plane,' with a browser Kanban board that runs many CLI agents in parallel, each in its own git worktree.

- **Category:** Local agent control plane / multi-agent orchestration board  
- **URL:** https://cline.bot/cli  
- **Relevance:** high  
- **How it works:** Cline CLI 2.0 (Feb 2026) brings the Cline agent from an IDE sidebar to the terminal with long-running work, parallel sessions, and automation-first headless usage, while keeping an interactive review path. Oversight is tunable: `-y` (YOLO) auto-approves and streams to stdout; otherwise approve each step or shift+tab to set auto-approve level; an approval-hooks system gates every tool call with a script (`--hook-command ./policy.sh`) to allow safe reads, require approval on writes, block prod-touching commands; `CLINE_COMMAND_PERMISSIONS` restricts allowed shell commands. Background/scheduled work via `cline schedule create` (cron agents for standups, dependency checks, nightly triage) and a 'Zen mode' to fire a task into the background and reclaim the terminal. Cline Kanban (`cline --kanban` -> http://localhost:3484) is a local web app: drop cards, hit play, watch many agents work in parallel, each in its own ephemeral git worktree + dedicated terminal; review a real-time diff scoped to message ranges (not one cumulative blob); comment inline on any diff line and feedback goes straight back to the agent; linked cards auto-start when their predecessor lands (dependency pipelines without scripts). Powered by the open-source Cline SDK agent runtime.  
- **Value prop:** Make parallel, long-running, partly-autonomous agent work legible and reviewable from one local board, solving the two real bottlenecks (waiting on inference, merge conflicts from parallelism) without locking you to a vendor or sending code to the cloud.  
- **Tech/stack:** Open-source agent runtime SDK; local web app (Kanban) on localhost:3484; git worktrees for isolation; cron for scheduling; BYOK hosted + local models. Free CLI (shipped with free Kimi K2.5/M2.5 access at launch).  
- **Pricing:** CLI and Kanban are free/open-source; bring your own model API keys (free first-party model access offered at launch). Local hosting, no per-seat board fee surfaced.  
- **Target user:** Developers wanting to run multiple coding agents in parallel locally with real review control and no vendor lock-in; strongly overlaps SmbOS's terminal-dwelling solo founder.  
- **Key features:**
    - Kanban board of agent tasks as cards; play to run many agents in parallel
    - Each card = own ephemeral git worktree + dedicated terminal (auto-managed, no merge conflicts)
    - Real-time diff scoped to message ranges, with inline line-level comments routed back to the agent
    - Dependency chains: linked cards auto-start when predecessor lands
    - Tunable oversight: per-step approval, shift+tab auto-approve, -y YOLO mode
    - Approval hooks: script-gated tool calls (allow reads / require approval on writes / block prod)
    - Cron-scheduled background agents (cline schedule create) + Zen background mode
    - Local-first (localhost board), BYOK across hosted + local model runtimes; open-source Cline SDK runtime
- **User feedback:**
    - (positive) testingcatalog.com + Latent.Space [AINews] coverage: Builders called Cline Kanban the likely default multi-agent interface because it tackles the two practical bottlenecks: inference-bound waiting and merge-conflict-heavy parallelism. The per-card worktree + real-time scoped diff + inline review combination drew strong praise.
    - (positive) cline.bot blog / DevOps.com control-plane framing: The control-plane positioning (terminal as the place agents execute and get governed) resonated; approval hooks and command-permission env vars are seen as the right primitives for trusting background agents.
- **Borrowable for SmbOS:**
    - The Kanban board as a direct analogue to SmbOS's plate columns ('On your plate' / 'In flight' / 'Coming up' / 'Recent runs'). Cline validates the local-web-board-over-parallel-agents UX; SmbOS could let queued cards auto-start when a dependency lands.
    - Diff scoped to message ranges + inline comments routed back to the agent: a powerful 'make autonomous work legible + correctable' pattern for SmbOS in-flight sessions, review the delta a session produced and reply inline rather than re-opening the whole session.
    - Tunable oversight ladder (per-step approval -> shift+tab auto-approve -> YOLO) is a cleaner model for SmbOS's single 'launch permission' Setting; offer graduated trust, not a binary.
    - Approval hooks as script-gated tool calls (allow reads / require approval on writes / block prod) is a concrete, ownable trust mechanism for SmbOS's launch-permission/budget guardrails.
    - Dependency chains between cards map to SmbOS multi-stage SOP work (plan->build->review->ship auto-advancing).
    - Cron-scheduled background agents with a 'reclaim your terminal' background mode matches SmbOS's scheduled cron runs and session-liveness model.

### Charm Crush - Glamorous open-source single-binary terminal AI coding agent (successor to OpenCode) with multi-provider model switching, LSP context, and MCP extensibility.

- **Category:** Terminal-native AI coding agent (single-agent, polished TUI)  
- **URL:** https://github.com/charmbracelet/crush  
- **Relevance:** medium  
- **How it works:** A single Go binary built on Charm's Bubble Tea TUI framework. CLI entry initializes a ConfigStore and an app.App orchestrator; user input flows from the TUI to an AgentCoordinator.Run which delegates to a SessionAgent backed by Charm's 'fantasy' multi-provider agent abstraction. BYOK across ~7 providers (OpenAI, Anthropic, etc.) with mid-session model switching that preserves context. Pulls extra context via LSP (Language Server Protocol) and connects to tools/resources via MCP. Project-level config via a generated CRUSH.md. It's a single interactive agent in a beautiful terminal UI, not a multi-agent supervisor/control plane.  
- **Value prop:** The most enjoyable, prettiest terminal coding agent: serious model-provider flexibility with LSP-enhanced context and MCP extensibility, in one portable binary across macOS/Linux/Windows/even Android/FreeBSD.  
- **Tech/stack:** Go + Bubble Tea TUI; 'fantasy' agent abstraction; LSP + MCP; single binary, BYOK; open-source (Charm). Successor to / rebrand from the OpenCode project after a contested acquisition.  
- **Pricing:** Free, open-source; BYOK API costs only.  
- **Target user:** Individual developers who live in the terminal and value UX polish and model flexibility; single-operator workflows.  
- **Key features:**
    - Single Go binary, broad cross-platform support
    - Beautiful Bubble Tea TUI with inline syntax highlighting and clear diff windows
    - Mid-session model switching across multiple providers, context preserved
    - LSP-enhanced context gathering
    - MCP resource/tool access
    - Project-level config via CRUSH.md
- **User feedback:**
    - (positive) Hacker News thread (news.ycombinator.com/item?id=44736176): Praised as 'ridiculously pretty,' 'the most enjoyable to use so far' vs Claude Code/Aider/OpenCode; clear, schematic Go codebase seen as a blueprint for agent architecture; LSP integration appreciated.
    - (negative) Hacker News thread (same): Concrete gripes: no up/down chat history, broken copy/paste, terminal crashes on Ctrl+C, 'open editor' does nothing, can't mix models (Haiku for simple + Sonnet for complex), requires API keys instead of Claude Pro subscription, weaker planning than Claude Code (single commands not batched), and it drops 'unexplained junk binary files' plus a low-value default CRUSH.md.
    - (mixed) aicoolies / vibecodinghub reviews: Solid planning loop for small-to-medium tasks but drifts on multi-day refactors spanning 50+ files; documentation lags the code; rougher onboarding than Cursor.
- **Borrowable for SmbOS:**
    - Polish-as-trust: the HN reaction shows that for terminal tools, UX craft (clear diffs, inline highlighting) materially drives adoption and perceived trust, reinforcing SmbOS's rule that dashboard states need real screenshot QA.
    - The cautionary tale of mid-session model switching being a top wished-for feature, and junk-file/empty-config-file generation eroding trust: SmbOS should never litter the user's repo and should keep generated SOP/config files genuinely useful from first creation.
    - 'Drifts on multi-day refactors spanning 50+ files' reinforces SmbOS's bias toward narrow, well-scoped SOP tasks over open-ended sprawl.
    - A single generated project config file (CRUSH.md / AGENTS.md) as the agent's instruction anchor parallels SmbOS's ~/sops + SessionStart-injected protocol; the lesson is make that anchor high-value, not boilerplate.

### AI agent observability dashboards (Langfuse, AgentOps, LangSmith, Laminar, Sentry, Arize) - The observability/'AIOps' layer for agents: dashboards that trace agent runs, model calls, tokens, cost, and tool invocations, increasingly on the OpenTelemetry gen_ai standard.

- **Category:** Agent observability / AIOps (monitoring + traces, not orchestration)  
- **URL:** https://langfuse.com/integrations/frameworks/vercel-ai-sdk  
- **Relevance:** medium  
- **How it works:** You instrument an agent (Vercel AI SDK, OpenAI Agents SDK, LangChain/LangGraph, Pydantic AI, etc.) and the platform captures traces of each run as nested spans: model calls, tool invocations, latency, tokens, and cost. The Vercel AI SDK ships built-in OpenTelemetry telemetry; Langfuse and others consume those OTel gen_ai semantic-convention spans, so instrumentation is often near-zero (e.g., Langfuse's observe() wrapper + propagateAttributes() to attach session/user metadata). Dashboards then show agent runs, duration, total model calls, tokens consumed, tool calls, plus eval harnesses (Langfuse) and prompt/version management. Sentry auto-instruments most major frameworks. This cluster monitors and evaluates autonomous work; it does not dispatch or supervise it.  
- **Value prop:** Make autonomous agent behavior legible and debuggable after the fact: see exactly what each run did, what it called, how long it took, and what it cost, grouped by session and user.  
- **Tech/stack:** OpenTelemetry-based; Langfuse and several others are open-source and self-hostable; SDK integrations across Vercel AI SDK / OpenAI Agents SDK / LangChain. Mostly cloud + self-host options.  
- **Pricing:** Varies: Langfuse open-source/self-host + paid cloud tiers; LangSmith/Arize/Datadog commercial; Sentry usage-based. (Cluster-level, not a single product.)  
- **Target user:** Developers and teams shipping agentic apps who need monitoring, debugging, cost tracking, and evals; complements rather than competes with SmbOS's orchestration role.  
- **Key features:**
    - Trace-per-run with nested spans (model calls, tool calls, latency, tokens, cost)
    - Session and user grouping of traces
    - Pre-built dashboards: runs, duration, total model calls, tokens, tool invocations
    - OpenTelemetry gen_ai semantic conventions as the emerging interop standard
    - Eval harness + versioned prompt management (Langfuse, LangSmith)
    - Near-zero-code auto-instrumentation (Sentry; AI SDK built-in telemetry)
- **User feedback:**
    - (mixed) laminar.sh / aimultiple 2026 rankings: Langfuse favored for prompt iteration + eval workflows and being open-source/self-hostable; the broader space is crowded and fragmenting across distinct approaches (Sentry, LangSmith, Langfuse, Arize, Datadog), with OTel gen_ai conventions cited as the consolidating standard that reduces lock-in.
- **Borrowable for SmbOS:**
    - Trace-per-run as the data model for SmbOS 'Recent runs': capture each session/SOP run as a structured trace (steps, tool calls, duration, cost) so the owner can see what an autonomous run actually did, in plain language.
    - Session/user grouping of traces maps to grouping SmbOS runs by SOP and by client/project for a legible history.
    - Standardize on OpenTelemetry gen_ai conventions for SmbOS run telemetry so the dashboard could later ingest from any agent runtime (Claude Code, OpenCode) without bespoke parsing.
    - A lightweight eval/quality signal on completed runs ('did this run meet the SOP's acceptance criteria?') would strengthen the 'reports completion back' step of SmbOS's do-loop beyond a binary done/not-done.



## Cluster: Autonomous + assistive coding agents

_Across this cluster, autonomy is cheap but trust is the scarce resource, and the tools that win solo/technical users buy trust with legibility primitives SmbOS can copy wholesale. Four recurring mechanisms: (1) an immutable, inspectable record of what the agent did - OpenHands' append-only EventLog, Amp's shareable Threads, Aider's one-commit-per-edit git history; SmbOS's 'Recent runs' and 'in flight' panels should be backed by exactly this, not a bare status field. (2) Graduated human-in-the-loop control rather than a binary on/off - Cline's risk-classified per-step approval, Roo's permission-scoped modes, Devin's confidence rating that tells you when to intervene; SmbOS's single 'launch permission' Setting should become per-SOP capability scopes (auto-run safe, approve destructive). (3) Hard cost legibility - the loudest complaints in the whole cluster are cost 'blackholes' (Factory) and unpredictable credit burn (Amp, Cursor cloud agents); Cline's live token readout + 'Spend Limit Reached' guard is the gold standard SmbOS's budget setting should match with a plain-language hard stop. (4) Scoping is the real differentiator - every tool is 'powerful but uneven, depends on scoping' (Devin, Factory), and tight upfront scoping with clear done-criteria is what separates a good run from a day-long hallucination spiral. That scoping discipline is precisely what SmbOS's SOP library encodes by design, which is the cluster's clearest gap and SmbOS's sharpest wedge: it ships the scoping layer these autonomous agents make the user reinvent per task. Finally, a cautionary contrast: Cursor's agent-first pivot drew real backlash for killing flow state by forcing constant context-switching to review parallel agents - validating SmbOS's plain-language, consolidated single-command-center framing over scattering the operator across dashboard, IDE, and Slack._

### Devin (Cognition) - Fully autonomous cloud 'AI software engineer' you delegate scoped tasks to, which plans, codes in a sandbox VM, and opens a PR.

- **Category:** Autonomous cloud coding agent  
- **URL:** https://cognition.ai/blog/devin-annual-performance-review-2025  
- **Relevance:** high  
- **How it works:** You assign a task in plain language (from Slack, a GitHub issue, or the web app). Devin produces a plan with an explicit confidence rating (low/medium/high); if confidence isn't high it asks clarifying questions or digs deeper. It then executes inside a sandboxed VM with its own terminal, browser, and editor, writes code, runs tests, debugs, and opens a PR for human review. It's delegation-first, not collaboration: it works while you're away and reports back when done or blocked. Best results come from small, well-scoped tasks (tests, lint fixes, first-draft PRs); it handles upfront scoping well but not mid-task requirement changes. Billed in ACUs (Agentic Compute Units) measuring VM time + model inference + bandwidth.  
- **Value prop:** Delegate backlog-sized engineering tasks end-to-end and get back a reviewable PR without babysitting a session.  
- **Tech/stack:** Closed-source cloud SaaS. Sandboxed cloud VMs per task. Model-backed (frontier models). Cloud-only, no local/OSS option.  
- **Pricing:** Team ~$500/mo per seat + ACU consumption; Enterprise quote-based (SSO, audit logs, SOC 2). Reported revenue jump $37M→$492M ARR May 2025→May 2026.  
- **Target user:** Engineering teams (and well-funded startups) wanting to offload scoped backlog tasks to an autonomous agent; $500/mo Team tier skews enterprise.  
- **Key features:**
    - Confidence rating on every plan (low/medium/high) that signals when a human should intervene
    - Sandboxed VM with terminal + browser + editor per task
    - Slack/GitHub-issue task intake (assign like a coworker)
    - Knowledge playbooks + DeepWiki entries you feed it to scope work
    - Human review gate at PR/merge: nothing reaches prod without approval
    - ACU consumption metering for cost
- **User feedback:**
    - (negative) The Register forums (Jan 2025) / testers: 'First AI software engineer is bad at its job': tasks that looked straightforward took days; Devin got stuck in dead-ends and produced overly complex, unusable solutions.
    - (negative) Evaluation cited across reviews (Railway deploy test): Pushes forward on impossible tasks: spent over a day trying approaches that didn't work while hallucinating non-existent platform features instead of stopping.
    - (negative) TeamBlind / dev community: Original launch demo widely called fake/overpromised; significant reputational backlash for underdelivering vs the demo.
    - (mixed) Scott Logic blog (Oct 2025) developer writeup: Workflow lessons were as valuable as the code: working with the agent is a time-management and scoping discipline; it rewards tight upfront scoping and punishes mid-task changes.
- **Borrowable for SmbOS:**
    - Attach an explicit confidence rating to each picked-up task/run and surface it on the plate, so the human knows when to step in vs let it run - a legibility cue SmbOS's 'in flight' panel lacks.
    - Codify the 'small, well-scoped task' discipline into the SOP/importer: an SOP should produce one tight, self-contained task with clear done-criteria, not an open-ended mission.
    - Frame the relationship as delegate-and-review: keep the human review/approval gate explicit at completion ('reports completion back') rather than auto-merging.
    - 'Knowledge playbook' pattern = your SOP library: pre-load durable context (repro steps, commands, conventions) the agent reuses across runs, which is exactly the ~/sops premise.
    - Detect and surface the 'pushing on an impossible task' failure mode: a budget/time guard that flags a stuck in-flight session for the human instead of burning ACUs/tokens.

### OpenHands (formerly OpenDevin, All Hands AI) - Open-source autonomous software-engineering platform with a tiny event-driven core, runnable fully local or as persistent cloud agents.

- **Category:** Open-source autonomous coding agent / SDK  
- **URL:** https://www.openhands.dev/  
- **Relevance:** high  
- **How it works:** Core is deliberately small (CodeAct paradigm): a stateless Agent emits Actions; a Conversation runs the loop and stores an append-only EventLog; a Workspace (local process or Docker container) executes Actions and returns Observations; an LLM wrapped by LiteLLM gives provider portability. Every action and observation is an immutable event, enabling deterministic replay, pause/resume, and debugging. Tasks enter from GitHub issues/PRs, Slack, PagerDuty incidents, CI/CD, or manual prompts in the 'Agent Canvas' workspace. The 2025 Software Agent SDK split agent logic, execution environment (local Docker or remote cloud sandbox), and interface (CLI/GUI/REST) into replaceable modules. Supports multi-agent delegation, microagents (specialized focused agents), and parallel agents. Cloud variant = 'agents that don't stop when you do.'  
- **Value prop:** A fully inspectable, self-hostable autonomous agent you can run locally, in CI, or as persistent cloud workers - no vendor lock-in.  
- **Tech/stack:** Open source (MIT). Python core, LiteLLM for model portability, Docker sandboxes. Local OSS, cloud, or self-hosted enterprise. Model-agnostic (Claude, Gemini, custom).  
- **Pricing:** Individual: free/OSS. Team: cloud backend + shared org features. Enterprise: custom with governance controls.  
- **Target user:** Developers and teams who want OSS, self-hosted, auditable autonomous agents; researchers; enterprises needing data-never-leaves-VPC.  
- **Key features:**
    - Append-only EventLog of every Action/Observation enabling deterministic replay + pause/resume
    - Local Docker sandbox OR remote cloud sandbox, swappable
    - Microagents: small specialized agents for focused tasks
    - Multi-entry task intake (GitHub, Slack, PagerDuty, CI/CD)
    - Agent Canvas: central workspace showing conversations + automation status
    - Budget controls, RBAC, and audit trails (enterprise)
- **User feedback:**
    - (positive) arXiv OpenHands paper / DEV Community deep dive: The tiny-core, event-stream architecture is praised as flexible and powerful; immutable event log makes runs debuggable and replayable, a trust win.
    - (mixed) mgx.dev analysis: Powerful generalist agent but the Docker-sandbox setup and operational complexity are a barrier for casual users; reliability varies by task.
- **Borrowable for SmbOS:**
    - Append-only event log per run is the strongest borrowable pattern: SmbOS's 'Recent runs' and 'in flight' panels would be far more trustworthy if backed by a replayable immutable event stream (every action/observation) rather than just a status field.
    - Pause/resume and deterministic replay let a human inspect exactly what an agent did - directly serves SmbOS's 'make autonomous work legible' goal.
    - Multi-entry task intake (issue/Slack/incident/cron) maps cleanly onto SmbOS triggers; OpenHands shows a clean way to normalize many sources into one plate.
    - Microagents = specialized SOP-scoped agents: a task picks up the right specialized prompt/agent, mirroring SmbOS's per-task primed Claude session.
    - Swappable local-Docker-vs-cloud-sandbox boundary is a model for SmbOS to keep local-first while allowing heavier scheduled/cron runs elsewhere.

### Aider - Terminal-based, git-native AI pair programmer that maps your whole repo and commits every edit as its own diff.

- **Category:** Assistive terminal coding agent (OSS)  
- **URL:** https://aider.chat/  
- **Relevance:** high  
- **How it works:** Runs in the terminal alongside any editor. A 'Coder' system coordinates LLM ↔ filesystem ↔ git: User Instruction → Coder → LLM → Edit Blocks → File Apply → Git Commit → Response. It builds a compact 'repo map' of the entire codebase so the model understands architecture, not just open files. Git-native: every edit becomes its own commit with a sensible message, so you diff/undo with normal git tools. Architect mode separates planning from editing. Model-agnostic across cloud and local (OpenAI, Anthropic, Gemini, DeepSeek, Ollama, OpenRouter, Bedrock, etc.). Edits land in real files so your editor picks them up live.  
- **Value prop:** Lightweight, transparent, fully-under-your-control AI coding where git is the safety net and audit log.  
- **Tech/stack:** Open source (Apache 2.0), Python. Local-first CLI; BYO API key or local model. Git is the persistence/audit layer.  
- **Pricing:** Free/OSS; you pay only your chosen model's API cost (or $0 with local models).  
- **Target user:** Hands-on developers who live in the terminal and want a transparent, cheap, model-flexible assistant they fully control.  
- **Key features:**
    - Repo map: compact whole-codebase context for the LLM
    - Git-native: one commit per edit, trivially auditable/undoable
    - Architect mode (plan) separate from edit mode
    - Massive model flexibility incl. fully local models
    - Terminal-first, editor-agnostic
- **User feedback:**
    - (positive) Hacker News (item 42702738, 'I use aider to work on the aider code base'): Called 'the tool to benchmark against'; the author dogfoods it on aider's own ~30k-line codebase - strong credibility signal.
    - (positive) Reddit / HN testimonials: 'Glimpse into the future of coding', 'makes software development feel lighter', users report doing more work in less time and tackling things outside their comfort zone.
- **Borrowable for SmbOS:**
    - Git-as-audit-log is the cleanest trust mechanism in the cluster: SmbOS could make every agent run produce a discrete, reviewable, revertable commit so 'Recent runs' maps 1:1 to git history the user already trusts.
    - The 'repo map' = a pre-built context artifact; SmbOS's SOPs are the analog, but Aider shows the value of an auto-generated structural map the agent always loads.
    - Architect/plan vs edit split reinforces SmbOS's case for a 'Prepare' step before 'Run' on a procedure.
    - One-commit-per-edit granularity is a model for legible, undoable autonomous work - favor many small reviewable units over one big opaque change.
    - Radical model flexibility (incl. local) is a positioning lesson: terminal-native solo founders value control and cheapness; SmbOS's local-first stance aligns.

### Cursor (Agent Mode + Background/Cloud Agents) - AI-native editor that evolved into an agent-first control center running parallel cloud agents that each open a PR.

- **Category:** Assistive IDE + autonomous background agents  
- **URL:** https://cursor.com/docs/agent/agents-window  
- **Relevance:** high  
- **How it works:** In-editor Agent Mode does multi-file edits with tool use. Background/Cloud Agents clone your repo into a fresh Ubuntu VM, work on a separate branch with internet access (install packages, run builds/tests), and push a PR when done; trigger with Ctrl+E or via a web app / Slack (@Cursor). Feb 2026 'Computer Use' gives each agent a full desktop+browser so it can open localhost and click through UI to visually verify changes. Cursor 2.0/3 added an Agents Window: a unified panel listing every running agent (its task, target repo, local-vs-cloud), where you click into any session to see chat history + file diffs, redirect it, review each branch separately, and merge when all finish. Runs many agents in parallel across repos.  
- **Value prop:** One control panel to dispatch, watch, redirect, and merge many autonomous coding agents working in parallel.  
- **Tech/stack:** Closed-source commercial (VS Code fork). Cloud agents in isolated Ubuntu VMs. Cloud + local. Frontier models incl. Cursor's own Composer model.  
- **Pricing:** Subscription tiers (Pro and up) plus usage; cloud-agent compute adds cost.  
- **Target user:** Professional developers and teams already in an IDE who want to fan out parallel agent work and review it centrally.  
- **Key features:**
    - Agents Window: single panel of all running agents with task/repo/location and live diffs
    - Parallel cloud agents, each on its own branch → PR
    - Computer Use: agent gets desktop+browser to visually verify UI changes
    - Slack + web app dispatch (assign tasks remotely)
    - Click into any session to inspect, redirect, or merge
- **User feedback:**
    - (negative) Hacker News / InfoQ (Cursor 3 agent-first interface, Apr 2026): Pushback that agent-first abandons the IDE-first identity; one commenter: constantly switching context to review/test agent code is mentally taxing and kills flow state.
    - (mixed) Reddit / community (cost concerns): Divided reception over cost overhead of cloud agents and the move away from hands-on editing toward supervising agents.
    - (mixed) Cursor community forum ('Group Diffs by Agent in Source Control'): Users want diffs grouped by which agent produced them - signal that reviewing parallel-agent output is hard without provenance in the review UI.
- **Borrowable for SmbOS:**
    - The Agents Window is the closest analog to SmbOS's 'In flight' panel - borrow its columns: task that started it, target, local-vs-cloud, live status; and make each in-flight row click-through to the session's history and diffs.
    - Let the human redirect a running session from the dashboard, not just put-back/done/dismiss - a mid-flight steering action.
    - Per-agent provenance on outputs (the forum complaint): tag every change/run with which task/SOP produced it so 'Recent runs' is auditable.
    - Heed the flow-state complaint: SmbOS's plain-language 'on your plate / in flight' framing should minimize context-switch cost - batch reviews, summarize what changed, don't force the user to reconstruct each session.
    - Computer-use visual verification → SmbOS could have a run self-verify its outcome (screenshot/check) and attach evidence to the completion report so the human trusts 'done.'

### Cline - Open-source VS Code coding agent with strict Plan/Act split and per-step human approval on every edit and command.

- **Category:** Assistive IDE coding agent (OSS)  
- **URL:** https://cline.bot/  
- **Relevance:** high  
- **How it works:** Open-source (Apache 2.0) VS Code extension. Plan mode is read-only: it explores the codebase, asks clarifying questions, proposes an approach, changes nothing. Act mode executes step by step, surfacing each file edit as a diff and each command as a preview that you Approve or Reject. Operations are risk-classified: safe reads/builds can auto-approve; destructive commands (rm, DROP TABLE) always require explicit approval ('YOLO Mode' disables guardrails for throwaway work). A shadow git repo checkpoints state after each tool use, so you can restore files-only, discard messages, or both. /newtask distills the conversation into plan/work-done/files/next-steps and starts a fresh context window to manage tokens. MCP + a one-click MCP Marketplace extend it. Every interaction shows token count + estimated cost, with a 'Spend Limit Reached' UI guard.  
- **Value prop:** Autonomous capability with the safety dials maxed: plan first, approve every change, roll back anything, never get a surprise bill.  
- **Tech/stack:** Open source (Apache 2.0), VS Code extension (also SDK/CLI). Local execution. BYO API key or pay-as-you-go Cline Provider. Model-agnostic.  
- **Pricing:** Free OSS; BYO key (~$0.01-$0.10/task) or Cline Provider pay-as-you-go, no subscription tier.  
- **Target user:** Developers who want autonomous agent power but insist on auditability, control, and cost predictability; BYO-key users.  
- **Key features:**
    - Plan/Act mode split (read-only planning vs approved execution)
    - Per-step approve/reject on every edit and command, with risk-classified auto-approve
    - Shadow-git checkpoints with granular restore (files / messages / both)
    - /newtask context handoff (plan, work done, files, next steps) to manage token cost
    - Live per-interaction token + cost display and a hard Spend Limit Reached guard
    - MCP + one-click MCP Marketplace
- **User feedback:**
    - (positive) DeployHQ 2026 guide / Augment Code comparison: Plan/Act split 'prevents the AI rewrote half my project failure mode'; per-step approval keeps users in control - repeatedly cited as the core trust feature.
    - (positive) GitHub / community: Being fully open-source and auditable (you can see exactly what leaves your machine) is a major adoption driver for privacy-conscious devs.
- **Borrowable for SmbOS:**
    - The Plan/Act mode split maps directly onto SmbOS's Prepare → Run; make 'Prepare' an explicit read-only planning state the human can review before the session is allowed to act.
    - Risk-classified approval is the most actionable trust pattern: SmbOS's 'launch permission' Setting could be graduated - auto-run safe SOPs, require an on-the-plate approval for destructive/irreversible ones, never blanket-allow.
    - Shadow-git checkpoints with granular restore = a concrete undo model for autonomous runs; SmbOS could checkpoint before a run and offer one-click revert from 'Recent runs.'
    - Live token + cost readout plus a hard 'Spend Limit Reached' guard is exactly what SmbOS's Settings 'budget' should enforce, with a plain-language stop ('paused: hit your budget').
    - /newtask context-handoff (plan, work done, files, next steps) is a clean template for how a long SmbOS session should report completion back to the plate - structured, skimmable, resumable.

### Roo Code - Open-source VS Code 'team of AI agents' with specialized modes (Code, Architect, Ask, Debug, Custom) that an orchestrator delegates between.

- **Category:** Assistive IDE multi-mode coding agent (OSS)  
- **URL:** https://docs.roocode.com/  
- **Relevance:** medium  
- **How it works:** Open-source VS Code extension (Cline fork lineage). Ships specialized modes, each with its own prompting strategy and tool/permission set: Code (everyday edits + terminal + MCP), Architect (read-only design/planning), Ask (fast answers, no file changes), Debug (logging, traces, root-cause isolation), and user-defined Custom modes. Roo can act as an Orchestrator: rather than one assistant with personalities, it delegates subtasks to the right specialized mode at the right time. Asks permission for every action by default; opt-in Auto-Approve lets it run long stretches autonomously. Permission boundaries are enforced per mode (e.g., Architect can't edit).  
- **Value prop:** A configurable in-editor 'dev team' where each role has scoped permissions, so you can dial autonomy per task type.  
- **Tech/stack:** Open source, VS Code extension. Local execution, model-agnostic, BYO key. MCP-extensible.  
- **Pricing:** Free OSS; pay only your model API costs.  
- **Target user:** Developers who want to tailor agent roles/permissions to their workflow; teams wanting role-scoped autonomy in-editor.  
- **Key features:**
    - Specialized modes with distinct tool/permission sets (Architect is read-only by design)
    - Orchestrator that delegates subtasks to the right mode
    - Fully custom modes (define your own role + permissions)
    - Per-action permission prompts with opt-in Auto-Approve
    - MCP support
- **User feedback:**
    - (positive) DataCamp tutorial / Xebia multi-agent workflow blog: The mode system + orchestrator is praised for keeping complex tasks organized; read-only Architect mode is a natural guardrail.
    - (mixed) Qubika review: Powerful and flexible but the configurability/permission surface has a learning curve; auto-approve can run long without stopping, which cuts both ways.
- **Borrowable for SmbOS:**
    - Permission-scoped modes are a strong model for SmbOS SOPs: each SOP/procedure could declare its capability scope (read-only audit vs file-writing vs external/destructive), and the plate enforces it - safer than one global launch permission.
    - Custom modes ≈ custom SOPs with their own primed prompt + allowed tools; reinforces SmbOS's per-SOP session priming.
    - An orchestrator that routes a request to the right specialized SOP is a natural extension of SmbOS's importer/triage: pick the SOP, then pick the capability scope.
    - 'Auto-Approve runs long without stopping' is a cautionary tale - SmbOS should pair any auto-run with a budget/time tripwire and a check-in, not unbounded autonomy.

### Factory.ai (Droids) - Agent-native platform with role-specialized 'Droids' that run long-horizon 'Missions' across terminal, IDE, and a web dashboard to ship mergeable PRs.

- **Category:** Autonomous + assistive coding platform (cross-surface)  
- **URL:** https://factory.ai/  
- **Relevance:** medium  
- **How it works:** Four specialized Droids: Code Droid (idea → mergeable PR), Knowledge Droid (research/docs), Reliability Droid (incident investigation/debugging), Product Droid (PRDs/feature planning). 'Missions' let you describe a business outcome in natural language and watch multiple Droids plan, execute, and verify over hours or days. Works across surfaces: web dashboard (assign tasks), IDE (VS Code/JetBrains), terminal/CLI (scripting + CI/CD), and Slack/Teams for quick fixes and incident support. Output is PRs intended for immediate merge; human review at the PR. Raised a $150M Series C (Khosla) in 2026.  
- **Value prop:** Describe an outcome, not steps; specialized agents coordinate across your whole toolchain to deliver review-ready work.  
- **Tech/stack:** Closed-source commercial platform. Cloud execution across surfaces. Token-based billing. BYOK option.  
- **Pricing:** Free BYOK tier; Pro $20/mo (20M tokens); Plus $100/mo; Max $200/mo; Enterprise custom (no self-serve).  
- **Target user:** Engineering teams wanting to delegate longer-horizon, cross-repo outcomes; enterprise buyers (custom tier).  
- **Key features:**
    - Role-specialized Droids (Code / Knowledge / Reliability / Product)
    - Missions: outcome-described, multi-Droid, multi-hour/day execution with verify step
    - Cross-surface presence (web dashboard, IDE, terminal, Slack/Teams)
    - CLI for CI/CD automation
    - PR-as-deliverable with human review gate
- **User feedback:**
    - (negative) eesel AI review (aggregating user reports): Code quality issues needing 'significant manual cleanup'; hours spent refactoring file structure and fixing type-safety problems the Droid introduced.
    - (negative) eesel AI / user reports: Token consumption described as a 'blackhole' causing budget overruns; advertised monthly rate masks unpredictable real cost. Basic auth flows flagged 'broken' for enterprise readiness.
    - (mixed) Fritz.ai / Coda One reviews: Strong for longer-horizon, cross-repo tasks vs in-editor copilots, but the verdict is 'powerful but uneven' - depends heavily on task scoping.
- **Borrowable for SmbOS:**
    - Role-specialized Droids ≈ SmbOS's library of SOPs as named, purpose-built workers; the framing 'pick the right specialist for the job' is more legible to a solo operator than a generic agent.
    - 'Missions' (describe an outcome, agents plan→execute→verify) is the aspirational shape of an SmbOS multi-stage work item; but pair it with the verify step explicitly so completion isn't claimed blindly.
    - The token 'blackhole' / budget-overrun complaint validates SmbOS's Settings budget as a differentiator - but it must show real-time spend and hard-stop, not just an advertised cap (Cline does this better).
    - Cross-surface presence is a both-sides lesson: SmbOS's value is being the one local command center, not scattering the user across dashboard+IDE+Slack; consolidate the plate rather than fragment it.
    - 'Powerful but uneven, depends on scoping' is the recurring cluster theme - SmbOS's SOP layer is exactly the scoping discipline these tools lack out of the box; lean into that as the wedge.

### Sourcegraph Amp - Frontier coding agent for terminal/editor with shareable Threads, autonomous subagents, and an Oracle reasoning model, billed pure pass-through.

- **Category:** Assistive terminal/IDE agent with team collaboration  
- **URL:** https://ampcode.com/manual  
- **Relevance:** high  
- **How it works:** Runs in terminal and editor extensions with three modes: deep (extended reasoning), smart (unconstrained SOTA models), rush (fast low-token GPT-5.5). Work happens in Threads - persistent conversations holding all messages, context, and tool calls, savable and resumable. The main agent autonomously spawns Subagents (isolated context windows, no inter-subagent comms) for independent parallel parts, and can autonomously invoke the Oracle (GPT-5.5 high-reasoning) for debugging/review without spending the main thread's tokens. Thread visibility is granular: private, workspace-shared, group-shared (enterprise), or unlisted public link - plus thread sharing and leaderboards for teams. The CLI shows real-time tool execution, thinking blocks, and reasoning chains you can expand/collapse. No subscription: buy credits ($5 min), pure LLM cost with zero markup for individuals/teams.  
- **Value prop:** A high-autonomy agent whose work is a shareable, inspectable artifact - and you pay only raw model cost.  
- **Tech/stack:** Commercial (Sourcegraph); CLI + editor extensions. Threads stored on Sourcegraph servers. Cloud-backed models; multi-model (Claude, GPT-5.5). Not OSS.  
- **Pricing:** No subscription; credits ($5 min) at raw LLM cost, zero markup for individuals/teams; Enterprise +50% (SSO, retention controls, analytics API).  
- **Target user:** Individual devs and teams who want a transparent, collaborative, pay-for-what-you-use agent; Sourcegraph's existing code-search base.  
- **Key features:**
    - Threads: persistent, savable, resumable, and shareable conversation artifacts
    - Granular thread visibility (private → workspace → group → public link) + leaderboards
    - Autonomous subagents with isolated context windows for parallel work
    - Oracle: a separate high-reasoning model auto-invoked for debugging/review, off the main token budget
    - Real-time expandable tool-execution + thinking-block view in the CLI
    - Pass-through, no-markup credit billing ($5 min, no subscription)
- **User feedback:**
    - (positive) HackerNoon (waitlist-drop announcement): Reported writing 70-80% of code for active users; the subagent context-multiplication is repeatedly singled out as the standout capability.
    - (positive) Medium teardowns (Brendan Bohan, Matt Tanner) + gvrooyen Substack: Oracle as an auto-invoked 'second opinion' on its own context window is praised for clean, focused deep analysis without polluting the main thread.
    - (mixed) zoltanbourne Substack ('Good, Bad and Ugly'): Powerful but the pay-per-use credit model makes cost feel unpredictable for heavy/exploratory use; the no-markup framing is liked but spend still surprises.
- **Borrowable for SmbOS:**
    - Threads-as-shareable-artifact is the single best legibility idea here: make each SmbOS run a persistent, savable, linkable thread with full tool calls - 'Recent runs' becomes a library of inspectable artifacts, not just status rows.
    - Granular visibility (private → workspace → public link) is overkill for a solo operator but the public-link idea lets a founder share a completed run as proof/handoff to a client or contractor.
    - The Oracle pattern - auto-escalate hard sub-problems to a stronger reasoning model on a separate budget - gives SmbOS a way to keep routine runs cheap while spending more only when a run is genuinely stuck, surfaced as 'thinking harder on this.'
    - Real-time expandable tool-execution + thinking-block view is exactly what SmbOS's 'in flight' panel should stream over SSE: collapsed by default, expandable to see what the agent is actually doing right now.
    - Pure pass-through, no-markup credit billing with a $5 floor is a trust-and-positioning move SmbOS can echo: the budget setting should read as 'your raw model spend, capped,' not an opaque platform fee.
    - Subagents with isolated context windows model how a single SmbOS task could fan out independent sub-steps while keeping the main run's context (and the human's mental model) clean.



## Cluster: Coding-agent orchestration, multi-session managers & autonomous loops

_The whole cluster has converged on one architecture and is now competing on trust, not plumbing. Nearly every tool = (1) isolate each agent (git worktree, or a Docker/Dagger container for safer code execution), (2) give each task a self-contained reviewable unit (a branch + diff, or a PR), and (3) put a board/dashboard/TUI over N parallel sessions. That base layer is commoditized and increasingly free (Conductor, Claude Squad, Vibe Kanban, container-use all free/OSS), and Terragon's death plus Anthropic shipping Claude Code Web shows thin session-wrappers get eaten by the platform vendor. The unsolved, repeatedly-cited problem is the HUMAN REVIEW BOTTLENECK: Simon Willison, the madewithlove reviewer, and multiple HN/Reddit voices all independently land on 'the agents aren't the constraint, I am - I can only review and land one significant change at a time, and N agents means N times the bugs to catch.' The winners differentiate on making autonomous work legible and trustworthy: container-use's 'record what the agent actually did, not what it claims' audit trail; Sculptor's roadmap 'Instruction audits' that check output against plaintext rules; Conductor's checkpoints/rollback; Vibe Kanban's explicit In-Review gate + comment-back-and-retry. Two failure modes recur as anti-patterns: permission/blast-radius overreach (Conductor's full-GitHub-account OAuth backlash; YOLO --autoyes / permission-skipping-by-default) and context amnesia per new session (which is precisely what an injected-spec-every-run model fixes). This is exactly SmbOS's lane. SmbOS already has the legibility surface (live-mirror dashboard, plain-language 'on your plate / in flight / coming up'), the trust controls (launch permission + budget, opt-in autonomy), and the context-priming model (SOP-injection hook = the cluster-wide answer to context amnesia, independently validated by Ralph and by AGENTS.md/Backlog.md). The borrowable upgrades: (1) make every run produce a concrete reviewable artifact (diff/PR/draft) on the plate, not just a 'done' status; (2) store and replay the real tool-call/command trace so 'completed' is verifiable, not asserted; (3) add an explicit needs-your-review state between 'in flight' and 'done'; (4) add comment-back-and-retry so the owner can nudge a run instead of restarting; (5) never strand the owner - every in-flight or scheduled run gets a one-click take-over-locally path (Sculptor Pairing Mode / terry / container-use 'drop into terminal'); and (6) keep a lightweight quick-run path so SmbOS avoids the 'great for big projects, overkill for a quick fix' critique that dogs task-master and GSD. SmbOS's defensible moat is NOT the session plumbing the whole cluster has commoditized - it's the SOP library, the post-run 'did this follow its SOP?' audit (an Instruction-audit SmbOS is uniquely positioned to ship), and the plain-language operating model for a non-babysitting solo owner._

### claude-task-master (Task Master AI) - PRD-to-task-graph engine: turns a plain-language spec into a structured, dependency-ordered task list that AI coding agents work through one task at a time.

- **Category:** AI planning / task-decomposition layer for coding agents  
- **URL:** https://github.com/eyaltoledano/claude-task-master  
- **Relevance:** high  
- **How it works:** You write a PRD in plain text at .taskmaster/docs/prd.txt. Task Master parses it (via an LLM) into a tasks.json: tasks with IDs, descriptions, subtasks, dependencies, and complexity scores, plus generated per-task markdown files. The agent then drives a lifecycle of CLI/MCP commands: 'next' (pick the next actionable unblocked task), 'expand' (decompose into subtasks), 'analyze-complexity', and 'research' (pull fresh context into a task). Ships two surfaces: an MCP server (recommended, integrates into Cursor/Windsurf/VS Code chat so you steer it in natural language) and a standalone CLI. Uses a multi-model split: a 'main' coding model, a 'research' model, and a 'fallback'. Tagged task lists let you run parallel workstreams. Tool-loading modes (all/standard/core, 36/15/7 tools) trade capability for token budget.  
- **Value prop:** Bridges the gap between a vague intent and executable work. Instead of an agent free-styling a big change, the work is pre-decomposed into small, ordered, individually-reviewable units with explicit dependencies, which reduces drift and rework.  
- **Tech/stack:** Node/TS CLI + MCP stdio server. Local, file-based (tasks.json + markdown in repo). Model-agnostic (Anthropic, OpenAI, Gemini, Perplexity, xAI, OpenRouter, Mistral, Groq, local Ollama).  
- **Pricing:** Free, open source (MIT-ish). BYO model API keys; free with Claude Code subscription.  
- **Target user:** Solo devs and small teams using Cursor/Claude Code/Windsurf who want their agent to follow a plan instead of improvising.  
- **Key features:**
    - PRD-to-tasks.json decomposition with dependencies + complexity scoring
    - 'next' command surfaces the single next unblocked task (do-loop primitive)
    - MCP server + CLI dual surface; no API key needed when using Claude Code as the model
    - Multi-model roles: main / research / fallback
    - Tagged task lists for parallel workstreams
    - Token-budget-aware tool loading (core/standard/all modes)
- **User feedback:**
    - (positive) tessl.io blog teardown: "Reduced 90% errors for my Cursor" - decomposing into small dependency-ordered tasks stops the agent from making sweeping unreviewable changes.
    - (positive) GitHub (27.6k stars) + Reddit/HN general reception: Widely seen as a 'game-changer' for keeping agents on-rails; the 'parse my PRD' moment is the hook.
    - (mixed) GitHub discussion on token waste (referenced in search): 36-tool 'all' mode burns ~21k tokens of context; users push toward core/standard modes. Some find the full PRD ceremony heavy for small tasks (overkill for a quick fix).
- **Borrowable for SmbOS:**
    - The 'next' command is exactly SmbOS's 'pick up the next thing on your plate' primitive - codify a single canonical 'what should I do next' resolver over the plate + queue.
    - Dependency + complexity metadata on tasks: SmbOS could tag SOP runs with prerequisites and an estimated-effort/cost score so 'Coming up' can auto-order and the dashboard can show 'blocked by'.
    - Separate 'main' vs 'research' model roles - SmbOS scheduled/triggered runs could route cheap recurring SOPs to a cheaper model and reserve the expensive model for the picked-up work, feeding the budget setting.
    - Importer parity: PRD->tasks mirrors SmbOS's brain-dump->SOPs importer; borrow the 'expand into subtasks' step so an imported SOP can be broken into checklist stages (maps to sop-work's plan/build/review/ship).
    - Token-budget tool modes are a concrete model for SmbOS's budget setting: expose a 'lean vs full' run mode.

### Conductor (Melty Labs) - Free Mac app that runs a team of parallel Claude Code / Codex / Cursor agents, each in its own isolated git worktree, with a unified dashboard to monitor, diff, and merge.

- **Category:** Multi-session GUI orchestrator (desktop, worktree-based)  
- **URL:** https://www.conductor.build/  
- **Relevance:** high  
- **How it works:** Native macOS app (Apple Silicon). Each task gets its own workspace = its own git worktree + branch + terminal + diff + review path. You spin up multiple agents at once; a central dashboard shows all active sessions and their state. Supports checkpoints and rollback, and a multi-model 'race' mode where several agents attempt the same task and you pick the winner. Uses your existing Claude auth (API key or Pro/Max). Review/merge happens in-app per workspace. It clones the repo from GitHub via OAuth rather than attaching to an already-checked-out local repo.  
- **Value prop:** Turns 'I have to babysit one terminal' into 'I delegate N scoped tasks and review them like PRs.' The mental model the reviewer landed on: delegation, not pair-programming. 'The skill isn't coding faster. It's knowing what can happen simultaneously.'  
- **Tech/stack:** Native macOS (Apple Silicon only; Intel WIP, no Win/Linux). Local worktrees, but GitHub-OAuth clone-based. Closed source. From Melty Labs (YC S24).  
- **Pricing:** Free app; BYO Claude/Codex/Cursor subscription (you pay model costs).  
- **Target user:** Mac-based solo devs / small teams comfortable running several coding agents at once and reviewing diffs.  
- **Key features:**
    - Per-task isolated workspace (worktree + branch + terminal + diff + review)
    - Unified dashboard over all running agents
    - Checkpoints + rollback for safety
    - Multi-model race mode (spin up competing implementations, keep the best)
    - Uses existing Claude Pro/Max/API auth; free app
- **User feedback:**
    - (negative) BigGo News / r/ + HN backlash (July 2025): OAuth asks for full read-write to the entire GitHub account incl. org settings and deploy keys; no fine-grained scopes. Users: 'I wanted a simple git worktree manager for my already-checked-out repo. Instead it requests GitHub permissions and clones the repo.'
    - (mixed) madewithlove hands-on blog: Parallel execution genuinely fast (4 bugs fixed in ~10 min across 4 agents), but: worktrees exclude untracked files (.env, node_modules) so each workspace needs bootstrapping; 4 agents = 4x tokens; new workspaces have 'context amnesia'; and '4 parallel agents potentially mean 4x as many bugs to catch' - human review is still the bottleneck.
    - (positive) madewithlove / The New Stack: Clean UI, checkpoints/rollback, and the exploration value of racing competing implementations are the standout wins.
- **Borrowable for SmbOS:**
    - The 'each task = workspace + branch + terminal + diff + review path' framing is the cleanest legible-unit-of-agent-work model - SmbOS 'In flight' cards should each link straight to that session's live terminal AND its eventual diff/output, not just a status.
    - Checkpoints + rollback as a first-class safety affordance: SmbOS could snapshot before a run and offer 'undo this run' on the Recent runs card - strong trust signal for a non-babysitting owner.
    - The untracked-files/.env bootstrapping pain is a warning: SmbOS 'Prepare' step for a procedure should explicitly capture the environment/secrets a run needs so picked-up sessions aren't broken on start.
    - 'Context amnesia per new workspace' is the exact problem SmbOS's SOP-injection hook solves - lean into it as a differentiator: every picked-up session starts primed with the SOP + prior-run notes.
    - Multi-model race mode -> SmbOS could offer 'run this SOP two ways and show me both' for high-stakes procedures.
    - The permissions backlash is a positioning lesson: SmbOS being local-first / minimal-scope is a trust advantage worth surfacing in Settings copy.

### Sculptor (Imbue) - Mac desktop app that runs parallel Claude Code agents in isolated Docker containers, with one-click 'Pairing Mode' to pull any agent's work into your local repo and IDE.

- **Category:** Multi-session GUI orchestrator (container-isolated)  
- **URL:** https://imbue.com/sculptor/  
- **Relevance:** high  
- **How it works:** Each agent runs in its own Docker container (not a worktree), so agents can safely execute code in parallel without polluting your machine or each other, and without per-agent dependency reinstalls. You 'spin up a new agent the moment you think of something.' Session history (plans, chats, tool calls, code changes) is preserved. The signature feature is Pairing Mode: one click syncs a container agent's work into your local repo and keeps git state + files synced bidirectionally, so the agent sees your edits/comments live and you test in your own IDE before committing. Merge step auto-flags conflicts; a beta 'Suggestions' feature flags code issues; roadmap includes 'Instruction audits' that check agent output against your plaintext rules.  
- **Value prop:** Solves the two pains the Claude Code community named: run multiple agents safely in parallel, and quickly verify their changes. Container isolation = blast-radius control; Pairing Mode = collapse the gap between 'agent's sandbox' and 'my real workflow.'  
- **Tech/stack:** macOS desktop app + Docker containers. Local execution. From Imbue (well-funded AI lab). Closed source.  
- **Pricing:** Not publicly stated on the announce page (research preview lineage); BYO Claude.  
- **Target user:** Developers who want safe parallel agents AND the ability to drop into real local pair-programming on any thread.  
- **Key features:**
    - Per-agent Docker container isolation (vs worktrees) - no dependency reinstall, safe code execution
    - Pairing Mode: bidirectional sync of a container agent into your local repo/IDE
    - Persistent session history (plans, chats, tool calls, diffs)
    - Auto-flagged merge conflicts + agent-assisted resolution
    - Beta 'Suggestions' (issue detection) and planned 'Instruction audits' (rule-violation checks)
- **User feedback:**
    - (positive) Imbue announce / community-driven roadmap: Direction came from Claude Code users explicitly asking for safe parallel agents, cross-session context persistence, and fast verification - strong product-market fit signal.
    - (mixed) Imbue blog (self-reported): The trust features that matter most (Suggestions issue-flagging, Instruction audits) are beta/roadmap, not shipped - verification is still largely manual review today.
- **Borrowable for SmbOS:**
    - 'Instruction audits' = check agent output against plaintext rules. SmbOS SOPs ARE plaintext rules; a post-run 'did this run follow its SOP?' audit is a natural, differentiated feature for the Recent runs card.
    - Pairing Mode's bidirectional 'pull the agent's work into my real environment' is a richer version of SmbOS 'pick up' - consider a 'take over this in-flight session locally' button that hands the live session to the owner's terminal.
    - Container isolation as the trust story: if SmbOS ever runs unattended/scheduled SOPs, containerizing them bounds blast radius without the owner babysitting.
    - Persistent session history (plans/chats/tool-calls/diffs intact) is what makes autonomous work legible after the fact - SmbOS Recent runs should store and replay the full run trace, not just a completion status.
    - 'Spin up an agent the moment you think of something' -> a frictionless capture-to-queue path from the dashboard (mirrors sop-new/quick-capture).

### Vibe Kanban (Bloop AI) - Open-source, self-hosted Kanban board for orchestrating CLI coding agents: write a ticket, assign an agent, it runs in an isolated worktree, you review the diff and merge from the board.

- **Category:** Multi-session GUI orchestrator (kanban-based)  
- **URL:** https://vibekanban.com/  
- **Relevance:** high  
- **How it works:** Run with `npx vibe-kanban` (binds a random free port). Two-pane UI: a Kanban board (To Do -> In Progress -> In Review -> Done/Cancelled) on the left and a live agent-interaction pane on the right that streams reasoning, commands, file ops, and MCP tool calls in real time. You connect a GitHub repo, create a task, assign it to a saved agent profile (Claude Code, Codex, Gemini, OpenCode, Copilot, Amp, Qwen, Cursor CLI). The agent runs in its own git worktree with permission-skipping flags on by default. You review the diff, add comments that go back to the agent as feedback, or reject and create a new attempt with a different agent/prompt. On accept it rebases onto main, merges, and cleans up the worktree. 'Open in IDE' opens the worktree in your editor.  
- **Value prop:** Built to fix the 'working synchronously with one agent leads to distraction and doomscrolling' problem - gives async, board-based oversight of many agents with a clear review gate and the ability to retry a failed task with a different agent.  
- **Tech/stack:** Local web app, `npx`-launched, GitHub-connected, per-task git worktrees. OSS.  
- **Pricing:** Free, open source, self-hosted. (Project announced sunsetting; continues community-maintained.)  
- **Target user:** Devs who prefer a GUI over juggling terminal windows and want async oversight of multiple agents.  
- **Key features:**
    - Kanban lifecycle with an explicit 'In Review' gate
    - Real-time streaming pane (reasoning, commands, file ops, MCP calls)
    - Per-task isolated worktree; auto rebase+merge+cleanup on accept
    - Comment-back-to-agent feedback loop; reject -> new attempt with different agent/prompt
    - Multi-agent profiles, saveable/reusable
    - Single-command local self-host
- **User feedback:**
    - (positive) Show HN (item 44533004), author comments: Co-author: you write a ticket, run it locally, watch responses, review diffs, comment back or reject and re-attempt - the explicit review gate resonated. One user updated docs with Amp via the board successfully.
    - (mixed) HN July 2025 thread: Overlap with Cursor's Agents UI and a crowded field of look-alikes raised 'why this over X' questions; 'great, now I have to spend my morning using vibe kanban to make a tui for vibe kanban' (the meta-sprawl joke).
    - (mixed) Eleanor Berger hands-on review: Permission-skipping flags are ON by default for autonomous running - convenient but a YOLO-mode safety concern for a tool that merges to main.
- **Borrowable for SmbOS:**
    - The kanban columns map almost 1:1 onto SmbOS's vocabulary: On your plate (To Do) -> In flight (In Progress) -> needs-your-review (In Review) -> Recent runs (Done). Borrow the explicit 'In Review' gate as a distinct state between 'in flight' and 'done' so completed-but-unverified work doesn't silently land.
    - Comment-back-to-agent and reject->new-attempt-with-different-prompt is a great human-in-the-loop primitive: SmbOS could let the owner reply to an in-flight or finished run to re-run it with a tweak, instead of starting from scratch.
    - The real-time streaming pane (reasoning + commands + tool calls) is the legibility gold standard - SmbOS's SSE live-mirror should stream the actual tool-call/command trace, not just a spinner, so 'in flight' is trustworthy.
    - 'Open in IDE' / take-over button: never strand the owner in read-only status; always offer a one-click path into the real session.
    - Permission-skipping-by-default is the anti-pattern to avoid - SmbOS's launch-permission + budget settings are the safer default; make autonomy opt-in per SOP.

### Claude Squad - Terminal-native (TUI) manager for multiple AI coding agents, each in its own tmux session + git worktree, with optional background auto-accept mode.

- **Category:** Multi-session TUI orchestrator (terminal-native)  
- **URL:** https://github.com/smtg-ai/claude-squad  
- **Relevance:** high  
- **How it works:** A Go TUI (`cs`). Each task/instance = a tmux session (isolated terminal) + a git worktree (isolated branch). Keys drive the whole loop: n/N new session (optionally with a starting prompt), enter/o attach to reprompt, ctrl-q detach, s commit+push branch to GitHub, c commit+pause, r resume, D kill, Tab toggles preview/diff. An experimental --autoyes (-y) flag runs instances in background YOLO/auto-accept mode so they complete without prompting. Configurable launch commands let it drive Claude Code (default), Codex, Gemini, Aider, OpenCode, Amp via named profiles. Requires tmux + gh.  
- **Value prop:** For terminal-dwellers who hit 'session sprawl' - gives a single TUI to spawn, attach, diff, pause/resume, and push N isolated agent sessions without manually juggling tmux windows and worktrees.  
- **Tech/stack:** Go TUI, tmux + git worktrees + gh CLI, fully local. OSS (~7.8k stars).  
- **Pricing:** Free, open source (Go). BYO agent/model.  
- **Target user:** Terminal-first solo devs (the exact 'lives in the terminal' persona) managing several concurrent agent tasks.  
- **Key features:**
    - Single TUI over N agents; each gets isolated tmux session + git worktree
    - Pause (c) / resume (r) sessions - checkpoint-like lifecycle
    - Background --autoyes auto-accept mode for unattended runs
    - In-TUI diff/preview toggle before checkout
    - Commit+push to GitHub from the TUI (s)
    - Multi-agent via configurable launch profiles
- **User feedback:**
    - (positive) GitHub (7.8k stars, 557 forks): Strong adoption among terminal-native users; the tmux+worktree pattern is the canonical DIY approach this productizes.
    - (mixed) README / general: --autoyes is flagged experimental; running background auto-accept across multiple worktrees is powerful but a known footgun (no review gate before changes land).
- **Borrowable for SmbOS:**
    - Pause/resume as explicit session states: SmbOS 'in flight' could support 'paused, waiting on you' vs 'actively running' - maps to the plate ('waiting for you') vocabulary and the inflight-session-liveness work currently in this branch.
    - The keyboard-driven do-loop (new -> attach -> diff -> commit -> resume) is a tight, legible state machine SmbOS's dashboard cards can mirror as buttons (the existing put-back/done/dismiss recovery is the same idea).
    - Named launch profiles (per-agent configurable commands) -> SmbOS could let an SOP declare which model/flags/permissions it launches with, baked into the procedure.
    - Background auto-accept is the opt-in autonomy SmbOS gates behind launch-permission - keep it explicit per-SOP and surface a clear 'this ran unattended' badge on Recent runs.
    - It validates SmbOS's persona: the real user lives in the terminal, but even terminal-natives want one pane that makes parallel/queued sessions legible - that pane is the dashboard.

### Ralph loop (Geoffrey Huntley) - A technique, not a product: run a coding agent in a bare `while` loop, feeding the same prompt + spec each iteration, doing exactly one task per loop with a fresh context window every time.

- **Category:** Autonomous-loop pattern / methodology  
- **URL:** https://ghuntley.com/ralph/  
- **Relevance:** medium  
- **How it works:** Core mechanism: `while :; do cat PROMPT.md | claude-code ; done`. Each iteration starts a fresh agent instance (clean context), reads a fixed 'stack' of files - @fix_plan.md (prioritized task list, regenerated often), @specs/* (requirements), @AGENT.md (build/run instructions), PROMPT.md (active instructions) - does ONE atomic task, commits only if tests pass, and the loop restarts. The non-obvious insight is the deliberate context reset: 'The more you use the context window, the worse the outcomes you'll get.' Subagents handle expensive operations so the primary agent stays a lean scheduler. Specs live external to the primary context. Guardrails baked into the prompt: search the codebase before assuming something isn't implemented; no placeholder implementations; run tests immediately; leave notes for future iterations; git-tag when clean.  
- **Value prop:** Cheap, dumb, durable autonomy. Reframes 'orchestration' as 'a loop + a good spec + a context reset.' Huntley built an entire programming language over 3 months this way; a YC team shipped 6 repos overnight; The Register reported $10/hr commercial-software cloning.  
- **Tech/stack:** Just bash + a coding CLI (Claude Code or Amp) + markdown spec files + git. Local or cloud.  
- **Pricing:** Free pattern. (Packaged variants exist: snarktank/ralph on GitHub; a ralph-loop Claude Code plugin.)  
- **Target user:** Senior engineers willing to write tight specs and supervise; greenfield projects.  
- **Key features:**
    - One task per loop + fresh context each iteration (context-rot avoidance)
    - External spec/plan files as the durable state between loops
    - Tests-pass-before-commit as the only stop/checkpoint condition
    - Subagents-as-workers, primary-agent-as-scheduler
    - Prompt-level guardrails (search-first, no placeholders, full implementations)
- **User feedback:**
    - (mixed) ghuntley.com (creator): Explicit limits: 'There's no way in heck I'd use Ralph in an existing codebase'; 'There is no way this is possible without senior expertise guiding Ralph.' Failure modes: placeholder implementations, non-deterministic search missing existing code, waking to a broken non-compiling codebase, context overflow from compile errors.
    - (mixed) The Register (2026-01-27): Sensationalized as 'vibe-clone commercial software for $10/hr' - real but with heavy caveats; works best greenfield + well-specified + deterministic tests.
    - (positive) Geocodio / DEV community: 'Ship features in your sleep' - teams report real overnight throughput when the spec and test loop are solid.
- **Borrowable for SmbOS:**
    - The 'fresh context + injected spec every iteration' IS SmbOS's SessionStart-hook model - Ralph is independent validation that priming each run from external markdown beats long sessions. Lean into it.
    - fix_plan.md / specs / AGENT.md as the durable inter-run state maps directly to SmbOS's ~/sops + plate: the plate is fix_plan.md, the SOP is the spec, CLAUDE.md is AGENT.md. SmbOS could formalize a per-SOP 'plan file' that scheduled/looped runs read and update.
    - 'One task per loop, tests-pass-before-commit' is the safest autonomous-run contract - SmbOS scheduled/cron SOPs should adopt a hard 'one unit + verify before reporting done' rule so unattended runs are trustworthy.
    - Run-notes-for-future-iterations: SmbOS should let a finished run append learnings back to its SOP (this already aligns with sop-update) so the loop self-improves.
    - The hard caveat - autonomy works greenfield + well-specified, fails on messy existing systems - tells SmbOS to scope unattended SOPs to well-defined, verifiable, low-blast-radius procedures and keep ambiguous work human-picked-up.

### Terragon / Terry - Cloud fleet of background Claude Code (and Codex/Amp/Gemini) agents: assign tasks from anywhere (incl. phone), each runs in a remote sandbox, opens a PR; `terry` CLI lets you pull a cloud session down to continue locally. (Shut down Jan 2026.)

- **Category:** Cloud background-agent orchestrator (async)  
- **URL:** https://github.com/terragon-labs/terragon-oss  
- **Relevance:** medium  
- **How it works:** Cloud platform that removed Claude Code's 'keep your terminal open' constraint. You give it a task; it spins a remote sandboxed container with its own repo copy; the agent reads files, edits, runs tests in isolation, and opens a PR. Multiple tasks run in parallel asynchronously while you sleep/commute. The `terry` CLI enables local takeover/continuation ('claude resume' to continue a cloud session locally). Now an OSS snapshot at shutdown (Jan 16, 2026); Anthropic's Claude Code Web is the official successor.  
- **Value prop:** Async, fire-and-forget agent work that produces reviewable PRs - 'virtual employees' you task from your phone, with a clean local-takeover escape hatch when you need to drive.  
- **Tech/stack:** Cloud sandboxed containers + PR-based output + a local CLI bridge. Now OSS.  
- **Pricing:** Was a paid cloud SaaS; now free OSS snapshot (defunct service).  
- **Target user:** Solo devs/founders who want to dispatch work asynchronously and review PRs later, not babysit a terminal.  
- **Key features:**
    - Cloud sandbox per task; agent produces a PR as the reviewable unit
    - Async task assignment from anywhere (mobile)
    - Multi-agent (Claude Code, Codex, Amp, Gemini)
    - `terry` CLI for seamless cloud->local session takeover
    - Parallel fleet of background agents
- **User feedback:**
    - (positive) Show HN (item 45127766) / Sawyer Hood on X: The core pitch - 'use Claude Code as a background agent, you don't have to keep your terminal open' - landed; PR-as-deliverable made async review natural.
    - (negative) Shutdown (terragonlabs.com, Jan 2026): Service shut down; Anthropic shipping first-party Claude Code Web ate the wedge. Lesson: thin cloud-wrappers over Claude Code are vulnerable to the platform vendor.
- **Borrowable for SmbOS:**
    - PR-as-the-reviewable-unit is the cleanest 'make autonomous work legible' pattern: a finished SmbOS run should produce a concrete, reviewable artifact (diff, draft doc, draft email) on the plate, not just 'done.'
    - Async dispatch + mobile task assignment -> SmbOS's RemoteTrigger / PushNotification path: let the owner queue a procedure or get notified of a completed run from their phone, with the dashboard as the review surface when back at the desk.
    - `terry`'s cloud->local takeover is the 'never strand the user' principle for async work: any scheduled/queued SmbOS run should be resumable/takeover-able into a live local session.
    - Strategic caution for SmbOS positioning: Terragon died because it was a thin wrapper Anthropic could replace. SmbOS's defensibility is the SOP library + owner-facing plain-language operating model, NOT the session plumbing - keep the moat in the SOPs and the do-loop, not in re-implementing background execution.

### container-use (Dagger) - Open-source MCP server that gives each coding agent its own containerized, git-branched dev environment, with a full command/log audit trail and a 'drop into the agent's terminal' escape hatch.

- **Category:** Agent-isolation infrastructure (MCP + containers)  
- **URL:** https://github.com/dagger/container-use  
- **Relevance:** medium  
- **How it works:** An MCP server you add to Claude Code/Cursor/any MCP agent. Each agent gets a fresh Dagger container in its own git branch (worktree-backed), so multiple agents run in parallel without conflicts and failures are discarded instantly. Every change is auto-committed, giving a complete audit trail you can review and merge with standard git. Crucially it records the full command history and logs of what agents actually did ('not just what they claim'), and you can drop into any agent's terminal to inspect state or take over when it's stuck. Containers configurable with custom base images/env/deps.  
- **Value prop:** Infrastructure-layer trust + isolation: run many agents safely, and get an honest, replayable record of every command - addressing the 'I can't trust what the agent says it did' problem.  
- **Tech/stack:** MCP stdio server + Dagger containerization + git worktrees/branches. Local. OSS.  
- **Pricing:** Free, open source (Dagger-backed).  
- **Target user:** Devs/teams wanting safe parallel agents and verifiable audit trails inside their existing MCP agent.  
- **Key features:**
    - Per-agent container + git branch isolation via Dagger
    - Auto-commit of every change = complete audit trail
    - Full command/log history ('what they did, not what they claim')
    - Drop-into-terminal takeover when an agent is stuck
    - MCP server - works across any MCP-compatible agent
    - Discard-failures-instantly via branch isolation
- **User feedback:**
    - (positive) Dagger blog / InfoQ / DeepWiki: 'Containing agent chaos' - the audit-trail + isolation framing resonates with teams burned by agents making unverifiable claims; auto-commit-everything makes review standard-git.
    - (mixed) General (Docker-complexity reviews, inferred): Docker/Dagger dependency adds setup overhead and complexity for solo users who just want a simple worktree - heavier than tmux/worktree approaches.
- **Borrowable for SmbOS:**
    - 'Record what the agent actually did, not what it claims' is the single strongest trust feature in this cluster - SmbOS Recent runs should store the real command/tool-call log and let the owner expand it, so 'completed' is verifiable, not asserted.
    - Auto-commit-every-change-to-a-branch makes review a standard, familiar operation - SmbOS runs that touch files should land on a branch/diff the owner can accept or discard, not mutate the working tree directly.
    - 'Drop into the agent's terminal to take over when stuck' = the takeover affordance SmbOS in-flight cards need; pairs with the inflight-session-liveness work to detect a stuck/dead session and offer takeover.
    - It's an MCP server (like SmbOS's own MCP stdio server) - validates SmbOS's architecture and suggests SmbOS could expose run-isolation/audit as MCP resources other agents consume.
    - Discard-failures-instantly via branch isolation -> SmbOS's 'dismiss / put back' recovery actions are the same instinct; make 'discard this run cleanly' a one-click, no-residue action.

### GSD (Get Shit Done) + Backlog.md (markdown spec-driven planners) - Two markdown-native, git-stored planning systems for AI-assisted dev: GSD is a Claude Code plugin that runs define->build->ship milestone/phase cycles; Backlog.md turns any git repo into a markdown kanban board treating AI agents as first-class collaborators.

- **Category:** Spec-driven planning + markdown task management for agents  
- **URL:** https://github.com/MrLesk/Backlog.md  
- **Relevance:** high  
- **How it works:** GSD (by TÂCHES): a Claude Code plugin/skill set. Flow: interview the user until the project is understood -> spawn parallel research agents (libraries, pitfalls) -> extract v1/v2/out-of-scope requirements -> build a roadmap of executable phases -> execute phases (wave-based parallelization) -> /complete-milestone archives + tags the release, /new-milestone starts the next cycle. State persists in .planning/ markdown docs across context resets; commands like /progress, /resume-work, /pause-work, /debug carry state. Backlog.md: a zero-config CLI that stores tasks/drafts/docs/decisions as markdown + YAML inside the repo (every change is a git commit), renders an instant terminal kanban AND a web UI, and ships AGENTS.md instruction files so agents produce predictable structured output. 100% offline/private, MIT, cross-platform.  
- **Value prop:** Make the plan itself durable, versioned, plain-text, and agent-readable - so both the human and the agent share one source of truth that survives context resets and lives in git.  
- **Tech/stack:** Plain markdown + YAML in git. Backlog.md = zero-config CLI (cross-platform) + web UI. GSD = Claude Code plugin/skills. Local, offline. OSS.  
- **Pricing:** Both free/OSS (Backlog.md MIT; GSD open plugin).  
- **Target user:** Solo devs/small teams who want a durable, git-versioned, human+agent-shared plan rather than ephemeral chat context.  
- **Key features:**
    - Markdown + YAML tasks stored in-repo; every change is a git commit (full history)
    - GSD: milestone -> phase roadmap with define/build/ship cycles + state across context resets
    - GSD: parallel research-agent fan-out during planning; wave-based phase execution
    - Backlog.md: instant terminal kanban + web UI from plain files; offline/private
    - AGENTS.md / instruction files so agents emit predictable structured results
    - Resume/pause/progress/debug commands that reload context
- **User feedback:**
    - (positive) Backlog.md GitHub / TerminalDock / forks (MrLesk, cytrowski, bradcstevens): 'Markdown-native, 100% private and offline, lives entirely inside your repo' is the loved property; multiple active forks indicate real traction. Treating AI agents as first-class via AGENTS.md is the differentiator.
    - (positive) DEV / codecentric GSD deep-dives: GSD's milestone/phase ceremony + state-across-context-resets is praised for keeping long projects coherent; the interview->research->roadmap flow gives structure casual prompting lacks.
    - (mixed) codecentric / general: The ceremony (interview, phases, milestones, many slash commands) is heavy for small tasks - a recurring 'great for big projects, overkill for a quick fix' tension (same critique as task-master).
- **Borrowable for SmbOS:**
    - These are SmbOS's closest philosophical cousins: plain-markdown, git-stored, agent-readable source of truth. Backlog.md's 'every change is a git commit' gives SmbOS a model for versioning SOP runs and plate changes with full history.
    - AGENTS.md / instruction files that make agents emit predictable structured output = exactly SmbOS's SessionStart SOP-injection. Borrow Backlog.md's idea of a per-task structured contract so a picked-up SmbOS session returns a predictable completion report.
    - Backlog.md proves the 'terminal kanban + web UI from the same plain files' pattern - validates SmbOS's dashboard-over-markdown approach and suggests offering a terminal view of the plate for the terminal-native user.
    - GSD's state-across-context-resets (pause-work/resume-work/progress) is the durability SmbOS needs for multi-stage work (sop-work's plan/build/review/ship) - store stage state in markdown so a resumed session reloads exactly where it stopped.
    - GSD's interview->research->roadmap flow is a richer importer: SmbOS's importer could add an interview + parallel-research step to turn a brain-dump into a phased SOP, not just a flat one.
    - The shared 'overkill for small tasks' critique is a direct warning for SmbOS: keep a lightweight quick-capture/quick-run path so the SOP ceremony never blocks a 2-minute task.



## Cluster: Agent inbox / human-in-the-loop control surfaces

_This cluster is converging on one architecture that SmbOS already instantiates, and the convergence is a strong validation signal. The pattern: a durable, checkpointed pause/resume engine underneath (LangGraph interrupt(), Inngest step.waitForEvent(), HumanLayer ACP's AwaitingHumanApproval, Vercel durable workflows) plus an inbox/card UI on top where a human accepts/edits/responds/ignores a proposed action shown with its concrete args and plain-language context. Two things separate the winners. (1) Learned/progressive trust: every serious player (HumanLayer auto-approvals, ServiceNow progressive delegation, Vercel stored preferences) is moving from a binary approve-everything toggle to autonomy that expands per-task as approval history accumulates, because the loudest real-user critique in the whole cluster (HN on HumanLayer) is automation bias: 'if the agent usually works, the human rubber-stamps and never catches the risky 5%.' The defensive UX answer is to gate only risky inputs (Vercel's needsApproval-as-predicate) and to surface what changed vs the last approved run, not 'approve?'. (2) The category is bifurcating into framework-coupled OSS inboxes (LangChain Agent Inbox, AgentKit) vs framework-agnostic SaaS inboxes (gotoHuman, HumanLayer API) vs local control surfaces (HumanLayer CodeLayer). SmbOS sits in the rarest and most defensible spot: a LOCAL, single-operator command center over real Claude Code sessions, and HumanLayer's CodeLayer (Go daemon + SQLite + REST + Tauri desktop + CLI orchestrating parallel Claude Code across worktrees) is almost the same architecture and the same bet, with the same launchd/daemon-liveness and session-lifecycle problems SmbOS is fighting. SmbOS's differentiators are plain-language owner-facing copy (the whole cluster uses 'inbox/approval/control tower'; SmbOS's 'on your plate / in flight / coming up' is warmer and clearer) and the SOP layer (none of these tools own the procedure library; they only own the approval moment). The biggest borrowable gaps for SmbOS: per-task typed action contracts + editable proposed args (Agent Inbox, gotoHuman, Vercel), learned per-SOP auto-approval / progressive delegation (HumanLayer, ServiceNow), routing 'waiting for you' to Slack/email/push so the loop closes when the founder isn't at the dashboard (HumanLayer, gotoHuman), and turning 'Recent runs' into an expandable per-step audit trail with diffs (Inngest Dev Server, ServiceNow auditability). One credibility warning from the field: HumanLayer was publicly called 'mostly vapor' for marketing CodeLayer/MULTICLAUDE features ahead of availability, so SmbOS should keep its Run/Queue/Prepare surfaces honest about what actually executes today._

### LangChain Agent Inbox - Open-source React/Next.js inbox UX for reviewing and responding to human-in-the-loop interrupts from LangGraph agents.

- **Category:** Agent inbox / HITL control surface (OSS, framework-coupled)  
- **URL:** https://github.com/langchain-ai/agent-inbox  
- **Relevance:** high  
- **How it works:** A LangGraph agent calls interrupt() with a HumanInterrupt payload, which checkpoints graph state into the persistence layer and pauses the run (works in production, frees resources, resumes from the same checkpoint when re-invoked). The Agent Inbox is a separate web app that connects to a LangGraph deployment via a LangSmith API key + deployment URL + graph/assistant ID (creds stored in browser localStorage). It polls for outstanding interrupts and renders each as an inbox item with a markdown 'description' (context) and an action_request (action name + args). The human resolves it with one of four HumanResponse actions; the response is sent back and the graph resumes. A hosted version exists at dev.agentinbox.ai; you can also self-host.  
- **Value prop:** Drops a ready-made, trustworthy review surface in front of any LangGraph agent so you don't hand-build an approval UI. The four-action vocabulary (accept/edit/respond/ignore) is a clean, copyable contract for human-agent handoff.  
- **Tech/stack:** TypeScript (~99%), React + Next.js + Tailwind. MIT licensed, fully OSS. Browser-local config; tightly coupled to LangGraph/LangSmith (not framework-agnostic).  
- **Pricing:** Free / OSS (MIT). Hosted inbox is free; you pay for LangGraph/LangSmith infrastructure separately.  
- **Target user:** Developers already building on LangGraph who need a human-approval/review surface without building their own UI.  
- **Key features:**
    - Four response actions: Accept (approve as-is), Edit (modify the proposed tool-call args inline before approval), Respond (freeform text feedback), Ignore (skip)
    - Per-interrupt config flags (allow_accept, allow_edit, allow_respond, allow_ignore) so the agent declares which actions are valid for THIS decision
    - Markdown 'description' field on each interrupt gives the human rich context about the pending decision
    - interrupt() checkpoints state to the persistence layer; runs survive process restarts and resume exactly where paused
    - Connects to multiple deployments/graphs; browser-local credential storage; hosted or self-hosted
- **Borrowable for SmbOS:**
    - Adopt the explicit per-task action contract: each plate item should declare which actions are valid (pick up / queue / dismiss / edit-and-run). SmbOS already has put-back/done/dismiss on in-flight tasks; formalize this as a typed 'allowed actions' set the SOP/task emits, like HumanInterrupt.config.
    - The Edit action is the key trust unlock: let the human modify the agent's proposed args/plan BEFORE it runs, not just approve/reject. SmbOS 'Prepare' could expose the primed task's parameters as editable fields.
    - Markdown 'description' per item: every plate/in-flight card should carry a plain-language 'why this is here and what it'll do' blurb (matches SmbOS house voice) rather than a bare task title.
    - The accept/edit/respond/ignore quartet is a battle-tested minimal vocabulary; map SmbOS's 'waiting for you' actions onto exactly these four to avoid dead-ends.
    - Resumable-from-checkpoint semantics: SmbOS's 'in flight -> put back -> pick up later' should preserve full session state so a put-back task resumes primed, not restarted.

### HumanLayer (SDK + CodeLayer + Agent Control Plane) - YC-backed human-in-the-loop layer for AI agents that started as an approval SDK (Slack/email) and evolved into CodeLayer, a local Tauri desktop 'outer-loop' control surface for orchestrating parallel Claude Code sessions.

- **Category:** HITL approval API + local agent control surface/IDE  
- **URL:** https://www.humanlayer.dev/  
- **Relevance:** high  
- **How it works:** Original SDK: lives at the tool-calling layer (framework- and LLM-agnostic). You wrap risky tools with @require_approval and expose @human_as_tool when the agent needs advice/missing context. The call pauses and routes an approval/feedback request over Slack or email; on response the agent resumes. Adds routing to specific people/teams, escalations, timeouts, state management, learned auto-approvals from prior decisions, and webhooks. CodeLayer (the current flagship, Apache-2.0): an open-source local desktop app for orchestrating AI coding agents built on Claude Code. Architecture = hld daemon (Go) that owns session lifecycle, persists to SQLite, and runs Claude Code, exposing a REST API; CodeLayer.app desktop UI (Tauri + React, keyboard-first/'Superhuman-style'); and a humanlayer CLI (TypeScript). 'MULTICLAUDE': run many Claude Code sessions in parallel across git worktrees plus remote cloud workers; approvals/feedback surface in the local UI. Agent Control Plane (ACP) is the Go/Kubernetes-CRD scheduler for 'outer-loop' unsupervised agents that make async tool calls (LLM/Agent/Task/ToolCall/ContactChannel CRDs); a tool call enters an AwaitingHumanApproval phase and routes through HumanLayer contact channels until approved.  
- **Value prop:** Lets you run agents headless/unsupervised and still gate the few risky steps through a human, over the channels the human already lives in (Slack/email) or a fast local control surface. The CodeLayer pivot is the closest analogue to SmbOS: a local daemon + desktop command center for managing multiple Claude Code sessions.  
- **Tech/stack:** SDK: Python/TS, cloud API. CodeLayer: Go (hld daemon), Tauri+React+Rust desktop, TypeScript CLI, SQLite, REST. Apache-2.0 (CodeLayer), ~11k stars. ACP: Go + Kubernetes CRDs + etcd, full MCP. Mix of OSS (CodeLayer/ACP) and hosted SaaS (approval API).  
- **Pricing:** SDK/API: free Starter ~1,000 operations/month, then pay-as-you-go, plus Premium/Enterprise (higher caps, branding, private deploy). Launch-HN pricing (~$20 / 200 operations) drew heavy pushback. CodeLayer/ACP are open source.  
- **Target user:** Engineering/product teams shipping headless or coding agents into production who need safe human gates; with CodeLayer, individual builders and teams orchestrating many parallel Claude Code sessions.  
- **Key features:**
    - @require_approval and @human_as_tool decorators at the tool layer; framework/LLM agnostic
    - Approvals routed over Slack and email with per-person/per-team routing, escalations, and timeouts
    - Learned/auto-approvals: remembers prior human decisions to stop asking for repeatedly-approved patterns
    - CodeLayer: local hld Go daemon + SQLite session store + REST API + Tauri/React desktop UI + CLI; parallel Claude Code sessions across git worktrees and remote cloud workers
    - Agent Control Plane: Kubernetes-CRD durable scheduler for unsupervised 'outer-loop' agents with AwaitingHumanApproval phase and full MCP support
    - Built and evangelizes '12-factor agents' (18k+ stars) and 'Advanced Context Engineering' as the methodology behind the tools
- **User feedback:**
    - (negative) Launch HN (news.ycombinator.com/item?id=42247368), Dec 2024: Pricing repeatedly attacked: 'Your entry price is steep... this isn't complicated to make... any competition would wipe out your pricing'; 'Per operation cost seems astronomical... you'll have a hard time getting people past that knee-jerk reaction.'
    - (negative) Launch HN thread: Automation-bias risk: 'If you have an agent that works quite well, the human will nearly always approve... the risky tasks won't be caught.' Plus 'How do you make sure an LLM won't eventually hallucinate approval?'
    - (mixed) Launch HN thread: 'Anyone can plug in a Slack client in an afternoon' and competitors named (Make.com HITL, gotohuman.com) -- core value seen as commoditizable; but others said 'easier to buy vs build... I've seen this come up a dozen times' and praised the Slack integration over alternatives.
    - (positive) Vendor testimonials via search (skywork.ai / brightcoding) ~2026: 'Our entire company is using CodeLayer now. We're shipping one banger PR after the other.' and 'improved my productivity (and token consumption) by at least 50%... the superhuman-style approach just makes so much sense.'
    - (negative) Starlog critical review (starlog.is, ~May 2026) and search summary: Called the context-engineering framework 'mostly vapor': 'you can't actually use most of this. CodeLayer isn't available' -- headline features (IDE, MULTICLAUDE) marketed ahead of general availability.
- **Borrowable for SmbOS:**
    - The CodeLayer architecture is a near-mirror of SmbOS and validates it: local Go/Python daemon + SQLite session store + REST/SSE + local desktop/web command center + CLI, orchestrating multiple Claude Code sessions across worktrees. SmbOS's launchd-vs-cron daemon pain and 'in flight' session model are the same problem space; watch their hld session-lifecycle design.
    - Learned auto-approvals: SmbOS's 'launch permission' setting could graduate from a global toggle to per-SOP learned trust ('you've approved this invoice-send SOP 8 times, auto-run it under $X budget'). This directly answers the HN automation-bias critique by reserving human attention for novel/risky runs.
    - Route approvals to where the human already is. SmbOS is terminal/dashboard-first, but a Slack/email/push 'a task is waiting for you' notification (push notification tool exists in this env) would close the loop when the founder isn't watching the dashboard.
    - Heed the automation-bias critique directly in UX: when a human is rubber-stamping, surface WHAT CHANGED vs the last approved run (a diff), not just 'approve?'. Make the risky 5% visually loud on the plate.
    - 'Outer-loop agent' framing (ACP) = SmbOS's scheduled/cron runs that pause for human feedback mid-flight. Adopt the explicit AwaitingHumanApproval state as a first-class plate status distinct from 'on your plate' (newly-landed) vs 'in flight' (running).
    - Lesson from the 'mostly vapor' review: don't market SmbOS surfaces that aren't usable yet. Keep the dashboard's Run/Queue/Prepare buttons honest about what actually executes.

### Inngest AgentKit (+ Inngest durable platform) - Open-source TypeScript multi-agent framework with durable execution, where human-in-the-loop is just step.waitForEvent() pausing a workflow for hours/days with no cron or DB hacks.

- **Category:** Agent orchestration framework + durable execution (HITL via pause/resume)  
- **URL:** https://agentkit.inngest.com/overview  
- **Relevance:** medium  
- **How it works:** AgentKit composes Agents into Networks coordinated by a Router (deterministic rule-based OR LLM-driven) that decides which agent runs next; shared Network State lets agents/tools/router collaborate. It runs on Inngest's durable-execution engine: every step is checkpointed, so a workflow can call step.waitForEvent() to pause indefinitely (mid-run, for human approval or review) and resume automatically when the matching event arrives, with state maintained for it, no polling, cron, or database glue. Local dev uses the Inngest Dev Server dashboard, which traces every run with full logs and per-step I/O for inspection/debugging. Multi-provider (OpenAI/Anthropic/Gemini), MCP tool support, UI streaming.  
- **Value prop:** Makes 'pause an autonomous workflow for a human, possibly for days, then resume exactly where it left off' a one-liner backed by durable infra, and gives a run-inspection dashboard for free. The durability + observability combo is the trust substrate under any inbox.  
- **Tech/stack:** TypeScript framework (npm @inngest/agent-kit), OSS. Runs on Inngest durable-execution platform (cloud or self-hostable engine). Dev Server for local. MCP support.  
- **Pricing:** AgentKit library is open source/free; underlying Inngest platform has its own usage-based pricing (free tier + paid steps/runs) for production.  
- **Target user:** TS developers building production multi-agent or long-running approval-chain workflows (onboarding, payments, reporting) who need durability and observability, not just a chat loop.  
- **Key features:**
    - step.waitForEvent(): pause a running workflow indefinitely for human approval/input; resumes on event with state intact, no cron/polling/DB
    - Durable execution: every step checkpointed; survives crashes, retries, and long external waits (API calls, webhooks, human waits)
    - Networks + Router (deterministic or LLM-based) for multi-agent orchestration with shared State
    - Inngest Dev Server dashboard: local run tracing, full logs and per-step input/output for every agent step
    - Multi-LLM providers, MCP tool support, UI streaming
- **Borrowable for SmbOS:**
    - step.waitForEvent() is the clean mental model for SmbOS's 'pick up later' / scheduled-then-human-gated runs: a run can sit in 'in flight, awaiting you' for days and resume primed. Make the wait a first-class, durable state rather than a re-spawn.
    - The Dev Server run-trace dashboard (per-step I/O + logs) is exactly the legibility SmbOS's 'Recent runs' needs: let the founder expand a completed run and see each step the agent took and what it produced, to build trust in autonomous work.
    - Deterministic-vs-LLM router distinction maps to SmbOS triggers: some plate items should land via deterministic rules (cron/inbox-watch verdicts), others via an LLM deciding 'this needs you' -- label which is which so the human knows how a task got on the plate.
    - Durable checkpointing as the answer to SmbOS's flaky launchd/cron liveness: model each task as a checkpointed step so a missed/killed session doesn't lose state and can be safely resumed.

### gotoHuman - Cloud, platform-agnostic 'agent inbox' SaaS: a no-code customizable review-form builder plus async webhook loop so any agent (n8n, LangGraph, MCP) can request human approval/editing.

- **Category:** Standalone agent inbox / approval-as-a-service (framework-agnostic SaaS)  
- **URL:** https://www.gotohuman.com/  
- **Relevance:** medium  
- **How it works:** Agent calls gotoHuman (SDK/HTTP/MCP/n8n node) to request a review; the item appears in a web Agent Inbox routed to an assignee or the whole team. Reviews are rendered from no-code templates you design: fields for text, images, markdown, JSON and controls like buttons, checkboxes, dropdowns. Reviewers can approve, edit AI output in-place, or trigger a regenerate loop (optionally editing the prompt), and compare versions via 'artifact versioning.' The human's decision returns to the agent via webhook and the workflow resumes. Notifications via Slack and email digests (with optional short-lived public links). Human decisions are captured as 'Agent Memory'/training dataset for improving outputs over time.  
- **Value prop:** You don't have to be on a specific framework or build any UI: design a review form, drop in a webhook, and get a polished team inbox with editing, versioning, routing, and a learning dataset. The customizable-form-per-task-type idea is the standout.  
- **Tech/stack:** Cloud-hosted SaaS (EU infra, GDPR, SOC/ISO certs). Integration-layer SDKs + MCP server + webhooks. Not OSS; not local.  
- **Pricing:** Usage-based; tiers exist (free/entry tiers referenced) but specifics not published on the page reviewed.  
- **Target user:** Builders/teams (often no-code/n8n) who want managed human oversight across heterogeneous agents without building or hosting a review UI.  
- **Key features:**
    - No-code review template builder: per-review-type forms with typed fields (text/image/markdown/JSON) and controls (buttons/checkboxes/dropdowns)
    - In-place editing of AI output + regenerate-with-edited-prompt loops; 'artifact versioning' to compare generated versions before approving
    - Team inbox with per-item or team-wide assignment; Slack + email digest notifications
    - Async webhook loop: request -> human review/edit -> webhook back -> resume
    - Broad integrations: n8n, Make, JS/TS + Python SDKs, LangGraph examples, MCP server, raw HTTP
    - 'Agent Memory': human decisions accumulate into a training dataset to improve future outputs
- **Borrowable for SmbOS:**
    - Per-task-type review templates: instead of one generic plate card, SmbOS could let a SOP define the exact fields/controls a human sees when picking up that task (e.g., an invoice SOP shows amount + recipient as editable fields with an Approve button). Forms typed to the SOP.
    - Edit-in-place + regenerate-with-edited-prompt: when a primed Claude Code session proposes output, let the founder tweak the prompt and re-run from the dashboard rather than dropping to the terminal.
    - Artifact versioning: keep prior versions of a run's output so the human can diff/compare before approving, reinforcing the 'show what changed' trust pattern.
    - 'Agent Memory' from decisions: SmbOS could feed pick-up/dismiss/edit history back into SOPs (via sop-update) so the library learns which tasks the founder always dismisses or always edits the same way.
    - Their explicit 'Agent Inbox' naming + team assignment shows the inbox metaphor is the category-standard mental model; SmbOS's 'On your plate' is the same idea in plainer voice, which is a positioning asset.

### Vercel AI SDK 6 (human-in-the-loop tool approval) - Not a standalone product but the most widely-copied HITL primitive: a single needsApproval flag on a tool plus addToolResult to send the human's decision back and resume the agent loop.

- **Category:** Framework primitive / reference pattern for tool-call approval  
- **URL:** https://ai-sdk.dev/cookbook/next/human-in-the-loop  
- **Relevance:** medium  
- **How it works:** Tools run automatically by default. Set needsApproval: true (or a function of the tool input, so only risky inputs gate) and the model's tool call is intercepted instead of executed. The frontend renders a confirm card on the tool-call message part; on the user's decision, useChat's addToolResult sends the approval/rejection back, and the agent loop continues. Approved patterns/preferences can be stored to skip future prompts. Tool schema is declared server-side but execution can happen in the browser. For longer waits, Vercel pairs this with the Workflow SDK / durable workflows (publish approval-request, wait for approval-response, verify approver permissions, then execute).  
- **Value prop:** Shows the minimum-viable HITL contract: one boolean (or input-predicate) to gate a tool, a render-the-tool-call-as-a-card UI convention, and one call to resume. The input-predicate form is the elegant bit, gate only the risky inputs, not the whole tool.  
- **Tech/stack:** TypeScript, AI SDK 6 + useChat, React/Next.js. OSS (AI SDK is open source). Local or cloud depending on host.  
- **Pricing:** Free / OSS (the SDK). Hosting/model costs separate.  
- **Target user:** TS/React/Next.js developers building chat-style agent UIs who want inline tool-call approval without leaving the conversation.  
- **Key features:**
    - needsApproval: true | (input) => boolean -- per-tool or per-input gating with no custom plumbing
    - Tool calls render as confirm cards in the chat stream; approval continues the agent loop in place
    - addToolResult resumes execution after the human decides; store preferences to auto-approve repeat patterns
    - Pairs with Workflow SDK / durable workflows for long-running approvals with permission checks
- **Borrowable for SmbOS:**
    - The input-predicate gate (needsApproval as a function of the args, not a global on/off) is the cleanest answer to SmbOS's binary 'launch permission' setting: gate a SOP run only when args cross a threshold (budget over $X, external recipient, production target).
    - Render-the-action-as-a-card convention: SmbOS's plate items ARE these confirm cards; keep the proposed action's concrete args visible on the card so approval is informed, not blind.
    - 'Store approved patterns to skip future prompts' is the same learned-trust idea as HumanLayer, expressed as a per-tool preference, simple enough for SmbOS to implement per-SOP without ML.

### ServiceNow AI Control Tower (enterprise 'control tower' pattern) - The enterprise incumbent framing of this category: a centralized governance/monitoring console over all agent activity, with policy-gated approvals, identity, and full auditability via MCP/Action Fabric.

- **Category:** Enterprise agent governance / control-tower console  
- **URL:** https://www.servicenow.com/  
- **Relevance:** low  
- **How it works:** AI Control Tower sits above all agent activity as a governance plane: agents trigger flows, playbooks, approvals, and catalog actions that run through the Control Tower, identity-verified and fully auditable. Action Fabric exposes the platform's system-of-action to any external AI agent via an MCP server, so autonomous agents can invoke governed workflows (with approvals) without a traditional UI. The pattern emphasizes policy-driven routing: a request goes to a human only when policy says so, and 'progressive delegation' expands an agent's autonomy as the user's own approval history builds trust.  
- **Value prop:** Shows where this category goes upmarket: not just an inbox but a governed, audited, identity-aware command center where approvals are policy-driven and autonomy is earned. The 'progressive delegation' and 'approve only when policy says' ideas are directly transplantable.  
- **Tech/stack:** Proprietary enterprise SaaS on the ServiceNow platform; MCP server (Action Fabric) for agent integration. Cloud, closed.  
- **Pricing:** Enterprise licensing (not published; high-touch sales).  
- **Target user:** Enterprises governing fleets of agents across functions; not SmbOS's solo-operator user, but the conceptual ceiling of the category.  
- **Key features:**
    - Centralized governance/monitoring across all agent activity (the 'control tower' single pane)
    - Policy-gated approvals: route to a human only when policy requires; otherwise auto-execute
    - Identity-verified, fully auditable execution of every agent-triggered action
    - Action Fabric: MCP-server exposure of governed workflows to any external agent
    - Progressive delegation: autonomy expands as the user's approval history builds trust
- **Borrowable for SmbOS:**
    - 'Progressive delegation' is the single most transferable idea: start a new SOP requiring approval, then expand its autonomy automatically as the founder's approval history accumulates. This is the productized version of SmbOS's launch-permission + budget settings and directly counters automation-bias by reserving attention for un-trusted SOPs.
    - 'Route to a human only when policy says so' reframes SmbOS's plate: most runs should NOT hit the plate; the plate should be the policy-defined exception set, keeping 'on your plate' short and high-signal.
    - Auditability as a trust feature: a per-run audit trail (what ran, with what args, what it changed, who approved) makes autonomous work legible; SmbOS 'Recent runs' should be an audit log, not just a status list.
    - The single-pane 'control tower' framing validates SmbOS's command-center dashboard as the right primary surface, but SmbOS's edge is plain-language and solo-operator scale, not enterprise governance chrome, keep that positioning.



## Cluster: SOP & process-documentation tools

_Three structural patterns cut across the whole cluster, and each is a wedge for SmbOS. (1) Every tool stops at DOCUMENT/ANSWER; none EXECUTE. Scribe/Tango/Guidde capture-to-doc, Tettra/Slite answer-from-doc, Trainual/SweetProcess/Notion store-and-assign, Process Street is the only one that 'runs' a procedure, and even that is human-clicked checklists. SmbOS is the only one where the SOP is run by an autonomous agent, and the do-loop (plate -> pick up -> primed session -> reports completion) is genuinely novel in this space. (2) Staleness/rot is the universal complaint, regardless of capture quality: Scribe screenshots break on any UI change, Notion rots without discipline, Whale/Tettra/Slite all had to bolt on owner+approval+verification+review-cadence machinery to fight it. SmbOS's structural answer is different and stronger: SOPs that are exercised on every run get their drift caught by use, not by a separate audit ritual, AND plain markdown read by an agent doesn't break when a button moves (Scribe's core weakness). (3) The 'SOPs as AI-agent context' thesis is now validated externally, Whale explicitly markets 'Train AI agents' and Slite/Tettra ground answers strictly in cited KB content, but every competitor does it as a cloud add-on on top of locked-in storage. SmbOS does it natively: plain files the agent reads, a SessionStart hook that injects the protocol, an MCP server that exposes the library. The recurring trust machinery worth adopting wholesale is the governance triad (per-SOP owner + approval status + change log) plus update-goes-through-review-before-live, plus citing-which-SOP-was-followed and escalating-to-the-owner-when-no-SOP-covers-it; together these make autonomous runs legible, which is the single thing that lets a solo founder actually trust the plate/in-flight model. Finally, per-seat pricing and free-tier rug-pulls (Process Street's 5-seat floor, Tango's tightened free tier, Whale's token metering) are the loudest market resentments, so SmbOS's single-operator, file-owned, no-seat, local-first model is clean counter-positioning for exactly its target user._

### Trainual - Cloud SOP + onboarding/training platform that turns processes into assigned, trackable training paths with quizzes and e-signatures.

- **Category:** SOP & training (LMS-leaning)  
- **URL:** https://trainual.com  
- **Relevance:** medium  
- **How it works:** You build a content tree: Subjects (e.g. 'Sales Process', 'Customer Support Intake') filed under departments/roles, each holding step content (text, images, embedded video, screen recordings). You assign Subjects to roles or groups, then track completion: viewed / completed / quiz-passed / e-signed. The core loop is manager-authored content -> assign to person/role -> employee reads & acknowledges -> dashboard shows progress. Fully cloud/SaaS, browser + mobile app. No local files, no OSS. AI features generate draft content and quizzes.  
- **Value prop:** One place where every process is documented, assigned to the right role, and provably acknowledged. Sells the 'business that runs without you' dream to SMB owners.  
- **Tech/stack:** Cloud SaaS, web + native mobile. Closed source. Pricing per-seat annual.  
- **Pricing:** Train ~$124/mo for 10 users, Scale ~$249/mo for 20; ~$3.75-$5/additional seat; annual commitment. Multiple tiers (Core/Pro/Premium/Enterprise) gate eSign, training paths, storage.  
- **Target user:** Non-technical SMB owners and ops managers (10-100 employees) standardizing onboarding/training. ~64% of G2 reviewers are small business.  
- **Key features:**
    - Role/department content tree with assignment
    - Completion tracking, quizzes, e-signatures for compliance
    - Progress dashboards showing who has/hasn't done their training
    - AI content + quiz generation
    - Mobile app for frontline staff
- **User feedback:**
    - (positive) G2 (987 reviews, 4.7/5): Clean structured UI, progress tracking and e-signatures praised for keeping onboarding consistent across locations.
    - (negative) SweetProcess comparison teardown (sweetprocess.com/trainual-vs-sweetprocess): Dashboard is confusing because Trainual must be heavily customized to fit your company; getting buy-in and learning the platform takes real time.
    - (negative) Shopify app review: 'Far too expensive for a small business... not worth the investment' at ~$50/seat-equivalent.
    - (mixed) Capterra / People Managing People review: Limited mobile polish and advanced features locked behind higher tiers; minor friction in renewal flow.
- **Borrowable for SmbOS:**
    - The 'business runs without you' framing resonates with solo founders. SmbOS's plate/in-flight model is the agent-executed version of that promise.
    - Assignment + acknowledgement as a trust primitive: Trainual proves a human saw the SOP. SmbOS could surface 'this run followed SOP vX, owner approved launch permission' as the analogous provable trail.
    - Role/department tree is heavy chrome for a solo operator. SmbOS's flat markdown library in ~/sops is the right counter-positioning: zero taxonomy overhead.

### Scribe - Browser/desktop extension that watches you do a task once and auto-generates a step-by-step guide with annotated screenshots.

- **Category:** Auto-capture step guides  
- **URL:** https://scribe.com  
- **Relevance:** high  
- **How it works:** Click record, perform the workflow; Scribe captures every click, types the action text, and grabs/annotates a screenshot per step. On stop it emits an editable guide (reorder steps, edit text, redact). Desktop apps (Mac/Windows, paid) extend capture beyond the browser to native apps. AI auto-writes titles/descriptions and auto-blurs anything resembling PII. Cloud-hosted guides with sharing/embed; SOC2. Closed source.  
- **Value prop:** Documentation as a byproduct of doing the work once, instead of a separate writing task. 'Capture, don't author.'  
- **Tech/stack:** Browser extension + Mac/Windows desktop capture, cloud backend. Closed source. Freemium.  
- **Pricing:** Free tier (limited # of scribes, browser-only); Pro per-seat (~$23-29/user/mo range); Enterprise custom with desktop capture + admin.  
- **Target user:** Ops, support, and CS teams documenting SaaS UI workflows; non-technical staff who can't write docs from scratch.  
- **Key features:**
    - One-pass capture of clicks -> screenshots + step text
    - Auto-redaction/blur of sensitive fields
    - AI-generated titles/descriptions
    - Desktop capture for non-browser apps (paid)
    - Embed/share, SOC2
- **User feedback:**
    - (positive) Capterra / Chrome Web Store reviews: Repeatedly called fastest way to document; non-technical staff produce clean guides with no missing steps because capture is automatic.
    - (negative) G2 reviews (via Glitter/ngram teardowns): When the app UI changes you re-record everything; screenshots go stale and maintenance is a real burden.
    - (negative) G2 reviews: Auto-generated step text captures WHAT happened but not WHY; lacks context and needs manual editing to be useful to someone who doesn't know the process.
    - (negative) Scribe support/community: Terminal/command-line output isn't captured; over-eager auto-blur redacts non-sensitive text that looks like a name; extra unwanted clicks get recorded.
- **Borrowable for SmbOS:**
    - Capture-don't-author is directly relevant to the importer: SmbOS turns past session history / brain-dumps into draft SOPs. Scribe proves byproduct-capture beats blank-page authoring.
    - The 'WHAT not WHY' complaint is the exact gap SmbOS can win on: a session transcript captures the reasoning/decisions, not just clicks, so SmbOS-generated SOPs can encode intent, not just steps.
    - Staleness/re-record pain is Scribe's core weakness. Markdown SOPs that an agent reads (vs pixel screenshots) don't break when a UI moves a button. Lean into 'your SOPs don't rot when the UI changes.'
    - Terminal-not-captured is a literal gap for a terminal-living founder. SmbOS operating inside Claude Code captures exactly what Scribe can't.

### Tango - Free-leaning Chrome extension that auto-generates how-to guides from your clicks, with optional in-app interactive walkthroughs.

- **Category:** Auto-capture step guides  
- **URL:** https://tango.ai  
- **Relevance:** medium  
- **How it works:** Turn on the extension, do the process; each click becomes a step with auto-captured screenshot + text, URLs recorded. Produces an editable guide and can also push 'live' interactive walkthroughs that overlay the real app to guide a user through. Annotation/blur editing. Cloud, closed source.  
- **Value prop:** Near-zero-effort guide creation plus the ability to guide someone through the live software, not just show them a doc.  
- **Tech/stack:** Chrome extension + cloud. Closed source. Freemium (formerly very generous free tier).  
- **Pricing:** Free tier (reduced over time); paid tiers for walkthroughs, analytics, larger teams.  
- **Target user:** SMB ops/support documenting browser SaaS workflows; teams wanting guided in-app onboarding.  
- **Key features:**
    - Auto step capture (clicks, URLs, screenshots)
    - Interactive in-app walkthroughs overlaid on the live product
    - Annotations, blur, editing
    - One-click page snapshot/video
    - 4.7/5 extension rating
- **User feedback:**
    - (positive) Product Hunt / Chrome Web Store (4.7/5): Praised as fast and simple for tutorials; one-click capture lowers the barrier to documenting.
    - (negative) Droidcrunch / extension reviews: Backlash over pricing-model changes and feature limits as the once-generous free tier tightened.
- **Borrowable for SmbOS:**
    - Interactive walkthrough overlaid on the live app = legibility of an action in context. SmbOS's dashboard 'In flight' view is the agent analogue: show the running session against the SOP it's following, step by step.
    - Tango's free-tier-then-paywall backlash is a cautionary tale: SmbOS being local-first, file-owned, and plugin-based avoids the rug-pull resentment of cloud SaaS pricing changes.

### Process Street - Checklist/workflow engine where SOPs are runnable templates with conditional logic, approvals, and automation, not just static docs.

- **Category:** Runnable workflow/process automation  
- **URL:** https://process.st  
- **Relevance:** high  
- **How it works:** You build a template (an SOP as an ordered task list). Running it spawns a 'checklist' instance someone works through. Form fields, conditional logic (branch/show/hide tasks based on answers), role assignment, approval steps, due dates, and automations (webhooks, integrations, scheduled runs) make each run dynamic. The key distinction vs doc tools: a procedure is executed and tracked as a live instance, with branching and approvals built in. Cloud SaaS, closed source.  
- **Value prop:** Procedures you actually run and complete, with branching and human approval gates, not docs that sit unread.  
- **Tech/stack:** Cloud SaaS, integrations + webhooks/API. Closed source. Per-seat with high seat floors.  
- **Pricing:** Startup ~$100/mo but bills for a 5-user minimum even if 2 use it; higher tiers for advanced automation; widely cited as the loudest complaint.  
- **Target user:** Ops teams running repeatable processes (onboarding, compliance, client delivery) who need accountability per run.  
- **Key features:**
    - Templates -> runnable checklist instances
    - Conditional logic / dynamic branching on form answers
    - Approval tasks (human sign-off gates inside a run)
    - Scheduled recurring runs + webhook/integration automations
    - Run history and completion tracking
- **User feedback:**
    - (positive) The Digital Project Manager / SolidGrowth reviews: Conditional logic is powerful once learned: 'the possibilities are endless' for dynamic branching processes.
    - (negative) Process Street review roundups: Pricing is the loudest complaint: 5-seat minimum forces paying for unused seats; advanced automation still lags dedicated tools; UI can feel slow.
    - (mixed) TDPM / Glitter alternatives teardown: Advanced users hit a ceiling on complex automation and find branching setup fiddly compared to purpose-built workflow engines.
- **Borrowable for SmbOS:**
    - This is the closest conceptual cousin: SOP-as-runnable-instance. SmbOS's 'Run/Queue/Prepare a Procedure' and 'Recent runs' map 1:1 to Process Street's template->checklist->history, but agent-executed instead of human-executed.
    - Approval tasks INSIDE a run are exactly SmbOS's human-in-the-loop gate: a step that pauses and waits for the owner. Borrow the pattern of inline approval checkpoints surfaced on 'your plate'.
    - Conditional logic = SOPs that branch on runtime answers. SmbOS SOPs in markdown could encode branch conditions the agent evaluates, keeping runs dynamic without a visual builder.
    - Per-seat/seat-floor resentment is the dominant complaint. SmbOS's single-operator, no-seat, local model is a clean wedge for solo founders priced out of these tools.

### SweetProcess - Straightforward SOP + process + policy documentation tool aimed at delegation, with a flatter learning curve than Trainual.

- **Category:** SOP documentation + delegation  
- **URL:** https://sweetprocess.com  
- **Relevance:** medium  
- **How it works:** Document Procedures (step-by-step), Processes (procedures chained), and Policies in one editor; assign to team members as tasks; track who completed what. Emphasis on fast onboarding and a single dashboard rather than a customizable taxonomy. Has its own AI draft generation. Cloud, closed source.  
- **Value prop:** Get documented and delegating fast, without the configuration overhead of a training LMS.  
- **Tech/stack:** Cloud SaaS, closed source.  
- **Pricing:** From ~$99/mo (team of up to 20), flatter than Trainual; positioned explicitly as cheaper than Trainual's $249.  
- **Target user:** SMB owners who want to offload/delegate work and need clean process docs without LMS complexity.  
- **Key features:**
    - Procedures / Processes / Policies model
    - Task assignment + completion tracking
    - Flat-fee-ish pricing vs per-seat creep
    - AI procedure drafting
    - Public/exportable knowledge base
- **User feedback:**
    - (positive) SweetProcess self-published comparisons (bias noted) + SourceForge: Easier to get started than Trainual; managers and end-users onboard fast with a single clear dashboard.
    - (mixed) Waybook / Glitter SOP roundups: Solid for documentation/delegation but lighter on training, automation, and analytics than competitors.
- **Borrowable for SmbOS:**
    - Procedures-chained-into-Processes is a clean mental model: a higher-order SOP that composes smaller SOPs. SmbOS could let a multi-stage 'work' (plan/build/review/ship, which it already tracks) reference and run sub-SOPs.
    - 'Document fast, delegate fast' is the human version of SmbOS's pitch ('document fast, let the agent run it'). The delegation framing is owner-friendly language worth echoing.

### Whale (usewhale.io) - AI SOP software that captures processes, auto-builds training, and explicitly positions SOPs as the knowledge layer for training AI agents.

- **Category:** AI SOP + training + agent-context  
- **URL:** https://usewhale.io  
- **Relevance:** high  
- **How it works:** Record a process (or upload a video) and 'Alice', Whale's AI, transcribes spoken steps into a numbered written SOP with the video embedded. SOPs get an owner, approval status, and change log; updates flow through an expert-review cycle before going live. AI builds quizzes/training flows and auto-assigns. In-tool search surfaces the right answer inside whatever app the team is using. Notably markets a 'Train AI agents' use case: SOPs as the grounding/context for company AI assistants. Cloud, closed source, token-metered AI.  
- **Value prop:** Your documented processes become both human training AND the trustworthy context that powers your AI agents.  
- **Tech/stack:** Cloud SaaS, token-metered AI features. Closed source.  
- **Pricing:** Per-seat tiers; AI features token-metered (a documented gotcha).  
- **Target user:** SMBs/franchises standardizing ops; increasingly teams wanting SOPs to ground internal AI assistants.  
- **Key features:**
    - AI (Alice) turns video/voice into structured SOPs
    - Per-SOP owner + approval status + change log (governed updates)
    - Expert-review cycle before an SOP goes live
    - AI-generated tests + auto-assigned training flows
    - 'Train AI agents' positioning: SOPs as agent context
- **User feedback:**
    - (positive) Whale marketing (cite-with-skepticism) + G2: Claims of ~50% faster onboarding and ~70% less documentation time by connecting training to live processes; governance (owner/approval/changelog) praised.
    - (negative) Research.com / G2 reviews: AI features used freely during trial burn through token allocation fast on paid plans, then become unavailable until reset.
- **Borrowable for SmbOS:**
    - Whale is the closest strategic competitor to SmbOS's thesis: SOPs as the grounding context for AI agents. Validation that 'SOPs -> agent context' is a real market, but Whale does it as cloud add-on; SmbOS does it natively (SessionStart hook injects the SOP protocol, MCP server exposes the library). That's a sharper, terminal-native execution.
    - Governance triad: every SOP has an OWNER + APPROVAL STATUS + CHANGE LOG, and edits pass an expert-review cycle before going live. SmbOS should attach this to agent-run SOPs: which SOP version a run used, who approved it, what changed since. Critical for trust in autonomous runs.
    - Update-goes-through-review-before-live is a strong human-in-the-loop pattern for SmbOS's sop-update/sop-review skills: drafted changes land on the plate for owner approval before becoming the live SOP an agent will follow.
    - Token-metering resentment validates SmbOS's budget/cost-report feature (sop-triggers) being owner-controlled and transparent rather than a surprise paywall.

### Guidde - AI that turns a screen capture into a narrated, professional how-to VIDEO in seconds (GPT-written script + synthetic voiceover).

- **Category:** AI video documentation  
- **URL:** https://guidde.com  
- **Relevance:** low  
- **How it works:** Browser extension 'Magic Capture' records clicks/scrolls; AI (GPT-based) generates a step storyline and a polished video with auto voiceover (100+ voices/languages) in ~2 seconds. Edit script/steps, then share or embed into Zendesk/Salesforce/Confluence/Teams/LMS. Cloud, closed source.  
- **Value prop:** Professional training video without a studio: capture once, AI narrates and produces.  
- **Tech/stack:** Browser extension + cloud AI (GPT). Closed source. Freemium.  
- **Pricing:** Free (25 videos); Pro from ~$9.90/mo annually (also cited $23-50/creator); Enterprise custom.  
- **Target user:** Support/CS/enablement teams producing customer- and employee-facing how-to video at volume.  
- **Key features:**
    - Magic Capture -> AI storyline -> finished video fast
    - 100+ AI voices/languages for narration
    - Deep embeds into support/CRM/LMS tools
    - Free tier (up to 25 videos)
- **User feedback:**
    - (positive) Research.com / Today Testing reviews: Fast, polished output and broad integrations make it indispensable for high-volume how-to content.
    - (mixed) Review roundups: Video-first output is heavier to maintain and less skimmable/searchable than text SOPs when processes change.
- **Borrowable for SmbOS:**
    - Mostly a counter-positioning lesson: video is the WRONG format for a terminal-living founder and for agent consumption. SmbOS's plain-markdown SOPs are both human-skimmable and machine-readable; video is neither for an agent.
    - The 'finished artifact in seconds from a raw capture' speed bar is worth matching in the importer: brain-dump in, clean draft SOP out, fast, with minimal editing.

### Tettra - Slack-first internal knowledge base whose AI bot 'Kai' answers questions from your wiki and nudges you to capture answers as new pages.

- **Category:** AI knowledge base / Q&A  
- **URL:** https://tettra.com  
- **Relevance:** medium  
- **How it works:** Connect Slack/Teams; author content in a simple editor (categories/subcategories). Ask a question in Slack or Tettra and Kai searches the KB and answers inline with sources; if it can't answer, it routes to the right human expert. Kai scans Slack for useful Q&A and prompts you to save them as new KB pages. Knowledge-automation: owners, review cadences, and verification badges keep pages fresh. Cloud, closed source.  
- **Value prop:** Answers where people already work (Slack), and a KB that maintains its own freshness via ownership + verification.  
- **Tech/stack:** Cloud SaaS, Slack/Teams integration. Closed source. No free plan.  
- **Pricing:** No free plan; per-seat paid tiers.  
- **Target user:** Slack-first small/mid teams tired of stale docs and repeated questions.  
- **Key features:**
    - Kai AI bot answers from KB inline in Slack, with sources
    - Routes unanswered questions to the right expert
    - Auto-suggests capturing Slack threads as new pages
    - Content owners + review cadence + verification badges
    - FAQ generation from existing content
- **User feedback:**
    - (positive) Product Hunt / knowledgebasesoftware.org: FAQ tool, verification workflow, and simple editor praised for keeping a reliable, current wiki; strong for Slack-native teams.
    - (negative) Compare Giants / review roundups: No free plan, limited customization, and value collapses if your team doesn't live in Slack.
- **Borrowable for SmbOS:**
    - Verification badges + content owners + review cadence directly inform SmbOS's sop-review skill (find stale/drifted SOPs). Surface a freshness/verification state per SOP on the dashboard Procedures library.
    - Kai's 'answer with sources / route to a human if I can't' is a clean honesty pattern. SmbOS agents should cite which SOP they followed and escalate to the owner's plate when no SOP covers the task, rather than improvising silently.
    - Capture-from-the-stream-of-work (Kai turns Slack threads into pages) mirrors SmbOS's importer turning session history into SOPs. Make it a proactive nudge: 'this run had no SOP, want to capture it as one?'

### Slite - Self-maintaining AI knowledge base whose 'Ask' synthesizes a cited answer across all docs, and which proactively flags stale/duplicate content.

- **Category:** AI knowledge base / Q&A  
- **URL:** https://slite.com  
- **Relevance:** medium  
- **How it works:** Author docs in a clean editor; 'Ask' answers natural-language questions by reading across the whole KB and synthesizing a direct, cited answer (only from your content, no hallucinated outside info). 'Self-maintaining' features flag outdated/duplicate docs and prompt cleanup, so the KB doesn't rot. Cloud, closed source. Notably has NO public API.  
- **Value prop:** The knowledge base that does the upkeep you keep putting off: trustworthy cited answers + automatic staleness detection.  
- **Tech/stack:** Cloud SaaS, closed source, NO developer API (cited limitation).  
- **Pricing:** Per-seat paid tiers; free/trial tier.  
- **Target user:** Small/mid teams wanting trustworthy internal answers without a doc-maintenance burden.  
- **Key features:**
    - Ask: cited, synthesized answers grounded only in your KB
    - Self-maintaining: flags outdated/duplicate docs for cleanup
    - Clean editor, fast onboarding ('just ask Slite')
    - Source citations on every answer
- **User feedback:**
    - (positive) Product Hunt / DeClom review: Ask is the standout: cited cross-doc answers cut new-hire onboarding from a week of questions to 'just ask Slite'.
    - (negative) Efficient App / review roundups: Slower performance, clunky search for some, and notably NO developer API so you can't build custom integrations on it.
- **Borrowable for SmbOS:**
    - 'Answers grounded ONLY in your content, with citations' is the trust bar for agent output. SmbOS runs should be traceable to specific SOP text, never free-improvised, and say so.
    - 'Self-maintaining: flag stale/duplicate docs' is exactly SmbOS's sop-review job-to-be-done. Make drift/overlap/staleness detection proactive and surfaced on the dashboard, not a manual audit.
    - The no-API complaint is instructive: SmbOS's plain markdown + MCP server is the opposite stance, fully programmable and agent-addressable. That openness is a feature to advertise.

### Notion-as-SOP - Using Notion's databases + templates as a DIY SOP system: flexible, cheap, but static docs with no execution or assignment-enforcement layer.

- **Category:** DIY / general docs as SOP  
- **URL:** https://notion.com/templates/category/standard-operating-procedure-sop  
- **Relevance:** high  
- **How it works:** Owners adopt SOP templates that create a database of procedure pages (relate/filter/visualize as board/timeline/calendar; views per role/division). Each SOP page is step content + owner + change-log section by convention. No runtime: nothing 'runs' a procedure or enforces completion; it's a structured doc store. Cloud, closed source, huge template marketplace.  
- **Value prop:** A free-form, familiar, cheap home for SOPs you can shape any way you want, no dedicated tool needed.  
- **Tech/stack:** Cloud SaaS + AI. Closed source. Has an API (unlike Slite).  
- **Pricing:** Notion's standard per-seat tiers; templates often free/cheap.  
- **Target user:** Founders and small teams already in Notion who don't want another tool/subscription.  
- **Key features:**
    - Database views filtered by role/division
    - Massive marketplace of SOP templates
    - Relate procedures to projects/people
    - Notion AI for drafting/search
- **User feedback:**
    - (positive) Notion Mastery / Taina tutorials: Database views per role and aesthetic, searchable SOPs make Notion a flexible no-extra-cost SOP home.
    - (negative) Notion SOP guidance + general critique: Static docs that are easy to over-build and let rot: no execution, no enforced acknowledgement, jargon/over-detail templates hurt clarity; freshness depends entirely on manual discipline.
- **Borrowable for SmbOS:**
    - Notion-as-SOP is the DEFAULT SmbOS competes against for technical founders. The wedge: Notion SOPs are inert docs a human must remember to follow; SmbOS SOPs are agent-executable and auto-injected at session start. Lead with 'your SOPs actually run.'
    - Static-and-rots is the universal failure mode across this whole cluster (Scribe screenshots, Notion discipline, Slite/Tettra needing verification). SmbOS's edge is SOPs that are exercised every run, so drift is caught by use, not by audit.
    - Files-you-own (markdown in ~/sops) vs locked-in cloud DB is a real positioning advantage for a terminal founder: greppable, version-controllable, AI-editable, no per-seat tax, no vendor lock-in.



## Cluster: AI automation / agent builders for SMB ops

_Two structural failure modes recur across the whole cluster and define SmbOS's opening: (1) Credit-metered pricing is the #1 complaint everywhere (Lindy 'expensive' = 42 mentions, Gumloop unpredictable Expert-tier burn, Bardeen's 'rug-pull' backlash, Zapier Agents 'costs quite a bit more'). A local-first, own-your-compute tool aimed at a technical solo founder sidesteps the single biggest source of category pain, and SmbOS's plain-language budget/launch-permission Settings is the anti-credit-anxiety stance, provided cost is shown BEFORE a run, not billed after. (2) Legibility of autonomous work is broken even in mature tools: n8n silently shows 'success' while writing partial data and stopping mid-flow; Lindy agents 'vanish from the dashboard'; Bardeen/Gumloop give poor error feedback. SmbOS's command-center framing (On your plate / In flight / Coming up / Recent runs) plus the inflight-session-liveness work is a direct answer: every session must always be visible with a real, verified completion state and never silently disappear or false-report done. On the human-in-the-loop axis, Relay.app is the sharpest analogue and the one to study most: approval/review as a native, droppable step with an 'approve / revise / send-back' action triad and interactive Slack/email notifications that let the human act without returning to the dashboard. SmbOS already has put-back/done/dismiss on the plate; the missing verb is 'revise and re-run,' and the missing config is per-procedure 'auto-run vs always-pause' (Relay's one-toggle AI review) layered on top of the global launch permission. Finally, the cold-start problem is solved everywhere by templates (Lindy 100+, Gumloop 180+, Zapier templates) - SmbOS's seeded starter SOP pack and Procedures library is the equivalent and should never present an empty plate on day one._

### Zapier Agents (+ Central) - AI teammates that act autonomously across 8,000+ apps from natural-language instructions, with a 'Needs action' approval queue.

- **Category:** AI agent builder (cloud, no-code, integration-first)  
- **URL:** https://zapier.com/agents  
- **Relevance:** high  
- **How it works:** Core loop is trigger -> instructions -> tools -> action -> logged activity. You build an agent by describing intent in plain English; a prompt assistant rewrites/optimizes the instructions (editable). You connect apps (triggers + actions from Zapier's 8,000-app library), attach data sources (Google Drive, Notion, Airtable docs as a knowledge base), and pick triggers: on-demand, scheduled, fired from a Zap, or from app events. The agent uses an LLM to decide which tools to call rather than following rigid if-then rules. All runs land in an activity/history dashboard. 'Zapier Central' was the earlier workbench brand that folded into Agents; launched Jan 2025, GA Dec 2025.  
- **Value prop:** Lowest-friction way to get an autonomous agent acting across the apps a business already uses, with the largest integration catalog and a built-in human-approval queue so you can dial oversight up or down.  
- **Tech/stack:** Cloud-only SaaS, proprietary. LLM-backed (model abstracted from user). No self-host, no OSS.  
- **Pricing:** Usage/credit-based add-on on top of Zapier plans; Agents and Tables called out by reviewers as meaningfully more expensive than core Zaps. No flat published agent price.  
- **Target user:** Non-technical operators and ops teams already on Zapier who want AI decisioning layered onto existing automations.  
- **Key features:**
    - Natural-language agent creation with a prompt-optimizer step
    - 8,000+ app integrations as agent tools
    - Data sources / knowledge base from Drive, Notion, Airtable
    - 'Needs action' dashboard section: agent pauses and requests info, approval, or re-auth
    - Draft-approval before sensitive actions (send email, update CRM)
    - Triggers: on-demand, scheduled, from Zaps, from app events
    - Full activity history log for every run
- **User feedback:**
    - (positive) Capterra / Trustpilot (Zapier general): Core automation praised as reliable and easy; complex automations without code, minimal learning curve.
    - (mixed) Cybernews review 2026: Agents and Tables 'cost quite a bit more' than core Zapier; cost concerns specifically around the newer agent functionality.
    - (negative) Trustpilot (older): Connections occasionally disconnect without reason, a trust issue for unattended autonomous runs.
- **Borrowable for SmbOS:**
    - The 'Needs action' queue is exactly SmbOS's 'On your plate' pattern: agent pauses and surfaces info-needed / approval / re-auth as discrete actionable items. Validate splitting plate items by reason (needs-approval vs needs-info vs broken-auth).
    - Prompt-optimizer step: when a user captures an SOP or task, offer to rewrite the brief into a stronger primed prompt before the session opens, and let them edit it.
    - Draft-before-send gating tied to action sensitivity (irreversible/external actions require approval; internal ones don't), driven by Settings 'launch permission'.
    - Attach data sources to a task as a lightweight knowledge base rather than only relying on the SOP markdown.

### Lindy - Conversational no-code builder for always-on AI 'employees' triggered by email/Slack/calendar events.

- **Category:** AI agent builder (cloud, no-code, vertical assistants)  
- **URL:** https://www.lindy.ai  
- **Relevance:** high  
- **How it works:** You describe an agent in plain English and Lindy generates it (trigger + actions) rather than drawing a flowchart. Triggers are event-based (email received, scheduled, calendar event); the agent then runs a sequence of tool calls and AI steps. 100+ templates seed common roles (inbox manager, meeting notetaker, lead qualifier, phone agent). Credit-metered per action: simple action ~1 credit, complex multi-step research 5-10+. Includes a 1M-character knowledge base on the free tier.  
- **Value prop:** Turn a described role into a running, always-on assistant in minutes, with templates that make the first agent feel concrete.  
- **Tech/stack:** Cloud-only proprietary SaaS, LLM-backed, no self-host/OSS.  
- **Pricing:** Free 400 credits/mo (no premium actions); Starter $19.99/2,000 credits; Pro $49.99/5,000 credits; Business custom/unlimited. Credit overages are the dominant complaint.  
- **Target user:** SMB owners and ops people who want a packaged 'AI employee' without building workflows.  
- **Key features:**
    - Conversational agent generation ('describe it, Lindy builds it')
    - 100+ role templates
    - Event triggers (email, Slack, calendar, schedule)
    - 1M-character knowledge base even on free tier
    - AI phone agent, lead gen, meeting notes as packaged agents
    - 4.7/238 reviews on SelectHub
- **User feedback:**
    - (negative) prospeo.io review aggregation: 'Expensive' is the single most common complaint (42 mentions); credit system makes real cost unpredictable, bill can exceed listed price with inadequate overage warnings.
    - (negative) theaffordablewebguy.com $100 test: AI phone agent never worked despite multiple rebuilds; lead gen failed on config errors; an agent vanished from the dashboard; credits consumed during troubleshooting.
    - (mixed) annikahelendi.substack.com honest review: Loved for accessibility and templates, but free plan is 'basically useless' because almost every useful workflow needs premium (credit-heavy) actions.
    - (positive) Trustpilot / SelectHub: 4.7 rating; users praise the no-code conversational builder and template quality.
- **Borrowable for SmbOS:**
    - Templates as the cold-start fix: SmbOS's 'Procedures' library should ship a seeded starter pack of ready-to-run SOPs so the plate is never empty on day one.
    - Lindy's credit-anxiety is a cautionary tale: SmbOS's Settings 'budget' should show projected/spent cost per run transparently and warn BEFORE a run blows the budget, not after.
    - 'Agent vanished from dashboard' is a legibility failure SmbOS can beat: every session/run must always be visible in 'In flight'/'Recent runs' with a clear terminal state, never silently disappear.

### n8n (AI agents) - Fair-code, self-hostable visual workflow engine with native LangChain AI nodes, autonomous agents, memory, and vector stores.

- **Category:** Workflow automation engine + AI agent framework (self-host or cloud, source-available)  
- **URL:** https://n8n.io/ai-agents/  
- **Relevance:** high  
- **How it works:** Visual node canvas where AI is a first-class primitive: LLM chains, autonomous agents with tool use, persistent memory, vector stores, embeddings, document loaders (70+ AI nodes as of n8n 2.0, Jan 2026, with native LangChain). Self-host via Docker (needs Postgres/Redis for production) on a cheap VPS for effectively unlimited executions, or use n8n Cloud. Agents make decisions and call tools mid-workflow; you can drop to custom code nodes anywhere.  
- **Value prop:** Maximum control and lowest marginal cost for technical users: own the infra, own the data, build arbitrarily complex AI workflows, pay for a VPS instead of per-task credits.  
- **Tech/stack:** Node/TypeScript, self-hostable via Docker (Postgres + Redis), source-available (Sustainable Use License). LangChain under the hood. Local-first option is the differentiator.  
- **Pricing:** Self-host free (VPS cost only; cited ~12x cheaper than cloud, 80-90% cheaper than Zapier at volume). n8n Cloud is execution-metered.  
- **Target user:** Technical builders / developers who want to self-host, control data, and avoid per-task credit pricing. Closest persona to SmbOS's real user.  
- **Key features:**
    - Self-host (Docker) or cloud; data stays local when self-hosted
    - 70+ AI nodes, native LangChain, persistent agent memory, vector stores
    - 400+ integrations + arbitrary custom-code nodes
    - Execution-based pricing (not per-task) drastically cheaper at volume
    - Source-available 'fair-code' license
    - Visual canvas with branching, error handling, conditional logic
- **User feedback:**
    - (positive) dev.to / community guides: Self-hosting + low-code is 'a developer's dream'; $5 VPS handles unlimited executions, ~12x cheaper than cloud.
    - (negative) dev.to onestardao pitfalls writeup: AI/LLM chains break in multi-step reasoning (context lost mid-chain); RAG returns irrelevant chunks; errors usually from a prior node emitting unexpected text/JSON shape.
    - (negative) educative.io / community: Silent failures: workflows >15-20 nodes stop midway but show 'success'; partial data written downstream; webhooks fire inconsistently; unclear error messages.
    - (negative) Talos / Infosecurity Magazine: Threat actors misuse n8n for malicious automation; two max-severity vulns let authenticated users take over server and steal stored credentials (self-host and cloud).
    - (mixed) Cipher Projects / community comparisons: Self-hosting requires real DevOps (Docker/Postgres/Redis); debugging large flows is messy.
- **Borrowable for SmbOS:**
    - The silent-success-with-partial-data failure mode is the strongest argument for SmbOS's design: sessions must report a real completion state back, and the dashboard should distinguish 'reported done' from 'went quiet'. The inflight-session-liveness work directly addresses this gap n8n still has.
    - Local-first / own-your-data positioning is shared DNA: lean into it as the trust story vs cloud credit-metered competitors.
    - 'Error usually from the previous step's unexpected output shape' argues for SmbOS to validate/normalize what a session hands back before marking a task done.
    - Execution-based (not per-task-credit) cost framing resonates with the technical solo founder; SmbOS's budget should feel like 'your compute' not 'rented credits.'

### Relay.app - Human-in-the-loop automation: build a workflow, drop approval checkpoints anywhere, and a person approves/edits before sensitive steps run.

- **Category:** Workflow automation with first-class human approval (cloud, low-code)  
- **URL:** https://www.relay.app  
- **Relevance:** high  
- **How it works:** Trigger plus a predictable, readable series of steps (app steps, AI steps, human checkpoints, utilities, branches, loops). The differentiator is human-in-the-loop as a native step type: an Approval checkpoint pauses the run and notifies an assignee until they approve; AI-step review is a single toggle that routes the AI output to email/Slack to approve/revise/send-back before continuing; Data-collection steps send a small form to fill missing info. Assignees are real workspace users, notified via interactive Slack/email. Editor is checklist-like rather than a wiring diagram.  
- **Value prop:** Automation you can trust with irreversible/customer-facing actions because a human gate is built into the workflow, not bolted on, and all HITL features are free on every plan.  
- **Tech/stack:** Cloud SaaS, proprietary, no self-host/OSS. Built-in AI actions (extraction, summarization, transcription, TTS, image gen) with model switching.  
- **Pricing:** Free: 200 steps + 500 AI credits. Professional $19/mo (750 steps). Team $138/mo (2,000 steps). 5,000 AI credits on paid; AI add-ons $19-149/mo. HITL free across all tiers.  
- **Target user:** Teams automating payments, customer comms, and other irreversible actions that need a person in the loop; readability-first operators.  
- **Key features:**
    - Approval checkpoint as a native, droppable step
    - One-toggle human review on any AI step (approve / revise / send back)
    - Data-collection form steps for human-only info
    - Interactive Slack/email notifications to named assignees
    - Checklist-style readable workflows
    - HITL included on all plans including free
- **User feedback:**
    - (positive) genesysgrowth.com comparison: HITL approval before sensitive actions is native to Relay, unlike Gumloop/Bardeen which rely on fully automated flows or manual review outside the workflow.
    - (positive) Lindy blog / workflowautomation.net: Checklist-like interface feels simpler and more flexible than Gumloop's flowchart for internal/team processes.
    - (mixed) miniloop pricing analysis: Step-based metering can be limiting at higher volume; AI credits separate from steps adds a second meter to track.
- **Borrowable for SmbOS:**
    - This is the closest analogue to SmbOS's human-in-the-loop philosophy. Steal the 'approve / revise / send-back' triad as the action set on an 'On your plate' approval item, not just a binary approve/dismiss (SmbOS already has put-back/done/dismiss; 'revise and re-run' is the missing verb).
    - Make the AI-step review a single toggle per procedure/SOP: some SOPs auto-run, some always pause for the human, configurable in the Procedures library, mirroring Settings 'launch permission' at per-procedure granularity.
    - Interactive notifications (Slack/email) that let the human approve from where they already are, instead of forcing them back to the dashboard, is a discoverability win for the plate.
    - Checklist-over-flowchart readability matches SmbOS's plain-language ethos; resist turning the dashboard into a node graph.

### Gumloop - AI-native drag-and-drop node canvas for building workflows and agents that reason across tools; Benchmark-backed, YC W24.

- **Category:** AI workflow / agent builder (cloud, no-code, node canvas)  
- **URL:** https://www.gumloop.com  
- **Relevance:** medium  
- **How it works:** Drag-and-drop canvas of 100+ nodes (input, read file, extract, AI step, send message, etc.); connect them into pipelines that call LLMs, scrape sites, process documents, and trigger on events. Agents can reason across multiple tools within a pipeline. Credit-metered: 1 credit base per run, then per-node costs (Standard AI/GPT-4.1-mini = 2, Advanced/Claude Sonnet 4 or GPT-4.1 = 20, Expert/GPT-5/o3 = 30). Pro plans bill by usage with unlimited seats (no per-user pricing). Raised $50M Series B from Benchmark, early 2026.  
- **Value prop:** Best-in-class for AI-heavy, logic-driven pipelines (document processing, unstructured extraction, research) with usage-not-seat pricing so whole teams can build.  
- **Tech/stack:** Cloud SaaS, proprietary, no self-host/OSS. Multi-model (GPT, Claude Sonnet 4, GPT-5/o3 tiers).  
- **Pricing:** Free 2,000 credits + 1 trigger flow; Solo $37/mo (10,000 credits, unlimited trigger flows); higher tiers usage-based with unlimited seats. Annual = 20% off.  
- **Target user:** AI-heavy teams doing document processing, extraction, and research automation who want a visual builder.  
- **Key features:**
    - Visual node canvas, 100+ prebuilt nodes
    - AI-native: agents reason across tools mid-pipeline
    - 180+ example workflows across marketing/sales/ops/eng/support
    - Unlimited seats (usage-based, not per-seat) on Pro
    - Tiered AI nodes by model cost
- **User feedback:**
    - (positive) TechCrunch (Mar 2026): $50M Series B from Benchmark; positioned to 'turn every employee into an AI agent builder' - strong category momentum.
    - (negative) till-freitag.com review + Gumloop docs: Credit consumption is hard to predict; AI-intensive nodes (esp. Expert-tier 30-credit calls) burn credits fast and make cost forecasting difficult.
    - (mixed) genesysgrowth.com comparison: Great for AI-heavy logic-driven flows but lacks native in-workflow human approval (Relay wins there); flowchart less approachable than checklist UIs.
- **Borrowable for SmbOS:**
    - Tiered model cost made explicit (cheap model = small cost, frontier model = big cost) is a transparency pattern: SmbOS could show the model/cost tier a procedure will use up front in the Run/Queue/Prepare choice.
    - 'Prepare' before 'Run' maps to Gumloop's dry-run/test-on-canvas; SmbOS's Prepare action can preview which tools/cost a run will incur before committing.
    - Usage-not-seat framing is right for a solo founder; reinforce that SmbOS cost = work done, not headcount.

### Bardeen - 'Zapier for your browser': local Chrome-extension automations and scrapers triggered one-click or on a schedule.

- **Category:** Browser-based automation / scraping (local, freemium, Chrome extension)  
- **URL:** https://www.bardeen.ai  
- **Relevance:** low  
- **How it works:** Runs as a Chrome extension executing automations locally in the browser: scraping, lead collection, and cross-app actions (Gmail, Notion, calendar, LinkedIn, Asana). One-click 'playbooks' or scheduled runs. Because it runs in-browser, automations only execute while Chrome is open, and heavy flows consume local CPU/RAM. Added an AI 'Magic Box' for natural-language automation creation. Shifted to a credit/paid-limit model that upset existing users.  
- **Value prop:** Fast, cheap browser-native automation for scraping and personal-productivity tasks without server infra.  
- **Tech/stack:** Chrome extension, local execution, proprietary, no self-host of a server (it IS the local runtime). LLM features cloud-backed.  
- **Pricing:** Freemium ~$10/mo entry; shifted to credits/paid limits. The pricing change was widely seen as a rug-pull.  
- **Target user:** Individual operators, recruiters, and SDRs doing browser-bound scraping and repetitive web tasks.  
- **Key features:**
    - Local in-browser execution (data stays on your machine)
    - One-click playbooks + scheduled runs
    - Strong web-scraping / LinkedIn lead collection
    - Natural-language automation builder (Magic Box)
    - Deep integrations with Gmail/Notion/calendar/LinkedIn
- **User feedback:**
    - (negative) G2: One reviewer called it 'essentially malware' after complex flows maxed out CPU/RAM (cost of local in-browser execution).
    - (mixed) Reddit thread: 'Zapier for your browser' - accurate, but automations stop the moment Chrome closes, a hard ceiling on reliability.
    - (negative) Review aggregators / Product Hunt: Credit confusion is the most common complaint; users felt 'rug-pulled' by an out-of-nowhere shift to credits and paid limits; recurring bugs and broken workflows with poor error feedback.
- **Borrowable for SmbOS:**
    - Local-execution-as-trust is shared with SmbOS (work runs on the user's machine, data stays local) - but Bardeen's 'stops when Chrome closes' ceiling shows the value of a persistent local daemon (SmbOS's launchd/cron approach) over a browser-bound runtime.
    - The 'rug-pull' backlash is a warning: for a tool a solo founder depends on daily, pricing/permission changes must be communicated loudly; SmbOS's local + plain-language Settings (budget, launch permission) is the anti-rug-pull stance.
    - Broken workflows with poor error feedback reinforce SmbOS's need for legible failure states in 'Recent runs.'

### Stack AI - Enterprise no-code platform to build, govern, and deploy AI agents as chat assistants, forms, or APIs with model routing and guardrails.

- **Category:** Enterprise AI agent builder (cloud, governance-first)  
- **URL:** https://www.stackai.com  
- **Relevance:** low  
- **How it works:** No-code workflow builder to assemble agents over data + LLMs + back-office systems, deployable as a chat assistant, an advanced form, or an API endpoint. Routes across OpenAI/Anthropic/Google/local LLMs with guardrails and an evaluation framework; IT teams set governance policies for model usage, cost, and behavior. Newer agents can execute commands, run scripts, read/write files, send email, post Slack. Integrates Slack, Teams, Salesforce, HubSpot, ServiceNow. YC-backed.  
- **Value prop:** Get agents into a regulated enterprise with security, governance, evals, and model-routing controls IT will actually approve.  
- **Tech/stack:** Cloud SaaS, proprietary; Free Edition + custom enterprise. Supports local LLM routing. No self-host of the platform.  
- **Pricing:** Free Edition (build/test/deploy basic agents, no card); Enterprise custom, per-seat, with a 60-90 day procurement cycle.  
- **Target user:** Enterprise IT and ops teams needing governed, auditable AI agents. Furthest from SmbOS's solo-founder persona.  
- **Key features:**
    - Deploy agent as chat / form / API
    - Multi-model routing (OpenAI/Anthropic/Google/local) with guardrails
    - Evaluation framework + governance policies (cost/usage/behavior)
    - Agents can run scripts, read/write files, send email/Slack
    - Enterprise integrations (Salesforce, ServiceNow, Teams)
- **User feedback:**
    - (positive) sitegpt.ai / marketermilk reviews: Strong for governed enterprise deployments; model flexibility and eval/guardrail tooling stand out.
    - (mixed) Dust.tt category analysis: Enterprise-only motion adds a 60-90 day procurement cycle; overkill for individuals/small teams.
- **Borrowable for SmbOS:**
    - The eval/guardrail framing - defining what 'good output' looks like and checking against it - could inform how SmbOS verifies a session actually completed its SOP correctly, beyond a self-reported 'done.'
    - Deploy-as-3-surfaces (chat / form / API) is a reminder that the same SOP could be invoked multiple ways; SmbOS already has Run/Queue/Prepare + cron + MCP as invocation surfaces.
    - Governance policies (cost/behavior caps) generalize SmbOS's Settings budget + launch-permission into per-procedure policy.



## Cluster: Personal "chief of staff" / do-loop / daily-planner systems

_The whole cluster is fighting one battle: how much autonomy to take, and how to keep the human's trust while taking it. They split cleanly into two camps. AUTONOMOUS (Motion, Reclaim, Cora, Lindy) silently decide - auto-schedule, auto-screen, auto-act - and they consistently bleed trust: Motion's auto-scheduler is called a 'black box' that 'reshuffles in ways that don't feel discerning'; Cora buries time-sensitive email in a digest and took Geoffrey Litt weeks to trust ('almost quit'); Lindy 'runs off and builds before it has all the info' while burning credits; Cal Newport's verdict on the whole category is that AI 'can organize your messages, but not handle them on your behalf.' MANUAL/ASSIST (Sunsama, Akiflow, Superhuman) keep the human in control via rituals, command bars, and keyboard speed, and their complaints are about effort and price, not betrayal. The durable lesson for SmbOS: its human-in-the-loop 'pick up to launch' gate is not a limitation, it's the exact feature the autonomous tools wish they had. SmbOS's winning move is to combine the autonomous camp's ambition (real multi-step agent work, scheduling, triggers) with the manual camp's trust posture - and bridge them with LEGIBILITY. Three concrete cross-tool patterns to steal: (1) the inbox-vs-feed distinction (Cora/Litt) - keep 'On your plate' strictly act-required and never let it decay into a skim-and-miss feed; (2) the workload/budget meter (Sunsama's over-commit counter + Lindy's credit anxiety) - show predictable cost and committed load BEFORE the operator launches, so they never fear clicking; (3) the always-on command bar + hotkey-everything (Akiflow/Superhuman) - for a terminal-dwelling operator, every plate action should be keyboard-driven, with natural-language task/schedule entry instead of exposed cron syntax. And ritualize the loop (Sunsama's morning-plan/evening-shutdown, Cora's twice-daily Brief) with a short, plain-language digest in SmbOS's existing calm vocabulary._

### Motion (usemotion.com) - AI calendar + task manager that auto-schedules your tasks into open calendar slots and reshuffles the whole day when things change.

- **Category:** AI auto-scheduler / do-loop planner  
- **URL:** https://www.usemotion.com  
- **Relevance:** high  
- **How it works:** You enter tasks with a deadline, priority, and duration estimate. Motion's auto-scheduler (it markets analysis of '1,000+ parameters': deadlines, priorities, durations, dependencies, your working hours/availability) places each task into the best open slot on a connected calendar (Google/Outlook). The core loop is fully automatic: when a meeting is added, runs long, or a deadline shifts, the engine recalculates and re-lays the entire day/week in seconds, so the calendar is always a live projection of 'when everything will actually get done.' Recurring tasks get auto-blocked. It has expanded into AI 'Employees'/agents and project management. Cloud SaaS, web + desktop + mobile (mobile is task-checking only, not full management). Closed source, requires connectivity.  
- **Value prop:** Removes the manual labor and anxiety of deciding when each task happens; the calendar becomes a self-healing plan rather than a static grid you maintain by hand.  
- **Tech/stack:** Cloud SaaS, calendar-integrated (Google/Outlook), web + Electron-style desktop + mobile. Closed source, online-only.  
- **Pricing:** ~$29/mo individual (annual) / $49/mo monthly; 7-day trial. Business/AI-employee tiers run much higher (users cite up to ~$600/mo for the top business support tier). App Store 4.1/5 (~1,800 ratings).  
- **Target user:** Busy knowledge workers, founders, and teams who want hands-off scheduling and will trade control for automation.  
- **Key features:**
    - Auto-scheduling engine that places tasks into calendar slots by priority/deadline/duration
    - Real-time full-day/week reshuffle when meetings or deadlines change
    - Recurring task auto-blocking (daily/weekly/monthly/quarterly)
    - Working-hours/availability constraints the engine respects
    - Project management + AI 'Employees'/agents layer (newer)
    - Calendar as the single source of truth for 'when will this get done'
- **User feedback:**
    - (negative) Morgen 'Akiflow vs Motion' teardown (morgen.so): The auto-scheduler is a 'black box': it 'shuffles tasks in unclear ways without explicit approval' and 'can end up reshuffling tasks in ways that don't feel discerning, even with priorities configured' - described as trust erosion.
    - (negative) Morgen teardown: Missing/uncompleted recurring tasks don't always reschedule automatically; personal tasks leak into work calendars creating unwanted visibility.
    - (mixed) Kristian Larsen 2-year review (kristian-larsen.com): 'I have used Motion for +2 years. It's AMAZING.' but the interface is 'not very intuitive,' there's a real learning curve, double-booked meetings during setup, and the 7-day trial is too short to feel the payoff. Mobile is for checking only.
    - (positive) Reddit sentiment via reviews: Users like the hands-off approach and cite 'reduced emotional labor when it comes to determining when things will get done.'
    - (negative) Morgen teardown: Migration trend toward Reclaim/Sunsama/Morgen; AI 'Employees' dismissed by some as 'glorified API calls'; tiered pricing called 'nickel-and-diming.'
- **Borrowable for SmbOS:**
    - The 'black box' complaint is the central lesson: SmbOS should make every autonomous decision LEGIBLE. When a task moves from 'coming up' to 'in flight' or gets rescheduled, show why (priority, deadline, budget) rather than silently reshuffling.
    - Motion proves the appeal of a calendar/board as a LIVE projection of 'when will this get done' - SmbOS's live-mirror dashboard already does this; lean into auto-recompute of 'Coming up' ordering when a new task lands.
    - Avoid full silent automation: Motion's trust erosion comes from acting without explicit approval. SmbOS's 'pick up to launch' human gate is the right antidote - keep it.
    - Borrow the duration-estimate + deadline + priority data model as the inputs that determine plate/queue ordering.

### Reclaim.ai - Calendar-defending auto-scheduler that flexibly finds and re-finds time for tasks, habits, and meetings around your existing events.

- **Category:** AI smart scheduling / habit defense  
- **URL:** https://reclaim.ai  
- **Relevance:** medium  
- **How it works:** Connects to Google Calendar. Three primitives: Tasks (auto-placed by deadline + estimated duration + your focus-time preferences), Habits (recurring priorities like 'deep work 9-11', 'exercise 7am' that get a defended flexible block and slide to the next open window when a meeting steals the slot), and Smart Meetings (finds optimal 1:1/team times across attendees' calendars). The loop is continuous re-optimization: as meetings get booked or priorities shift, it reschedules tasks and habits in real time, with a user-set 'defense aggressiveness' per habit. Cloud SaaS, calendar-native, closed source.  
- **Value prop:** Protects recurring priorities and deep work from meeting creep without manual rescheduling; flexible blocks flex instead of being abandoned.  
- **Tech/stack:** Cloud SaaS, Google-Calendar-native. Closed source, online-only.  
- **Pricing:** Freemium; paid tiers (~$8-18/user/mo range historically). Closed source SaaS.  
- **Target user:** Calendar-heavy professionals and teams who want recurring routines and focus time defended automatically; only valuable to people who live in a digital calendar.  
- **Key features:**
    - Flexible auto-rescheduling tasks with deadline + duration
    - Habits with per-habit 'defense aggressiveness' that auto-slide around meetings
    - Smart 1:1/team meeting time-finding across calendars
    - Buffer time, travel time, and personal-vs-work calendar sync
    - Real-time re-optimization as the schedule changes
- **User feedback:**
    - (positive) Help center + multiple 2026 reviews (clickup.com, kripeshadwani.com): Praised for flexibly defending habits/deep work: 'if your 9am deep work slot gets taken by a meeting, Reclaim moves it to the next available window automatically.'
    - (mixed) Review aggregation (worksmarterlab, focuzed.io): Effectiveness 'is largely dependent on the use of calendar applications' - useless to anyone who doesn't already run their life on a calendar; some find the flexing blocks add calendar clutter.
- **Borrowable for SmbOS:**
    - The 'defense aggressiveness' slider per recurring item is a great pattern for SmbOS scheduled/cron SOPs: let the user set how aggressively a scheduled run claims time/budget vs. yields to ad-hoc plate items.
    - Habits-as-flexible-recurring-blocks maps to SmbOS's cron-scheduled SOPs: a scheduled run that can't fire (budget hit, session busy) should slide to the next window and SAY it slid, not silently drop.
    - The failure mode to avoid: SmbOS is for terminal-dwelling operators, not calendar-centric users - don't make the dashboard's value contingent on calendar discipline the way Reclaim does.

### Sunsama - Guided, deliberately-manual daily planner with a morning ritual and an end-of-day shutdown that pulls tasks from your tools into one committed, time-estimated plan.

- **Category:** Guided daily planner / ritual-based do-loop  
- **URL:** https://sunsama.com  
- **Relevance:** high  
- **How it works:** Sunsama's loop is a human ritual, not an AI. Each morning it walks you through: (1) review yesterday (what completed, what carried over, a reflection/gratitude prompt), (2) build today's task list by pulling from ~16 integrations (Asana, Linear, Jira, GitHub, Todoist, Notion, Trello, Slack, Google Tasks, etc.) plus calendar events, (3) add a time estimate to each task (a live 'workload counter' warns if you've over-committed vs. available hours), (4) prioritize/defer (drag to tomorrow, snooze to a date, or delete), (5) optionally auto-post your plan writeup to a Slack channel. At day's end a shutdown ritual closes the loop. Time-blocking onto the calendar is supported but user-driven. Deliberately NOT auto-scheduling. Cloud SaaS, closed source.  
- **Value prop:** Reduces overwhelm by forcing a realistic, time-boxed daily commitment and a reflective open/close loop, keeping the human in full control of what they take on.  
- **Tech/stack:** Cloud SaaS, integration-heavy. Closed source, online-only.  
- **Pricing:** $20-25/mo, no free tier - widely cited as one of the most expensive individual productivity subscriptions. Outdated UI and weak mobile app are common gripes.  
- **Target user:** Intentional knowledge workers and founders who want a calm, deliberate daily commitment loop and explicitly reject AI auto-scheduling.  
- **Key features:**
    - Structured morning planning ritual + end-of-day shutdown ritual
    - Per-task time estimates with a live 'workload counter' over-commitment warning
    - Pull tasks from ~16 tools + calendar into one unified daily plan
    - Drag-to-defer / snooze / carry-over for unfinished work
    - Optional auto-post of the daily plan to Slack for team visibility
- **User feedback:**
    - (positive) Reddit via Saner.AI/Morgen roundups: 'I've been a subscriber to Sunsama for over a year now and honestly it's the single best productivity app I've used.' Praised for reducing overwhelm via the rituals.
    - (negative) Reddit: 'The most expensive subscription I have in my set of tools.' Recurring complaints: high price, outdated UI, weaker mobile app, limited project tracking.
    - (mixed) Morgen/Saner comparisons: The deliberately-manual approach is loved by some and a dealbreaker for others who want AI to suggest/reschedule the day automatically.
- **Borrowable for SmbOS:**
    - The morning 'plan' + evening 'shutdown' ritual is a strong frame for a do-loop. SmbOS could add a lightweight daily/session-start digest ('here's what's on your plate, in flight, and coming up') and an end-of-session 'recent runs' recap - turning the dashboard into a ritual, not just a panel.
    - The 'workload counter' that warns when you've over-committed maps directly to SmbOS's budget/launch-permission settings: show a live 'today's committed runs vs. budget' meter so the operator sees over-commitment before launching.
    - Carry-over/defer/snooze mechanics for unfinished work map to SmbOS's plate recovery actions (put back / done / dismiss) - Sunsama validates that explicit human triage of carryover is core, not a nuisance.
    - Sunsama's whole bet - humans WANT to stay in control and reject silent automation - validates SmbOS's human-in-the-loop 'pick up' gate as a feature, not a limitation.
    - Optional 'post my plan to Slack' = a legibility/accountability surface. SmbOS could let a run optionally report its plan/completion to a chosen channel for the solo operator's own record or a client.

### Akiflow - Keyboard-first task consolidator: pull tasks from everywhere into one inbox, then drag them onto the calendar as time blocks via an always-available command bar.

- **Category:** Time-blocking + command-bar task hub  
- **URL:** https://akiflow.com  
- **Relevance:** high  
- **How it works:** Akiflow unifies tasks from many sources into a single inbox, then you manually drag each task onto the calendar to turn it into a time block (bidirectional calendar sync). The signature surface is a global Command Bar (alt+space) that's always reachable: you type natural language ('Call the vet tomorrow at 9', 'Pay rent on the first of every month') or speak it, and it parses into a scheduled task. Nearly every action (create, schedule, move, snooze, reschedule) has a hotkey - it's optimized for mouse-free speed. Automation is intentionally light vs. Motion; the human does the time-blocking. Desktop-first (with mobile), closed source SaaS.  
- **Value prop:** One fast, keyboard-driven place to capture and time-block everything, so you work from a single consolidated view instead of many app inboxes.  
- **Tech/stack:** Desktop-first app + mobile, calendar-integrated. Closed source, online-only.  
- **Pricing:** ~$34/mo (widely cited); refund/cancellation reported as difficult. Closed source SaaS.  
- **Target user:** Power users and keyboard-driven operators who want a fast capture + manual time-block workflow and prefer control over AI auto-scheduling.  
- **Key features:**
    - Always-on global Command Bar (alt+space) with natural-language + voice task entry
    - Unified inbox pulling tasks from many integrations
    - Drag-to-calendar time-blocking with bidirectional sync
    - Hotkey for essentially every action (create/schedule/move/snooze)
    - Manual, high-control planning (deliberately light automation)
- **User feedback:**
    - (positive) Theo James review (medium.com), squeezegrowth: Command Bar + hotkeys 'make you fast once you get the hang of them'; consolidation and bidirectional sync mean you 'really work from one place.'
    - (negative) Morgen 'Akiflow vs Motion' teardown: 'Long stretches with no support response,' sync glitches between desktop and mobile time slots, 'floating tasks and duplicate issues,' and a community 'launched before ready' assessment.
    - (negative) Morgen teardown: Immature AI that 'can't answer basic queries,' no true recurring/conflict-checking, an unskippable tutorial, and a 'manual re-planning tax on chaotic weeks.'
- **Borrowable for SmbOS:**
    - The always-available Command Bar is the single most transferable UX for a terminal-dwelling operator: a global hotkey overlay on the dashboard to capture a task onto the plate, run/queue a Procedure, or launch a session - without mouse navigation. This fits SmbOS's keyboard-native user perfectly.
    - Natural-language task entry that parses into a scheduled/queued item ('run invoice-followup every Monday 9am') maps directly to SmbOS's scheduling/triggers - let owners create cron SOPs in plain language instead of cron syntax (which house style already forbids exposing).
    - Akiflow's 'manual re-planning tax on chaotic weeks' is a warning: fully-manual queuing gets heavy. SmbOS should offer optional auto-ordering of 'Coming up' so the operator isn't hand-sorting the queue every day.
    - Unified-inbox-then-act is exactly SmbOS's plate→pick-up→session loop; Akiflow validates 'one consolidated surface you act from' as the winning shape.

### Cora (cora.computer, by Every) - AI 'chief of staff for your inbox' that screens email, archives the noise, drafts replies in your voice, and delivers a twice-daily Brief - turning the inbox from an obligation into a feed.

- **Category:** Autonomous email chief-of-staff  
- **URL:** https://cora.computer  
- **Relevance:** high  
- **How it works:** Cora connects to Gmail and learns your patterns from historical email (who matters, what you reply to, your writing voice). Three functions: (1) Screening - it decides what truly needs you and keeps only human emails requiring your direct response in the inbox, archiving/redirecting the rest; (2) Drafting - when it has enough context it pre-writes a reply in your voice for you to review and send; (3) Brief - twice a day it sends a scannable digest summarizing everything you should read but don't need to act on. You can also chat with Cora 'like a chief of staff' to adjust filing/handling. The deliberate reframe (per Geoffrey Litt) is 'inbox = obligation, feed = optional reading': it converts a pile of must-handle items into a scrollable story you check 2x/day. Gmail-only, cloud, closed source.  
- **Value prop:** Reclaim attention by collapsing a 3-hour inbox into a 30-second read and only surfacing the few things that genuinely need a human, with drafts pre-staged for the ones that need a reply.  
- **Tech/stack:** Cloud SaaS, Gmail-integrated, separate web interface for the Brief. Closed source.  
- **Pricing:** $15/mo standalone ($20/mo in the Every bundle). Out of beta in 2025; ~2,500 beta users at launch. Gmail-only; pay per extra account.  
- **Target user:** Overwhelmed-inbox knowledge workers and founders willing to hand email triage to AI but who still want to approve outgoing replies.  
- **Key features:**
    - AI screening that keeps only human, response-needed mail in the inbox
    - Twice-daily Brief digest of everything else (read, don't respond)
    - Reply drafting in the user's learned voice (human reviews before send)
    - Chat/natural-language control of filing and handling rules
    - Voice/pattern learning from historical email at onboarding
- **User feedback:**
    - (mixed) Geoffrey Litt on X (@geoffreylitt, 1938306471470792939): 'It felt very strange at first (I almost quit) but then I came around and I'm a fan. The key insight is that it turns email from an inbox into a feed. Inbox = tacit obligation; feed = optional.' Trust took weeks to build.
    - (negative) Brian Donohue blog (bthdonohue.com): Time-shifting into a digest causes 'hyper-skimming' so 'time-sensitive matters got buried in digests'; active exchanges became awkwardly asynchronous; the separate website felt disconnected, especially on mobile - 'time-shifting works best for genuinely unimportant content, but determining what matters requires integration, not isolation.'
    - (mixed) Cal Newport, 'Why Can't AI Empty My Inbox?' (calnewport.com): Cora 'can organize your messages, but not handle them on your behalf.' Filtering/summarizing works ('only 24 new emails... every one relevant'), but full autonomy is an unsolved 'Turing test' because email needs relationship/hierarchy nuance. Argues for bounded, assisted improvements not full automation.
    - (positive) Every launch + Product Hunt (every.to, producthunt.com): Framed as a '$150K chief of staff for $15/mo'; users praise daily summaries, voice-matched drafts, and the single-focus design.
- **Borrowable for SmbOS:**
    - The 'inbox vs feed' reframe is directly transferable to SmbOS's vocabulary: 'On your plate' = obligation (must act), and a 'Recent runs'/digest = feed (read, don't act). Make sure SmbOS clearly separates ACT-required items from FYI items so the plate never becomes a feed people hyper-skim and miss.
    - Cora's biggest risk - important things buried in a digest, trust taking weeks - is the strongest argument for SmbOS's design: never auto-handle silently; keep a human 'pick up' gate, and make the autonomous part (screening/ordering) legible so trust builds in days, not weeks.
    - Draft-but-don't-send (human approves outgoing) is the exact human-in-the-loop shape SmbOS should keep for any session that produces external artifacts. Newport's point ('organize but not handle on your behalf') is the safe default line.
    - Twice-daily Brief = a cheap, high-trust legibility pattern: SmbOS could emit a short owner-facing digest ('3 runs completed, 1 waiting for you, 2 coming up') in plain language, the same calm copy register SmbOS already uses.
    - Chat-to-adjust-handling ('talk to it like a chief of staff') maps to SmbOS's MCP/Claude Code session: let the operator refine an SOP or scheduling rule conversationally instead of editing config.
    - The integration-not-isolation lesson: SmbOS's dashboard living next to the actual work (sessions, SOPs) beats a separate disconnected surface like Cora's standalone Brief website.

### Lindy - No-code AI-agent builder ('AI employees') that chains triggers and tools to autonomously triage email, schedule, take meeting notes, and run multi-step workflows in natural language.

- **Category:** No-code AI agent / autonomous workflow builder  
- **URL:** https://www.lindy.ai  
- **Relevance:** medium  
- **How it works:** You build 'Lindys' (agents) from templates or natural-language descriptions. Each agent owns a task (lead qualification, inbox triage, meeting notes, CRM updates) and acts autonomously when a trigger event fires (new email, meeting invite, etc.). Unlike Zapier's static automations, a Lindy uses an LLM to make decisions, read context, and chain multi-step actions across integrations (Gmail, calendar, Slack, Zoom/Meet/Teams, CRMs). It can parse a meeting invite, schedule it, send confirmations, and update Slack in one chained flow, or triage email, draft replies, follow up, and update the CRM. Runs on a credit system (each action/model call burns credits). Cloud SaaS, closed source.  
- **Value prop:** Spin up always-on AI 'employees' for repetitive multi-step workflows without code, replacing manual handling of routine email/scheduling/CRM busywork.  
- **Tech/stack:** Cloud SaaS, GPT-4-class models, broad SaaS integrations. Closed source, online-only.  
- **Pricing:** Free tier (~400 credits/mo); paid from ~$20-50/mo. Credit system makes real cost unpredictable - the #1 complaint.  
- **Target user:** Solopreneurs and small teams (sales/ops heavy) who want to automate routine multi-step workflows but lack the budget/desire for code or a real assistant.  
- **Key features:**
    - Natural-language / template-based agent ('Lindy') creation
    - Event-triggered autonomous multi-step workflows across many integrations
    - Email triage + context-aware drafting + follow-up + CRM update chains
    - Meeting scheduling, recording, and auto note/action-item extraction
    - LLM decision-making mid-workflow (vs. static if-this-then-that)
- **User feedback:**
    - (negative) Trustpilot / G2 / Reddit aggregation (dialora.ai, prospeo.io): 'Expensive' is the single most common complaint (42 mentions). The credit system creates 'credit anxiety' that 'seriously limits how users use the tool,' making people avoid experimenting because every interaction costs money.
    - (negative) Annika Helendi honest review (substack) + Reddit: The agent builder 'can be infuriating... either running off and building before it has all the info, or building flows that don't make sense and it can't seem to fix.' Errors during building still burn credits; debugging is costly.
    - (mixed) cybernews / salesrobot 3-month review: 'Excels at routine, repetitive tasks' and easy to set up simple agents, but 'shows limitations with complex, multi-step processes or custom integrations' - 'okay for simple automations but rubbish for anything complex.' Support sometimes unresponsive.
- **Borrowable for SmbOS:**
    - Credit anxiety is the lesson: Lindy's metered-per-action billing makes users AFRAID to use the product. SmbOS already has a budget/cost-report concept - keep cost visible and PREDICTABLE (e.g., per-run estimate before launch, a budget meter on the dashboard) so the operator never fears clicking 'pick up.'
    - The 'agent ran off and built before it had all the info' complaint argues for SmbOS's primed-session + SOP approach: a session launched against an explicit SOP has the context up front, reducing the half-baked autonomous behavior Lindy users hate.
    - Lindy's trigger→multi-step-agent model is the same shape as SmbOS triggers/scheduling launching a primed Claude Code session - but SmbOS's differentiator should be legibility + a human gate, exactly the things Lindy users say break ('flows that don't make sense and it can't fix').
    - Templates as the on-ramp: Lindy's template gallery lowers activation cost. SmbOS's 'Procedures' library (Run/Queue/Prepare) + a starter pack is the analog - invest in a strong seed library so the do-loop has something to do on day one.

### Superhuman (AI workflow / Split Inbox) - Keyboard-first email client that uses Split Inbox streams + AI summarize/instant-reply to make inbox-zero fast, with the human staying in the driver's seat.

- **Category:** Power-user email workflow (assist, not autonomous)  
- **URL:** https://superhuman.com  
- **Relevance:** medium  
- **How it works:** Superhuman sits on top of Gmail/Outlook as a fast, keyboard-driven client. Its core triage primitive is Split Inbox: incoming mail auto-sorts into multiple named streams (VIP/executives, specific clients, projects, team) so you process by context instead of one overwhelming list. AI layers on top: thread summarization, and Instant Reply (an AI-drafted response you review or send). Nearly every action is a hotkey, so power users blast to inbox-zero fast. Crucially the AI ASSISTS triage and drafting; the human still reads and decides - it does not screen-and-archive autonomously like Cora. Cloud SaaS, closed source, premium-priced.  
- **Value prop:** Make a human-driven inbox-zero workflow dramatically faster via keyboard speed + context-split streams + AI drafts, without surrendering the inbox to autonomous handling.  
- **Tech/stack:** Cloud SaaS over Gmail/Outlook, native-feeling desktop + mobile clients. Closed source.  
- **Pricing:** Premium (~$30/mo historically). Closed source SaaS.  
- **Target user:** High-volume email power users (founders, execs, sales) who want maximum speed and keep manual control of triage.  
- **Key features:**
    - Split Inbox: auto-categorized streams (VIP/client/project) processed by context
    - Keyboard-first design - a hotkey for nearly every action
    - AI thread summarization and Instant Reply drafts (review-or-send)
    - Read statuses, reminders, fast load - speed as the core value
    - Human-in-control triage (assist, not autonomous screening)
- **User feedback:**
    - (positive) Superhuman blog + reviews (blog.superhuman.com, aiquiks): Split Inbox solves the 'one single overwhelming list' problem: 'if you reply in the order they appear, your brain is constantly forced to switch gears' - context streams reduce that thrash and make inbox-zero easier.
    - (mixed) Reviews (ventureburn, max-productive): Speed + keyboard workflow loved by power users; price and the learning curve (everything is shortcuts) are the recurring objections. AI assist is incremental, not autonomous - a feature for control-keepers, a gap for automation-seekers.
- **Borrowable for SmbOS:**
    - Split Inbox = context streams. SmbOS's plate already splits into 'On your plate / In flight / Coming up / Recent runs' - Superhuman validates that splitting one queue into context lanes reduces cognitive thrash. Consider further splitting the plate by client/project lane for multi-client operators.
    - Keyboard-first everything: Superhuman's whole value is speed via hotkeys. For SmbOS's terminal-dwelling user, every dashboard action (pick up, run, queue, dismiss) should have a hotkey, not just a click target - pairs with the Akiflow command-bar idea.
    - Assist-not-autonomous as a deliberate position: Superhuman deliberately keeps the human triaging and only AI-drafts. This is the trust-preserving middle ground SmbOS occupies (human picks up the task; agent does the work). It's a viable, defensible stance against the 'black box' tools.
    - AI summarize-the-thread → SmbOS could auto-summarize a completed run ('here's what the session did') so 'Recent runs' is scannable, the same way Superhuman summarizes long threads.



## Cluster: Runbooks, executable markdown & terminal ops for engineers

_The whole cluster is converging on the same trust pattern SmbOS already bets on: a plain-markdown source of truth (Runme, Obsidian, Warp Notebooks all export/store markdown, no lock-in), made executable, with a human checkpoint and an audit trail. The differentiators that separate winners from wikis are the four things SmbOS already has and the markdown-only tools lack: (1) human-in-the-loop approval that pauses a run mid-stream after the agent has ENRICHED context (Tines's 'ask after enriching, not before'), (2) a complete legible audit ledger of every run so autonomy is trustworthy in hindsight (Rundeck, Tines), (3) multiple trigger modes for one procedure (on-demand / scheduled / event-triggered, per Rundeck and Warp), and (4) saved knowledge auto-feeding the agent's context (Warp Drive -> Oz). The cross-tool failure mode everyone cites is runbook bitrot ('the runbook is already lying to you'), which pure executable-markdown can't fix; the market is now pulling toward agentic verification, which is SmbOS's structural advantage (a Claude-driven /sop-review that detects drift and a do-loop that reports completion back). Positioning lane: Rundeck/Tines are enterprise/team and heavyweight (JVM server, SOAR), Warp is a closed AI terminal with a login-wall trust scar, and Notion/Obsidian are passive stores. None target the technical SOLO operator with a local-first, near-zero-setup, plain-language ('on your plate', 'in flight') command center over their own recurring business SOPs. Borrow the parameterized 'Prepare' step (Warp Workflows), the publish/approval gate (Rundeck), the enrich-then-approve checkpoint (Tines), and keep the local-first/no-login posture that Warp's backlash shows users punish you for violating._

### Runme (by Stateful) - Turns plain-markdown docs and READMEs into interactive, executable DevOps notebooks runnable from a VS Code extension, CLI, or browser.

- **Category:** Executable markdown / runbook notebook  
- **URL:** https://runme.dev/  
- **Relevance:** high  
- **How it works:** Parses fenced code blocks (shell, bash, python, ruby, js/ts, lua, perl, php) in any markdown file and makes each block a clickable, runnable cell. A shared shell session persists env vars across cells and lets you pipe one cell's output into the next, just like a terminal. Named cells are addressable: `runme run deploy-staging`; unnamed blocks are skipped unless `--allow-unnamed`. `runme tui` opens an interactive picker that uses a 'proximity rule' to surface root-level files first. Runs in CI with `--all --skip-prompts`. Same markdown drives the notebook UI, the CLI, and CI, so the doc IS the automation.  
- **Value prop:** Your existing markdown docs become the automation: no migration, no lock-in, the doc and the runnable runbook are the same file, so ops procedures stop rotting into stale wiki pages.  
- **Tech/stack:** Go CLI core; built on VS Code's open notebook platform (also runs in VSCodium, Codespaces, Gitpod, code-server, Docker). Shell/Bash 'kernel' model like Jupyter but for ops. Markdown is the source of truth (Git-checkable). Cloud renderers for AWS/GCP/Azure resources. OSS, ~2.3k+ GitHub stars.  
- **Pricing:** Core CLI + VS Code extension are open source (Apache 2.0). Commercial entity is Stateful; cloud/team features pitched but no public per-seat pricing surfaced. Effectively free for solo use.  
- **Target user:** DevOps/SRE/platform engineers maintaining deployment, infra, and incident-response runbooks that rot when they're static wiki pages.  
- **Key features:**
    - Plain-markdown source of truth, 100% Git-compatible, no lock-in (same idea as SmbOS ~/sops)
    - Named, addressable cells you can run individually or all at once
    - Shared persistent shell session: env vars + piped output carry across cells
    - Three execution surfaces from one file: notebook UI, CLI, CI/CD
    - Confirmation prompts before running (bypassable with --skip-prompts for non-interactive)
    - Cloud-native renderers that show AWS/GCP/Azure resources inline
    - Designed explicitly to fight runbook bitrot (docs tested in CI so they can't drift silently)
- **User feedback:**
    - (positive) b-nova teardown blog: Praised for making boring docs into interactive terminals; the markdown-native approach means existing READMEs become runbooks with near-zero migration.
    - (positive) CNCF Sandbox application (github.com/cncf/sandbox issue #127): Submitted to CNCF Sandbox as a legitimate DevOps-notebook project, signaling real ecosystem traction beyond a toy.
    - (mixed) Dev|Journal / DevOps.com 2026 articles on 'the runbook is already lying to you': Broader industry sentiment: static/markdown runbooks (even executable ones) still rot and get out of sync with reality; the field is moving toward AI agents that verify state, which pressures pure executable-markdown tools to add agentic verification.
- **Borrowable for SmbOS:**
    - Markdown-as-source-of-truth with named, individually-runnable cells maps directly onto SmbOS SOPs; let a single SOP step be 'run this one block' not just 'run the whole SOP'.
    - Shared persistent session that carries env vars + piped output across steps; SmbOS 'in flight' sessions could expose intermediate outputs so the human sees what carried forward.
    - One artifact, multiple surfaces: the same SOP markdown drives the dashboard 'Run', a CLI invocation, and a scheduled/cron run. Reinforces SmbOS's 'Run/Queue/Prepare' triple.
    - Confirmation-before-run as the default with an explicit --skip-prompts escape hatch; matches SmbOS's launch-permission/budget trust model.
    - Anti-bitrot framing: SmbOS /sop-review (stale/drift detection) is a strong wedge Runme validates demand for, but Runme can't auto-verify SOPs the way a Claude-driven reviewer can.

### Warp (Workflows, Notebooks, Agent Mode / Warp Drive) - AI-first terminal where saved parameterized commands (Workflows) and runnable markdown runbooks (Notebooks) live next to the prompt and feed an embedded agent (Oz/Agent Mode).

- **Category:** AI terminal + executable runbooks + agent  
- **URL:** https://www.warp.dev/  
- **Relevance:** high  
- **How it works:** Two modes: a clean terminal for shell, and a conversation view for multi-turn work with the Oz agent. Agent Mode lets you describe a high-level task in natural language; it asks permission to run commands, reads the output, self-corrects on errors, and steps you through. Workflows are named, described, parameterized command templates (interactive args) you save and search by name instead of memorizing flags. Notebooks are markdown-flavored runbooks with embeddable Workflows and runnable code blocks you execute with a click in a pane next to the prompt. Critically, the agent auto-pulls context from your Warp Drive (Workflows, Notebooks, Rules, env vars, MCP) so saved team knowledge shapes agent answers.  
- **Value prop:** Team command knowledge and runbooks stop living in a wiki and start living next to the prompt, where an agent can read them as context and step you through multi-step tasks with permission gates.  
- **Tech/stack:** Native Rust terminal (GPU-rendered, fast). Local NL classifier ships in-app so command vs natural-language detection happens on-device; request only leaves on Enter. Warp Drive = cloud-synced store of Workflows, Notebooks, Env Vars, Rules, MCP servers. Notebooks export to markdown (no lock-in). Cloud agents ('Oz'). Closed source.  
- **Pricing:** Warp Drive free for up to 3 team members with limited Notebooks/Workflows; paid plans (~$15/seat range cited on HN) unlock unlimited sharing + more agent usage. Login was historically mandatory (major complaint), removed Dec 2024.  
- **Target user:** Individual developers and engineering teams who live in the terminal and want AI + shared, parameterized command knowledge in one place.  
- **Key features:**
    - Workflows = parameterized, named, searchable command primitives ('alias with a description and args')
    - Notebooks = runnable markdown runbooks living beside the prompt, step-through without copy-paste or context switch
    - Agent Mode asks permission before each command, reads output, self-corrects
    - Local NL classifier: nothing leaves the machine until you hit Enter (privacy mitigation)
    - Warp Drive auto-feeds saved Workflows/Notebooks/Rules/MCP as agent context
    - Real-time team sync; drag a Notebook into a Team drive to share, edits sync live
    - Markdown export = no lock-in
- **User feedback:**
    - (negative) Hacker News thread 42247583 ('Warp - no more login required'): 'I have never uninstalled a program faster in my life' (jakebasile) over the mandatory login; users noted Warp acknowledged the problem two years before fixing it, eroding trust. Telemetry of shell commands to a third party called a dealbreaker.
    - (mixed) Hacker News (same thread): Skepticism about the $73M raise / unit economics vs free alternatives (iTerm2, WezTerm, Kitty); 'the damage is done.' But actual users cite real speed gains over iTerm, polished UI, command blocks, and responsive devs.
    - (positive) Warp blog + DataCamp/TheLinuxCode 2026 guides: Workflows-as-shared-primitives and runbooks-next-to-the-prompt praised as ending wiki copy-paste; agent self-correction and permission prompts seen as the right human-in-the-loop default.
- **Borrowable for SmbOS:**
    - Parameterized, named, searchable command primitives (Workflows): SmbOS SOPs could expose typed parameters/args at 'Prepare' time so a run is filled in before it starts, not mid-stream.
    - Permission-before-each-command agent loop with output read-back and self-correction is exactly SmbOS's do-loop; Warp validates 'ask, run, observe, correct' as the trust pattern users accept.
    - Saved knowledge auto-feeds the agent's context (Drive -> Agent): SmbOS could auto-inject the relevant SOP + recent runs into the Claude session it primes, so picked-up tasks start with full context.
    - Local-first privacy posture as a trust signal (NL classifier on-device; nothing sent until Enter). SmbOS is already local; lean on 'your SOPs and runs never leave your machine' as a differentiator vs cloud runbook SaaS.
    - The login-wall backlash is a cautionary tale: keep SmbOS install/use friction near zero; never gate the core loop behind an account.
    - Markdown export / no-lock-in as an explicit promise, even though the live surface is richer than markdown.

### Rundeck (PagerDuty Runbook Automation / Process Automation) - Open-source web console that turns ops scripts into self-service Jobs that non-experts can safely run, schedule, and audit across many nodes with RBAC.

- **Category:** Runbook automation / self-service ops platform  
- **URL:** https://www.rundeck.com/  
- **Relevance:** high  
- **How it works:** Subject-matter experts define Jobs (wrapping existing scripts/tools/automation) and publish them through an approval/publishing workflow. Granular RBAC/ACLs mean self-service users only see and can invoke the actions they're authorized for. Jobs run on demand (web UI / API / CLI), on a schedule, or triggered by alerts (e.g. PagerDuty integration), across any number of target nodes. Every execution is logged for audit. The core value: convert 'file a ticket and wait' into 'click a safe button,' moving toil off the experts while keeping a boundary between who-defines and who-runs.  
- **Value prop:** Experts wrap their scripts as safe, parameterized buttons with role-based access and a full audit log, so others can self-serve operations without server access or a ticket queue.  
- **Tech/stack:** JVM stack: Groovy (~58%) + Java (~20%), Grails web app; frontend in JS/Vue/TypeScript. Runs as a web service with CLI + WebAPI. Needs Java 11+. Heavyweight, server-deployed (not local-first).  
- **Pricing:** Community edition open source (Apache 2.0, maintained by PagerDuty). Commercial 'PagerDuty Runbook Automation / Process Automation' adds enterprise features; quote-based.  
- **Target user:** DevOps/SRE/IT-ops teams that want to delegate operational tasks to other stakeholders (support, on-call, devs) without giving out server access.  
- **Key features:**
    - Self-service catalog: experts author, others safely execute
    - Fine-grained RBAC/ACL so users only see authorized actions
    - Publishing/approval workflow before a job becomes runnable by others
    - Scheduling + alert-triggered + on-demand execution across many nodes
    - Full audit log of every run (who ran what, when, output)
    - Web UI + REST API + CLI for the same jobs
- **User feedback:**
    - (negative) Kestra / SaaSHub Rundeck-alternatives roundups: Steep learning curve; the Java/Grails backend and dependencies are operationally complex to run and maintain at scale; UI feels limited/dated. Users migrate to Ansible Semaphore ('lightweight, easy to use') or Kestra.
    - (mixed) SaaSHub user comparisons: Powerful and battle-tested for delegated ops + audit, but heavyweight overkill for a solo operator; large node counts add performance overhead.
    - (positive) PagerDuty positioning / DevOpsSchool writeups: Still the reference example of 'turn a script into a safe, auditable, self-service button' with RBAC and approval gates; that pattern is widely copied.
- **Borrowable for SmbOS:**
    - The 'author vs runner' boundary with a publish/approval gate before something becomes runnable maps to SmbOS SOP status (draft -> approved) and the launch-permission setting.
    - Full audit log of every run (who/what/when/output) is exactly SmbOS 'Recent runs'; Rundeck shows users will trust autonomy only if every execution is legible after the fact.
    - Self-service catalog of safe buttons = SmbOS 'Procedures' library with Run/Queue/Prepare; Rundeck proves the demand but is enterprise/heavyweight, leaving the solo-operator niche open.
    - Three trigger modes for the same job (on-demand, scheduled, alert-triggered) is the model SmbOS cron + triggers should match: one SOP, multiple ways to fire it.
    - Rundeck's complaint (heavy JVM server, steep learning curve) is SmbOS's opening: deliver the same safe-self-service-runbook value as a local, plain-markdown, near-zero-setup tool.

### Tines - No-code visual workflow builder that wires runbooks to real systems, mixing deterministic steps, agentic AI steps, and explicit human approval gates.

- **Category:** Workflow/runbook automation with human-in-the-loop (SOAR-adjacent)  
- **URL:** https://www.tines.com/  
- **Relevance:** high  
- **How it works:** You build a workflow on a visual canvas as a sequence/branch of actions. Three action types combine: deterministic steps (fixed-rule lookups, enrichments, notifications, ticket updates), agentic steps (AI reasoning for classification/triage inside guardrails), and human-in-the-loop steps (manual approval gates via Pages/forms that PAUSE execution until an authorized person reviews). The design principle Tines pushes: 'gather context BEFORE requesting human approval, not after,' so the human sees a fully-enriched decision and just approves/rejects irreversible actions. Triggers are observable conditions (alert strings, schedules, API calls). Every action is auto-logged.  
- **Value prop:** A runbook stops being a wiki page and gets wired to systems, with the automation enriching context first and only then pausing for a human to approve the irreversible step.  
- **Tech/stack:** Cloud SaaS (self-hostable enterprise option). Drag-and-drop 'Storyboard' canvas with an exposed code layer for edge cases. Native integrations + API actions. Strong audit logging. Closed source.  
- **Pricing:** Free Community Edition, no sales call required; paid tiers quote-based for teams/enterprise.  
- **Target user:** Originally security ops (phishing triage, SOC), now broader ops teams who want runbooks wired to systems with controlled human checkpoints. Not built for SRE service-restoration.  
- **Key features:**
    - Mix of deterministic + agentic + human-approval steps in one workflow
    - Human-in-the-loop Pages/forms that pause a run for explicit approval mid-stream
    - 'Enrich first, then ask the human' so approval decisions arrive pre-contextualized
    - Visual canvas for non-engineers with a code escape hatch for power users
    - Automatic audit trail of every action (no manual documentation)
    - Free Community Edition with no sales gate
- **User feedback:**
    - (mixed) incident.io 2026 runbook-automation-tools guide: Excellent at security triage / replacing legacy SOAR (XSOAR, Phantom, Demisto), but lacks service-catalog awareness, on-call routing, and post-mortem generation that SRE/DevOps incident workflows need; security-shaped scope.
    - (positive) Tines own framing (widely echoed): 'The runbook stops being a wiki page and gets wired to systems instead of being written as text' resonates; the deterministic/agentic/human three-way split is cited as the right mental model for trustworthy automation.
- **Borrowable for SmbOS:**
    - 'Enrich context BEFORE asking the human, not after': SmbOS should have the agent gather everything (recent runs, relevant files, draft output) so a task on the plate arrives decision-ready, not as a bare 'approve?' prompt.
    - Explicit human-approval gate that PAUSES a run mid-stream (not just at the start): SmbOS 'in flight' sessions could surface an approval checkpoint for irreversible/expensive steps, then resume.
    - The deterministic / agentic / human-in-the-loop taxonomy is a clean way to classify SmbOS SOP steps; mark which steps are auto-safe vs which need owner sign-off.
    - Every action auto-logged so the audit trail writes itself; reinforces making SmbOS 'Recent runs' a complete, trustworthy ledger of agent actions.
    - Free Community Edition / no-sales-call is the right GTM for a developer-first tool; matches SmbOS plugin distribution.
    - Tines's SRE/post-mortem gap shows positioning matters: SmbOS for the solo operator's recurring business SOPs is a distinct, underserved lane vs incident-response SOAR.

### Notion / Obsidian runbooks (with Execute Code plugin) - General knowledge tools repurposed as runbook homes: Notion for team-facing operational docs, Obsidian (plain-text + Execute Code plugin) for durable, locally-executable runbooks.

- **Category:** Knowledge base repurposed as runbook store  
- **URL:** https://obsidian.md/ , https://www.notion.so/  
- **Relevance:** medium  
- **How it works:** Notion stores operational docs in databases with views, good for team-facing 'how we do X' pages, but commands are static text you copy-paste into a terminal. Obsidian keeps runbooks as plain-text markdown in a local vault; the Execute Code plugin turns fenced code blocks into runnable cells inside the note (notebook-like), and Templater scaffolds consistent docs (postmortem template, code-review checklist, ADR). The recurring critique across teardowns: during a real incident an outdated wiki runbook 'might as well not exist,' and copy-pasting commands from a doc is the failure mode executable tools exist to kill.  
- **Value prop:** Runbooks live next to all your other notes instead of a separate ops silo; Obsidian keeps them as durable local plain-text you can even run inline, but neither adds scheduling, approval, or audit.  
- **Tech/stack:** Notion: cloud, database-backed, block editor, closed. Obsidian: local-first, plain-markdown vault, huge community-plugin ecosystem. Execute Code plugin runs fenced code blocks (Python, JS, Rust, Go, ~15 langs) inside a note; Templater adds JS-powered templates for consistent note/SOP creation.  
- **Pricing:** Obsidian free for personal use, plugins free/community; Notion freemium with per-seat team pricing.  
- **Target user:** Engineers and small teams who already keep notes here and want runbooks/incident postmortems/ADRs to live alongside everything else rather than in a separate ops tool.  
- **Key features:**
    - Runbooks live next to all other team/personal knowledge (low context-switch)
    - Obsidian = local-first plain markdown, durable, no vendor lock-in, Git-friendly
    - Execute Code plugin makes code blocks runnable inside notes (poor-man's notebook)
    - Templater scaffolds consistent SOP/postmortem/ADR structure from templates
    - Notion databases give nice views/relations for team-facing process docs
- **User feedback:**
    - (negative) Ravoid 'Your wiki is slowly killing engineering velocity' teardown: Wiki-style runbooks (Notion/Confluence) rot, lack execution, and force copy-paste; 'during an incident that runbook might as well not exist if it's outdated or requires copy-pasting commands into a terminal.'
    - (mixed) tech-insider / Echoprysm Notion-vs-Obsidian comparisons 2026: Obsidian wins for durable interlinked runbooks/incidents as plain text and can execute code via plugins; Notion wins for team-facing collaborative docs but stays static. Neither is a real automation/scheduling/approval layer.
- **Borrowable for SmbOS:**
    - Validates SmbOS's core bet: plain-markdown, local-first, Git-friendly SOPs (the Obsidian model) over cloud wiki lock-in (the Notion model).
    - 'Runbooks should live next to your other knowledge, not in a separate ops silo' argues for SmbOS to integrate where the operator already works (terminal/Claude Code) rather than being one more dashboard to remember.
    - Templater-style scaffolding = SmbOS's importer/template seeding: enforce consistent SOP structure so steps are uniformly runnable.
    - The universal complaint (copy-pasting commands from a stale doc, 'the runbook is lying to you') is the exact pain SmbOS's executable + drift-reviewing SOPs target; lead marketing with it.
    - Gap to exploit: these tools have NO scheduling, NO human-approval gate, NO multi-session/agent orchestration, NO audit ledger. SmbOS's do-loop + plate + cron + recent-runs is precisely the missing layer on top of plain-markdown runbooks.



## Cluster: Scheduled / background AI agents & cron-for-agents

_Across this cluster the entire competitive frontier has converged on two ideas SmbOS already centers, which validates the bet and shows where to go deeper. First, durable human-in-the-loop pause/resume is now the defining primitive: Trigger.dev waitpoint tokens, Inngest waitForEvent, Devin/Genie 'return when blocked,' and ChatGPT agent's permission prompts are all the same pattern, an agent pausing cheaply until a human approves, then resuming exactly where it left off. SmbOS's 'In flight -> On your plate -> pick up/resume' loop IS this primitive, just rendered in owner-plain language instead of dev SDK terms; the borrow is to make it formally durable (resume-from-pause, zero cost while waiting) and to make every paused run a one-click answerable plate item. Second, legibility of autonomous work is the trust battleground, and it splits the field cleanly: the infra tools (Inngest, Trigger.dev) win on per-step traces + auto-captured per-run cost/tokens/latency + replay, while the first-party/consumer tools (Claude Code Routines, ChatGPT Tasks) draw the loudest complaints precisely for cost opacity, lock-in, and noisy/pointless scheduled runs. SmbOS's structural advantages, local-first, plain-markdown SOPs you own, a live dashboard with Recent runs and a budget, line up directly against those complaints. The highest-leverage moves: (1) attach real cost to every run and show remaining budget plainly (kills the #1 Routines/Claude-Code complaint); (2) make 'Recent runs' a replayable step trace, not a status badge; (3) add skip/conditional logic so scheduled SOPs don't fire pointless work (kills ChatGPT Tasks' #1 complaint); (4) end every run with a reviewable artifact on the plate (the Devin/Genie trust contract); and (5) recover missed/late scheduled runs, which matters more here than for cloud competitors because this repo's own memory documents that Darwin launchd timers don't fire and cron is the fallback. Positioning-wise, the HN backlash against Routines ('I want a commodity, not a platform,' anti-lock-in, ToS chilling effect) is a direct opening: SmbOS as the local, file-owned, model-agnostic scheduler-and-plate is exactly what that audience says it wants._

### Claude Code Routines (Scheduled Tasks) - Anthropic's own cron-for-agents: schedule a Claude Code prompt or slash command to run as a cloud agent on your repo, even when your laptop is closed.

- **Category:** First-party agent scheduler / cloud agent runner  
- **URL:** https://claude.ai/code/routines  
- **Relevance:** high  
- **How it works:** You package a prompt or slash command plus repo(s) and connectors once, attach one or more triggers (cron cadence: hourly/daily/weekdays/weekly in local TZ, or webhook, or GitHub event), and Anthropic runs it on its cloud. Unlike a static cron script, the agent takes different actions based on context and available connectors. It hands back a result when done (PR, draft, lint-fix pass). This is the closest direct analogue to SmbOS's 'Coming up' (queued/scheduled) and 'Recent runs' surfaces, but cloud-hosted and headless rather than a local dashboard.  
- **Value prop:** Recurring agent work with zero infra: no server, no keeping your machine on. Same Claude Code config you already use, just on a schedule/trigger.  
- **Tech/stack:** Anthropic-managed cloud infra (server-side, not local). A routine = saved Claude Code config (prompt + one or more repos + connectors). Triggers: cron schedule, webhook/API call, GitHub events; multiple triggers can be combined on one routine. Created at claude.ai/code/routines or via /schedule in the CLI. Closed-source, proprietary.  
- **Pricing:** Bundled into paid Claude plans (Pro/Max/Team/Enterprise), research preview since Apr 14 2026. Daily run caps: Pro 5/day, Max 15/day, Team/Enterprise 25/day; metered overage if enabled. Token-metered underneath, so 'multitasking' multiple concurrent sessions burns tokens fast.  
- **Target user:** Existing Claude Code users (developers) who want recurring/triggered agent runs without standing up their own scheduler.  
- **Key features:**
    - Cron + webhook + GitHub-event triggers, combinable on one routine
    - Runs server-side so it works with laptop closed
    - Reuses existing Claude Code config (prompt, repos, connectors, skills)
    - Typical jobs: babysitting open PRs, nightly lint-and-fix, morning draft generation for review
    - Local /schedule slash command to create from the CLI
- **User feedback:**
    - (mixed) The Register, 'Claude Code routines promise mildly clever cron jobs' (2026-04-14): Framed as only 'mildly clever' automation; warns that running multiple concurrent sessions 'burns through tokens far more rapidly,' implying cost inefficiency.
    - (negative) Hacker News thread id=47768133 (Claude Code Routines): Dominant sentiment is anti-lock-in: 'I want a commodity, I want a provider, not a platform.' Routines seen as an 'unnecessarily complex wrapper around simple functionality (cron jobs, webhooks) that could be implemented locally,' creating lock-in.
    - (negative) Hacker News thread id=47768133: Trust erosion: users report perceived model 'nerfing,' hidden system prompts, disappearing 1M context, and ToS ambiguity about using subscriptions with third-party CLIs/bots (a 'chilling effect').
    - (negative) HN id=44759427 / AOL coverage on usage limits: Broad Claude Code cost anxiety: users hitting usage limits 'way faster than expected,' caching bugs that silently raised costs 10-20x. Relevant because Routines run on the same metered substrate.
- **Borrowable for SmbOS:**
    - Triggers as a first-class, combinable concept: let one SOP fire on a schedule AND on an event (inbox arrival, webhook) AND manually, surfaced together in 'Coming up' (matches sop-triggers already in the plugin).
    - A 'routine = saved config' object (prompt + scope + connectors) maps cleanly to an SOP-with-a-trigger; make that object visible and editable in the dashboard, not buried in cron syntax.
    - Lean into the anti-lock-in sentiment as positioning: SmbOS is local-first, plain-markdown SOPs in ~/sops, git-syncable memory, model-agnostic-ish. The HN crowd explicitly wants this. 'Your SOPs and schedules are plain files you own' is a real wedge.
    - Surface token/cost burn honestly: the loudest complaint is invisible cost. SmbOS's Settings budget + 'Recent runs' with per-run cost directly answers the #1 Routines pain.
    - Cap/quota visibility: Routines have opaque daily caps; SmbOS can show remaining budget/runs plainly ('3 of your daily runs left').

### Trigger.dev - Open-source TypeScript framework for durable background jobs and AI agents, with no-timeout long runs, retries, queues, and human-in-the-loop waitpoints.

- **Category:** Durable execution / background-job runtime (agent infra)  
- **URL:** https://trigger.dev  
- **Relevance:** high  
- **How it works:** Developer writes tasks as durable functions in TS. The runtime handles scheduling (crons/schedules), automatic retries, concurrency/queue control, and idempotency. The standout for SmbOS: Waitpoint tokens. A task can pause indefinitely (checkpointed, zero idle compute) until a human completes the token via SDK call, React hook, or a POST to a returned callback URL. This is the canonical human-in-the-loop approval primitive. You can also stream a running task to the foreground (subscribe to runs, stream AI output).  
- **Value prop:** Production-grade durability for long/async agent work without managing infra: no serverless timeouts, automatic recovery, and built-in approval gates that cost nothing while waiting.  
- **Tech/stack:** TypeScript SDK; you write normal async code, deploy tasks to Trigger.dev's runtime (cloud or self-hosted). Tasks can include system packages (browsers, Python, FFmpeg). HTTP-invoked. OSS on GitHub (triggerdotdev/trigger.dev). Has an MCP server and 'agent skills'.  
- **Pricing:** Open source (self-host) + managed cloud. Free $0 ($5 free usage, 10 concurrent runs, 10 schedules, 1-day log retention), Hobby (~$10 usage, 50 concurrent), Pro (~$50 usage, 200+ concurrent). Billed only while tasks execute (idle/waiting is free).  
- **Target user:** TypeScript developers building AI features/agents and heavy async jobs into their own product.  
- **Key features:**
    - Waitpoint tokens: pause a run for human approval indefinitely at zero idle cost; resume via callback URL/SDK/React hook
    - No timeouts: long-running AI/media tasks that serverless can't handle
    - Automatic retries + idempotency; only the work, not the whole job, is wasted on failure
    - Scheduled tasks (crons) + event triggers
    - Subscribe/stream a background run to the foreground (move work from background to visible)
    - Self-hostable OSS; MCP server + agent skills
- **User feedback:**
    - (positive) Hacker News id=37753461 ('use it every day'): 'Trigger.dev is awesome, use it every day. Feature list is quite impressive.' Praised as an easier-to-use Temporal for TS devs with good integrations.
    - (positive) Show HN id=37750763 (V2 launch) + aichief review 2026: Type-safe approach, dev speed, scalability, clear docs, and responsive founder support repeatedly cited as strengths vs Zapier/n8n/Inngest.
    - (mixed) HN / GitHub discussion #784 (v3): Earlier versions ran tasks inside the existing deployment, so individual tasks were bounded by serverless timeouts; users found it hard to reason about what would actually run as a true background job. (v3/v4 addressed long runs.)
- **Borrowable for SmbOS:**
    - Waitpoint as the model for the 'On your plate' handoff: a run can pause and sit on the human's plate, then resume exactly where it left off when the human approves/answers, with no compute burned while waiting. This is precisely SmbOS's pick-up loop made durable.
    - Callback-URL approval: each pending run exposes a one-click resume action (the dashboard button is the 'complete the token' call). Cheap, legible human-in-the-loop.
    - 'Idle waiting is free' framing for the budget story: pausing for the owner doesn't cost money; only active agent work does. Reassuring for budget-anxious solo operators.
    - Move background to foreground: let a user click an 'In flight' session and stream its live output, then drop back. Trigger.dev's subscribe/stream model is the UX precedent.
    - Position SmbOS as the local/plain-markdown counterpart to a dev-infra product: same durability ideas, but for SOPs an owner can read, not TypeScript tasks.

### Inngest (incl. AgentKit) - Durable-execution platform that turns each agent step (LLM call, tool call, save) into a tracked, retryable, resumable unit, with built-in approval pauses and per-step cost/latency observability.

- **Category:** Durable workflow / agent orchestration infra  
- **URL:** https://www.inngest.com/ai  
- **Relevance:** high  
- **How it works:** You decompose an agent into steps; each step.run() is memoized so on crash/resume completed steps return cached results instantly and only the failed step retries. Workflows can pause mid-run for approval ('hours or days, state maintained automatically') via waitForEvent. Every LLM call is a first-class event capturing prompt, response, token count, latency, and cost automatically. Flow control adds concurrency limits and throttling by any identifier (e.g. per-user) so one spike can't exhaust shared OpenAI quota. The Dev Server gives step-by-step traces, replay, and re-trigger.  
- **Value prop:** Make autonomous multi-step agent work reliable AND legible: nothing is lost on failure, humans can approve mid-flight, and every run is a replayable trace with cost attached.  
- **Tech/stack:** SDK across languages; step.run() as the core durable primitive, step.invoke() to call sub-agents synchronously (parent pauses without burning compute), step.waitForEvent() for human-in-the-loop. Functions invoked over HTTP, so they run on any serverless/HTTP host. AgentKit is its agent framework; useAgent React hook streams durable workflows to the frontend. Local Dev Server for traces/replay.  
- **Pricing:** Managed cloud with free tier + usage tiers; local Dev Server is free. (Step-based / run-based billing.)  
- **Target user:** Engineering teams putting AI agents/workflows into production who need reliability and observability.  
- **Key features:**
    - Per-step durability + memoization: resume from failure, no duplicated work
    - waitForEvent: pause days for human approval, state auto-maintained
    - Automatic per-LLM-call observability: prompt, tokens, latency, cost
    - Flow control: concurrency + throttling by arbitrary key (per-user fairness)
    - Cron/scheduled functions; missed runs logged and recoverable
    - Dev Server: full step traces, replay a run, re-trigger a function
    - useAgent hook streams a durable run to the UI in real time
- **User feedback:**
    - (positive) Inngest blog 'Durable Execution: The Key to Harnessing AI Agents in Production': Positions durable steps as what makes production agents debuggable and reliable; steps become 'observable, recoverable, testable operations.' (Vendor source; reflects the design thesis devs buy into.)
    - (mixed) General dev comparisons (aichief / dev community vs Trigger.dev): Often compared head-to-head with Trigger.dev; choice comes down to language/ecosystem and serverless vs managed-runtime preference rather than a clear winner.
- **Borrowable for SmbOS:**
    - Per-run trace = the 'Recent runs' detail view: show each SOP run as an ordered list of steps with status, so an owner can see exactly what the agent did and where it's waiting. Legibility is the whole trust story.
    - Auto-captured cost/tokens/latency PER step rolled up per run: directly powers SmbOS's budget feature and makes spend legible (the antidote to the Routines/Claude-Code cost-opacity complaints).
    - Replay / re-trigger a run from the dashboard: if a scheduled SOP run fails or drifts, let the owner re-run it with one click instead of reconstructing context.
    - 'Missed runs never stay missed': SmbOS runs scheduled work via cron; surface and let the owner recover missed/late runs (the repo's own memory notes Darwin launchd timers don't fire, so a missed-run recovery surface is especially valuable here).
    - waitForEvent as the formal model for 'In flight -> On your plate -> resume': a session that needs the owner pauses cheaply and re-enters the plate, then resumes on answer.
    - Concurrency/throttling by key: if SmbOS ever runs several sessions, fairness/limits per project prevents one runaway SOP from starving the budget.

### ChatGPT Tasks + ChatGPT agent (formerly Operator) - Consumer-grade scheduled AI: ChatGPT can run prompts on a schedule and deliver results by push/email, and its agent mode autonomously operates a virtual computer/browser to complete multi-step tasks.

- **Category:** Consumer scheduled assistant + computer-use agent  
- **URL:** https://openai.com/index/introducing-chatgpt-agent/  
- **Relevance:** medium  
- **How it works:** For Tasks: you phrase a request, set a time/recurrence (clock icon), and ChatGPT runs it autonomously and delivers results via push notification or email at the scheduled time. For agent: you hand it a goal and it works in a sandboxed virtual computer, browsing and acting; it can pause to ask for permission on consequential steps and you can take over the browser. This is the consumer/non-technical end of the same do-loop SmbOS implements, but cloud-hosted, browser-driven, and far less legible about cost/steps.  
- **Value prop:** Zero-setup recurring automation and 'do the task for me' for non-technical users, delivered where they already are (ChatGPT, email, push).  
- **Tech/stack:** Cloud. Tasks = scheduled prompt runs with daily/weekly/monthly repeat. ChatGPT agent uses a Computer-Using Agent (CUA) model driving its own virtual browser (clicks, types, scrolls) plus connectors (Gmail, Drive, GitHub) for context. Closed-source.  
- **Pricing:** Bundled in ChatGPT paid tiers (Plus/Pro/Team). Tasks limited to 10 active tasks per user.  
- **Target user:** Mainstream consumers and prosumers; non-technical users automating reminders, recurring content, follow-ups.  
- **Key features:**
    - Scheduled prompts with daily/weekly/monthly recurrence
    - Results delivered via push notification or email
    - Agent mode: autonomous virtual browser + computer use (CUA)
    - Connectors (Gmail/Drive/GitHub) for context
    - Permission prompts on consequential actions; user can take over
- **User feedback:**
    - (negative) OpenAI Help Center + multiple reviews: Hard 10-active-task cap; tasks with multiple run-times count as multiple tasks, so the cap is hit fast. Users must delete tasks to add new ones.
    - (negative) Reddit/review roundups on ChatGPT Tasks: No conditional logic, so notifications are 'repetitive and useless'; the lack of smart triggering undermines it as a task manager. Still 'in beta' after months.
    - (mixed) VentureBeat 'OpenAI's agentic era begins' + Operator coverage: Agent/Operator 'operates slowly, sometimes hesitates on simple interface decisions, and is not yet capable of replacing direct human control.'
- **Borrowable for SmbOS:**
    - Plain-language scheduling UX (no cron syntax) is exactly SmbOS house style; ChatGPT's 'every weekday at 7am, your timezone' phrasing is the bar to match or beat in 'Coming up'.
    - Deliver results where the human is: push/email digest of completed runs. SmbOS could push a 'here's what got done overnight' summary instead of requiring the owner to open the dashboard.
    - Avoid the 10-task cap trap: don't conflate one recurring SOP with N entries; SmbOS should model a schedule as one object with many fire times (this is also a Routines mistake to avoid).
    - Add conditional/skip logic so scheduled runs don't fire pointless work: 'only run if there's something on the plate / new inbox items,' answering ChatGPT Tasks' #1 complaint (noise).
    - Permission-to-act + take-over model: SmbOS's Settings 'launch permission' is the same instinct; borrow agent mode's explicit 'pause and ask before a consequential action,' surfaced as a plate item.

### Cosine Genie / Devin (autonomous background SWE agents) - Async autonomous software-engineer agents you assign tickets to; they plan, code, test, and open a PR in the background, reporting back via Slack/UI when done or blocked.

- **Category:** Autonomous background coding agent  
- **URL:** https://cosine.sh  
- **Relevance:** medium  
- **How it works:** You delegate a task (ticket/Slack/NL prompt); the agent autonomously analyzes the repo, plans, edits, runs tests, iterates, and opens a PR for human review, or returns for clarification when blocked. Devin adds scheduled chores (daily QA, release notes, doc upkeep) and API-triggered tasks from CI/CD, Slack, issue trackers. The defining UX is delegation + async report-back + human reviews the PR rather than the work, the same trust contract SmbOS's pick-up/report-completion loop is built on.  
- **Value prop:** Offload whole tickets to an agent that works in parallel and returns a reviewable artifact (PR), so the human reviews instead of implements.  
- **Tech/stack:** Cloud. Cosine's Genie 2 is a custom-trained model (30% SWE-Bench, 72% SWE-Lancer claims). Task intake from Jira ticket, Slack message, or UI prompt; works in background on the codebase, opens PRs. Devin similar, with Desktop app, API, and 'scheduled chores.' Closed-source.  
- **Pricing:** Cosine: seat + credit pool. Hobby $20/seat/mo (5M credits), Pro $200/seat/mo (60M credits), 80 free tasks. Devin: subscription/usage; widely reported as pricey.  
- **Target user:** Engineering teams delegating well-scoped coding tasks; less for solo non-coders.  
- **Key features:**
    - Task intake from Slack / issue tracker / NL prompt
    - Fully async background execution; opens a PR for review
    - Returns for clarification when blocked (human-in-the-loop checkpoints)
    - Devin: scheduled 'chores' (recurring QA, release notes, docs) + API triggers
    - Parallel work across many tickets at once
- **User feedback:**
    - (mixed) Trickle 'Devin AI Review: The Good, Bad & Costly Truth (2025 Tests)': Capable on well-scoped tasks but costly and inconsistent on ambiguous work; reviewers land around 7.5/10 and stress tight scoping and human review.
    - (positive) Cosine pricing/product pages + skywork deep dive: Praised as a genuinely agentic/async 'AI engineer' (PRs, codebase retrieval) rather than an autocomplete copilot; benchmark claims (30% SWE-Bench, 72% SWE-Lancer) used as proof.
    - (negative) General SWE-agent sentiment (HN/Reddit on Devin-class tools): Recurring complaint that autonomous agents overstate readiness, do well on demos/benchmarks but need heavy human review and clear scoping in real repos.
- **Borrowable for SmbOS:**
    - The 'review the artifact, not the work' contract: every SmbOS run should end with a concrete, reviewable output (draft, diff, summary) landing on the plate, not just a 'done' status. Trust comes from a reviewable artifact.
    - Return-when-blocked as a plate item: when a session needs a decision, it should surface a specific question on 'On your plate' with enough context to answer in one step (mirrors Genie/Devin's clarification checkpoints).
    - Scheduled 'chores' framing (Devin): recurring upkeep SOPs (weekly review, stale-SOP audit, digest) are a natural fit for SmbOS's sop-triggers; name them plainly as recurring chores in 'Coming up'.
    - Intake from where work already lives: let an SOP be triggered from an inbox/Slack/issue source, not only the dashboard, so tasks land on the plate automatically (the repo already does inbox-watch sync; generalize it).
    - Honesty about scope/limits: the consistent market lesson is that autonomous agents over-promise. SmbOS's plain 'waiting for you' / explicit launch-permission framing should keep the human firmly in the loop and set expectations low and honest.



## Cluster: Local-first command-center dashboards for technical solo operators

_The cluster splits into two camps, and SmbOS sits at their intersection - which is its strongest defensible position. Camp one is local-first agent/session command centers: Claude Code Agent View (first-party), claude-code-command-center, and tmux/Zellij. The dominant, now-validated pattern here is a state-grouped board that bubbles 'needs-you' rows to the top, lets the human peek-and-reply WITHOUT attaching to the full session, keeps autonomous work alive via a supervisor/daemon that survives disconnect, and makes invisible work legible with cheap model-generated one-line summaries. SmbOS's 'On your plate / In flight / Coming up' already mirrors this; the live edge to win on is liveness fidelity (Agent View and command-center both separate TASK state from PROCESS-alive state - the exact problem on the inflight-session-liveness branch) and making the deliverable the clickable pickup point colored by how-much-it-needs-you. Camp two is procedures-as-plain-files-plus-LLM: Superpowers (markdown skills the agent reads before acting, with gated brainstorm->plan->execute->review) and CRM-CLI (local SQLite + MCP server where you narrate in natural language and the LLM does the structured write). Both prove SmbOS's core bet - owned plain files + MCP + an LLM doing the structured work on top - is a loved, adopted shape for the terminal-native solo operator. Three cross-tool signals matter most for SmbOS: (1) Trust is built by legibility + explicit consent gates, not autonomy - Agent View refuses unwatched bypass-permission modes until accepted once, Superpowers blocks execute until a plan is approved, and these map directly to SmbOS's launch-permission/budget settings and the 'Prepare' verb (preview intent before granting launch). (2) The universal failure mode in this cluster is opaque state: Homepage's silent widget auth failures with unhelpful errors are the anti-pattern SmbOS's plain-language house style ('waiting for you', 'in flight') is built to beat - when something breaks, say what and which SOP in plain words. (3) The differentiator is NOT the dashboard plumbing (someone already shipped the identical FastAPI+SQLite+WebSocket+vanilla-JS stack) - it's the SOP/do-loop layer that closes the circle: task lands on the plate -> human picks up -> primed session runs -> completion reports back, with scheduling. Borrow the proven legibility mechanics (peek-and-reply, Haiku row summaries, two-tier liveness glyphs, deliverable-as-pickup, always-visible verbs á la Zellij) and lean hard into the anti-Raycast positioning: your data is just plain-markdown files you own, local-first, your model - exactly the lock-in/closed/cloud/no-BYO-key complaints that dog the closed players._

### Claude Code Agent View - Anthropic's built-in single-screen TUI for dispatching and supervising many background Claude Code sessions, surfacing which ones need you.

- **Category:** Multi-agent session command center (first-party)  
- **URL:** https://code.claude.com/docs/en/agent-view  
- **Relevance:** high  
- **How it works:** Core loop: open `claude agents` -> type a task and press Enter to dispatch a background session -> each session appears as a row grouped by state (Ready for review, Needs input, Working, Completed) with the needs-you rows pinned to the top -> press Space to 'peek' (most recent output or the blocking question) and reply inline without attaching -> press Enter/right-arrow to 'attach' into the full conversation, left-arrow to detach (session keeps running). A supervisor daemon keeps sessions alive without a terminal; finished sessions are stopped after ~1h to free resources but resume from disk on next interaction. Pin (Ctrl+T) keeps a session hot. Sessions persist across sleep/supervisor restart but fail on machine shutdown (recoverable by interacting). Also driveable headlessly from the shell: `claude --bg`, `claude agents --json`, `claude attach/logs/stop/respawn/rm <id>`.  
- **Value prop:** Turn invisible, scattered agent work into one legible at-a-glance board where the human only intervenes on the rows that need them, without losing any session context.  
- **Tech/stack:** Local-only. A per-user supervisor (daemon) process hosts each background session as its own full Claude Code process, separate from any terminal. State on disk under ~/.claude/jobs/<id>/state.json and ~/.claude/daemon/roster.json. Row summaries generated by a Haiku-class model. TUI rendered in the terminal. File edits isolated into git worktrees under .claude/worktrees/.  
- **Pricing:** Included on Pro, Max, Team, Enterprise, and API plans. Background sessions consume the same subscription quota as interactive ones (10 agents = ~10x burn).  
- **Target user:** Technical operators / developers running Claude Code who want to parallelize agent work and only step in when needed. Exactly SmbOS's real user.  
- **Key features:**
    - State-grouped rows with needs-you bubbled to top: Ready for review, Needs input, Working, Completed/Failed/Stopped
    - Two-tier glyphs: color = task state, shape = whether the underlying process is alive (✻ alive, ∙ exited-but-resumable, ✢ /loop sleeping with run count + countdown)
    - Peek panel (Space): shows the blocking question or latest output + an editable suggested reply (Tab); multiple-choice questions answerable with a number key; no full transcript needed
    - Haiku-generated one-line row summaries refreshed at most every 15s + on each turn end; parallel work shows a done/total count like 2/5
    - PR status as a first-class signal: PR #N label colored yellow/green/purple/grey by check/review/merge state, so 'pick up the result' = merge when it turns green
    - Terminal tab title shows awaiting-input count ('2 awaiting input'); state persists on disk across daemon restarts and sleep
    - Shell-scriptable headless API: claude --bg, agents --json (machine-readable state incl. waitingFor reason), attach/logs/stop/respawn/rm
    - Filters (s:blocked, a:<agent>, #PR), grouping by state or directory, pin, rename, reorder; recurring tasks packaged as a skill so you re-dispatch without retyping
    - Permission-mode gating: bypassPermissions/auto refused for unwatched sessions until accepted once interactively
- **User feedback:**
    - (mixed) Anthropic Claude Code docs (official, agent-view page): Explicitly labeled 'research preview'; docs warn interface/shortcuts may change. Honest about limits: rate limits scale linearly with agent count, sessions are local-only and die on machine shutdown (show as 'failed', recoverable), Claude-created worktrees are deleted with the session including uncommitted changes.
    - (positive) rits.shanghai.nyu.edu writeup + buildfastwithai/mindstudio guides: Framed as a genuine workflow shift: 'kick off a long task, send it to background, start a second agent, monitor both, pull forward only when it needs attention.' The needs-input-first sort and reply-without-attaching are repeatedly called out as the killer ergonomics.
- **Borrowable for SmbOS:**
    - SmbOS already mirrors the state-grouped board (On your plate / In flight / Coming up). Borrow the two-tier glyph idea: separate the TASK state (waiting/working/done) from the PROCESS liveness (session alive vs exited-but-resumable) - directly relevant to the inflight-session-liveness branch you're on.
    - Adopt 'peek + reply without attaching': let the owner answer a blocking question or pick a multiple-choice option straight from the dashboard card without opening the full Claude session. Suggested-reply prefill (Tab) lowers the cost of unblocking.
    - Haiku-generated one-line row summaries refreshed on a cadence (every 15s + on turn end) is a cheap, proven pattern to make autonomous work legible. SmbOS's 'In flight' cards could carry a model-written 'what it's doing right now' line instead of raw status.
    - PR/result as the pickup point: make the deliverable (a PR turning green, a file written, an invoice drafted) the clickable thing the owner acts on, colored by 'how much it needs you.' Maps to SmbOS 'Recent runs' / completion reporting.
    - Permission-mode gating: unwatched/autonomous modes require a one-time interactive acceptance before any session can run unattended. Mirrors SmbOS's Settings 'launch permission' and budget gates - keep that explicit human consent step.
    - Persist session state on disk so the dashboard survives restarts and can resume an exited session from where it left off (your liveness work). Show 'process exited, resumes on pickup' rather than a scary 'failed.'
    - Tab-title / OS-level awaiting-input count as an ambient signal the owner sees without the dashboard focused (analogue: tray badge).

### claude-code-command-center (amahpour) - Open-source web dashboard that watches Claude Code hook events and JSONL transcripts to show every local session's live state, cost, and context in a browser.

- **Category:** Multi-agent session command center (third-party, web)  
- **URL:** https://github.com/amahpour/claude-code-command-center  
- **Relevance:** high  
- **How it works:** Claude Code hooks are installed into settings; on each event they POST to /api/hooks, which updates per-session state (status, cost, tokens, context usage) in SQLite. A file watcher tails the JSONL transcripts. WebSocket broadcasts state changes to all connected dashboard clients in real time. The UI shows live transcripts, collapsible tool-call history, and cost/token analytics charts.  
- **Value prop:** A trustworthy live mirror of all your local Claude sessions in one browser tab - exactly SmbOS's 'live-mirror dashboard' thesis, built by someone else with the same stack.  
- **Tech/stack:** Nearly identical to SmbOS's dashboard: FastAPI + uvicorn backend, SQLite (aiosqlite) with FTS5 full-text search, a JSONL file-watcher on ~/.claude/projects/, and a vanilla HTML/CSS/JS frontend (no build step) with xterm.js for terminal rendering, talking over REST + WebSocket. Local-only, no cloud.  
- **Pricing:** Free / open source. Self-hosted on localhost:4700.  
- **Target user:** Developers running multiple Claude Code sessions who want a browser command center with analytics, search, and ticket/PR linking.  
- **Key features:**
    - Five session states with colors: Working (green), Waiting (yellow, needs input/permission), Idle (blue), Stale (grey, >5min no activity), Completed (grey)
    - Hook-event ingestion via POST /api/hooks (the same mechanism SmbOS uses for its plate auto-sync)
    - WebSocket fan-out to all dashboard clients (SmbOS uses SSE - same legibility goal)
    - Live transcript view with collapsible tool calls; FTS5 full-text search across past sessions
    - Per-session cost/token/context-usage tracking with analytics charts
    - Jira ticket auto-detection from git branch names with clickable links; GitHub PR / GitLab MR links
    - Zero build step (vanilla JS + xterm.js); runs entirely on localhost
- **User feedback:**
    - (positive) GitHub README (project self-description): Pitches the local-only, no-build, hook-driven architecture as the whole point - validates that FastAPI + SQLite + WebSocket + vanilla JS is the de-facto stack for a Claude Code command center, the same call SmbOS made.
- **Borrowable for SmbOS:**
    - Confirms SmbOS's architecture is the right shape; the differentiator must be the SOP/do-loop layer (pick-up -> primed session -> completion report), not the dashboard plumbing. Don't out-build them on transcript-viewing.
    - Their explicit 'Stale (>5min no activity)' state is a clean liveness heuristic - directly useful for your inflight-session-liveness work to distinguish 'in flight and progressing' from 'in flight but stalled.'
    - Per-session cost/token/context tracking surfaced as charts pairs with SmbOS's Settings 'budget' - show spend per run on the card, not just a global budget cap.
    - Auto-linking external artifacts (Jira tickets from branch names, PRs) to sessions is a low-cost trust/legibility win: tie a run to the concrete thing it touched.
    - xterm.js gives an attach-the-transcript escape hatch in-browser; SmbOS could offer 'open full session' from a card without forcing the owner into a terminal.

### CRM-CLI (crmcli.sh) - A local-first personal CRM that lives in the terminal with a built-in MCP server so Claude can read and update your contacts, deals, and follow-ups.

- **Category:** Local-first founder/operator data tool with MCP  
- **URL:** https://www.crmcli.sh/  
- **Relevance:** high  
- **How it works:** Install the binary; `crm` manages contacts, organizations, deals, interactions, tasks, and tags from the command line. The MCP server is the creator's most-used surface: after a meeting you tell Claude what happened in natural language and it logs the interaction, updates the deal, and creates follow-up tasks. Claude maintains a per-contact summary field as a 'living dossier' for pre-meeting context. Everything is plain CLI + a single local SQLite file.  
- **Value prop:** Your data stays a local file you own; an LLM does the structured data entry for you through MCP, turning a chore (CRM upkeep) into a natural-language aside.  
- **Tech/stack:** Go (~3k LOC), single static binary, local SQLite at ~/.crm/crm.db with FTS5 search. No cloud, no accounts. Ships an MCP stdio server (`crm mcp serve`). Outputs table/JSON/CSV/TSV for Unix piping.  
- **Pricing:** Free / open source (single static binary).  
- **Target user:** Solo founders/operators who live in the terminal and found Notion/spreadsheets/SaaS CRMs too heavy. The same persona as SmbOS's real user.  
- **Key features:**
    - Single static binary, zero-config: install, add a contact, done (no setup wizard, no account)
    - Local SQLite (~/.crm/crm.db) with FTS5 - full data ownership, greppable, no cloud
    - MCP stdio server so Claude reads/writes the CRM directly ('tell Claude what happened, it logs it')
    - AI-maintained 'living dossier' summary field per contact for pre-meeting prep
    - Unix-composable: table/JSON/CSV/TSV output for piping into other tools
- **User feedback:**
    - (positive) Show HN (news.ycombinator.com/item?id=47292114) + creator's own framing: Origin story resonates: built it because Notion/spreadsheets/CRM apps were 'all too heavy.' Creator calls the MCP server the most-used feature - the value is the LLM doing structured entry from a natural-language recap, not the CLI itself. (Thread was small; limited external sentiment.)
- **Borrowable for SmbOS:**
    - Validates SmbOS's core bet: plain local files + MCP server + an LLM that does the structured work on top is the winning shape for a terminal-native solo operator. SOPs-in-~/sops is the same move as CRM-in-~/.crm.
    - 'Tell Claude what happened, it logs the interaction and creates the follow-up' is the do-loop in miniature. SmbOS could let an owner narrate a completed task in plain language and have it auto-update the plate / log the run / queue the next step.
    - The 'living dossier' pattern: an AI-maintained, always-current summary field. SmbOS SOPs could carry an auto-maintained 'last run notes / current state' block so a freshly picked-up session is primed with context without re-reading history.
    - Unix-composable output (JSON/CSV) as a first-class feature - SmbOS already has stdlib scripts; make their state queryable/pipeable so power users can script the plate.
    - Zero-config install as a trust signal for the terminal persona: no wizard, no account, your data is just a file.

### Raycast (+ AI Extensions) - macOS (now Windows) keyboard-first command palette that grew from a launcher into an AI agent that takes actions across your installed extensions.

- **Category:** Command palette / launcher with AI tool-calling  
- **URL:** https://www.raycast.com/  
- **Relevance:** medium  
- **How it works:** Invoke with a hotkey (default Alt/Opt+Space) to open the command bar. Beyond launching apps and running ~40 window-management commands, AI Extensions let Raycast AI take action: an extension exposes its commands as tools, and from AI Chat / Quick AI / Root Search you @-mention it (sparkle icon marks AI-enabled extensions); the LLM picks which tool to call with which args and runs it. Raycast says it AI-enabled ~50 existing extensions. Window-management commands cycle sizes (½, ⅔, ⅓) on repeat; a raycast://confetti URL scheme celebrates long-running script completion.  
- **Value prop:** One keystroke to search and now to ACT - the pivot from 'search' to 'search + act' via natural-language tool-calling over an extension ecosystem.  
- **Tech/stack:** Proprietary, closed-source macOS-native app (Windows in preview). Extensions authored in React + TypeScript + Node against Raycast's API and built-in UI component library. AI routes to multiple third-party LLM providers. Cloud-backed for AI/sync.  
- **Pricing:** Free core; Pro (~$8/mo, was a point of complaint) adds AI with access to OpenAI/Anthropic/Perplexity/etc. models. AI Extensions are a Pro feature. No bring-your-own-key for the AI add-on (a recurring complaint).  
- **Target user:** Power users and developers who want a fast keyboard-driven hub for search, window management, snippets, clipboard, and now AI actions. Adjacent persona to SmbOS but desktop-launcher-shaped, not SOP/do-loop-shaped.  
- **Key features:**
    - Keyboard-first command palette as the single entry point (hotkey -> type -> act)
    - AI Extensions: @-mention an extension and the LLM chooses the tool + args to run actions, not just chat
    - Sparkle-icon affordance marks AI-enabled extensions so users know what's actionable
    - React/TS/Node extension SDK with a provided UI component library - large third-party ecosystem
    - Multi-provider model access (OpenAI, Anthropic, Perplexity, DeepSeek, Gemini) behind one UI
    - Delightful flourishes: confetti URL scheme for script completion; window-management size cycling
- **User feedback:**
    - (negative) alternativeto.net reviews + ai-review.com: AI is seen as overpriced: ~$8/mo add-on (some cite an effective ~$16/mo), and no bring-your-own-API-key, vs ~$3/mo alternatives. macOS-only historically excluded Windows/Linux users.
    - (negative) Hacker News thread 39300574 + 46024754: Frustration with the proprietary, closed extension model ('proprietary software that doesn't allow me to do what I want'); worry Raycast is using VC runway to underprice and squeeze out Alfred - lock-in concerns. Spawned OSS clones (RustCast, Tauri/Rust Linux launchers).
    - (positive) MacStories hands-on + git-tower 'Mastering Raycast': AI Extensions praised as genuinely useful for cross-app actions; the keyboard-first launcher is a beloved daily driver. The act-not-just-search pivot lands.
- **Borrowable for SmbOS:**
    - The 'search -> act' pivot is the SmbOS thesis in launcher form: don't stop at showing SOPs, make them runnable in one gesture. Keep the Run/Queue/Prepare verbs front and center on the Procedures library.
    - Discoverability affordance: Raycast's sparkle icon tells users which extensions can take AI action. SmbOS should make it visually obvious which SOPs are runnable-by-agent vs reference-only, and which are scheduled.
    - Tool-calling over a library where the model picks the right tool+args is exactly the SmbOS SOP-selection problem. The lesson: a clean per-SOP tool/arg contract beats free-text so the agent reliably picks the right procedure.
    - Cautionary contrast: Raycast's lock-in/closed/cloud/no-BYO-key complaints are precisely SmbOS's differentiators (plain-markdown, local-first, your files, your model). Lean into 'your data is just files' as the anti-Raycast positioning.
    - Delight as trust: a small completion flourish (Raycast's confetti) when an autonomous run finishes successfully makes long-running agent work feel finished and owned - cheap to add to a completion-reported run.

### Homepage / Homarr (self-hosted homelab dashboards) - Self-hosted single-pane dashboards that aggregate links and live widgets for all your services; Homepage is YAML/Docker-label driven, Homarr is a UI-configured React app.

- **Category:** Self-hosted aggregation dashboard (homelab)  
- **URL:** https://gethomepage.dev/  
- **Relevance:** medium  
- **How it works:** You declare services (Homepage: in YAML or via Docker labels; Homarr: via drag-and-drop UI). Each service can be a plain link or a live widget that calls the service's API (with an API key) to show status/stats (e.g., download counts, container health, media now-playing). The page polls those APIs and renders cards/widgets. Homepage is static + proxied for speed; Homarr stores config and renders dynamically.  
- **Value prop:** One trustworthy at-a-glance page for everything you run, with live status pulled from each service rather than just dead bookmarks.  
- **Tech/stack:** Homepage: fully static, proxied, configured via YAML files or Docker label discovery; 100+ service-API widget integrations. Homarr: React app, configured through a UI (v1.0 rewrite explicitly dropped YAML - 'no YAML involved'), Docker integration, built-in RSS reader, Home Assistant. Both local/self-hosted.  
- **Pricing:** Free / open source, self-hosted (Docker).  
- **Target user:** Homelabbers and self-hosters who want one bookmarkable page that both links to and shows live status of their services. Adjacent (infra dashboard, not work/agent dashboard) but instructive on config burden.  
- **Key features:**
    - 100+ service integrations that pull live status into widgets (Homepage)
    - Two config philosophies: declarative YAML/Docker-labels (Homepage, version-controllable) vs UI-first no-YAML (Homarr)
    - Docker label auto-discovery so new containers appear without manual config (Homepage)
    - Fast static + proxied rendering (Homepage); dark mode, RSS, Home Assistant control (Homarr)
    - Self-hosted, local-first, data stays on your box
- **User feedback:**
    - (positive) alternativeto.net + Lemmy/homelab blogs: Loved for being 'easy to setup, easy to use, minimalist and quick'; converts from Heimdall say 'never looked back.' The live-status-not-just-links value is the draw.
    - (negative) gethomepage GitHub issues/discussions (#5208, #1753, #5008, #3152, #2285): Widget API integrations are brittle and hard to debug: trailing-slash breaks an API call; wrong/ignored API keys; duplicate service names silently overwrite each other's cached auth keys and the error message doesn't say which API failed or why. Config errors fail opaquely.
    - (mixed) Homarr 1.0 changelog: Homarr explicitly removed YAML in v1.0 ('no YAML involved') as a direct response to config-file friction - but the rewrite requires migrating your compose file, a breaking change.
- **Borrowable for SmbOS:**
    - Live-status-not-dead-links is the whole point: SmbOS's dashboard should always show the real current state of each SOP/run (last run, in flight, stalled), never a stale list. This is the 'trustworthy live mirror' bar.
    - Config-burden lesson: Homepage's opaque widget failures (silent auth overwrites, unhelpful error messages) are exactly what SmbOS's plain-language copy rule avoids. When a run or trigger misconfigures, say in plain words what broke and which SOP, never a raw error.
    - Homepage's Docker-label auto-discovery (services appear without hand-config) suggests SmbOS could auto-discover SOPs/triggers from ~/sops frontmatter so the library and schedule populate themselves - no separate registry to keep in sync.
    - The YAML-vs-UI split maps to SmbOS's markdown SOPs + dashboard: keep the source of truth as editable plain-text files (version-controllable, AI-editable), and treat the dashboard as a view/invoker over them - avoid Homarr's mistake of trapping config in a UI database.
    - Declarative-and-version-controllable config is a feature for the technical persona; don't hide SOP/trigger definitions behind UI-only state.

### Superpowers (obra/superpowers) - A Claude Code plugin that ships composable markdown 'skills' (instructions, checklists, process diagrams) and enforces a gated brainstorm -> plan -> execute -> review workflow.

- **Category:** Claude Code workflow/skills framework (direct peer plugin)  
- **URL:** https://github.com/obra/superpowers/  
- **Relevance:** high  
- **How it works:** Ships 14+ composable skills as markdown that Claude reads before taking action. It enforces a structured pipeline where each step gates the next: mandatory Socratic brainstorming to refine requirements -> isolate a branch -> write a junior-engineer-grade plan -> execute with red-green-refactor TDD and subagent-driven code review. The 'skill = markdown instructions + checklist + process diagram Claude reads first' model is identical in spirit to SmbOS SOPs.  
- **Value prop:** Turn a coding agent from improviser into a disciplined process-follower by giving it reusable, gated procedures it must read and follow.  
- **Tech/stack:** Claude Code plugin (markdown skills + commands), requires Claude Code 2.0.13+. Skills are plain markdown files Claude reads before acting. Built by Jesse Vincent / Prime Radiant.  
- **Pricing:** Free / open source. Installed via /plugin marketplace add obra/superpowers-marketplace.  
- **Target user:** Developers using Claude Code who want a disciplined, repeatable methodology instead of ad-hoc prompting. Same delivery vehicle (a Claude Code plugin) and same plain-markdown-instruction substrate as SmbOS.  
- **Key features:**
    - Skills as plain-markdown instruction files Claude reads before acting (same substrate as SmbOS SOPs)
    - Gated workflow: brainstorm -> plan -> execute -> review, each step blocking the next
    - Composable skills covering the full SDLC (TDD, debugging, brainstorming, subagent-driven dev + review)
    - Distributed as a Claude Code plugin via a marketplace (same channel as SmbOS)
    - Mandatory brainstorm/plan gates that force human-legible intent before the agent builds
- **User feedback:**
    - (positive) blog.fsck.com (author Jesse Vincent, Oct 2025) + builder.io teardown: Widely cited as 'the structured workflow that actually works' - the gating (can't execute until a plan is approved) is credited with making agent output reliable. The plain-markdown-skill format is praised as inspectable and editable, not a black box.
    - (positive) Medium guides (Yee Fei, manav ghosh) + claudepluginhub: Strong adoption signal; treated as a reference implementation for how to package repeatable agent procedures as markdown skills. Validates the SOP-as-markdown thesis directly.
- **Borrowable for SmbOS:**
    - Strongest direct peer: confirms 'procedures as plain markdown the agent reads before acting' is a proven, loved pattern. SmbOS SOPs and Superpowers skills are the same primitive - SmbOS's edge is the owner-facing dashboard + do-loop + scheduling on top.
    - Gating as a trust mechanism: Superpowers blocks execute until a plan is approved. SmbOS's 'pick up -> primed session' could insert an explicit plan/approval gate for higher-stakes SOPs before the agent acts unattended - a human-in-the-loop checkpoint that maps to your launch-permission setting.
    - Composable/referenced skills (skills that call other skills) supports SmbOS's 'SOPs reference, don't paraphrase' memory rule - let SOPs compose canonical sub-procedures instead of restating them.
    - A marketplace/starter-pack distribution model: Superpowers ships a ready library of skills. SmbOS's sop-init starter pack is the analogue - ship enough good SOPs that the do-loop has something to chew on day one.
    - The brainstorm gate produces a human-legible artifact (the plan) before work starts. SmbOS could surface a 'what this run will do' preview on the card (its Prepare verb) so the owner sees intent before granting launch.

### tmux / Zellij (terminal multiplexer dashboards) - Terminal multiplexers used as persistent, panel-based command centers; Zellij modernizes the UX with discoverable modes and a persistent status bar, tmux stays minimal and scriptable.

- **Category:** Terminal multiplexer as personal command center  
- **URL:** https://zellij.dev/  
- **Relevance:** medium  
- **How it works:** Both split a terminal into panes/tabs and persist sessions across detach/reattach (work keeps running when you disconnect - same durability idea as Agent View's supervisor). tmux is configured via keybindings in a dotfile and excels at scripted, SSH/remote-first layouts. Zellij ships ready-to-use layouts (one command to split into columns/rows), dedicated modes (Pane, Tab, Session, etc.), and a persistent status bar that always shows the current mode and the available keys - built-in onboarding rather than memorized chords.  
- **Value prop:** A persistent, panel-based workspace that survives disconnects; Zellij's bet is that discoverability (always-visible modes + keys) beats tmux's power-user configurability for most people.  
- **Tech/stack:** tmux: C, since 2007, ~5MB, Unix-philosophy, heavily config-driven (.tmux.conf). Zellij: Rust, ~15MB, embeds a WASM plugin runtime, ships pre-defined layouts and a persistent on-screen status/hint bar. Both purely local terminal tools.  
- **Pricing:** Free / open source. Both local.  
- **Target user:** Terminal-native developers/operators (SmbOS's persona) who run long-lived, multi-pane sessions for monitoring, dev servers, logs, and tasks.  
- **Key features:**
    - Session persistence across detach/reattach - long-running work survives disconnect (durability parallel to Agent View's daemon)
    - Zellij: persistent status bar showing current mode + available keys = built-in onboarding, no memorized chords
    - Zellij: pre-defined layouts usable immediately with no config; dedicated modes for navigation
    - tmux: deeply scriptable + remote/SSH-first, minimal footprint, mature ecosystem
    - Both local-only, no cloud, plain-text config
- **User feedback:**
    - (positive) Multiple 2026 comparisons (dasroot.net, maketecheasier, mrpbennett.dev, tmuxai.dev): Zellij's persistent status bar is repeatedly called 'a brilliant onboarding mechanism' - users love that it shows which mode you're in and what keys are available without docs. 'Replaced tmux, screen, and my entire terminal workflow.'
    - (mixed) rrmartins Medium comparison + dasroot.net: tmux loyalists value its scriptability and minimal footprint for remote work; the tradeoff is a steep config/learning curve (memorized chords, hand-tuned .tmux.conf). Zellij's WASM runtime costs ~3x the memory but it's negligible on modern hardware.
- **Borrowable for SmbOS:**
    - Zellij's persistent always-visible 'what mode am I in / what keys are available' bar is the strongest UX lesson: never make the operator remember what they can do. SmbOS's dashboard should always surface the available verbs (pick up / reply / dismiss / run) in context on each card - discoverability over memorization. This aligns with your CLAUDE.md rule against stranding the user and the plain-vocabulary house style.
    - Session-persistence-across-disconnect is the durability model SmbOS needs for 'In flight': a picked-up session should survive the owner closing the dashboard and reappear with its state intact (reinforces the inflight-session-liveness work).
    - tmux-vs-Zellij is the 'configurable power vs immediate discoverability' tension SmbOS faces: keep SOPs as power-user-editable plain text (tmux side) while making the dashboard immediately usable with zero config and obvious affordances (Zellij side).
    - Pre-defined layouts / starter templates reduce time-to-value - SmbOS's starter SOP pack and default dashboard layout should make the do-loop demonstrable on first launch with no setup.

