# Access Control Checklist (7 patterns) — Immunefi V04

## 1. Modifier consistency
- [ ] Similar functions have different modifiers (one `onlyOwner`, the other doesn't)
- [ ] Inherited contracts override visibility/modifier
- [ ] Diamond/multi-facet proxies — every facet is checked
- **Check:** grep `function ` + compare modifiers

## 2. tx.origin instead of msg.sender
- [ ] `require(tx.origin == owner)` — phishing attack (the victim's contract calls you)
- [ ] `tx.origin` in auth logic is almost always a bug
- **Fix:** msg.sender, or signed messages with EIP-712

## 3. Default visibility (Solidity < 0.5.0)
- [ ] Functions without visibility — default to `public`
- [ ] Modern Solidity requires an explicit modifier — but old code is often migrated with bugs

## 4. Role hierarchy / OpenZeppelin AccessControl
- [ ] DEFAULT_ADMIN_ROLE = a single EOA → key compromise = everything
- [ ] Role granting has no timelock
- [ ] `_setRoleAdmin` misconfigured (admin role admin = admin)
- **Pattern:** check who can grant/revoke roles

## 5. Upgrade authority
- [ ] Proxy admin = EOA (not a multisig)
- [ ] UUPS `_authorizeUpgrade()` without access control
- [ ] Beacon admin without a timelock
- **Critical:** upgrade authority = full control over the logic

## 6. Emergency stop / Pausable
- [ ] No `pause()` function — can't stop an exploit in progress
- [ ] `pause()` available only to owner — single point of failure
- [ ] No `unpause` cooldown — an attacker who gains access can pause/unpause to manipulate

## 7. Constructor / initializer issues
- [ ] An upgradeable contract uses `constructor` instead of `initialize()` — the implementation contract can be taken over
- [ ] `initialize()` has no `initializer` modifier — re-initialization
- [ ] Implementation deployed without `_disableInitializers()` in the constructor
- **Real cases:** Wormhole ($320M), Audius

---

## Manual checks

```bash
# Find all admin/owner restricted functions
slither contracts/ --print contract-summary

# Find tx.origin uses
grep -rn "tx.origin" contracts/

# Check upgrade authority
grep -rn "_authorizeUpgrade\|upgradeTo\|upgradeAndCall" contracts/

# Find OpenZeppelin AccessControl roles
grep -rn "hasRole\|grantRole\|_setupRole\|DEFAULT_ADMIN_ROLE" contracts/
```

## Solodit search keywords
`access control`, `tx.origin`, `unprotected initialize`, `unauthorized upgrade`, `missing modifier`, `role admin`
