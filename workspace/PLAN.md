1. Create a Python script named knit.py that accepts command-line arguments.
2. Parse the command-line to handle the 'compile' subcommand and input file path.
3. Read the input .knit file line by line, tracking line numbers.
4. Implement comment stripping while respecting quoted strings in pattern names.
5. Tokenize and parse each statement, validating syntax according to the spec.
6. Track state: pattern name, cast_on value, rows, bind_off, errors, etc.
7. Validate all rules: token boundaries, case sensitivity, order constraints, duplicates, etc.
8. Expand bracketed repeats and row repeats into a flat sequence of instructions.
9. Simulate stitch counts row by row, detecting underflow/overflow.
10. Construct the output JSON with proper error reporting and expanded rows if valid.
11. Ensure stdout contains only JSON, with errors going to stderr.
12. Set correct exit codes: 0 for valid, 1 for invalid, 2 for CLI/file errors.