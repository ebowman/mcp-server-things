---
description: Decompose a goal or spec into a beads epic with bounded, dependency-ordered tasks.
argument-hint: <goal, or path to a spec file>
---

Decompose the following into a beads work graph: $ARGUMENTS

Rules for a good decomposition:
- Create one epic for the goal:
  `bd create "<goal>" -t epic -p 1 --description "<why + high-level design>"`
- Break it into **bounded tasks** — each completable by a fresh Sonnet session in a single pass. A task has one clear deliverable and a testable done-criterion. If it needs more than that, split it.
  `bd create "<task>" -t task -p <2-3> --parent <epic-id> --description "<input, output, done-criteria>"`
- Wire real dependencies so `bd ready` only ever surfaces work that can actually start:
  `bd dep add <blocked-id> <blocker-id>`   # blocked depends on blocker
- Keep `bd ready` crisp. No vague someday-items, no research-maybe tasks, nothing not immediately actionable. If it isn't ready to be worked, it doesn't belong in the graph yet.
- Do not implement anything. Planning only.

When done, print the resulting graph (`bd ready` plus the epic tree) for my review before any execution.
