# -*- coding: utf-8 -*-
"""Replay for t11_applicable.py — proves the detector DISTINGUISHES four situations
(APPLICABLE / MAYBE / two SKIPs), not just "does not crash". Builds temporary targets in a tempdir."""
import os, sys, json, tempfile, shutil, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
DET = os.path.join(HERE, "t11_applicable.py")

def build(files):
    d = tempfile.mkdtemp()
    for rel, content in files.items():
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
    return d

def run(target, model=None):
    cmd = [sys.executable, "-X", "utf8", DET, target]
    if model:
        cmd += ["--model", model]
    p = subprocess.run(cmd, capture_output=True)
    out = (p.stdout or b"").decode("utf-8", "replace")
    try:
        return json.loads(out), p.returncode
    except Exception:
        return {"verdict": "ERR", "raw": out}, p.returncode

VAULT_SOL = """
contract Vault {
  mapping(address => uint256) public balanceOf;
  uint256 public totalSupply;
  uint256 public totalAssets;
  function deposit(uint256 a) external { totalSupply += a; }
  function withdraw(uint256 a) external { totalSupply -= a; }
  function redeem(uint256 s) external {}
}
"""
# MODEL_MOVEMENT: I-01 / I-02 lines are Russian-language fixture input matched by the Russian
# movement regex ("on ANY sequence of deposit/withdraw" / "share price is monotone between calls"): KEEP verbatim.
MODEL_MOVEMENT = """
## Invariants
- **I-01** | conservation | check: sum(balanceOf) == totalSupply на ЛЮБОЙ последовательности deposit/withdraw | pred: ENFORCED
- **I-02** | share-price | check: цена доли монотонна между вызовами | pred: ENFORCED
- **I-03** | access | check: only owner calls pause | pred: ENFORCED
"""
MODEL_NO_MOVEMENT = """
## Invariants
- **I-01** | access | check: only owner calls setFee | pred: ENFORCED
- **I-02** | bound | check: fee <= 1e18 in setFee | pred: ENFORCED
"""
PARSER_RS = """
pub fn decode(buf: &[u8]) -> Result<Header> {
    let magic = read_u32(buf);
    let len = read_u32(buf);
    Ok(Header { magic, len })
}
"""

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))

# 1) APPLICABLE — foundry + value-accounting + order-dependent I-NN
d = build({"foundry.toml": "[profile.default]\n", "src/Vault.sol": VAULT_SOL,
           "system_model.md": MODEL_MOVEMENT})
r, rc = run(d)
check("1 APPLICABLE: vault+movement → APPLICABLE", r.get("verdict") == "APPLICABLE", r.get("verdict"))
check("1 Foundry engine recognized", "Foundry" in (r.get("engine") or ""), r.get("engine"))
check("1 order-dependent I-NN found (I-01)",
      any(x["id"] == "I-01" for x in r.get("order_dependent_I", [])), r.get("order_dependent_I"))
check("1 exit code 0", rc == 0, rc)
shutil.rmtree(d, ignore_errors=True)

# 2) MAYBE — build+stateful present, but no order-dependent I-NN
d = build({"foundry.toml": "[profile.default]\n", "src/Vault.sol": VAULT_SOL,
           "system_model.md": MODEL_NO_MOVEMENT})
r, rc = run(d)
check("2 MAYBE: stateful but I-NN without movement → MAYBE", r.get("verdict") == "MAYBE", r.get("verdict"))
check("2 exit code 2", rc == 2, rc)
shutil.rmtree(d, ignore_errors=True)

# 2b) MAYBE — the model is empty altogether (no file)
d = build({"foundry.toml": "[profile.default]\n", "src/Vault.sol": VAULT_SOL})
r, rc = run(d)
check("2b MAYBE: model is empty → MAYBE (finish T10)", r.get("verdict") == "MAYBE", r.get("verdict"))
check("2b model_invariants_total==0", r.get("model_invariants_total") == 0, r.get("model_invariants_total"))
shutil.rmtree(d, ignore_errors=True)

# 3) SKIP — no build config (docs only)
d = build({"README.md": "# docs", "system_model.md": MODEL_MOVEMENT})
r, rc = run(d)
check("3 SKIP: no build → SKIP", r.get("verdict") == "SKIP", r.get("verdict"))
check("3 exit code 3", rc == 3, rc)
shutil.rmtree(d, ignore_errors=True)

# 4) SKIP — a Rust build exists, but a stateless parser (not value-accounting) → T8, not T11
d = build({"Cargo.toml": "[package]\nname=\"p\"\n", "src/lib.rs": PARSER_RS})
r, rc = run(d)
check("4 SKIP: stateless parser → SKIP (this is T8 differential)", r.get("verdict") == "SKIP", r.get("verdict"))
check("4 reason mentions T8", "T8" in (r.get("reason") or ""), r.get("reason"))
shutil.rmtree(d, ignore_errors=True)

# 5) APPLICABLE — Solana/Anchor + Trident engine
ANCHOR_RS = """
#[account]
pub struct Pool { pub amount: u64, pub balance: u64 }
pub fn deposit(ctx: Context<D>, a: u64) -> Result<()> { token::transfer(cpi, a) }
"""
d = build({"Anchor.toml": "[programs.localnet]\n", "programs/p/src/lib.rs": ANCHOR_RS,
           "system_model.md": MODEL_MOVEMENT})
r, rc = run(d)
check("5 APPLICABLE: Anchor+movement → APPLICABLE", r.get("verdict") == "APPLICABLE", r.get("verdict"))
check("5 Trident engine recognized", "Trident" in (r.get("engine") or ""), r.get("engine"))
shutil.rmtree(d, ignore_errors=True)

print("=== T11 APPLICABLE-DETECTOR REPLAY ===\n")
ok = 0
for name, passed, detail in results:
    print(("  [PASS] " if passed else "  [FAIL] ") + name + (("  — %r" % (detail,)) if detail and not passed else ""))
    ok += 1 if passed else 0
print("\n%d/%d green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
