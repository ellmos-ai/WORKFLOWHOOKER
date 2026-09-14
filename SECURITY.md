# Security policy

## Reporting a vulnerability

Do not include secrets, local paths, hook payloads, or project content in a
public issue.

Use the private vulnerability-reporting form in the Security tab of the public
release repository. Publication is blocked until that private channel has been
enabled and verified.

Include the affected version, operating system, host/provider, a minimal
reproduction, and the impact. Redact personal or project-specific data.

## Scope

WorkflowHooker runs commands inside a user's agent host and reads local project
state. Review generated hook snippets before installation and pin the Python
environment used by the host. The project does not automatically modify host
configuration and does not make network requests.

The optional action guard follows fail-safe defaults inside the running hook:
an unreadable policy, malformed payload, unresolved target, or lock-inspection
failure denies only the matched critical file action. Context and advisory
failures remain non-blocking. Provider-level crashes and timeouts can still be
fail-open, so retain host permissions and operating-system controls as the
primary security boundary.

Guard errors use bounded, fixed messages. They do not echo tool inputs,
lock-file contents, exception strings, secrets, or local target paths. The
completion gate is read-only with respect to projects: it neither removes
locks nor modifies or resets working trees.
