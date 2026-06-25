// AetherDesk Call Center - Production Fonoster Voice Application
// Handles all inbound/outbound calls with AI-powered routing

const VoiceServer = require("@fonoster/voice").default;
const {
  GatherSource,
  VoiceRequest,
  VoiceResponse,
  Verb
} = require("@fonoster/voice");

// Redis client for real-time state
const Redis = require("ioredis");
const redis = new Redis({
  host: process.env.REDIS_HOST || "aetherdesk-redis",
  port: parseInt(process.env.REDIS_PORT || "6379"),
  password: process.env.REDIS_PASSWORD,
});

// Agent Registry Manager
class AgentRegistry {
  constructor() {
    this.agents = new Map();
    this.callAssignments = new Map();
  }

  async loadAgents() {
    // Load from database via API
    try {
      const response = await fetch(
        `http://${process.env.API_HOST || "aetherdesk-api"}:3000/api/v1/tenants/${process.env.TENANT_ID}/agents`
      );
      if (response.ok) {
        const agents = await response.json();
        agents.forEach((agent) => {
          this.agents.set(agent.id, agent);
        });
      }
    } catch (error) {
      console.error("Failed to load agents:", error);
    }
  }

  async getAvailableAgent(skills = [], tenantId = null) {
    const available = [];
    for (const [id, agent] of this.agents) {
      if (
        agent.status === "available" &&
        (!tenantId || agent.tenantId === tenantId) &&
        (skills.length === 0 || skills.some((s) => agent.skills.includes(s)))
      ) {
        available.push(agent);
      }
    }

    if (available.length === 0) return null;

    // Round-robin or least calls
    return available.sort((a, b) => (a.totalCalls || 0) - (b.totalCalls || 0))[0];
  }

  async updateAgentStatus(agentId, status) {
    const agent = this.agents.get(agentId);
    if (agent) {
      agent.status = status;
      await redis.publish("agent:status", JSON.stringify({ agentId, status }));
    }
  }
}

// Call Queue Manager
class CallQueue {
  constructor() {
    this.queue = [];
  }

  async enqueue(callData) {
    this.queue.push({
      ...callData,
      enqueuedAt: Date.now(),
      position: this.queue.length + 1,
    });
    await redis.lpush("call:queue", JSON.stringify(callData));
  }

  async dequeue() {
    const item = await redis.rpop("call:queue");
    if (item) {
      this.queue = this.queue.filter((c) => c.sessionRef !== item.sessionRef);
      return JSON.parse(item);
    }
    return null;
  }

  get length() {
    return this.queue.length;
  }

  getQueuePosition(sessionRef) {
    return this.queue.findIndex((c) => c.sessionRef === sessionRef) + 1;
  }
}

// Analytics Tracker
class Analytics {
  constructor() {
    this.metrics = {
      totalCalls: 0,
      completedCalls: 0,
      missedCalls: 0,
      totalTalkTime: 0,
    };
  }

  async trackCallStart(callData) {
    this.metrics.totalCalls++;
    await redis.hincrby("analytics:current", "active_calls", 1);
    await redis.lpush(
      "analytics:timeline",
      JSON.stringify({ ...callData, timestamp: Date.now() })
    );
  }

  async trackCallEnd(callData) {
    this.metrics.completedCalls++;
    this.metrics.totalTalkTime += callData.duration || 0;
    await redis.hincrby("analytics:current", "active_calls", -1);
    await redis.hincrby("analytics:current", "completed_calls", 1);
  }

  async getMetrics() {
    return {
      ...this.metrics,
      activeCalls: parseInt(
        (await redis.hget("analytics:current", "active_calls")) || "0"
      ),
    };
  }
}

// Initialize components
const agentRegistry = new AgentRegistry();
const callQueue = new CallQueue();
const analytics = new Analytics();

// Map caller intent to agent skills
const intentToSkills = (intent) => {
  const map = {
    sales: ["sales", "inbound", "outbound"],
    support: ["support", "general"],
    billing: ["billing", "accounts"],
    technical: ["technical", "engineering"],
    account: ["account", "general"],
    general: ["general", "support"],
  };
  return map[intent?.toLowerCase()] || ["general"];
};

// Create main Voice Server
const voiceServer = new VoiceServer();

voiceServer.listen(async (req, voice) => {
  const { ingressNumber, sessionRef, appRef } = req;

  console.log(`[CALL] Incoming from ${ingressNumber}, session: ${sessionRef}`);

  try {
    // Track call start
    await analytics.trackCallStart({
      sessionRef,
      callerNumber: ingressNumber,
      timestamp: Date.now(),
    });

    // Step 1: Answer the call
    await voice.answer();
    console.log(`[${sessionRef}] Call answered`);

    // Step 2: Play welcome message
    await voice.say(
      "Thank you for calling AetherDesk. Your experience matters to us."
    );

    // Step 3: Identify caller intent using AI
    await voice.say("How can I help you today?");

    let callerIntent = "general";
    try {
      const result = await voice.gather({
        source: GatherSource.SPEECH,
        timeout: 15000,
        languageCode: "en-US",
        hints: [
          "sales",
          "support",
          "billing",
          "account",
          "technical",
          "pricing",
          "complaint",
          "feedback",
          "order",
          "cancel",
        ],
      });

      if (result.speech) {
        callerIntent = result.speech;
        console.log(`[${sessionRef}] Detected intent: ${callerIntent}`);
      }
    } catch (e) {
      console.log(`[${sessionRef}] No speech detected, using default routing`);
    }

    // Step 4: Route to best agent
    const skills = intentToSkills(callerIntent);
    const tenantId = req.appData?.tenantId || process.env.DEFAULT_TENANT_ID;
    const agent = await agentRegistry.getAvailableAgent(skills, tenantId);

    if (agent) {
      console.log(
        `[${sessionRef}] Routing to agent ${agent.name} (${agent.id})`
      );

      // Update agent status
      await agentRegistry.updateAgentStatus(agent.id, "busy");

      // Announce connection
      await voice.say(
        `Connecting you with ${agent.displayName || agent.name}. Please hold.`
      );

      // Transfer to agent
      const sipExtension = agent.sipExtension;
      await voice.transfer(`sip:${sipExtension}@${process.env.FS_HOST || "aetherdesk-freeswitch"}`);

      console.log(`[${sessionRef}] Transferred to agent ${agent.id}`);
    } else {
      console.log(`[${sessionRef}] No agents available, queuing`);

      await voice.say(
        "All agents are currently busy. Your call is very important to us."
      );

      // Add to queue
      await callQueue.enqueue({
        sessionRef,
        ingressNumber,
        intent: callerIntent,
        tenantId,
      });

      // Wait in queue with periodic updates
      let waitTime = 0;
      const maxWait = 180000; // 3 minutes
      const checkInterval = 30000; // 30 seconds

      while (waitTime < maxWait) {
        await voice.wait(checkInterval);
        waitTime += checkInterval;

        const position = callQueue.getQueuePosition(sessionRef);
        const message =
          position === 1
            ? "You are next in line."
            : `There are ${position - 1} callers ahead of you.`;

        await voice.say(message);

        // Check if agent became available
        const availableAgent = await agentRegistry.getAvailableAgent(
          skills,
          tenantId
        );
        if (availableAgent) {
          await callQueue.dequeue();
          await agentRegistry.updateAgentStatus(availableAgent.id, "busy");

          await voice.say(
            `An agent is available. Connecting you with ${availableAgent.name}.`
          );
          await voice.transfer(
            `sip:${availableAgent.sipExtension}@${process.env.FS_HOST || "aetherdesk-freeswitch"}`
          );
          return;
        }

        if (waitTime % 60000 === 0 && waitTime > 0) {
          await voice.say(
            `You have been waiting for ${waitTime / 60000} minute(s). We appreciate your patience.`
          );
        }
      }

      // Offer voicemail/callback
      await voice.say("We're sorry for the wait. Would you like to leave a message?");

      const { digits: choice } = await voice.gather({
        maxDigits: 1,
        finishOnKey: "#",
        timeout: 15000,
      });

      if (choice === "1") {
        await voice.say(
          "A representative will call you back shortly. Thank you for calling AetherDesk."
        );
      } else {
        await voice.say("Thank you for calling AetherDesk. Have a great day!");
      }
    }

    // Cleanup
    await analytics.trackCallEnd({
      sessionRef,
      duration: voice.getCallDuration?.() || 0,
    });

    // Reset agent status after call
    if (agent) {
      setTimeout(() => {
        agentRegistry.updateAgentStatus(agent.id, "available");
      }, 5000);
    }
  } catch (error) {
    console.error(`[${sessionRef}] Call handling error:`, error);
    try {
      await voice.say("We apologize for the inconvenience. Please try again later.");
    } catch (e) {
      console.error(`[${sessionRef}] Error in fallback:`, e);
    }
  } finally {
    await voice.hangup();
  }
});

console.log("=".repeat(60));
console.log("  AetherDesk Voice Server (Powered by Fonoster)");
console.log("  Status: Starting...");
console.log("=".repeat(60));

// Start server
const port = parseInt(process.env.PORT || "50061");
voiceServer.listenOn(port, () => {
  console.log(`  Listening on port ${port}`);
  console.log(`  Environment: ${process.env.NODE_ENV || "development"}`);
  console.log(`  Redis: ${process.env.REDIS_HOST || "localhost"}:${process.env.REDIS_PORT || "6379"}`);
  console.log(`  API: ${process.env.API_HOST || "localhost"}:${process.env.API_PORT || "3000"}`);
  console.log("=".repeat(60));

  // Load agents and start
  agentRegistry.loadAgents();

  // Reload agents periodically
  setInterval(() => agentRegistry.loadAgents(), 60000);
});