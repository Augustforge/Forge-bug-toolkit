# Kwil / KGW black-box testing

Raw, SDK-less testing of any **Kwil v0.3** database node (`kwild`), usually fronted by a
**KGW gateway**. Built and **live-validated on idos-production (2026-06-21)**.

Tool: [`kwil_blackbox.py`](kwil_blackbox.py). Auto-flagged by
[`chain_detect.py`](../../chain_detect.py) (`kwil_target` / `kwil_maybe` fields) when a target
is a Kuneiform/`schema.sql` repo or a `nodes.*`/`kgw.*` gateway host.

## When this applies

- Target exposes a JSON-RPC at `…/rpc/v1` answering `kgw.authn_param` / `user.call` / `user.broadcast`.
- Schema uses Kwil action modifiers: `public` / `private` / `owner` / `view`, and `@caller`.
- Examples: idOS (nodes.idos.network), TRUF.network, any kwilteam/trufnetwork `kwil-db` deployment.

## What you can do (no funds, own accounts only)

1. **Read VIEW actions** — `kb.call(ns, action, args)`. Zero-arg VIEWs are trivial payloads.
2. **`@caller` IDOR discriminator** — authenticate as your burner, then call a `@caller`-scoped
   VIEW with a spoofed `sender` (a dead address with no profile).
   - Own/empty data back → gateway binds `caller = cookie` → **secure**.
   - Victim's data back → gateway honors arbitrary `sender` → **IDOR** (open-mode footgun:
     `usersvc` `authenticate`/`txCtx` set `@caller` from the claimed sender with no sig check;
     only a per-account-binding gateway closes it).
3. **KGW SIWE auth** — `kb.kgw_auth()` performs the `kgw.authn_param → personal_sign → kgw.authn`
   flow and persists the `__Host-kgw_session` cookie. Note the literal `"Issue At:"` typo in the
   message template and that the message does **not** contain the signer address.
4. **Write-tx error-oracle** — `kb.error_oracle(ns, action, args)` broadcasts a write that hits an
   enforcement/precompile check and returns `result.log`. **State never changes** (the action
   errors out, `gas:false`). Use it to confirm — on the deepest reachable layer — that:
   - `PRIVATE` actions reject direct calls (`"action is private"`),
   - `OWNER` actions reject non-owners (`"action is owner-only"`),
   - signature precompiles are ecrecover-sound (garbage sig → `"EVM signature verification failed"`;
     a valid sig over the real message passes the crypto then fails on ownership).

## Wire formats (validated live; LittleEndian framing)

- `WriteString/WriteBytes` = `uint32(len) + bytes`. `acVersion`/`aeVersion`/`txVersion` = 0.
- **ActionCall** (read): `u16(0) + WS(ns) + WS(action) + u16(numArgs) + Σ WriteBytes(EncodedValue)`.
- **ActionExecution** (write): `u16(0) + WS(ns) + WS(action) + u16(numCalls=1) + u16(numArgs) + Σ WriteBytes(EncodedValue)`.
- **EncodedValue**: `u16(0) + WriteBytes(DataType) + u16(1) + WriteBytes([0x01]+value)`; `DataType`
  marshals BigEndian internally. Validated value types: `text`, `int8` (BE u64), `uuid` (16 raw bytes).
  Re-check `core/types/data_types.go` for others.
- **JSON-RPC field types**: `body.payload`/`challenge`/`signature` → **base64**; `sender` (`HexBytes`)
  → **hex, no 0x**; `auth_type="secp256k1_ep"`; `Identifier()` expects the **20-byte eth address**
  (not the pubkey) → `@caller` = any public address.
- **Outer tx signature** (`personal_sign` over):
  `"<desc>\n\nPayloadType: execute\nPayloadDigest: <sha256(payload)[:20] hex>\nFee: 0\nNonce: <n>\n\nKwil Chain ID: <chain>\n"`.
  Nonce from `user.account {id:{identifier:hex,key_type:"secp256k1"},status:1}` + 1.
  Broadcast: `user.broadcast {tx:{signature, body:{desc,payload:b64,type:"execute",fee:"0",nonce,chain_id}, serialization:"concat", sender:hex}, sync:1}`.

## CLI quickstart

```bash
# probe a VIEW (read)
py -3 kwil_blackbox.py call  --rpc https://nodes.idos.network/rpc/v1 --action get_wallets
# IDOR discriminator
py -3 kwil_blackbox.py idor  --rpc <url> --key 0x.. --action get_wallets --spoof 0xdead...01
# write-path enforcement oracle (no state change)
py -3 kwil_blackbox.py oracle --rpc <url> --chain idos-production --key 0x.. \
      --action create_access_grant --args text:0xgrantee uuid:4444....-.... int8:0
```

See also memory `project_idos_hunt` (worked case + the deeper engine reasoning).
