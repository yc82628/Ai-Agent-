import sys
import json
import re

def strip_comments(line):
    in_quotes = False
    for i, c in enumerate(line):
        if c == '"' and (i == 0 or line[i-1] != '\\'):
            in_quotes = not in_quotes
        if c == '#' and not in_quotes:
            return line[:i].rstrip()
    return line.rstrip()

def parse_pattern(line, line_num):
    line_stripped = strip_comments(line)
    if not line_stripped:
        return None
        
    if line_stripped == 'pattern' or not line_stripped.startswith('pattern'):
        return None
    
    # Must have space after 'pattern'
    match = re.match(r'^pattern\s+("[^"]*")\s*$', line_stripped)
    if match:
        name = match.group(1)[1:-1]  # strip quotes
        return {'type': 'pattern', 'name': name, 'line': line_num}
    else:
        return {'type': 'error', 'code': 'MALFORMED_PATTERN', 'message': 'Malformed pattern declaration.', 'line': line_num, 'row': None}

def parse_cast_on(line, line_num):
    line_stripped = strip_comments(line)
    if not line_stripped:
        return None
        
    if line_stripped == 'cast_on' or not line_stripped.startswith('cast_on'):
        return None
    
    match = re.match(r'^cast_on\s+(\d+)$', line_stripped)
    if match:
        value = int(match.group(1))
        if value <= 0:
            return {'type': 'error', 'code': 'MALFORMED_CAST_ON', 'message': 'Cast on value must be positive.', 'line': line_num, 'row': None}
        return {'type': 'cast_on', 'value': value, 'line': line_num}
    else:
        return {'type': 'error', 'code': 'MALFORMED_CAST_ON', 'message': 'Malformed cast on statement.', 'line': line_num, 'row': None}

def parse_row(line, line_num):
    line_stripped = strip_comments(line)
    if not line_stripped:
        return None
        
    if line_stripped == 'row' or not line_stripped.startswith('row'):
        return None
    
    # Match row <num>: <instructions>
    match = re.match(r'^row\s+(\d+)\s*:\s*(.*)$', line_stripped)
    if not match:
        return {'type': 'error', 'code': 'MALFORMED_ROW', 'message': 'Malformed row declaration.', 'line': line_num, 'row': None}
    
    row_num = int(match.group(1))
    if row_num <= 0:
        return {'type': 'error', 'code': 'MALFORMED_ROW', 'message': 'Row number must be positive.', 'line': line_num, 'row': None}
    
    instr_text = match.group(2)
    if not instr_text.strip():
        return {'type': 'error', 'code': 'MALFORMED_ROW', 'message': 'Row has no instructions.', 'line': line_num, 'row': row_num}
    
    # Parse instruction list
    instructions, errors = parse_instruction_list(instr_text, line_num, row_num)
    if errors:
        # Return first error only? But we want all errors.
        # We'll collect all errors later.
        pass
    
    return {
        'type': 'row',
        'row': row_num,
        'line': line_num,
        'instructions': instructions,
        'raw_instructions': instr_text
    }

def tokenize_instruction_list(instr_text):
    # Split by commas, but handle brackets
    tokens = []
    i = 0
    while i < len(instr_text):
        c = instr_text[i]
        if c == '[':
            depth = 1
            start = i
            i += 1
            while i < len(instr_text) and depth > 0:
                if instr_text[i] == '[':
                    depth += 1
                elif instr_text[i] == ']':
                    depth -= 1
                i += 1
            if depth != 0:
                return None  # unmatched bracket
            tokens.append(instr_text[start:i])
        elif c == ',':
            tokens.append(',')
            i += 1
        elif c.isspace():
            i += 1
        else:
            start = i
            while i < len(instr_text) and instr_text[i] not in ',[]':
                i += 1
            tokens.append(instr_text[start:i])
    return tokens

def parse_bracket_repeat(token, line_num, row_num):
    # token is like [k2,p2] x3 or [k1]x2
    if not token.startswith('['):
        return None, []
    
    # Find the closing bracket
    depth = 0
    for i, c in enumerate(token):
        if c == '[':
            depth += 1
        elif c == ']':
            depth -= 1
            if depth == 0:
                inner = token[1:i]
                rest = token[i+1:].strip()
                break
    else:
        return None, [{'type': 'error', 'code': 'MALFORMED_ROW', 'message': 'Unclosed bracket in instruction.', 'line': line_num, 'row': row_num}]
    
    # Must have space before x
    if not rest.startswith(' x'):
        return None, [{'type': 'error', 'code': 'MALFORMED_ROW', 'message': 'Missing space before x in bracket repeat.', 'line': line_num, 'row': row_num}]
    
    count_part = rest[2:].strip()
    if not count_part:
        return None, [{'type': 'error', 'code': 'MALFORMED_ROW', 'message': 'Missing repeat count in bracket repeat.', 'line': line_num, 'row': row_num}]
    
    if not re.fullmatch(r'\d+', count_part):
        return None, [{'type': 'error', 'code': 'MALFORMED_ROW', 'message': 'Bracket repeat count must be a positive integer.', 'line': line_num, 'row': row_num}]
    
    count = int(count_part)
    if count <= 0:
        return None, [{'type': 'error', 'code': 'MALFORMED_ROW', 'message': 'Bracket repeat count must be positive.', 'line': line_num, 'row': row_num}]
    
    # Parse inner instruction list
    inner_tokens = tokenize_instruction_list(inner)
    if inner_tokens is None:
        return None, [{'type': 'error', 'code': 'MALFORMED_ROW', 'message': 'Malformed instruction in bracket repeat.', 'line': line_num, 'row': row_num}]
    
    inner_instructions = []
    inner_errors = []
    i = 0
    while i < len(inner_tokens):
        tok = inner_tokens[i]
        if tok == ',':
            i += 1
            continue
        if tok.startswith('['):
            # Nested bracket
            nested_instr, nested_errs = parse_bracket_repeat(tok, line_num, row_num)
            if nested_errs:
                inner_errors.extend(nested_errs)
            else:
                inner_instructions.append({'type': 'bracket', 'instructions': nested_instr, 'count': 1})  # count handled by outer
            i += 1
        else:
            # Simple stitch
            stitch_match = re.match(r'^(k|p)(\d+)$', tok)
            if stitch_match:
                stitch_type = stitch_match.group(1)
                stitch_count = int(stitch_match.group(2))
                if stitch_count <= 0:
                    inner_errors.append({'type': 'error', 'code': 'UNKNOWN_STITCH', 'message': f'Invalid stitch count {stitch_count}.', 'line': line_num, 'row': row_num})
                else:
                    inner_instructions.append({'type': 'stitch', 'stitch': stitch_type, 'count': stitch_count})
            elif tok in ['yo', 'k2tog', 'ssk', 'inc', 'dec']:
                inner_instructions.append({'type': 'stitch', 'stitch': tok, 'count': 1})
            else:
                inner_errors.append({'type': 'error', 'code': 'UNKNOWN_STITCH', 'message': f'Unknown stitch {tok}.', 'line': line_num, 'row': row_num})
            i += 1
    
    if inner_errors:
        return None, inner_errors
    
    return {'type': 'bracket', 'instructions': inner_instructions, 'count': count}, []

def parse_instruction_list(instr_text, line_num, row_num):
    tokens = tokenize_instruction_list(instr_text)
    if tokens is None:
        return [], [{'type': 'error', 'code': 'MALFORMED_ROW', 'message': 'Unclosed bracket in instruction list.', 'line': line_num, 'row': row_num}]
    
    if not tokens:
        return [], [{'type': 'error', 'code': 'MALFORMED_ROW', 'message': 'Empty instruction list.', 'line': line_num, 'row': row_num}]
    
    instructions = []
    errors = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok == ',':
            i += 1
            continue
        
        if tok.startswith('['):
            # Bracket repeat
            if i > 0 and tokens[i-1] != ',':
                errors.append({'type': 'error', 'code': 'MALFORMED_ROW', 'message': 'Missing comma before bracket repeat.', 'line': line_num, 'row': row_num})
                i += 1
                continue
            if i < len(tokens) - 1 and tokens[i+1] != ',':
                # Check if next is comma or end
                # But could be end of list
                pass
            
            bracket_instr, bracket_errors = parse_bracket_repeat(tok, line_num, row_num)
            if bracket_errors:
                errors.extend(bracket_errors)
            else:
                instructions.append(bracket_instr)
            i += 1
        else:
            # Simple stitch
            stitch_match = re.match(r'^(k|p)(\d+)$', tok)
            if stitch_match:
                stitch_type = stitch_match.group(1)
                stitch_count = int(stitch_match.group(2))
                if stitch_count <= 0:
                    errors.append({'type': 'error', 'code': 'UNKNOWN_STITCH', 'message': f'Invalid stitch count {stitch_count}.', 'line': line_num, 'row': row_num})
                else:
                    instructions.append({'type': 'stitch', 'stitch': stitch_type, 'count': stitch_count})
            elif tok in ['yo', 'k2tog', 'ssk', 'inc', 'dec']:
                instructions.append({'type': 'stitch', 'stitch': tok, 'count': 1})
            else:
                errors.append({'type': 'error', 'code': 'UNKNOWN_STITCH', 'message': f'Unknown stitch {tok}.', 'line': line_num, 'row': row_num})
            i += 1
    
    # Check for empty tokens or double commas
    text_no_brackets = re.sub(r'\[[^\]]*\]', '', instr_text)
    if re.search(r',\s*,', text_no_brackets) or text_no_brackets.strip().startswith(',') or text_no_brackets.strip().endswith(','):
        errors.append({'type': 'error', 'code': 'MALFORMED_ROW', 'message': 'Empty instruction in list.', 'line': line_num, 'row': row_num})
    
    return instructions, errors

def parse_repeat(line, line_num):
    line_stripped = strip_comments(line)
    if not line_stripped:
        return None
        
    if line_stripped == 'repeat' or not line_stripped.startswith('repeat'):
        return None
    
    # Must be 'repeat rows <start>-<end> x<count>'
    # No internal spaces in range or count
    match = re.match(r'^repeat\s+rows\s+(\d+)-(\d+)\s+x(\d+)$', line_stripped)
    if not match:
        # Check if it has the structure but invalid count or range
        partial_match = re.match(r'^repeat\s+rows\s+(\d+)-(\d+)\s+x(.*)$', line_stripped)
        if partial_match:
            count_str = partial_match.group(3)
            if not count_str:
                return {'type': 'error', 'code': 'INVALID_REPEAT_COUNT', 'message': 'Missing repeat count.', 'line': line_num, 'row': None}
            if not re.fullmatch(r'\d+', count_str) or int(count_str) <= 0:
                return {'type': 'error', 'code': 'INVALID_REPEAT_COUNT', 'message': 'Repeat count must be a positive integer.', 'line': line_num, 'row': None}
        return {'type': 'error', 'code': 'MALFORMED_REPEAT', 'message': 'Malformed repeat statement.', 'line': line_num, 'row': None}
    
    start = int(match.group(1))
    end = int(match.group(2))
    count_str = match.group(3)
    count = int(count_str)
    
    if start <= 0 or end <= 0:
        return {'type': 'error', 'code': 'INVALID_REPEAT_RANGE', 'message': 'Repeat range must use positive row numbers.', 'line': line_num, 'row': None}
    
    if start > end:
        return {'type': 'error', 'code': 'INVALID_REPEAT_RANGE', 'message': 'Repeat start must be <= end.', 'line': line_num, 'row': None}
    
    if count <= 0:
        return {'type': 'error', 'code': 'INVALID_REPEAT_COUNT', 'message': 'Repeat count must be positive.', 'line': line_num, 'row': None}
    
    return {
        'type': 'repeat',
        'start': start,
        'end': end,
        'count': count,
        'line': line_num
    }

def parse_bind_off(line, line_num):
    line_stripped = strip_comments(line)
    if not line_stripped:
        return None
        
    if line_stripped == 'bind_off':
        return {'type': 'bind_off', 'line': line_num}
    elif line_stripped.startswith('bind_off'):
        return {'type': 'error', 'code': 'MALFORMED_BIND_OFF', 'message': 'Malformed bind off statement.', 'line': line_num, 'row': None}
    else:
        return None

def parse_statement(line, line_num):
    parsers = [
        parse_pattern,
        parse_cast_on,
        parse_row,
        parse_repeat,
        parse_bind_off
    ]
    
    for parser in parsers:
        result = parser(line, line_num)
        if result is not None:
            return result
    
    # If no parser matched, check if it starts with any keyword
    line_stripped = strip_comments(line)
    if not line_stripped:
        return None
        
    keywords = ['pattern', 'cast_on', 'row', 'repeat', 'bind_off']
    for kw in keywords:
        if line_stripped.startswith(kw):
            # But didn't match - so malformed
            return {'type': 'error', 'code': f'MALFORMED_{kw.upper()}', 'message': f'Malformed {kw} statement.', 'line': line_num, 'row': None}
    
    return {'type': 'error', 'code': 'UNKNOWN_STATEMENT', 'message': 'Unknown statement.', 'line': line_num, 'row': None}

def expand_bracket_repeat(instr):
    # instr is {'type': 'bracket', 'instructions': [...], 'count': N}
    expanded = []
    for _ in range(instr['count']):
        for sub in instr['instructions']:
            if sub['type'] == 'bracket':
                expanded.extend(expand_bracket_repeat(sub))
            else:
                expanded.append(sub)
    return expanded

def flatten_instructions(parsed_instructions):
    flattened = []
    for instr in parsed_instructions:
        if instr['type'] == 'bracket':
            expanded = expand_bracket_repeat(instr)
            flattened.extend(expanded)
        else:
            flattened.append(instr)
    return flattened

def simulate_row(instructions, start_stitches, line_num, row_num):
    # instructions are already flattened
    remaining = start_stitches
    produced = 0
    
    for instr in instructions:
        stitch = instr['stitch']
        count = instr['count']
        
        if stitch in ['k', 'p']:
            if remaining < count:
                return None, {'type': 'error', 'code': 'STITCH_UNDERFLOW', 'message': f'Row {row_num} consumes more stitches than available.', 'line': line_num, 'row': row_num}
            remaining -= count
            produced += count
        elif stitch == 'yo':
            produced += 1
        elif stitch == 'k2tog':
            if remaining < 2:
                return None, {'type': 'error', 'code': 'STITCH_UNDERFLOW', 'message': f'Row {row_num} consumes more stitches than available.', 'line': line_num, 'row': row_num}
            remaining -= 2
            produced += 1
        elif stitch == 'ssk':
            if remaining < 2:
                return None, {'type': 'error', 'code': 'STITCH_UNDERFLOW', 'message': f'Row {row_num} consumes more stitches than available.', 'line': line_num, 'row': row_num}
            remaining -= 2
            produced += 1
        elif stitch == 'inc':
            if remaining < 1:
                return None, {'type': 'error', 'code': 'STITCH_UNDERFLOW', 'message': f'Row {row_num} consumes more stitches than available.', 'line': line_num, 'row': row_num}
            remaining -= 1
            produced += 2
        elif stitch == 'dec':
            if remaining < 2:
                return None, {'type': 'error', 'code': 'STITCH_UNDERFLOW', 'message': f'Row {row_num} consumes more stitches than available.', 'line': line_num, 'row': row_num}
            remaining -= 2
            produced += 1
        
        if produced > 10000:
            return None, {'type': 'error', 'code': 'STITCH_OVERFLOW', 'message': f'Row {row_num} produces more than 10,000 stitches.', 'line': line_num, 'row': row_num}
    
    return produced, None

def main():
    if len(sys.argv) != 3 or sys.argv[1] != 'compile':
        print('', file=sys.stderr)
        sys.exit(2)
    
    filepath = sys.argv[2]
    try:
        with open(filepath, 'r') as f:
            lines = f.readlines()
    except Exception:
        sys.exit(2)
    
    # Parse all lines
    statements = []
    errors = []
    
    bind_off_line = None
    cast_on_line = None
    cast_on_value = None
    pattern_name = None
    valid_pattern_found = False
    valid_cast_on_found = False
    valid_bind_off_count = 0
    
    # We need to collect all statements first
    for i, line in enumerate(lines):
        line_num = i + 1
        stmt = parse_statement(line, line_num)
        if stmt is None:
            continue
        
        if stmt['type'] == 'error':
            errors.append(stmt)
        else:
            statements.append(stmt)
    
    # Now process statements in order
    seen_rows = set()
    row_declarations = {}  # row_num -> stmt
    repeat_statements = []
    
    for stmt in statements:
        if stmt['type'] == 'pattern':
            if valid_pattern_found:
                errors.append({'type': 'error', 'code': 'DUPLICATE_PATTERN', 'message': 'Duplicate pattern declaration.', 'line': stmt['line'], 'row': None})
                pattern_name = None
            else:
                pattern_name = stmt['name']
                valid_pattern_found = True
        elif stmt['type'] == 'cast_on':
            if valid_cast_on_found:
                errors.append({'type': 'error', 'code': 'DUPLICATE_CAST_ON', 'message': 'Duplicate cast on declaration.', 'line': stmt['line'], 'row': None})
            else:
                cast_on_value = stmt['value']
                cast_on_line = stmt['line']
                valid_cast_on_found = True
        elif stmt['type'] == 'row':
            row_num = stmt['row']
            # Check if after bind_off
            if bind_off_line is not None and stmt['line'] > bind_off_line:
                errors.append({'type': 'error', 'code': 'BIND_OFF_OUT_OF_ORDER', 'message': 'Row after bind off.', 'line': stmt['line'], 'row': row_num})
            # Check for duplicate row
            if row_num in seen_rows:
                errors.append({'type': 'error', 'code': 'DUPLICATE_ROW', 'message': f'Duplicate row number {row_num}.', 'line': stmt['line'], 'row': row_num})
            else:
                # Check for out of order
                if seen_rows and row_num <= max(seen_rows):
                    # But not duplicate
                    if row_num not in seen_rows:
                        errors.append({'type': 'error', 'code': 'OUT_OF_ORDER_ROW', 'message': f'Row {row_num} is out of order.', 'line': stmt['line'], 'row': row_num})
                seen_rows.add(row_num)
                row_declarations[row_num] = stmt
            # Also check if cast_on is after this row
            if cast_on_line is not None and cast_on_line > stmt['line']:
                errors.append({'type': 'error', 'code': 'CAST_ON_OUT_OF_ORDER', 'message': 'Cast on appears after row.', 'line': cast_on_line, 'row': None})
        elif stmt['type'] == 'repeat':
            if bind_off_line is not None and stmt['line'] > bind_off_line:
                errors.append({'type': 'error', 'code': 'BIND_OFF_OUT_OF_ORDER', 'message': 'Repeat after bind off.', 'line': stmt['line'], 'row': None})
            # Validate range
            start = stmt['start']
            end = stmt['end']
            if start <= 0 or end <= 0:
                errors.append({'type': 'error', 'code': 'INVALID_REPEAT_RANGE', 'message': 'Repeat range must use positive row numbers.', 'line': stmt['line'], 'row': None})
            elif start > end:
                errors.append({'type': 'error', 'code': 'INVALID_REPEAT_RANGE', 'message': 'Repeat start must be <= end.', 'line': stmt['line'], 'row': None})
            else:
                # Check if all rows in range exist
                missing = []
                for r in range(start, end + 1):
                    if r not in row_declarations:
                        missing.append(r)
                if missing:
                    errors.append({'type': 'error', 'code': 'INVALID_REPEAT_RANGE', 'message': f'Repeat range references missing rows {missing}.', 'line': stmt['line'], 'row': None})
            repeat_statements.append(stmt)
        elif stmt['type'] == 'bind_off':
            if valid_bind_off_count > 0:
                errors.append({'type': 'error', 'code': 'DUPLICATE_BIND_OFF', 'message': 'Duplicate bind off declaration.', 'line': stmt['line'], 'row': None})
            else:
                bind_off_line = stmt['line']
                valid_bind_off_count += 1
    
    # Check for missing pattern
    if not valid_pattern_found:
        errors.append({'type': 'error', 'code': 'MISSING_PATTERN', 'message': 'Missing pattern declaration.', 'line': None, 'row': None})
    
    # Check for missing cast_on
    if not valid_cast_on_found:
        errors.append({'type': 'error', 'code': 'MISSING_CAST_ON', 'message': 'Missing cast on declaration.', 'line': None, 'row': None})
    
    # Now check for statements after bind_off
    if bind_off_line is not None:
        for stmt in statements:
            if stmt['type'] != 'bind_off' and stmt['line'] > bind_off_line:
                # We already added BIND_OFF_OUT_OF_ORDER for rows and repeats
                # But for other statements, we need to add
                if stmt['type'] not in ['error']:
                    # But errors might be already added
                    # We need to check if BIND_OFF_OUT_OF_ORDER is already present for this line
                    has_error = False
                    for err in errors:
                        if err['line'] == stmt['line'] and err['code'] == 'BIND_OFF_OUT_OF_ORDER':
                            has_error = True
                            break
                    if not has_error:
                        errors.append({'type': 'error', 'code': 'BIND_OFF_OUT_OF_ORDER', 'message': 'Statement after bind off.', 'line': stmt['line'], 'row': stmt.get('row') if stmt['type'] == 'row' else None})
    
    # Sort errors by line number, then by code order
    error_code_order = [
        'MISSING_PATTERN',
        'MALFORMED_PATTERN',
        'DUPLICATE_PATTERN',
        'MISSING_CAST_ON',
        'MALFORMED_CAST_ON',
        'DUPLICATE_CAST_ON',
        'CAST_ON_OUT_OF_ORDER',
        'UNKNOWN_STATEMENT',
        'MALFORMED_ROW',
        'DUPLICATE_ROW',
        'OUT_OF_ORDER_ROW',
        'UNKNOWN_STITCH',
        'STITCH_UNDERFLOW',
        'STITCH_OVERFLOW',
        'MALFORMED_REPEAT',
        'INVALID_REPEAT_COUNT',
        'INVALID_REPEAT_RANGE',
        'MALFORMED_BIND_OFF',
        'DUPLICATE_BIND_OFF',
        'BIND_OFF_OUT_OF_ORDER'
    ]
    
    def error_key(err):
        line = err['line'] if err['line'] is not None else float('inf')
        code = err['code']
        code_index = error_code_order.index(code) if code in error_code_order else len(error_code_order)
        return (line, code_index)
    
    errors.sort(key=error_key)
    
    # Determine bind_off output
    bind_off_output = valid_bind_off_count > 0
    
    # If any error, output invalid result
    if errors:
        result = {
            'pattern_name': pattern_name,
            'cast_on': cast_on_value,
            'valid': False,
            'errors': errors,
            'expanded_rows': [],
            'final_stitch_count': None,
            'bind_off': bind_off_output
        }
        print(json.dumps(result, indent=2))
        sys.exit(1)
    
    # No errors - now expand rows
    # First, build source row sequence
    # But we need to include repeats
    # Order by row number
    source_rows = []
    for row_num in sorted(row_declarations.keys()):
        source_rows.append(row_declarations[row_num])
    
    # Build expanded row sequence
    expanded_rows = []
    current_index = 1
    
    # We'll process statements in order, but only rows and repeats
    # Actually, we need to expand according to source order of statements
    # But statements include pattern, cast_on, etc.
    # We only care about row and repeat
    # Let's collect the sequence of source row numbers to expand
    row_sequence = []
    
    for stmt in statements:
        if stmt['type'] == 'row':
            row_sequence.append(stmt['row'])
        elif stmt['type'] == 'repeat':
            start = stmt['start']
            end = stmt['end']
            count = stmt['count']
            # Add the range 'count' times
            for _ in range(count):
                for r in range(start, end + 1):
                    row_sequence.append(r)
    
    # Now simulate
    current_stitches = cast_on_value
    simulation_errors = []
    
    for source_row_num in row_sequence:
        stmt = row_declarations[source_row_num]
        
        # Flatten instructions
        flat_instructions = flatten_instructions(stmt['instructions'])
        
        # Simulate
        end_stitches, error = simulate_row(flat_instructions, current_stitches, stmt['line'], source_row_num)
        if error is not None:
            simulation_errors.append(error)
            break
        
        # Create expanded row
        expanded_row = {
            'expanded_row_index': current_index,
            'source_row': source_row_num,
            'instructions': [],
            'start_stitches': current_stitches,
            'end_stitches': end_stitches
        }
        
        # Convert flat_instructions to output format
        for instr in flat_instructions:
            expanded_row['instructions'].append({
                'stitch': instr['stitch'],
                'count': instr['count']
            })
        
        expanded_rows.append(expanded_row)
        current_stitches = end_stitches
        current_index += 1
    
    if simulation_errors:
        # Only first error
        errors.extend(simulation_errors[:1])
        result = {
            'pattern_name': pattern_name,
            'cast_on': cast_on_value,
            'valid': False,
            'errors': errors,
            'expanded_rows': [],
            'final_stitch_count': None,
            'bind_off': bind_off_output
        }
        print(json.dumps(result, indent=2))
        sys.exit(1)
    
    # Success
    result = {
        'pattern_name': pattern_name,
        'cast_on': cast_on_value,
        'valid': True,
        'errors': [],
        'expanded_rows': expanded_rows,
        'final_stitch_count': current_stitches,
        'bind_off': bind_off_output
    }
    print(json.dumps(result, indent=2))
    sys.exit(0)

if __name__ == '__main__':
    main()