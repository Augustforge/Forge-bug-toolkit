# Checklist: Go Language Footguns (consensus / validator / relayer / bridge targets)

Language-level Go traps that become **security-critical** in web3 Go code: Cosmos-SDK chains, geth/erigon
forks, Tendermint/CometBFT, Heimdall, bridge event-listeners & relayers, oracle daemons, sequencers.
Behavioral consensus bugs (cross-client divergence, log-topic confusion, precompile state-commit) live in
**Cat 18 / 2.6 / 15.10-12** — this list is the *language substrate* below them. Source: Sigma Prime
"Go for Security Auditors" (Burnik, 2026). Run on any target where `go.mod` exists.

**First step:** read `go.mod` → note the Go version. Several traps (loop-var capture, parallel-test capture)
were silently fixed in **Go 1.22** — older `go` directive = those traps are live.

## Error-handling traps (the highest-yield — silent error swallow = bypassed safety)
- [ ] **Typed-nil return** — a func declares a concrete error pointer (`var e *MyErr = nil`) and returns it
      directly; the interface is `(type=*MyErr, value=nil)` so `if err != nil` **fires falsely** OR a
      `return e` of a nil typed-pointer reads as success-with-error / error-with-success. Map every
      validation/verification path that returns a typed error var, not a bare `nil`/`error`.
- [ ] **Stale error reference** — after a successful op sets `err = nil`, a later `type assertion`
      (`x, ok := v.(T)`) or map-read fails its `ok` check but the branch returns `...%w, err)` referencing
      the OLD (nil) err → failure reported as success, or wrong wrapped cause. Grep `, ok :=` and
      `, exists :=` whose failure branch references an `err` not set in that branch.
- [ ] **Ignored errors** — `_ = f()` or `v, _ := f()` on a security op (signature verify, decode, balance
      read, state write, nonce check). Each ignored error on a validation path = a hypothesis.
- [ ] **Variable shadowing** — inner `err :=` (note `:=`) inside `if`/`for` shadows outer `err`; the outer
      check later reads a stale value. Run `go vet -vettool=$(which shadow)` / `go vet -shadow`.

## Silent state-loss traps
- [ ] **Value receiver where pointer intended** — `func (s State) Update(...)` (value) mutates a COPY; the
      caller's state is unchanged. A `Checkpoint()`/`Set*()`/`Apply*()`/`Slash()`/`Increment*()` method on a
      value receiver = mutation silently dropped → accounting/validator-set/height update lost. Diff every
      state-mutating method's receiver: `(s *T)` vs `(s T)`.
- [ ] **Slice aliasing** — `b := a[i:j]` shares the backing array; `b[k]=x` mutates `a`. Two consequences:
      (1) zeroing key material / secrets via one slice does NOT clear other aliases → **key remnant in
      memory**; (2) concurrent mutation through an alias = state corruption. Grep slice re-slicing of
      sensitive buffers (private keys, signatures, BLS shares, session secrets).
- [ ] **append capacity trap** — `append` to a slice with spare `cap` writes into the SHARED backing array
      (no copy); a sibling slice silently sees / loses the element. Check `append` on sub-slices that other
      code still holds.
- [ ] **Sparse/indexed array init** — `[...]T{100, 3: 400, 500}` auto-fills gaps with zero values; in a
      wire/serialization/witness buffer those silent zeros can break signature/Merkle/quorum verification.

## Panic / DoS traps (node-halt, liveness)
- [ ] **nil map write** — reading a nil map is fine, **writing panics**. Struct fields of map type default
      to `nil`; if any external-input path writes to an uninitialized map field → remote panic → node crash.
      Grep `map[` struct fields → confirm init before write.
- [ ] **Unchecked index / slice bound** — attacker-controlled length/offset into a slice (calldata-derived
      loop bound, header field) → out-of-range panic. Pair with Cat 14.9 (calldata loop-bound).
- [ ] **defer-arg eval timing** — `defer f(g())` evaluates `g()` at the `defer` statement, not at return
      (`defer log("%v", time.Since(start))` records 0). Security angle: a deferred `unlock()`/`cleanup(x)`
      capturing a value computed too early → wrong resource released / guard not restored. Multiple defers
      run LIFO.
- [ ] **Infinite event loop without `ctx.Done()`** — `for { select { ... } }` with no cancellation arm =
      goroutine leak / DoS; trace every `for select` for an exit path.

## Concurrency
- [ ] **Goroutine loop-var capture (Go < 1.22)** — `for i := …; { go func(){ use(i) }() }` captures `i` by
      reference → all goroutines see the final value. Same for `for _, v := range`. Security: signing /
      validating / indexing the wrong element. Fix marker is `i := i` / `v := v` inside the loop — absence
      on a pre-1.22 module = bug.
- [ ] **Blank-identifier positional logic** — `for _, x := range xs` where correctness actually depends on
      the discarded index (operator order, validator slot, partition id).

## Test-coverage blind spots (intended-behavior reject / unaudited paths)
- [ ] **Build-tag-hidden tests** — `//go:build integration` (or `_test` files behind tags) skipped in
      default CI; security-relevant tests may never run. Enumerate all build tags in `*_test.go`.
- [ ] **External `_test` package** — `package foo_test` can only touch exported API; internal-state bugs go
      untested. Note which packages test only through the public surface.
- [ ] **Parallel-test var capture (Go < 1.22)** — `t.Run` subtests calling `t.Parallel()` without `tc := tc`
      all test the LAST case → green suite, wrong coverage.
- [ ] **Fuzz `t.Skip()` ≠ reject** — a skipped fuzz input still enters the corpus; a guard that "skips"
      malformed input isn't actually excluding it.

## Pragmas / build (rare but high-impact — immediate deep-dive flags)
- [ ] **`//go:linkname`** — accesses unexported symbols of other packages, breaks encapsulation → audit the
      linked symbol's invariants. Immediate flag.
- [ ] **`//go:noescape`** — wrong annotation → pointer that should escape stays on stack → use-after-free.
- [ ] **`//go:nosplit`** — disables stack-growth check → deep recursion = stack overflow.
- [ ] **Module-path case encoding** — `!c` = capital `C` in module paths (`!cosm!wasm` = `CosmWasm`); matters
      when diffing/auditing dependency provenance (supply-chain / typosquat lens).
