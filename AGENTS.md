# Site Safety Watch: rules for every coding agent on the team

Read this whole file before you change anything. It applies to every agent the team uses and to
the person driving it. Breaking a hard rule can disqualify the team.

## 1. Read first

- `plans/MASTERPLAN-site-safety-watch.md`: why we build this, the demo story, the cut list.
- `plans/SCOPE-OF-WORK-site-safety-watch.md`: who owns what and the frozen contracts (section 0).
- Where the two disagree, the masterplan wins. If you are unsure, stop and ask Hemnaath (lead).
- Completion rule: one hazard (blocked exit) end to end first. Clip, local vision, de-duplicated
  event, Slack, human disposition, stored record. Nothing in "stretch" starts before that loop
  has been recorded once.

## 2. Hard rules (event)

1. **Runtime inference only on the GB10.** Product code calls only the box's local vLLM
   (`http://127.0.0.1:8000/v1`, model `nvidia/Qwen3.6-35B-A3B-NVFP4`). No cloud model or hosted
   API in the product, not even as a fallback. You may use the cloud to write code; the code
   you write may not call it. Read the endpoint from `VLLM_BASE_URL`, never hardcode another host.
2. **Built today, from scratch.** Every file is written on Sat 2026-10-03 after 09:00. Do not
   paste code from earlier projects. Libraries from pip are fine.
3. **Nothing from Canary Pact** (glasswing-canary-pact or canary-pact-onprem): no code, prompts,
   schemas, fixtures, skill files or UI.
4. **No AI attribution anywhere.** No Co-Authored-By trailers, no "Generated with" lines, no
   model or tool names in commits, PR text, README, writeup or slides. `.claude/settings.json`
   already turns this off for Claude Code. For any other tool, turn its trailer off or delete it
   from the message before you commit.
5. **No em dashes** in code, strings, comments, docs, commits or PR text. Use a comma, colon or
   parentheses.
6. **Measured numbers only.** Every latency, count, accuracy, memory or watts figure comes from a
   logged run on the GB10 (`story/numbers.json`). Label every assumption as one. Never invent a
   number, even as a placeholder in a README or slide.
7. **Public repo, so no secrets and no faces.** Slack tokens live only on the box in
   `~/.slack-tokens` (mode 600) and are read from the environment. Never commit clips, frames,
   the database or anything showing a person. `.gitignore` already covers `data/`, video files,
   `.env` and `.slack*`; do not weaken it.

## 3. Git workflow (GitHub enforces this)

- `dev` is the default branch. It only changes through a pull request. No approval is needed,
  so you merge your own PR.
- `main` only changes through a pull request from `dev`, and it needs one approving review from
  a teammate who did not open it. No direct pushes or force pushes to either branch, admins
  included.

Each task:

```bash
git switch dev && git pull
git switch -c <name>/<topic>          # e.g. mithuna/ssw-cli, rahul/eval, hemnaath/slack-alert
# work, commit (plain message, no trailers)
git push -u origin HEAD
gh pr create --base dev --fill
gh pr merge --squash --delete-branch
```

Promoting to `main` (people only, at the gates):

```bash
gh pr create --base main --head dev --title "Gate N"
# a different teammate reviews and approves, then:
gh pr merge --merge                   # merge commit, never squash, so dev and main stay in step
```

Agents never push to `dev` or `main` directly, never force-push, never approve a PR and never
merge into `main`. Keep each PR small and inside your own folder. Pull `dev` before every task.
The PR description is the team's log: what changed, how you checked it (command and output),
and any measured number with the command that produced it.

## 4. Who owns what

| Folder | Owner | Holds |
|---|---|---|
| `watcher/` | Mithuna | frame sampler, vision call, JSON validation, de-duplication, SQLite store, rule table, the `ssw` CLI |
| `agent/` | Hemnaath | OpenClaw skill and tools, Slack alert and disposition, box setup scripts |
| `story/` | Rahul | `labels.csv`, replay, eval, `numbers.json` |
| `data/` | not committed | clips, frames, `ssw.db` |
| `plans/`, `AGENTS.md` | Hemnaath | change only by PR, and tell the team |

To change a file in someone else's folder, tag the owner in the PR.

## 5. Frozen contracts

Section 0 of the scope of work is the seam between the three of us: Event JSON, the SQLite
schema (`data/ssw.db`), the rule table, the vision endpoint and the `ssw` CLI. Build against it
exactly. A contract change needs all three people to agree, and it goes in its own PR that
edits section 0 and the code together.

## 6. The box: Hemnaath only

- Only Hemnaath connects to the GB10. On Mithuna's or Rahul's laptop, an agent never SSHes,
  tunnels or copies files to the box. See "Box access" in the scope of work.
- On laptops, code runs with the fake vision client (`--fake-vision`, canned Event JSON with the
  same interface). To run on the real model, merge to `dev` and message Hemnaath, who runs it on
  the box and sends back the JSON, logs and numbers.
- `~/site-safety-watch` on the box is the copy that runs the demo. Hemnaath keeps it on `dev`
  and only pulls there.
- On the box: long jobs go in tmux or `docker run -d`, never a bare SSH session. Do not
  download models (venue Wi-Fi is slow) and do not restart the `vllm-main` container casually.

## 7. Clock (Sat 2026-10-03)

Gate 1 12:45, Gate 2 14:30, Gate 3 15:30, record the core demo 15:30 to 16:15. Feature freeze
17:00: after that, only fixes on the demo path. 18:00: no more code, no more commits.
