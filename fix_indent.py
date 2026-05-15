#!/usr/bin/env python
"""Fix main.py health check indentation."""
import re

path = r"C:\Users\User\Desktop\aetherdesk_scaffold\apps\api\main.py"
with open(path) as f:
    content = f.read()

# Replace the broken try block - match exactly what's there
old = """try:
         if USE_POSTGRES:
             pool = await get_pg_pool()
             if pool:
                 await pool.fetchval("SELECT 1")
                 db_status = "connected"
     except Exception:
         db_status = "disconnected"

     overall"""

new = """try:
        if USE_POSTGRES:
            pool = await get_pg_pool()
            if pool:
                await pool.fetchval("SELECT 1")
                db_status = "connected"
    except Exception:
        db_status = "disconnected"

    overall"""

if old in content:
    content = content.replace(old, new)
    with open(path, "w") as f:
        f.write(content)
    print("FIXED!")
else:
    # Print the exact bytes around line 399
    lines = content.split("\n")
    for i, line in enumerate(lines[398:410], start=399):
        print(f"{i}: {repr(line)}")
    print("COULD NOT FIND MATCH")