# Security Policy

## Scope of use

Forge Bug Toolkit is a **white-hat** security research tool. It is for finding and proving
vulnerabilities so they can be fixed — nothing else.

- Run it only against targets you are **explicitly authorized** to test: within a bug-bounty
  program's scope, or under a written engagement.
- It measures impact on a fork, never against live state. No DoS, market manipulation,
  live-state mutation, phishing, RAT/C2, mass-targeting, or destruction of data.
- You are responsible for using it legally and within scope.

## Reporting a vulnerability in the toolkit itself

If you find a security issue **in this tool** (for example, the prompt-injection guard can be
bypassed, or a module exfiltrates data it shouldn't), report it privately first:

- Open a [GitHub Security Advisory](https://github.com/Augustforge/Forge-bug-toolkit/security/advisories/new),
  or
- Email **august@augustusforge.com** with the details and a proof of concept.

Please give a reasonable window to fix before public disclosure. There is no paid bounty for
the tool itself — this is a community project — but credit is given for valid reports.
