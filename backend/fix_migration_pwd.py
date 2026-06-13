#!/usr/bin/env python3
"""Fix PG password URL encoding + SQLAlchemy 2.0 compatibility."""
import re
import sys

path = '/tmp/migrate_sqlite_to_pg.py'

with open(path) as f:
    code = f.read()

# Fix 1: URL-encode the @ in password
old = 'PG_PASSWORD = os.environ.get("PG_PASSWORD", "Ch@1nKe_PG_2026")'
new = 'from urllib.parse import quote_plus as _qp; PG_PASSWORD = os.environ.get("PG_PASSWORD", _qp("Ch@1nKe_PG_2026"))'
code = code.replace(old, new)

# Fix 2: All conn.execute("...") multi-line -> conn.execute(text(...))
# Pattern: conn.execute(\n  "SQL"\n)
code = re.sub(
    r'conn\.execute\(\s*\n\s*"([^"]*)"\s*\n\s*\)',
    lambda m: 'conn.execute(text("""' + m.group(1) + '"""))',
    code
)

# Fix 3: Single-line too
code = re.sub(
    r'conn\.execute\("([^"]*)"\)',
    lambda m: 'conn.execute(text("""' + m.group(1) + '"""))',
    code
)

with open(path, 'w') as f:
    f.write(code)

import ast
try:
    ast.parse(code)
    print('Syntax OK')
except SyntaxError as e:
    print(f'Syntax Error: {e}')

print('Lines with text():', code.count('text('))
print('Lines with conn.execute:', code.count('conn.execute('))
