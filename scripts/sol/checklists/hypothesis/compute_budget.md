# Checklist: Compute Budget DoS

- [ ] All loops bounded? `.take(MAX)` or explicit count?
- [ ] No invoke / find_program_address inside loop?
- [ ] No large allocations with attacker-controlled size?
- [ ] CU consumption estimated for worst-case input?
- [ ] Account realloc bounded in size?
