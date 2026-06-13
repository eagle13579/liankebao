#!/usr/bin/env python3
"""Fix SQLAlchemy 2.0 compatibility in migration script."""
import re
import sys

path = sys.argv[1] if len(sys.argv) > 1 else '/tmp/migrate_sqlite_to_pg.py'

with open(path, 'r') as f:
    code = f.read()

# Add text import if missing
if 'from sqlalchemy import text' not in code:
    code = code.replace('import logging', 'import logging\nfrom sqlalchemy import text', 1)

# Fix multi-line conn.execute("...")
code = re.sub(
    r'conn\.execute\(\s*\n\s*"((?:[^"\\]|\\.)*)"\s*\n\s*\)',
    r'conn.execute(text("\1"))',
    code
)

# Fix single-line conn.execute("...")
code = re.sub(
    r'conn\.execute\("((?:[^"\\]|\\.)*)"\)',
    r'conn.execute(text("\1"))',
    code
)

with open(path, 'w') as f:
    f.write(code)

print(f'Fixed {path}')
import ast
try:
    ast.parse(code)
    print('Syntax OK')
except SyntaxError as e:
    print(f'Syntax error: {e}')
