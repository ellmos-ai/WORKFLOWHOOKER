# Roadmap

Future work is tracked against observable acceptance criteria:

- Add contract tests for each supported host version.
- Add structured diagnostics that do not expose local paths or payload content.
- Expand advisory state sources only when they can remain read-only and
  fail-open; hard action guards must preserve target-scoped fail-closed errors.
- Measure false-positive rates before enabling any check by default.
- Publish signed artifacts after the release repository and reporting channel
  have been verified.

Roadmap items are not promises and may change.
