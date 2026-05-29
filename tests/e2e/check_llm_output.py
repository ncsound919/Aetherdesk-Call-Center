import json, httpx

SYSTEM_PROMPT = """You are an intent classifier for a call center IVR system.
Classify into: pharmacy_refill, billing_refund, tech_support_password, generalInquiry, agent_handoff.
Respond with JSON only: {"intent": "...", "entities": {}, "confidence": 0.9, "reasoning": "..."}"""

for text in ["I need a refill", "You charged me twice", "My password isnt working"]:
    r = httpx.post("http://localhost:11434/api/chat",
        json={
            "model": "llama3.2:1b",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Current utterance: {text}"}
            ],
            "format": "json",
            "temperature": 0.1,
            "num_predict": 40,
            "stream": False,
        }, timeout=30)
    content = r.json()["message"]["content"]
    try:
        parsed = json.loads(content)
        intent = parsed.get("intent", "???")
        conf = parsed.get("confidence", "?")
    except:
        intent = "PARSE_FAIL"
        conf = 0
    print(f"[{intent:25s}] conf={conf:.2f}  input={text}")
