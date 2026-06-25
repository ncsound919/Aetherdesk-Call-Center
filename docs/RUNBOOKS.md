# AetherDesk Incident Runbooks

## Telephony Outage (Severity: Critical)
**Impact:** Complete or partial loss of voice connectivity
**Detection:** Vendor health checks fail, active call count drops, SIP registration failures

### Steps
1. **Check provider status** (60s timeout)
   - Twilio: https://status.twilio.com
   - Fonoster: Check `docker logs aetherdesk-fonoster`
2. **Test SIP connectivity**
   - `docker exec aetherdesk-freeswitch fs_cli -x "status"`
   - Check SIP registration count
3. **Check FreeSWITCH**
   - `docker exec aetherdesk-freeswitch fs_cli -x "sofia status"`
4. **Enable failover** (30s timeout)
   - If primary provider down, switch to secondary via config
5. **Notify escalation contacts**

### Escalation
- L1 (15m): On-call engineer
- L2 (30m): Engineering lead, Ops manager
- L3 (60m): VP Engineering, CTO

## Database Failure (Severity: Critical)
**Impact:** No new data can be written, call routing fails
**Detection:** DB health check fails, connection pool exhausted

### Steps
1. **Check DB process** (30s)
   - `docker exec aetherdesk-db pg_isready -U aetherdesk_admin`
2. **Check connections** (30s)
   - `docker exec aetherdesk-db psql -U aetherdesk_admin -c "SELECT count(*) FROM pg_stat_activity"`
3. **Check disk space** (15s)
   - `docker exec aetherdesk-db df -h /var/lib/postgresql/data`
4. **Attempt restart** (60s)
   - `docker restart aetherdesk-db`
5. **Enable read-only mode** if write fails

## LLM Degradation (Severity: High)
**Impact:** AI agent responses delayed, intent classification fails
**Detection:** Groq/Ollama response time > 5s, error rate > 10%

### Steps
1. **Check LLM health** (30s)
   - Groq: `curl https://api.groq.com/openai/v1/models`
   - Ollama: `curl http://localhost:11434/api/tags`
2. **Check rate limits** (15s)
   - Verify API key quota not exceeded
3. **Switch fallback model** (30s)
   - Configure alternate model in .env
4. **Enable cached responses** (60s)
   - Serve cached responses for common intents

## Security Incident (Severity: Critical)
**Impact:** Potential unauthorized access or data breach
**Detection:** Unusual access patterns, audit log anomalies

### Steps
1. **Isolate system** (60s)
   - Revoke compromised credentials
   - Block suspicious IPs at firewall
2. **Preserve evidence** (30s)
   - Export audit logs, access logs
   - Capture memory dumps if needed
3. **Assess scope** (5m)
   - Determine what data may have been accessed
4. **Notify legal** (10m)
   - Required for data breaches under GDPR/HIPAA
5. **Notify affected customers** (1h)
   - Per regulatory requirements

---

## Vendor Health Monitoring
- **Twilio**: Check `https://api.twilio.com` health (every 60s)
- **Deepgram**: Check API key validity (every 60s)
- **Groq**: Check API endpoint (every 60s)
- **Chatterbox**: Check local TTS service (every 60s)

Vendor status is available at `/health/vendors` endpoint.
