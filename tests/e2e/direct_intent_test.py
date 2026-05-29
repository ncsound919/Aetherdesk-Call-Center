"""Test intent classifier directly (not through HTTP)."""
import asyncio, time
from apps.api.services.intent_classifier import classifier

async def main():
    t0 = time.time()
    result = await classifier.classify("I need to refill my blood pressure medication")
    elapsed = time.time() - t0
    print(f"[{elapsed:.1f}s] intent={result.intent}, confidence={result.confidence}")
    print(f"  reasoning: {result.reasoning}")

    t0 = time.time()
    result = await intent_classifier.classify("You charged me twice and I want a refund")
    print(f"[{time.time()-t0:.1f}s] intent={result.intent}, reasoning={result.reasoning[:60]}")

    t0 = time.time()
    result = await intent_classifier.classify("My password isnt working")
    print(f"[{time.time()-t0:.1f}s] intent={result.intent}, reasoning={result.reasoning[:60]}")

asyncio.run(main())
