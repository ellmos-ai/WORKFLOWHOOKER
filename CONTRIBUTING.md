# Contributing

This public repository owns the `workflowhooker` runtime and its behavioral tests.
Develop shared functionality here. Private deployments consume a pinned public
revision and keep host settings, private inputs and historical evidence outside
the public package. A private extension is warranted only for actual private
executable behavior; it must not shadow the core namespace.

The historical private repository retains its Git history. Never force-push one
repository's history over the other. Check `git remote -v` before pushing and
start public changes from the public default branch.

Install `.[dev]`, run `python -m pytest`, and verify the built wheel in a fresh
environment outside the checkout. Provider changes also require tests against
the declared `hook-master` dependency. Passing private tests alone does not
verify the public artifact.

Keep optional behavior disabled by default. Do not commit private registries,
transcripts, host paths, credentials, session receipts or local lock files.
