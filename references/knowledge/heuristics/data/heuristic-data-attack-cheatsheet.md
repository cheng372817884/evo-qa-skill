---
id: heuristic-data-attack-cheatsheet
type: reference
scope: universal
title: "Data Type Attack Cheat Sheet"
summary: "Concrete attack values for strings, numerics, dates, files"
tags: ['data', 'attacks', 'cheatsheet']
domains: []
priority: high
confidence: 1.0
verified_runs: 0
failed_runs: 0
last_used_at: null
last_succeeded_at: null
review_state: active
retrieval_weight: 1.0
source_type: imported
source_ref: "github.com/danashby/Exploratory-Testing-Skill (MIT)"
decay_history: []
revival_history: []
created_at: 2026-06-17
updated_at: 2026-06-17
---

## Part 5: Data Type Attack Cheat Sheet

Specific input values to probe for common vulnerabilities. Apply these to any input field.

### String / Text Inputs
- Empty string
- Single space / multiple spaces / only whitespace
- Very long string (255 chars, 1000 chars, 65535 chars)
- SQL injection: `' OR '1'='1`, `'; DROP TABLE users;--`
- XSS: `<script>alert(1)</script>`, `<img src=x onerror=alert(1)>`
- Special characters: `! @ # $ % ^ & * ( ) - _ + = [ ] { } | \ : ; ' " < > , . ? /`
- Unicode and emoji: `™`, `©`, `€`, `🎉`, `中文`, `العربية`
- Null character: `\0`
- Newline / carriage return: `\n`, `\r\n`
- Format strings: `%s %d %n %x`
- Path traversal: `../../etc/passwd`, `..\windows\system32`
- HTML entities: `&lt;`, `&amp;`, `&nbsp;`
- Extremely long word with no spaces (tests wrapping/truncation)

### Numeric Inputs
- Zero
- Negative numbers
- Very large number (beyond int32, int64)
- Very small decimal (0.0001, 0.000001)
- Maximum integer: `2147483647`, `2147483648`, `-2147483648`
- Floating point precision edge: `0.1 + 0.2`
- Scientific notation: `1e10`, `1e-10`
- Infinity, NaN
- Number as a string: `"123"`

### Date / Time Inputs
- Invalid dates: Feb 30, Sept 31, Feb 29 in a non-leap year
- Leap day: Feb 29 in a leap year
- Year boundaries: Jan 1 / Dec 31
- Millennium / century boundaries: Y2K, Y2K38 (Unix epoch)
- Daylight saving transition times
- Time zone edge cases: UTC±14, half-hour offsets
- Date in the past vs future vs today
- Different formats: `June 5 2025`, `06/05/2025`, `2025-06-05`, `06-05-25`
- Clock reset: moving system clock backwards or forwards
- Time difference between client and server

### File / Path Inputs
- Non-existent file path
- Already exists (overwrite scenario)
- No disk space available
- Write-protected or read-only
- File locked by another process
- File on a remote or unmapped drive
- Corrupted file
- Empty file (0 bytes)
- Maximum file size
- Wrong file type / extension mismatch
- File with special characters in the name

---

