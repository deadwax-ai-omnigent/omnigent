---
name: debate
description: Have Claude, GPT, and Gemini partners critique each other's answers across a configurable number of rounds (default 1) before converging on a synthesis. Use when the user wants the three perspectives stress-tested against each other, not just shown side by side.
---

# debate — make the three partners argue it out

Normally Debby fans a question out to all three partners and shows the three
answers side by side. **debate** goes further: it relays each partner's
answer to the *other two* partners for criticism, loops that for a configurable
number of rounds, and then converges on a synthesis.

## Rounds

The user picks how many rounds of back-and-forth to run. **Default: 1
round.** A "round" is one full cross-critique exchange (each partner sees
and criticizes the other's latest answer). Honor an explicit count from the
user ("debate this for 3 rounds"); otherwise run 1.

## Procedure

1. **Round 0 — collect the opening answers.** If you do not already have a
   fresh answer from each partner for this question, dispatch it to all three
   (`claude`, `gpt`, `gemini`) in parallel via `sys_session_send` (ANSWER mode),
   give each call a stable per-partner `title` — the topic with the partner's
   name attached (e.g. `debate-pricing-claude` / `debate-pricing-gpt` /
   `debate-pricing-gemini`), end your turn, and collect all three with
   `sys_read_inbox`. If you already showed the user all three answers this
   turn, reuse those as round 0.

2. **For each debate round (default 1):**
   - Send `claude` the OTHER partners' latest answers (GPT's and Gemini's) and
     ask it to critique both answers and then give its own updated answer
     (CRITIQUE mode). Reuse that partner's own `title` so it continues its thread.
   - Send `gpt` the OTHER partners' latest answers (Claude's and Gemini's) and
     ask the same.
   - Send `gemini` the OTHER partners' latest answers (Claude's and GPT's) and
     ask the same. Dispatch all three in the same turn so they run concurrently.
   - End your turn; collect all three updated answers with `sys_read_inbox`.
   - Always cross the answers: in round N, each partner critiques the other
     two's round N-1 answers — never its own. Pass the answers as text in the
     message; the partners have no shared memory of each other.

3. **Converge.** After the final round, write the synthesis yourself:

       ## 🟠 Claude — final
       <Claude's last answer, lightly trimmed>

       ## 🔵 GPT — final
       <GPT's last answer, lightly trimmed>

       ## 🟣 Gemini — final
       <Gemini's last answer, lightly trimmed>

       ## How the debate moved them
       <3-5 bullets: what each conceded, what each held, where they
        ultimately agreed or still diverge>

       ## Synthesis
       <your even-handed convergence — the strongest combined answer,
        flagging any genuine remaining disagreement rather than papering
        over it>

## Notes

- Keep it even-handed. You are the moderator, not a fourth debater — your own
  opinion enters only in the Synthesis, and even there it is a synthesis of
  the three, not a new position.
- One round is usually enough to surface the real disagreement; more rounds
  tend to converge or repeat. If two rounds produce no new movement, say so
  and converge early rather than burning further rounds.
- If a partner returns an empty or unclear result mid-debate, inspect its
  conversation with `sys_session_get_history` before re-dispatching; don't
  silently drop a voice from the debate.
- With three voices, watch for coalitions (two aligning against the third).
  The synthesis should acknowledge strong consensus where it emerges, as well
  as genuine three-way splits.
