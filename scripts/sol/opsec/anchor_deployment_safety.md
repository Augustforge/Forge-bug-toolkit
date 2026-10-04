# Anchor Deployment Safety — OPSEC Checklist

This guide is for **test deployment of a PoC** on devnet/testnet during a hunt. Applies to every Anchor program you deploy.

## Critical Path: IDL Authority Race

Anchor programs have a **permissionless IDL authority claim** via `IdlCreateAccount`. After `anchor deploy` there is a window (seconds to minutes) when:
- Program deployed, but IDL not claimed
- Attacker can call `IdlCreateAccount` first → seize IDL authority
- Upload a malicious IDL → users' frontend is misled, phishing via substituted args

**This is not theory — it is a known attack vector since 2023** (Accretion writeup).

### Mandatory steps after deploy:

```bash
# 1. Deploy
anchor deploy --provider.cluster devnet

# 2. IMMEDIATELY claim IDL authority
anchor idl init --filepath target/idl/PROGRAM.json PROGRAM_ID --provider.cluster devnet

# 3. Verify authority claimed by you
anchor idl authority PROGRAM_ID --provider.cluster devnet
# Should output your wallet pubkey

# 4. If you ever transfer ownership of program:
anchor idl set-authority --new-authority NEW_PUBKEY PROGRAM_ID
```

**Never** leave a program deployed without a claimed IDL. Attack window = time until you notice.

## Bytecode Verification

After deploy, compare bytecode locally and on-chain:

```bash
solana program dump PROGRAM_ID dumped.so
sha256sum dumped.so target/deploy/PROGRAM.so
# Should match
```

If they don't match → code was tampered with during deploy (compromised CI, malicious dependency, MITM).

## Upgrade Authority

Default: deployer keypair = upgrade authority. This means:
- Anyone with access to your keypair can upgrade the program and drain funds
- Mitigation: transfer upgrade authority to a multisig (Squads v4) OR revoke via `solana program set-upgrade-authority --final`

For a devnet PoC — usually ok to leave as is. For a mainnet deploy (if you ever do) — multisig **mandatory**.

## Keypair Hygiene

- **One keypair = one hunt**. Do not reuse a keypair across different bounty programs.
- Keypair is stored in `~/.bbt/sol_wallets/<hunt-id>/keypair.json` via `solana_wallet_manager.py`.
- **Never** commit keypair.json to git. It should already be in `.gitignore`.
- After the hunt closes — `rotate` the keypair, do not delete it (needed as evidence for the disclosure timeline).

## Submission Account Separation

When you submit a bug to Immunefi/Sec3:
- Submission portal account = whitehat handle (consistent across submissions to one platform — for reputation)
- On-chain wallet for receiving payout = **different** for each hunt
- The link between submission handle and payout wallet is visible only to you and the platform — do NOT publish it

## Chain Analytics Awareness

After disclosure your payout wallet appears on the public blockchain. If you used the same wallet for:
- Deploying PoC programs
- Calling RPC endpoints with test txs
- Linking to a main wallet via mixer (badly configured)

→ chain analytics (Chainalysis, Arkham) link the activities. Mitigation: payout → mixer → cold storage → forget.

## Devnet vs Mainnet PoC

- **Devnet**: always for PoC. Never run an exploit on mainnet even for verification.
- Use `solana-test-validator` locally for a full mainnet fork — this is safer than devnet (devnet is also public).
- If you need to fork specific protocol state — clone programs:

```bash
solana-test-validator --clone PROGRAM_ID_1 --clone ACCOUNT_1 --url mainnet-beta --reset
```

## Final OPSEC Audit Before Submit

Checklist before pressing "Submit" on Immunefi:

- [ ] PoC reproduces bug on local fork (not mainnet)
- [ ] Submission portal handle != on-chain payout wallet
- [ ] Whitehat handle reputation stable (Immunefi Level / Sec3 history)
- [ ] No on-chain transactions linking discovery to your main wallet
- [ ] Disclosure timeline documented locally (date+hash of evidence)
- [ ] Report does NOT include attacker-controlled wallet addresses (only attacker_role = ATTACKER placeholder)
