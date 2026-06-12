# Secret Spec: A Knitting Compiler

## 1. Goal

Build a command-line tool called **Knitting Compiler**.

The tool reads knitting pattern files written in a small domain-specific language, parses them, validates them, expands repeats, simulates stitch counts row by row, and prints one structured JSON document to stdout.

This is a compiler/interpreter-style problem. The domain is knitting because the sponsor is called Needle, and apparently we are all committed to the bit. The technical task is still serious: parsing, validation, simulation, error recovery, and deterministic output.

## 2. Required CLI

Your tool must support exactly this command shape:

```bash
python knit.py compile <input_file>
```

Example:

```bash
python knit.py compile examples/scarf.knit
```

The `compile` command must print exactly one JSON document to stdout.

It must not print logs, debug output, explanations, success messages, stack traces, or any other non-JSON text to stdout.

All diagnostic or debug output, if any, must go to stderr. For judging, stdout is the contract.

## 3. Input Files

Input files use the `.knit` extension.

Example:

```text
pattern "Tiny Doom Scarf"

cast_on 10

row 1: k10
row 2: p10
row 3: k2, yo, k6, k2tog

repeat rows 1-3 x2

bind_off
```

Blank lines are allowed.

Line numbers are 1-based physical line numbers in the input file. Blank lines and comments still count for line numbering.

## 4. Comments

A `#` character outside a quoted pattern name begins a comment.

A comment extends from `#` to the end of the line.

For comment stripping, double quotes are tracked lexically before pattern validation. A `#` character after an opening double quote is treated as part of the attempted quoted string until a closing double quote is found. If the quote is never closed, the line is malformed; the `#` does not start a comment in that case. Escaped quotes are not supported.

Examples:

```text
# full-line comment
row 1: k10   # inline comment
```

The parser must ignore comments.

## 5. Case Sensitivity

All keywords and stitch operations are case-sensitive and lowercase.

Valid keywords:

```text
pattern
cast_on
row
repeat
bind_off
```

Valid stitch operations:

```text
k
p
yo
k2tog
ssk
inc
dec
```

Examples:

```text
row 1: k10      # valid
row 1: K10      # invalid: UNKNOWN_STITCH
Pattern "Hat"   # invalid: UNKNOWN_STATEMENT
```

## 6. Statement Recognition and Malformed Statements

After removing comments and trimming leading/trailing whitespace:

- An empty line is ignored.
- Statement recognition requires a token boundary. A recognized keyword must be followed by whitespace or end of line. The keyword must not be glued directly to its argument or to other text. For example, `patterned "Hat"`, `pattern"Hat"`, `cast_on10`, `row1: k1`, `repeatrows 1-2 x1`, and `bind_offnow` are all `UNKNOWN_STATEMENT`, not malformed versions of their visually similar statements.
- A line beginning with a recognized statement keyword but not matching that statement's required syntax must be reported using the corresponding malformed error code.
- A line that does not begin with any recognized statement keyword must be reported as `UNKNOWN_STATEMENT`.
- Trailing non-comment text after an otherwise valid statement makes that statement malformed. For example, `cast_on 10 extra` is `MALFORMED_CAST_ON`, `row 1: k1 extra` is `MALFORMED_ROW`, and `repeat rows 1-1 x1 extra` is `MALFORMED_REPEAT`.
- If a malformed statement uses a recognized keyword, the corresponding missing-statement error is suppressed. For example, a file containing only `pattern Bad` should report `MALFORMED_PATTERN`, not both `MALFORMED_PATTERN` and `MISSING_PATTERN`.

Examples:

```text
pattern Tiny Doom Scarf     # MALFORMED_PATTERN: missing double quotes
cast on 10                  # UNKNOWN_STATEMENT: keyword is not cast_on
cast_on ten                 # MALFORMED_CAST_ON
row 1 k10                   # MALFORMED_ROW: missing colon
repeat row 1-3 x2           # MALFORMED_REPEAT
bind_off now                # MALFORMED_BIND_OFF
bind_offnow                 # UNKNOWN_STATEMENT: no token boundary after bind_off
patterned "Hat"             # UNKNOWN_STATEMENT: no token boundary after pattern
pattern"Hat"                # UNKNOWN_STATEMENT: no token boundary after pattern
cast_on10                   # UNKNOWN_STATEMENT: no token boundary after cast_on
repeatrows 1-2 x1           # UNKNOWN_STATEMENT: no token boundary after repeat
row1: k1                    # UNKNOWN_STATEMENT: no token boundary after row
cast_on 10 extra            # MALFORMED_CAST_ON: trailing non-comment text
```

## 6A. Positive Integers

All positive integers in this spec are parsed as base-10 integer values. Leading zeros are allowed as long as the resulting value is positive.

Examples:

```text
cast_on 05              # valid, value 5
row 01: k1              # valid row number 1
row 1: k01              # valid stitch count 1
[k1] x02                # valid repeat count 2
repeat rows 01-02 x03   # valid range 1-2, count 3
```

All output JSON must use normalized integer values, not the original textual representation. For example, `row 01: k1` has `source_row: 1`.

```text
cast_on 00              # invalid: MALFORMED_CAST_ON
row 00: k1              # invalid: MALFORMED_ROW
[k1] x00                # invalid: MALFORMED_ROW
repeat rows 00-01 x1    # invalid: INVALID_REPEAT_RANGE
```

## 7. Pattern Declaration

Every pattern must contain exactly one pattern declaration:

```text
pattern "Pattern Name"
```

The pattern name is any sequence of characters inside double quotes, excluding newline and unescaped double quote.

Escaped quotes are not supported.

Examples:

```text
pattern "Tiny Doom Scarf"   # valid
pattern ""                  # valid, empty name
pattern Tiny Doom Scarf      # invalid
pattern "Bad " Name"        # invalid
```

The output `pattern_name` value must preserve the pattern name string. JSON escaping is allowed as long as it represents the same string value after JSON parsing.

If multiple valid pattern declarations exist, the compiler must report `DUPLICATE_PATTERN` for each additional valid pattern declaration after the first. The error `line` must be the line of the additional duplicate declaration. In this case, output `pattern_name: null`.

If a file contains a recognized but malformed `pattern` statement and no valid pattern declaration, report `MALFORMED_PATTERN`, suppress `MISSING_PATTERN`, and output `pattern_name: null`.

## 8. Cast On

Every pattern must contain exactly one cast-on declaration:

```text
cast_on 24
```

Rules:

- `cast_on` must be a positive integer.
- `cast_on` must appear before any row statement.
- A row statement means any non-empty, non-comment line recognized with the `row` keyword and token boundary, including malformed rows, empty rows, rows with unknown stitches, and rows with invalid row numbers such as `row 0: k1`.
- Duplicate `cast_on` declarations are invalid.
- If any recognized `cast_on` statement appears after rows, report `CAST_ON_OUT_OF_ORDER`, even if that `cast_on` statement is malformed.
- If a `cast_on` statement appears after rows and is also a duplicate, report both `CAST_ON_OUT_OF_ORDER` and `DUPLICATE_CAST_ON`.

Examples:

```text
cast_on 24     # valid
cast_on 0      # invalid: MALFORMED_CAST_ON
cast_on -3     # invalid: MALFORMED_CAST_ON
cast_on ten    # invalid: MALFORMED_CAST_ON
```

If multiple syntactically valid `cast_on` declarations exist, the compiler must report `DUPLICATE_CAST_ON` for each additional valid `cast_on` declaration after the first. The error `line` must be the line of the additional duplicate declaration. In this case, output `cast_on: null`.

If the only syntactically valid `cast_on` appears after a row statement, output the parsed `cast_on` value, but report `CAST_ON_OUT_OF_ORDER`. That `cast_on` value is not usable for stitch simulation.

If a malformed `cast_on` appears after rows, report both `MALFORMED_CAST_ON` and `CAST_ON_OUT_OF_ORDER`. The malformed recognized `cast_on` suppresses `MISSING_CAST_ON`. A malformed `cast_on` does not count as a duplicate declaration. `DUPLICATE_CAST_ON` is reported only for additional syntactically valid `cast_on` declarations after the first valid `cast_on`.

If a file contains a recognized but malformed `cast_on` statement and no syntactically valid cast-on declaration, report `MALFORMED_CAST_ON`, suppress `MISSING_CAST_ON`, and output `cast_on: null`.

## 9. Row Syntax

Rows use this format:

```text
row <number>: <instruction_list>
```

Examples:

```text
row 1: k10
row 2: p10
row 3: k2, yo, k6, k2tog
```

Rules:

- Row numbers must be positive integers.
- Rows must appear in strictly increasing order.
- Duplicate row numbers are invalid.
- Duplicate detection takes priority over out-of-order detection. If a row number was already claimed by any earlier structurally valid positive row header, report `DUPLICATE_ROW` only for that line, never `OUT_OF_ORDER_ROW`.
- `OUT_OF_ORDER_ROW` is reported only for a non-duplicate valid positive row number that is lower than the greatest previously claimed source row number.
- Example: `row 3`, then `row 2`, then another `row 2` reports `OUT_OF_ORDER_ROW` for the first `row 2` and `DUPLICATE_ROW` for the second `row 2`. Example: `row 3`, then `row 2`, then `row 4` reports `OUT_OF_ORDER_ROW` for `row 2`; `row 4` is not out of order.
- A row with an invalid row number, such as `row 0: k1` or `row -1: k1`, is `MALFORMED_ROW` and does not claim a source row number.
- A row must contain at least one instruction.
- An empty row such as `row 5:` is invalid and must be reported as `MALFORMED_ROW`. Because the header is structurally valid, it still claims source row number 5.
- Rows may not appear after `bind_off`.
- A row with a structurally valid header, such as `row 1: ...`, claims that source row number even if its instruction list is empty, malformed, or contains invalid stitches. It still counts for duplicate detection, out-of-order detection, and row repeat range existence.
- A duplicate row is invalid and is not inserted into the internal source row sequence used for row repeat expansion or stitch simulation.
- An out-of-order row is invalid and is not inserted into the internal source row sequence used for row repeat expansion or stitch simulation.
- Duplicate and out-of-order rows still claim their source row number for later duplicate detection, as long as their row header is structurally valid and their row number is a positive integer.
- Because duplicate and out-of-order rows are not simulated, the compiler must not emit `STITCH_UNDERFLOW` or `STITCH_OVERFLOW` errors caused only by the instructions inside those rows. Other detectable errors on those rows, such as `UNKNOWN_STITCH` or malformed bracket syntax, must still be reported where possible.

## 10. Supported Stitch Operations

The compiler must support the following stitch operations.

| Stitch | Meaning |
|---|---|
| `kN` | knit N stitches |
| `pN` | purl N stitches |
| `yo` | yarn over |
| `k2tog` | knit two together |
| `ssk` | slip slip knit |
| `inc` | increase |
| `dec` | decrease |

For counted stitches, `N` must be a positive integer.

Examples:

```text
k1
k10
p24
```

Invalid examples:

```text
k0
p-2
k
p
```

Invalid stitch tokens must be reported as `UNKNOWN_STITCH`.

## 11. Stitch Count Model

The compiler tracks the number of live stitches on the working row.

For each row:

- `start_stitches` is the number of stitches available when the row begins.
- For the first expanded row, `start_stitches` is equal to `cast_on`.
- For every later expanded row, `start_stitches` is equal to the previous expanded row's `end_stitches`.
- `end_stitches` is the number of stitches produced by the row after all instructions are processed.

This means `k10` consumes 10 stitches from the previous row and produces 10 stitches in the working row. The count does not change.

Stitch semantics:

| Stitch | Consumes | Produces |
|---|---:|---:|
| `kN` | N | N |
| `pN` | N | N |
| `yo` | 0 | 1 |
| `k2tog` | 2 | 1 |
| `ssk` | 2 | 1 |
| `inc` | 1 | 2 |
| `dec` | 2 | 1 |

During simulation, the compiler must track remaining stitches available from the previous row.

Stitch simulation only begins if there is exactly one valid usable `cast_on` value. A usable `cast_on` is a syntactically valid, non-duplicate `cast_on` that appears before any row statement. If `cast_on` is missing, malformed, duplicated, or out of order, do not perform stitch simulation and do not emit `STITCH_UNDERFLOW` or `STITCH_OVERFLOW`.

If a row reaches `STITCH_UNDERFLOW`, simulation stops at the first underflow. Do not continue simulating that row or any later rows. Emit at most one `STITCH_UNDERFLOW` error for the source row where simulation stopped.

If the produced stitch count for the current working row exceeds 10,000 at any point while processing that row, report `STITCH_OVERFLOW`. Simulation stops immediately at that point. Do not continue simulating that row or any later rows. Emit at most one `STITCH_OVERFLOW` error for the source row where simulation stopped.

If `STITCH_UNDERFLOW` or `STITCH_OVERFLOW` occurs during a repeated instance of a source row, the error `line` is the physical line of the original source row and `row` is the original source row number.

Example:

```text
cast_on 5
row 1: k3, k4
```

Simulation:

- Row starts with 5 stitches.
- `k3` consumes 3, leaving 2 available from the previous row.
- `k4` requires 4, but only 2 remain.
- This is `STITCH_UNDERFLOW`.

## 12. Instruction Lists

An instruction list is a comma-separated list of instructions.

Examples:

```text
k10
k2, p6, k2
k2, yo, k6, k2tog
```

Whitespace around commas is optional.

Instructions must be separated by commas. A whitespace-separated sequence inside a single instruction item is not split into multiple instructions. For example, `row 1: k1 dance10` is `MALFORMED_ROW`, not `UNKNOWN_STITCH`, because the instruction list is not comma-separated correctly. By contrast, `row 1: k1, dance10` reports `UNKNOWN_STITCH` for the comma-separated unknown stitch token.

A malformed whitespace-separated instruction item is not further tokenized for additional `UNKNOWN_STITCH` errors. For example, `row 1: k0 dance10` reports `MALFORMED_ROW` only for that malformed instruction item, not separate `UNKNOWN_STITCH` errors for `k0` and `dance10`.

Each comma-separated invalid stitch token produces its own `UNKNOWN_STITCH` error. For example, `row 1: dance10, twirl2` reports two `UNKNOWN_STITCH` errors, one for `dance10` and one for `twirl2`, ordered by their source position within the row.

Empty comma-separated instruction items are `MALFORMED_ROW`. For example, `row 1: k1,,p1`, `row 1: k1,`, and `row 1: ,k1` are all `MALFORMED_ROW`. Non-empty neighboring items may still be inspected for independently detectable `UNKNOWN_STITCH` errors, but the row is skipped entirely for stitch simulation if it has `MALFORMED_ROW` or `UNKNOWN_STITCH`.

These must parse identically:

```text
row 1:k10
row 1: k10
row 1: k2,yo,k6,k2tog
row 1: k2, yo, k6, k2tog
```

## 13. Bracketed Repeats

Instruction lists may contain bracketed repeats:

```text
[k2, p2] x3
```

A valid bracketed repeat has this shape:

```text
[<instruction_list>] x<count>
```

There must be at least one whitespace character between the closing `]` and the `x<count>` token. The `x` and the count must be contiguous.

Examples:

```text
[k2, p2] x3    # valid
[k2,p2] x3     # valid
[k2,p2]x3      # MALFORMED_ROW
[k2] x 3       # MALFORMED_ROW
```

A bracketed repeat repeats the bracketed instruction list exactly `N` total times.

Example:

```text
row 1: [k2, p2] x3
```

Equivalent expanded instruction list:

```text
k2, p2, k2, p2, k2, p2
```

Nested bracketed repeats are required.

Example:

```text
row 1: [k1, [p1, yo] x2] x3
```

The repeat count must be a positive integer.

Invalid bracket syntax or invalid bracket repeat counts must be reported as `MALFORMED_ROW`.

Note: bracketed repeats are part of row syntax, so bracket-related errors use `MALFORMED_ROW`, not `INVALID_REPEAT_COUNT`. A bracketed repeat must appear as a comma-separated instruction-list item. It may not be adjacent to another instruction without a comma; for example, `row 1: [k1] x2 k1` is `MALFORMED_ROW`.

Invalid stitch tokens inside a syntactically valid bracketed repeat are reported as `UNKNOWN_STITCH`, not `MALFORMED_ROW`. For example, `row 1: [k0] x2` reports `UNKNOWN_STITCH`, because the bracketed repeat syntax is valid but `k0` is not a valid stitch token.

If a row contains both malformed bracket syntax and independently detectable unknown stitch tokens, report both `MALFORMED_ROW` and `UNKNOWN_STITCH` where possible. If malformed bracket syntax prevents reliable parsing of part of the instruction list, the compiler is not required to scan that unparseable region token-by-token; reporting only the errors confidently detected is acceptable. If the bracket structure is parseable and an unknown stitch appears inside it, report `UNKNOWN_STITCH`.

## 14. Row Repeats

The compiler must support row repeat statements:

```text
repeat rows <start>-<end> x<count>
```

Example:

```text
repeat rows 1-3 x2
```

A row repeat repeats the referenced source row range `count` additional times beyond the original rows.

Therefore:

```text
row 1: k10
row 2: p10
repeat rows 1-2 x2
```

Expands to this row source sequence:

```text
1, 2, 1, 2, 1, 2
```

The original rows appear once, then the range is repeated 2 additional times.

Important convention:

- Bracketed repeats produce exactly `N` total iterations.
- Row repeats produce `N` additional iterations beyond the original source rows.

This difference is intentional and mirrors common knitting language. Yes, it is slightly annoying. So is parsing.

Rules:

- `start` and `end` must be positive integers.
- `start` must be less than or equal to `end`.
- `count` must be a positive integer.
- The range and count tokens must not contain internal whitespace. `repeat rows 1-3 x2` is valid syntax. `repeat rows 1 - 3 x2` and `repeat rows 1-3 x 2` are `MALFORMED_REPEAT`.
- A syntactically present count token after `x` that is not a positive integer, such as `x0`, `x-1`, or `xtwo`, is `INVALID_REPEAT_COUNT`, not `MALFORMED_REPEAT`.
- A missing count after `x`, such as `repeat rows 1-2 x`, is also `INVALID_REPEAT_COUNT`, not `MALFORMED_REPEAT`.
- Integer-looking non-positive range values, such as `repeat rows 0-1 x1` or `repeat rows -1-2 x1`, are `INVALID_REPEAT_RANGE`, not `MALFORMED_REPEAT`.
- Every row in the referenced range must already exist as an original source row at the point where the repeat statement appears in source order. A later row declaration does not satisfy an earlier repeat. For example, `repeat rows 1-1 x1` before `row 1: k1` reports `INVALID_REPEAT_RANGE`.
- Rows with structurally valid headers but invalid bodies, such as rows with `UNKNOWN_STITCH` or `MALFORMED_ROW`, count as existing source rows for repeat range validation. A repeat referencing such a row is not `INVALID_REPEAT_RANGE` solely because the row body is invalid.
- Rows that are claimed but excluded from simulation or expansion because of `DUPLICATE_ROW`, `OUT_OF_ORDER_ROW`, or placement after `bind_off` also count as existing source rows for repeat range validation.
- Row repeat references always refer to original source row numbers, not previously expanded rows.
- Multiple row repeat statements are allowed.
- Expansion follows source statement order exactly. For example, `row 1`, then `repeat rows 1-1 x1`, then `row 2`, then `repeat rows 1-2 x1` expands to source row sequence `1, 1, 2, 1, 2`.
- A row repeat may not appear after `bind_off`.
- A row repeat after `bind_off` must still be parsed for its own errors, but it is excluded from the internal expanded row sequence used for simulation.

Invalid row repeats must be reported as either `MALFORMED_REPEAT`, `INVALID_REPEAT_RANGE`, or `INVALID_REPEAT_COUNT`, as appropriate.

Use `MALFORMED_REPEAT` when the line begins with `repeat` but does not have the required `repeat rows <start>-<end> x<count>` structure. Use `INVALID_REPEAT_COUNT` when the structure is otherwise recognizable but the count after `x` is not a positive integer. Use `INVALID_REPEAT_RANGE` when the structure is otherwise recognizable but the range values are invalid, including non-positive start/end values, `start > end`, or references to missing source rows.

A single repeat statement may produce multiple different error codes. For example, `repeat rows 2-4 x0` may produce both `INVALID_REPEAT_COUNT` and `INVALID_REPEAT_RANGE` if row 4 does not exist. Similarly, `repeat rows 0-2 x0` produces both `INVALID_REPEAT_COUNT` and `INVALID_REPEAT_RANGE` because the count is invalid and the range contains a non-positive row number. However, a single repeat statement must emit at most one `INVALID_REPEAT_RANGE`, even if the range is invalid for multiple reasons such as `start > end` and missing referenced rows.

For internal expansion and simulation, an invalid row repeat statement must be excluded from the expanded row sequence. The compiler must still continue parsing later statements and may include later valid row repeat statements in the internal sequence if simulation is still possible.

## 15. Bind Off

Patterns may contain a `bind_off` statement:

```text
bind_off
```

Rules:

- `bind_off` is optional.
- If present, `bind_off` must be the last non-empty, non-comment statement in the file.
- Duplicate `bind_off` statements are invalid.
- Any non-empty, non-comment statement after a syntactically valid `bind_off` is invalid and must report `BIND_OFF_OUT_OF_ORDER`, except for a second syntactically valid `bind_off`, which reports `DUPLICATE_BIND_OFF` only.
- Statements after `bind_off` must still be fully parsed for their own errors. `BIND_OFF_OUT_OF_ORDER` is additional, not exclusive, except for the duplicate valid `bind_off` case described above. For example, `row 3: dance10` after `bind_off` should report both `BIND_OFF_OUT_OF_ORDER` and `UNKNOWN_STITCH`; `pattern Bad` after `bind_off` should report both `BIND_OFF_OUT_OF_ORDER` and `MALFORMED_PATTERN`.

A malformed `bind_off` statement after a syntactically valid `bind_off`, such as `bind_off now`, reports both `MALFORMED_BIND_OFF` and `BIND_OFF_OUT_OF_ORDER`. Only a second syntactically valid `bind_off` reports `DUPLICATE_BIND_OFF` without `BIND_OFF_OUT_OF_ORDER`.

A row or row repeat after `bind_off` is invalid and is excluded from the internal source row sequence or expanded row sequence used for simulation. It must still be parsed for all independently detectable errors. A structurally valid positive row header after `bind_off` still claims its source row number for duplicate detection, out-of-order detection, and row repeat range existence. Therefore, if `bind_off` is followed by `row 1: k1` and then `repeat rows 1-1 x1`, the repeat does not report `INVALID_REPEAT_RANGE` merely because `row 1` is after `bind_off`; the repeat is still invalid/excluded because it appears after `bind_off`.

The output field `bind_off` must be `true` if a syntactically valid `bind_off` statement is present anywhere in the file, even if the full pattern is invalid for other reasons.

If no syntactically valid `bind_off` statement is present, `bind_off` must be `false`.

## 16. Error Recovery

The compiler must report all errors it can reasonably detect, not only the first error.

Continue parsing after errors where possible.

Examples:

- A malformed row should not prevent detecting a later duplicate row number.
- An unknown stitch should not prevent detecting a later invalid repeat range.
- A missing pattern declaration should not prevent parsing rows and reporting row-specific errors.

If a row cannot be parsed at all, skip that row for simulation purposes, but continue parsing later statements.

If a row has a structurally valid row header but contains an empty instruction list, malformed instructions, malformed bracket syntax, or unknown stitches, it still counts as an original source row for duplicate detection, out-of-order detection, and repeat range existence. However, skip the entire row for simulation purposes. Do not partially simulate a row with `UNKNOWN_STITCH` or `MALFORMED_ROW`.

If a row repeat references an invalid-but-claimed source row, including a row with a broken body, a duplicate row, an out-of-order row, or a row after `bind_off`, the repeat range itself is still range-valid. During internal expansion and simulation, occurrences of excluded source rows are skipped. This remains true even if every row in the referenced range is excluded; the repeat does not report `INVALID_REPEAT_RANGE` solely for that reason and contributes no rows to internal expansion or simulation. Since the final output is invalid whenever any error exists, `expanded_rows` is still empty in the emitted JSON.

Rows with invalid row numbers, such as `row 0: k1` or `row -1: k1`, do not claim source row numbers and do not count for duplicate detection, out-of-order detection, or row repeat range existence.

Rows that report `DUPLICATE_ROW` or `OUT_OF_ORDER_ROW` are invalid and are excluded from the internal source row sequence used for row repeat expansion and stitch simulation. They still claim their source row number for later duplicate detection if their row header is structurally valid and positive. They may still report other independently detectable errors, but their stitch instructions must not produce `STITCH_UNDERFLOW` or `STITCH_OVERFLOW`.

Rows after `bind_off` are invalid and excluded from simulation, but their headers still claim source row numbers for duplicate detection, out-of-order detection, and row repeat range existence if structurally valid and positive.

If there is no exactly one valid usable `cast_on` value, skip stitch simulation entirely. A syntactically valid `cast_on` that appears after a row is still reported in the top-level `cast_on` field, but it is not usable for simulation. For example, a file with `pattern "X"` and `row 1: k999` but no valid usable `cast_on` reports `MISSING_CAST_ON` or `CAST_ON_OUT_OF_ORDER` as applicable, not a stitch-count error.

If simulation reaches `STITCH_UNDERFLOW` or `STITCH_OVERFLOW`, stop simulation entirely at the first such error. Do not continue simulating the current row or any later rows.

If any error is present, the final output must have:

```json
"valid": false
```

and `expanded_rows` must be an empty array.

## 17. Error Object Schema

Each error object must use this schema:

```json
{
  "type": "error",
  "code": "ERROR_CODE",
  "message": "Human-readable message",
  "line": 4,
  "row": 2
}
```

Rules:

- `type` must always be exactly `"error"`.
- `code` must be one of the defined error codes in Section 18.
- `message` must be a non-empty human-readable string.
- Exact message wording is implementation-defined. The normative error fields are `type`, `code`, `line`, and `row`; automated evaluation must not require exact `message` string matches.
- `line` must be an integer source line number when the error is tied to a physical line; otherwise it must be `null`.
- `row` must be an integer source row number when the error is tied to a row; otherwise it must be `null`.
- Every error object must include all five keys: `type`, `code`, `message`, `line`, and `row`.

Errors should be ordered by source line number when possible. Errors with `line: null` should appear after line-specific errors. When multiple errors occur on the same physical source line, order them by the order of their error codes in the Section 18 table, not by implementation-specific detection order. When multiple errors with the same code occur on the same physical source line, order them by their source position from left to right where applicable. In particular, `INVALID_REPEAT_COUNT` is ordered before `INVALID_REPEAT_RANGE` because that is the order used in the Section 18 table.

## 18. Error Codes

The following error codes are allowed.

| Code | Meaning |
|---|---|
| `MISSING_PATTERN` | No `pattern` statement was found. If a `pattern` statement exists but is malformed, use `MALFORMED_PATTERN` instead. |
| `MALFORMED_PATTERN` | A line begins with `pattern` but does not match `pattern "Name"`. |
| `DUPLICATE_PATTERN` | More than one valid pattern declaration was found. |
| `MISSING_CAST_ON` | No `cast_on` statement was found. If a `cast_on` statement exists but is malformed, use `MALFORMED_CAST_ON` instead. |
| `MALFORMED_CAST_ON` | A line begins with `cast_on` but does not contain a positive integer. |
| `DUPLICATE_CAST_ON` | More than one valid `cast_on` declaration was found. |
| `CAST_ON_OUT_OF_ORDER` | `cast_on` appears after a row declaration. |
| `UNKNOWN_STATEMENT` | A non-empty, non-comment line does not begin with a recognized statement keyword. |
| `MALFORMED_ROW` | A line begins with `row` but does not match row syntax, has an invalid row number, has no instructions, or has malformed bracket syntax. |
| `DUPLICATE_ROW` | The same valid row number is declared more than once. A duplicate row must not also report `OUT_OF_ORDER_ROW` solely because it repeats an earlier row number. |
| `OUT_OF_ORDER_ROW` | A non-duplicate valid row number is lower than a previously claimed valid row number. |
| `UNKNOWN_STITCH` | A stitch token is not one of the supported operations. |
| `STITCH_UNDERFLOW` | An operation requires more stitches than remain available at that point in the row. |
| `STITCH_OVERFLOW` | A validly parsed row produces more than 10,000 stitches at the end of the row. |
| `MALFORMED_REPEAT` | A line begins with `repeat` but does not have the required repeat statement structure. |
| `INVALID_REPEAT_COUNT` | A repeat count token is present after `x` but is not a positive integer. |
| `INVALID_REPEAT_RANGE` | A repeat range is invalid or references rows that do not exist as original source rows. |
| `MALFORMED_BIND_OFF` | A line begins with `bind_off` but is not exactly `bind_off`. |
| `DUPLICATE_BIND_OFF` | More than one syntactically valid `bind_off` statement was found. |
| `BIND_OFF_OUT_OF_ORDER` | A valid `bind_off` statement appears before a later non-empty, non-comment statement, except for a second syntactically valid `bind_off`, which uses `DUPLICATE_BIND_OFF` only. |

No warnings are defined in this spec.

The only valid `type` value is `"error"`.

## 19. Required JSON Output Schema

The program must print exactly one JSON object with these top-level fields:

```json
{
  "pattern_name": "Tiny Doom Scarf",
  "cast_on": 10,
  "valid": true,
  "errors": [],
  "expanded_rows": [],
  "final_stitch_count": 10,
  "bind_off": true
}
```

Top-level field rules:

| Field | Type | Rule |
|---|---|---|
| `pattern_name` | string or null | The parsed pattern name, or `null` if no valid pattern declaration exists or if `DUPLICATE_PATTERN` is reported. |
| `cast_on` | integer or null | The first syntactically valid cast-on value, or `null` if no syntactically valid cast-on declaration exists or if `DUPLICATE_CAST_ON` is reported. A cast-on value that is syntactically valid but out of order is still output here, but it is not usable for simulation. |
| `valid` | boolean | `true` only if no errors were detected. |
| `errors` | array | Empty when valid; otherwise contains error objects. |
| `expanded_rows` | array | Contains expanded row objects only when `valid` is `true`. Must be empty when `valid` is `false`. |
| `final_stitch_count` | integer or null | Final stitch count when valid; `null` when invalid. |
| `bind_off` | boolean | `true` if a syntactically valid `bind_off` statement was present, otherwise `false`. |

If `valid` is `false`, `expanded_rows` must be `[]` and `final_stitch_count` must be `null`, even if some rows were parsed successfully.

If a valid pattern contains no rows, `expanded_rows` must be `[]` and `final_stitch_count` must equal `cast_on`.

## 20. Expanded Row Object Schema

Each expanded row object must have this structure:

```json
{
  "expanded_row_index": 1,
  "source_row": 1,
  "instructions": [
    {
      "stitch": "k",
      "count": 10
    }
  ],
  "start_stitches": 10,
  "end_stitches": 10
}
```

Field rules:

| Field | Type | Rule |
|---|---|---|
| `expanded_row_index` | integer | Sequential index in the expanded output, starting at 1. |
| `source_row` | integer | Original source row number this expanded row came from. |
| `instructions` | array | Fully expanded flat instruction list after bracketed repeat expansion. Bracketed repeat structure must never be preserved in output JSON. |
| `start_stitches` | integer | Stitch count entering this row. |
| `end_stitches` | integer | Stitch count after this row is processed. |

Example:

```text
row 1: k10
row 2: p10
repeat rows 1-2 x2
```

Expanded rows:

| expanded_row_index | source_row |
|---:|---:|
| 1 | 1 |
| 2 | 2 |
| 3 | 1 |
| 4 | 2 |
| 5 | 1 |
| 6 | 2 |

## 21. Instruction Object Schema

Each instruction object must have this structure:

```json
{
  "stitch": "k",
  "count": 10
}
```

Rules:

- Every instruction object must include `stitch` and `count`.
- For counted stitches `kN` and `pN`, `count` is `N`.
- For `yo`, `k2tog`, `ssk`, `inc`, and `dec`, `count` must be `1`.

Examples:

```text
k10      -> {"stitch": "k", "count": 10}
yo       -> {"stitch": "yo", "count": 1}
k2tog    -> {"stitch": "k2tog", "count": 1}
```

## 22. Valid Output Example

Input:

```text
pattern "Tiny Doom Scarf"
cast_on 10
row 1: k10
row 2: k2, yo, k6, k2tog
bind_off
```

Output:

```json
{
  "pattern_name": "Tiny Doom Scarf",
  "cast_on": 10,
  "valid": true,
  "errors": [],
  "expanded_rows": [
    {
      "expanded_row_index": 1,
      "source_row": 1,
      "instructions": [
        {
          "stitch": "k",
          "count": 10
        }
      ],
      "start_stitches": 10,
      "end_stitches": 10
    },
    {
      "expanded_row_index": 2,
      "source_row": 2,
      "instructions": [
        {
          "stitch": "k",
          "count": 2
        },
        {
          "stitch": "yo",
          "count": 1
        },
        {
          "stitch": "k",
          "count": 6
        },
        {
          "stitch": "k2tog",
          "count": 1
        }
      ],
      "start_stitches": 10,
      "end_stitches": 10
    }
  ],
  "final_stitch_count": 10,
  "bind_off": true
}
```

## 23. Invalid Output Example: Missing Pattern

Input:

```text
cast_on 10
row 1: k10
```

Output:

```json
{
  "pattern_name": null,
  "cast_on": 10,
  "valid": false,
  "errors": [
    {
      "type": "error",
      "code": "MISSING_PATTERN",
      "message": "Missing pattern declaration.",
      "line": null,
      "row": null
    }
  ],
  "expanded_rows": [],
  "final_stitch_count": null,
  "bind_off": false
}
```

## 24. Invalid Output Example: Multiple Errors

Input:

```text
pattern Tiny Doom Scarf
cast_on 5
row 1: k3, k4
row 1: dance10
repeat rows 2-4 x0
bind_off
row 3: k5
```

One acceptable output shape:

```json
{
  "pattern_name": null,
  "cast_on": 5,
  "valid": false,
  "errors": [
    {
      "type": "error",
      "code": "MALFORMED_PATTERN",
      "message": "Malformed pattern declaration.",
      "line": 1,
      "row": null
    },
    {
      "type": "error",
      "code": "STITCH_UNDERFLOW",
      "message": "Row 1 consumes more stitches than available.",
      "line": 3,
      "row": 1
    },
    {
      "type": "error",
      "code": "DUPLICATE_ROW",
      "message": "Duplicate row number 1.",
      "line": 4,
      "row": 1
    },
    {
      "type": "error",
      "code": "UNKNOWN_STITCH",
      "message": "Unknown stitch dance10.",
      "line": 4,
      "row": 1
    },
    {
      "type": "error",
      "code": "INVALID_REPEAT_COUNT",
      "message": "Repeat count must be a positive integer.",
      "line": 5,
      "row": null
    },
    {
      "type": "error",
      "code": "INVALID_REPEAT_RANGE",
      "message": "Repeat range references rows that do not exist.",
      "line": 5,
      "row": null
    },
    {
      "type": "error",
      "code": "BIND_OFF_OUT_OF_ORDER",
      "message": "Statement appears after bind_off.",
      "line": 7,
      "row": 3
    }
  ],
  "expanded_rows": [],
  "final_stitch_count": null,
  "bind_off": true
}
```

The exact `message` strings are implementation-defined. The messages shown in this example are illustrative only. For error comparison, `type`, `code`, `line`, and `row` are normative; `message` is only required to be a non-empty human-readable string.

## 25. Exit Codes

The process must exit with:

| Exit code | Meaning |
|---:|---|
| 0 | The input was compiled successfully and `valid` is `true`. |
| 1 | The input was processed but `valid` is `false`. |
| 2 | CLI usage error, for example missing file argument or unreadable file. |

Even when exiting with code 1, stdout must contain exactly one valid JSON object following this spec.

For exit code 2, stdout must be empty. Stderr may contain a short human-readable diagnostic, but stderr is not part of the judged output.

## 26. Constraints

Input and runtime constraints:

- Input files will be under 100 KB.
- Total original source row count will be at most 1000.
- Total stitch count per expanded row must not exceed 10,000.
- If the produced stitch count for the current working row exceeds 10,000 at any point while processing a validly parsed row, report `STITCH_OVERFLOW`, stop simulating immediately, and do not simulate subsequent rows.
- If simulation reaches `STITCH_UNDERFLOW`, stop simulating immediately and do not simulate subsequent rows.
- Runtime must be under 5 seconds per invocation.

Anything slower is treated as failure. It is a scarf compiler, not a moon landing.

## 27. Out of Scope

The following are not part of this DSL:

- color
- yarn weight
- needle size
- cabling
- bobbles
- lace charts
- graphical knitting charts
- real-world knitting correctness beyond this spec
- any feature not explicitly listed in this document

Any behavior, syntax, feature, output field, or recovery policy not explicitly defined in this spec is out of scope and will not be tested or judged. Participants may implement unspecified behavior however they like, as long as it does not change the required behavior defined here.
