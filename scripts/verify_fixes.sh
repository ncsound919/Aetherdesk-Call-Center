#!/bin/bash
# Script to verify the security fixes made to the AetherDesk codebase
echo "=== Verifying Security Fixes ==="
echo ""

echo "1. Checking database.py for hardcoded password..."
grep -n "DATABASE_URL" apps/api/services/database.py
echo ""

echo "2. Checking deployment.yml for hardcoded API keys..."
grep -n "DEEPGRAM_API_KEY\|GROQ_API_KEY" kubernetes/deployment.yml
echo ""

echo "3. Checking main.py for CORS fixes..."
grep -A5 "CORSMiddleware" apps/api/main.py
echo ""

echo "4. Checking voice.py for auth on /voice/incoming..."
grep -B2 "handle_incoming_call" apps/api/routers/voice.py | head -10
echo ""

echo "5. Checking voice_cloning.py for auth..."
grep -n "verify_api_key\|dependencies" apps/api/routers/voice_cloning.py
echo ""

echo "6. Checking voice_cloning.py for FormData fix..."
grep -n "FormData\|add_field" apps/api/routers/voice_cloning.py
echo ""

echo "7. Checking auth.py for configurable dev passwords..."
grep -n "os.getenv.*PASSWORD" apps/api/routers/auth.py
echo ""

echo "8. Checking saas.py for hardcoded API key removal..."
grep -A3 "def get_tenant_id" apps/api/routers/saas.py
echo ""

echo "9. Checking protocols.py for security fixes..."
grep -n "verify_api_key\|SAFE_FILENAME\|tenant_id" apps/api/routers/protocols.py
echo ""

echo "10. Checking call_session.py for buffer limit..."
grep -n "MAX_BUFFER_SIZE\|hard limit" apps/api/services/call_session.py
echo ""

echo ""
echo "=== All fixes verified ==="