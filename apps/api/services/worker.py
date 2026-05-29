import asyncio
import os

import redis
import structlog

from apps.api.services.actions import Actions
from apps.api.services.orchestrator import Orchestrator
from apps.api.services.queue import QueueManager

logger = structlog.get_logger()

class AutonomousWorker:
    def __init__(self, redis_client):
        self.qm = QueueManager(redis_client)
        self.actions = Actions()
        self.orchestrator = Orchestrator(self.actions)
        self.running = True

    async def run(self):
        logger.info("autonomous_worker_started", mode="AUTO")
        while self.running:
            # Check if auto-mode is enabled for the default tenant
            # In a real app, you'd iterate over tenants with auto-mode ON

            item = self.qm.claim("general", "AUTO-WORKER-001")
            if item:
                logger.info("processing_queue_item", session_id=item['session_id'])

                # Simulate agent processing
                history = [{"from": "customer", "text": item['preview']}]
                response = await self.orchestrator.step({}, history, item['preview'])

                logger.info("auto_worker_response", response=response.text)

                # Record for QA
                await self.orchestrator.record_session(item['session_id'], history + [{"from": "agent", "text": response.text}])

                # In a real system, you'd send the response back via the protocol (e.g. Twilio)

            await asyncio.sleep(5) # Poll every 5 seconds

async def start_worker():
    r = redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        decode_responses=True
    )
    worker = AutonomousWorker(r)
    await worker.run()

if __name__ == "__main__":
    asyncio.run(start_worker())
