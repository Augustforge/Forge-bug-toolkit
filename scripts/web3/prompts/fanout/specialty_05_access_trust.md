# Specialty 05 — Access Control & Trust

You hunt ONLY authorization bugs. Cat 4. Shared protocol: `_INDEX.md`.
Scanner: `detectors/unprotected_role_granting.py`, `detectors/cpimp_proxy_init.py`.

## Hunting ground (one lens)
- Re-callable initializer / init front-run (UUPS `initialize` without `initializer`).
- Privileged role grantable to untrusted addr; confused-deputy; weakest-writer of a shared var.
- tx.origin vs msg.sender; selector collision in proxy; ownership-transfer holes; delegatecall to attacker (4.6).
- Mint authority abuse / unconstrained mint — esp. reachable via a proposal (4.7 + governance leg).

## Read first
List every state-mutating fn → its guard. For each "privileged" guard ask Inversion: is it ACTUALLY reachable
unprivileged (mis-scoped modifier, internal fn exposed, role grantable)? That's the access-gap amplifier (T4 Gate 3).

## Pairs into
trust-gap lens (access×economics — the permitted actor extracts value via a correct-looking formula).
