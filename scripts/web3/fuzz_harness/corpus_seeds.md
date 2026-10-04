# Differential Fuzz — Seed Corpus (divergence triggers)

Seed `./corpus` with inputs at the edges where parsers historically disagree. The fuzzer mutates
from these, but good seeds reach divergence orders of magnitude faster.

## Universal byte-level triggers
- **Control bytes inside strings:** `0x0B` (vertical tab — the actual `json-rust` vs `serde_json`
  divergence), `0x09` tab, `0x00` NUL, `0x7F`, raw `0x0A`/`0x0D` newlines.
- **Whitespace variants:** leading/trailing/interior spaces, BOM (`0xEF 0xBB 0xBF`), non-ASCII spaces.
- **Number edges:** leading zeros (`007`), `+`-prefixed, `-0`, very large (> u64::MAX), `NaN`/`Infinity`,
  `1e999`, hex vs decimal, trailing `.` / leading `.`.
- **Structural:** empty input, empty string/array/object, deeply nested (1000+ levels), duplicate keys,
  trailing bytes after a valid message, missing terminator.

## Format-specific
- **SSZ:** oversized/short offsets, offsets with gaps (ghost regions), offset not multiple of length,
  `sum(variable_lengths) != total_variable_section_size`, max-list-length boundary.
- **RLP:** non-canonical length prefixes, leading-zero lengths, single-byte-as-string vs raw.
- **borsh/BCS:** trailing bytes, length-prefix overflow, enum discriminant out of range.
- **protobuf:** unknown fields, repeated singular field, wrong wire-type for field number.

## How to generate
Hand-write a handful per category as raw files in `./corpus`, or script it:
`for i, seed in enumerate(seeds): open(f"corpus/seed_{i}", "wb").write(seed)`.
