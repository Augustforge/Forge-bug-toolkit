# Prompt: Frontend Compromised

Lens: contracts are perfect, but the user signs whatever the frontend tells them. What if the UI is hijacked (CDN, DNS, build pipeline, dependency, social)? What does the contract still accept?

> Examples: Curve frontend hijack (2022), Balancer (2023), 5 protocols in one March 2026 week (per threat_intel section 2).

## Questions

1. **Where is the frontend deployed?** Vercel / Cloudflare / AWS S3 / IPFS? Single-point-of-failure?
2. **Subresource Integrity (SRI)**: critical JS bundles SRI-tagged? Or just loaded as-is?
3. **CSP**: strict policy or `unsafe-eval` / `unsafe-inline` allowed?
4. **EOA signing pattern**: user signs `approve(spender, MAX_UINT)` — drainer collects via Permit2 / standard approval
5. **Permit / Permit2 signature**: protocol uses signatures off-chain → on-chain submit? Frontend can craft adversarial permit
6. **Domain separator**: EIP-712 — protocol checks chainId, verifyingContract correct?
7. **Contract-side**: can contract distinguish user-intent from frontend-injected params?
8. **Approval surface**: protocol expects user to approve max? Or precise amounts? (Max approval = drainer paradise)

## Specific bug classes

- **Approval drainer**: user approves UI's recommended `MAX_UINT`, malicious UI redirects allowance to attacker contract
- **Permit2 signature**: user signs off-chain permit with adversarial `spender` set by frontend
- **Sign-in-with-Ethereum**: signature includes nonce/expiry — malicious frontend reuses?
- **Multicall composition**: frontend composes multicall with extra malicious step user can't decipher
- **Custom message signing**: protocol uses non-EIP-712 message — wallet can't display intent clearly

## Contract-side defenses (what protocol CAN do)

- Precise approval amounts (no MAX_UINT in frontend code)
- Permit2 with `SignatureTransfer` (single-use, expires) vs `AllowanceTransfer` (persistent)
- EIP-712 with descriptive type names (wallet shows intent)
- On-chain `recipient` matches `msg.sender` where it makes sense
- Reject "max" allowances in protocol logic (cap allowance, reset periodically)
- Time-locked critical operations

## Output

1. **Frontend attack vector**: CDN / dep / DNS / build-time inject
2. **Contract-side vulnerability**: what the user signs that the contract accepts without further check
3. **Mitigation gap**: what the contract should validate on its side
4. **Severity**: Variable (depends on TVL exposed to frontend trust)

## Anti-pattern

"Frontend security is not our problem" — NO. A well-protected contract design limits the blast radius of any frontend compromise. It is a protocol DESIGN problem.

---

## Source:

(paste signing / permit / approval logic + frontend code excerpts if available)
