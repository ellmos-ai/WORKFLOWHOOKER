# Contributing

## Where development happens

This repository is the **public, curated** side of a two-repository pair:

| Repository | Role |
|---|---|
| `ellmos-ai/workflowhooker` | public distribution — curated, tested, release-ready |
| `ellmos-ai/workflowhooker-provenance` | private twin — full development history |

Development and the complete history live in the **private twin**. What reaches
`main` here are curated, tested changes, brought over by squash or cherry-pick.

**`main` is never force-pushed with development history.** The two branches have
deliberately separate shapes: the private twin keeps every step, this one keeps
the story a reader needs. Pushing one over the other destroys that distinction
in both directions.

## Practical consequences

- A local clone that tracks a `master` branch belongs to the private twin, not
  to this repository. Check `git remote -v` before pushing; a stale remote
  reference is easy to mistake for a diverged branch.
- Fixes made directly against this repository go on a branch taken from
  `origin/main`, with only the fix commits on it — never a rebase of a
  development branch onto `main`.
- Tests must be green on the branch you actually push. A fix verified on the
  development side is not verified here until it runs against this tree.
