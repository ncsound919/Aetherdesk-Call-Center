import sqlite3
import os

db_path = 'aetherdesk.db'

print(f"Connecting to database at {os.path.abspath(db_path)}...")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 1. Insert default tenant
cursor.execute("""
INSERT OR REPLACE INTO tenants (id, name, slug, email, phone) 
VALUES ('TENANT-001', 'Acme Corp', 'acme', 'acme@example.com', '+15555555555')
""")

# 2. Insert agent profile with system prompt (Script)
system_prompt = """You are Aether, a highly conversational B2B sales agent for AetherDesk.
Your goal is to pitch the caller on upgrading their call center with AI Agents.
- Be extremely friendly, polite, and enthusiastic.
- Talk like a real human (use filler words like 'um', 'uh', 'so' occasionally, but keep it natural).
- Keep your answers short (1-2 sentences maximum) for natural voice conversation.
- Pitch the benefits: 24/7 coverage, instant responses, and 80% cost savings.
- Your call to action is to get them to book a demo.
"""

cursor.execute("""
INSERT OR REPLACE INTO agent_profiles (id, tenant_id, name, prompt, parameters) 
VALUES ('voice_78f08fdb', 'TENANT-001', 'Aether-Voice-Clone', ?, '{"tools": ["search_knowledge_base", "handoff_to_human"]}')
""", (system_prompt,))

# 3. Insert active rental
cursor.execute("""
INSERT OR REPLACE INTO rentals (id, tenant_id, profile_id, start_time, end_time, duration_type, status) 
VALUES ('RENT-002', 'TENANT-001', 'voice_78f08fdb', '2026-05-17 00:00:00', '2026-05-18 00:00:00', 'day', 'active')
""")

conn.commit()
conn.close()
print("Seeded database successfully for new voice!")
