# 0004 — The LLM has no write path

**Status:** accepted · **Date:** sprint day 11 · **Owner:** Ali
**Amended** when the Copilot moved to its own component — see the note at the end.

## Context

An LLM agent over this system makes six modules legible to a non-technical
audience. The tempting next step is to let it act: adjust an offer, approve a
limit, launch a campaign. It would demo well.

## Decision

The LLM reads and explains. It never decides. Enforced structurally:

- No CVM endpoint creates, alters or approves anything. `/v1/offer/next-best`
  *computes* an offer; it does not send one.
- The feature-store connection is opened **read-only** at the connection level.
- Consuming components get an **allowlisted** set of endpoints
  (`docs/INTEGRATION.md` §3) and no database credentials at all.
- Every answer must cite the tool output it came from; with no grounding, the
  agent refuses rather than guessing.

## Consequences

**Good.** A prompt-injected or simply confused agent cannot move money, change
a price, or approve credit. The demo is safe to run live in front of
evaluators. It is also a clean answer to the anticipated question "why isn't
the LLM making the pricing decisions?" — because an LLM has no place in a path
that moves money.

**Bad.** The agent cannot complete an action a user asks for; it can only
produce the cohort and hand it to the Campaign Builder.

**Why enforcement is structural rather than prompt-based.** A system prompt is
advisory. A read-only connection is not. Several independent layers means no
single mistake — a reworded prompt, a new tool, a careless refactor — reopens
the path.

---

## Amendment: the branch split

This ADR was written when the Copilot lived in this repository. It now belongs
to Component 5, owned by another team member.

**The decision strengthens rather than changes.** `ali_branch` no longer
contains an agent, an LLM client in any decision path, or a write-capable tool
— so the path does not merely have guards on it, it does not exist. What was a
set of four in-process constraints is now a process boundary: the agent is in a
different service, reaching us over HTTP through an allowlisted, read-only
contract.

The obligations on the agent side (cite tool output, refuse without grounding,
never invent a number) transfer to the Copilot owner and are restated in
`docs/INTEGRATION.md` §5, which is the document they actually read.