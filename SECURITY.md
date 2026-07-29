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
