#!/usr/bin/env python3
"""
kwil_blackbox.py — Raw Kwil v0.3 (KGW-fronted) black-box testing WITHOUT the SDK.

Hard-won, LIVE-VALIDATED capability (idos-production, 2026-06-21). Works on ANY
Kwil/KGW target (nodes.*, kwild "mode":"open" behind a KGW gateway). Lets you:
  - call @caller-scoped VIEW actions (read)          → IDOR / access-control discriminator
  - authenticate through the KGW SIWE gateway        → per-account session cookie
  - construct & broadcast WRITE transactions by hand → exercise OWNER/PRIVATE/precompile checks
  - run the ERROR-ORACLE: broadcast a tx that hits an enforcement check, read result.log,
    learn whether the check holds — WITHOUT changing state (actions error out, gas:false).

This is the deepest reachable layer of a Kwil target (engine canExecute + signature
precompiles) and it needs ZERO funds and touches ONLY your own accounts.

Byte formats below were reverse-engineered from kwil-db core/types and confirmed by a
tx that was included + executed on idos-production. Validated EncodedValue types:
text / int8 / uuid. For other types re-check core/types/data_types.go EncodedValue.MarshalBinary.

--------------------------------------------------------------------------------
ETHICS / SCOPE: white-hat only. Localize ALL tests to accounts you control. Never
read or mutate a real victim's rows. The error-oracle deliberately picks calls that
REVERT (gas:false) so state never changes. Auth-message signing is allowed.
--------------------------------------------------------------------------------

Usage (CLI):
  py -3 kwil_blackbox.py authn   --rpc https://nodes.idos.network/rpc/v1 --chain idos-production --key 0x..
  py -3 kwil_blackbox.py call    --rpc <url> --action get_wallets            # zero-arg VIEW
  py -3 kwil_blackbox.py idor    --rpc <url> --key 0x.. --action get_wallets --spoof 0xdead..01
  py -3 kwil_blackbox.py oracle  --rpc <url> --chain <id> --key 0x.. \
                                 --action create_access_grant --args text:foo int8:0 uuid:4444....

Programmatic:
  kb = KwilBlackbox(rpc, chain, priv_key)
  kb.kgw_auth()
  print(kb.call("main", "get_wallets", []))                 # read
  log = kb.error_oracle("main", "add_delegate_as_owner",    # write-path enforcement probe
                        [EV.text("0x..."), EV.text("0x...")])
"""
import argparse
import base64
import hashlib
import http.cookiejar
import json
import struct
import sys
import urllib.error
import urllib.request
import uuid as _uuid

try:
    from eth_account import Account
    from eth_account.messages import encode_defunct
except ImportError:
    print("[!] needs eth_account:  py -3 -m pip install eth-account", file=sys.stderr)
    raise


# ---------------------------------------------------------------------------
# Wire encoders (Kwil v0.3, LittleEndian framing). VALIDATED LIVE.
# ---------------------------------------------------------------------------
def _u16(n):                       # little-endian uint16
    return struct.pack("<H", n)


def _wb(b):                        # WriteBytes = uint32(len) + bytes
    return struct.pack("<I", len(b)) + b


def _ws(x):                        # WriteString
    return _wb(x.encode())


def _datatype(name):
    """DataType.MarshalBinary — BigEndian internal. version(0)+len+name+isArray(0)+meta(0,0)."""
    return struct.pack(">H", 0) + struct.pack(">I", len(name)) + name.encode() + b"\x00" \
        + struct.pack(">H", 0) + struct.pack(">H", 0)


def _encoded_value(type_name, data):
    """EncodedValue.MarshalBinary: u16(ver=0)+WriteBytes(DataType)+u16(numData=1)+WriteBytes([1]+data).
    The leading 0x01 marks not-null."""
    return _u16(0) + _wb(_datatype(type_name)) + _u16(1) + _wb(b"\x01" + data)


class EV:
    """EncodedValue builders for the validated scalar types."""
    @staticmethod
    def text(x):
        return _encoded_value("text", x.encode())

    @staticmethod
    def int8(n):
        return _encoded_value("int8", struct.pack(">Q", n))   # BigEndian uint64

    @staticmethod
    def uuid(u):
        if isinstance(u, str):
            u = _uuid.UUID(u)
        return _encoded_value("uuid", u.bytes)                # 16 raw bytes


def encode_action_call(namespace, action, args):
    """ActionCall payload (read). args = list of EncodedValue blobs (from EV.*)."""
    return _u16(0) + _ws(namespace) + _ws(action) + _u16(len(args)) \
        + b"".join(_wb(a) for a in args)


def encode_action_execution(namespace, action, args):
    """ActionExecution payload (write). One call, numArgs args."""
    return _u16(0) + _ws(namespace) + _ws(action) + _u16(1) + _u16(len(args)) \
        + b"".join(_wb(a) for a in args)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
class KwilBlackbox:
    def __init__(self, rpc_url, chain_id=None, priv_key=None):
        self.rpc_url = rpc_url
        self.chain_id = chain_id
        self.priv_key = priv_key
        if priv_key:
            self.address = Account.from_key(priv_key).address.lower()[2:]  # hex no-0x
        else:
            self.address = None
        cj = http.cookiejar.CookieJar()
        self._op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        self._cj = cj

    def rpc(self, method, params):
        req = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        r = urllib.request.Request(
            self.rpc_url, data=json.dumps(req).encode(),
            headers={"Content-Type": "application/json"})
        try:
            return json.loads(self._op.open(r, timeout=30).read().decode())
        except urllib.error.HTTPError as e:
            return {"_http_error": e.code, "_body": e.read().decode()[:600]}

    # --- KGW SIWE gateway auth → per-account session cookie -----------------
    def kgw_auth(self):
        if not self.priv_key:
            raise ValueError("kgw_auth needs a private key")
        pp = self.rpc("kgw.authn_param", {})["result"]
        msg = (
            pp["domain"] + " wants you to sign in with your account:\n\n"
            + ((pp["statement"] + "\n") if pp.get("statement") else "")
            + "\n"
            + "URI: %s\n" % pp["uri"]
            + "Version: 1\n"
            + "Chain ID: %s\n" % pp["chain_id"]
            + "Nonce: %s\n" % pp["nonce"]
            + "Issue At: %s\n" % pp["issue_at"]            # NOTE: literal "Issue At:" (sic)
            + ("Expiration Time: %s\n" % pp["expiration_time"] if pp.get("expiration_time") else "")
        )
        s = Account.sign_message(encode_defunct(text=msg), private_key=self.priv_key)
        sig = base64.b64encode(s.r.to_bytes(32, "big") + s.s.to_bytes(32, "big") + bytes([s.v])).decode()
        return self.rpc("kgw.authn", {
            "nonce": pp["nonce"], "sender": self.address,
            "signature": {"sig": sig, "type": "secp256k1_ep"}})

    # --- read (VIEW) --------------------------------------------------------
    def call(self, namespace, action, args, sender=None):
        """Unauthenticated/cookie-ridden VIEW call. `sender` overrides @caller (IDOR probe)."""
        payload = encode_action_call(namespace, action, args)
        return self.rpc("user.call", {
            "body": {"payload": base64.b64encode(payload).decode(), "challenge": ""},
            "auth_type": "secp256k1_ep",
            "sender": sender if sender is not None else (self.address or ""),
            "signature": ""})

    def call_scalar(self, namespace, action, args, sender=None):
        """Convenience: first scalar of first row, or None."""
        r = self.call(namespace, action, args, sender)
        try:
            return r["result"]["query_result"]["values"][0][0]
        except Exception:
            return None

    # --- write tx -----------------------------------------------------------
    def account_nonce(self):
        acc = self.rpc("user.account", {
            "id": {"identifier": self.address, "key_type": "secp256k1"}, "status": 1})
        try:
            return acc["result"]["nonce"] + 1
        except Exception:
            return 1

    def build_tx(self, namespace, action, args, nonce, desc=""):
        if not self.priv_key:
            raise ValueError("build_tx needs a private key")
        payload = encode_action_execution(namespace, action, args)
        digest = hashlib.sha256(payload).digest()[:20]
        sign_msg = "%s\n\nPayloadType: %s\nPayloadDigest: %x\nFee: %s\nNonce: %d\n\nKwil Chain ID: %s\n" % (
            desc, "execute", digest, "0", nonce, self.chain_id)
        ts = Account.sign_message(encode_defunct(text=sign_msg), private_key=self.priv_key)
        txsig = ts.r.to_bytes(32, "big") + ts.s.to_bytes(32, "big") + bytes([ts.v])
        return {
            "signature": {"sig": base64.b64encode(txsig).decode(), "type": "secp256k1_ep"},
            "body": {"desc": desc, "payload": base64.b64encode(payload).decode(),
                     "type": "execute", "fee": "0", "nonce": nonce, "chain_id": self.chain_id},
            "serialization": "concat", "sender": self.address}

    def broadcast(self, namespace, action, args, nonce=None, desc=""):
        if nonce is None:
            nonce = self.account_nonce()
        tx = self.build_tx(namespace, action, args, nonce, desc)
        return self.rpc("user.broadcast", {"tx": tx, "sync": 1})

    def error_oracle(self, namespace, action, args, nonce=None):
        """Broadcast a write-tx that hits an enforcement/precompile check and return result.log.
        State does NOT change (the action errors out, gas:false). Returns the log string."""
        r = self.broadcast(namespace, action, args, nonce=nonce)
        try:
            return r["result"]["log"]
        except Exception:
            return json.dumps(r)[:600]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _parse_args_spec(specs):
    """['text:foo', 'int8:0', 'uuid:4444...'] → [EncodedValue, ...]."""
    out = []
    for s in specs or []:
        t, _, v = s.partition(":")
        if t == "text":
            out.append(EV.text(v))
        elif t == "int8":
            out.append(EV.int8(int(v)))
        elif t == "uuid":
            out.append(EV.uuid(v))
        else:
            raise SystemExit("unknown arg type %r (use text:/int8:/uuid:)" % t)
    return out


def _load_key(args):
    if args.key:
        return args.key
    if args.key_file:
        data = json.loads(open(args.key_file, encoding="utf-8").read())
        return data.get("privateKey") or data.get("private_key")
    return None


def main():
    ap = argparse.ArgumentParser(description="Raw Kwil v0.3 / KGW black-box tester")
    ap.add_argument("mode", choices=["authn", "call", "idor", "oracle"])
    ap.add_argument("--rpc", required=True)
    ap.add_argument("--chain", default=None)
    ap.add_argument("--key", default=None, help="hex private key (0x..)")
    ap.add_argument("--key-file", default=None, help="JSON file with privateKey field")
    ap.add_argument("--namespace", default="main")
    ap.add_argument("--action", default=None)
    ap.add_argument("--args", nargs="*", default=[], help="EncodedValue specs text:/int8:/uuid:")
    ap.add_argument("--spoof", default=None, help="sender address to spoof @caller (idor mode)")
    a = ap.parse_args()

    kb = KwilBlackbox(a.rpc, a.chain, _load_key(a))

    if a.mode == "authn":
        print(json.dumps(kb.kgw_auth(), indent=2))
        return

    args = _parse_args_spec(a.args)

    if a.mode == "call":
        print(json.dumps(kb.call(a.namespace, a.action, args), indent=2))
    elif a.mode == "idor":
        kb.kgw_auth()
        print("[own ] ", kb.call_scalar(a.namespace, a.action, args))
        print("[spoof]", kb.call_scalar(a.namespace, a.action, args, sender=a.spoof))
        print("→ same/own-data on spoof = gateway binds caller (secure); "
              "victim data = IDOR")
    elif a.mode == "oracle":
        kb.kgw_auth()
        print("result.log:", kb.error_oracle(a.namespace, a.action, args))


if __name__ == "__main__":
    main()
