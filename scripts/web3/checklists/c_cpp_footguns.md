# C / C++ Security Footguns Checklist

Companion to `go_language_footguns.md`. For C/C++ node/validator/crypto targets — **Firedancer** (C/Rust), powHSM, any native daemon. Source: Trail of Bits `c-review` (47 passes / 7 clusters). Pair with Cat 26 (constant-time / zeroization) and Cat 18.12 (node impl patterns). Language-level traps that survive review because they "compile and pass tests."

## 1. Memory safety
- Use-after-free / double-free — esp. across an async/callback boundary or error path that frees then falls through.
- Buffer over/under-read: `memcpy`/`strcpy`/`sprintf` with attacker-influenced length; off-by-one on NUL terminator.
- Stack buffer + recursion/`alloca` on attacker-controlled depth → stack clash.
- Dangling pointer after `realloc` moves the block (old pointer still used).
- Iterator/pointer invalidation after container resize (C++ `vector` push during iteration).

## 2. String / formatting
- `snprintf`/`vsnprintf` **return value mishandling** — returns the length that WOULD be written (can exceed buffer) → using it as bytes-written truncates/over-advances.
- Format-string injection (`printf(user)` instead of `printf("%s", user)`).
- `strncpy` not NUL-terminating when src ≥ n.

## 3. Arithmetic / type
- Signed integer overflow = UB → compiler may **delete** the overflow check that follows (`if (x+y < x)`).
- Implicit narrowing (`size_t`→`int`, `u256`→`u64`), sign-extension surprises, `size_t` underflow wrapping to huge (loop/alloc DoS).
- `int` used for sizes/offsets that can exceed 2^31.

## 4. Syscall / IO handling
- `EINTR` not handled — blocking syscall returns early on signal, treated as failure/success wrongly.
- Return value of `read`/`write`/`recv` ignored (partial read assumed complete); socket lifecycle misuse.
- `errno` read after an intervening call that clobbers it.

## 5. Concurrency
- Data race on shared state without atomics/lock; lock-order inversion → deadlock.
- Holding a lock across a blocking/callback call.
- TOCTOU on files/fds.

## 6. C++ semantics
- Move-after-use (using a moved-from object).
- Lambda capturing a local by reference that outlives the scope (dangling capture).
- Exception thrown across a C ABI boundary / from a destructor → terminate.
- Iterator invalidation; `std::string_view`/`span` outliving its backing buffer.

## 7. Ambient state / platform (Windows-relevant for cross-platform nodes)
- DLL planting / search-order hijack; unquoted service paths.
- Privilege/IPC: named-pipe/shared-memory without ACL; predictable temp paths.
- Uninitialized memory read leaking secrets (pair with Cat 26 zeroization).

## How to use
At T1, if the target is a C/C++ repo (`*.c`/`*.cpp`/`*.h`, `CMakeLists.txt`/Makefile), walk clusters 1-7 over the top-5 files; every hit → H-{NN}. For secret-handling code also run Cat 26 (zeroize/constant-time). Highest-yield for node targets: cluster 1 (memory), 3 (arithmetic→deleted-check), 4 (EINTR/partial-read).
