"""Fix database.py to return dicts from SQLite instead of Row objects."""
import re

path = r"C:\Users\User\Desktop\aetherdesk_scaffold\apps\api\services\database.py"
with open(path) as f:
    content = f.read()

# Add dict_factory after sqlite3 import
content = content.replace(
    "import sqlite3\n",
    "import sqlite3\n\ndef _dict_factory(cursor, row):\n    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}\n"
)

# Update _get_sqlite_conn to use dict_factory
content = content.replace(
    "    conn.row_factory = sqlite3.Row\n    return conn",
    "    conn.row_factory = _dict_factory\n    return conn"
)

with open(path, "w") as f:
    f.write(content)

print("Fixed database.py")