focused on evolving BotCheck into an **inbound route + full inbound agent harness** that can be developed in-platform and then deployed as a standalone LiveKit agent.

## Overall view

You already have the right base pieces:

* a **control plane API** with scenarios, runs, schedules, packs, providers, SIP-related routes, auth, and audit endpoints, which is the right place for inbound agent lifecycle management. 
* a **LiveKit-based agent runtime** that already loads scenario context from room/job metadata, fetches scenario definitions from the API, runs turn-by-turn logic, and reports results back. That is exactly the kind of runtime you want to extend into inbound agent execution, not rebuild from scratch. 
* a **documented architecture** that already models inbound and outbound voice, LiveKit rooms, the SIP bridge, tenant isolation, artifacts, and judging. 
* a **web app and visual-builder direction**, which gives you the right surface for a guided “Add inbound agent” flow.  

So the question is not “can BotCheck do this?”
It’s really: **how do you reshape the product so inbound agent harnessing becomes a first-class path rather than a side feature?**

## What BotCheck is missing for this next step

Right now the repo is strongest at **testing a bot**. The next stage requires BotCheck to also be strong at **hosting and shaping a bot runtime**.

That means adding four first-class concepts:

1. **Inbound Route**
2. **Inbound Agent**
3. **Knowledge / Skills / MCP Bindings**
4. **Deployment Profile**

Those need to sit alongside scenarios, not be buried inside them.

## The product shift I’d make

Today the core object looks like:

* scenario
* run
* judge report

For inbound harnessing, the core object model should become:

* **Scenario** = conversation behavior and testable logic
* **Inbound Agent** = scenario + runtime persona + tools/knowledge + handoff policy
* **Inbound Route** = DID/SIP route → room/agent dispatch behavior
* **Deployment Profile** = shared harness runtime vs dedicated LiveKit deployment

That is the cleanest way to avoid turning “scenario” into an overloaded mess.

## Sharp review by area

### 1) Product positioning

Your current README strongly sells testing, telephony realism, scenario logic, judging, and compliance. That is good. 

But for the inbound direction, the product story should become:

**“Design, test, route, and deploy inbound voice agents on LiveKit.”**

Then testing becomes one pillar, not the entire headline.

I’d reposition the value props like this:

* Build inbound voice agents with guided setup
* Attach knowledge, skills, and MCP tools
* Route real SIP/WebRTC traffic into those agents
* Test them under realistic scenarios
* Promote them to standalone LiveKit deployments

That better reflects where the architecture wants to go. The current docs already show enough backend maturity to support that repositioning.  

### 2) Architecture

Your architecture is already close to supporting this. The key reason is the agent entrypoint consumes metadata and fetches runtime context from the API. That is exactly the pattern you want for inbound routing. 

Instead of treating room metadata as only `run_id + scenario_id`, treat it as a richer runtime envelope, for example:

```json
{
  "mode": "inbound_agent",
  "tenant_id": "acme",
  "agent_id": "claims-intake-01",
  "scenario_id": "claims-intake-v3",
  "route_id": "sip-mainline-uk",
  "deployment_profile": "shared-runtime",
  "trace": { "...": "..." }
}
```

That lets one shared LiveKit worker runtime power many inbound agents during development.

Architecturally, I would add these components:

* **Inbound Route Service**
* **Inbound Agent Registry**
* **Knowledge/Tool Binding Service**
* **LiveKit Dispatch Manager**
* **Agent Deployment Exporter**

These can still live inside the API service initially, but they should be explicit concepts in your domain model.

### 3) API / control plane

Your FastAPI main app already exposes routers for scenarios, runs, schedules, packs, providers, destinations, SIP pools, tenants, audit, and admin. That means the API is already set up in a way that can absorb new bounded areas without feeling out of place. 

I would add these route groups:

* `/inbound-agents`
* `/inbound-routes`
* `/knowledge-packs`
* `/skills`
* `/mcp-bindings`
* `/deployments`

Minimal example resource model:

#### inbound_agents

* id
* tenant_id
* name
* description
* scenario_id
* greeting
* voice config
* handoff policy
* knowledge pack refs
* skill refs
* mcp binding refs
* runtime mode
* enabled
* version

#### inbound_routes

* id
* tenant_id
* name
* channel (`sip`, `webrtc`, `http`)
* did / trunk / endpoint matcher
* livekit dispatch settings
* target agent id
* business hours policy
* failover target
* enabled

#### deployments

* id
* tenant_id
* agent_id
* mode (`shared_runtime`, `dedicated_runtime`)
* livekit agent name
* environment (`dev`, `staging`, `prod`)
* status
* artifact/version metadata

This would keep the platform understandable as it grows.

### 4) Runtime / agent design

This is where your repo is strongest technically.

The current `services/agent/src/agent.py` already has the bones of a generic runtime:

* fetch scenario
* fetch provider runtime context
* derive runtime overlays
* run scenario
* report turns/finalization
* use room metadata
* keep circuit breakers/provider fallbacks in the runtime layer. 

That is very good.

What I would change is to formally split runtime into two modes:

#### Mode A: Harness Caller

What you already have:

* synthetic caller
* turn execution
* test transcripts
* judge callbacks

#### Mode B: Inbound Agent

New behavior:

* answer inbound call
* act as the called party
* use knowledge/skills/MCP
* optionally emit transcript/judge artifacts when run in “test mode”

Do not build a separate codebase for this.
Build a shared runtime kernel with different orchestrators:

* `HarnessScenarioExecutor`
* `InboundAgentExecutor`

The current structure suggests you are already moving toward that type of composition. 

### 5) Scenario model

Right now scenarios are central, which is correct. The change I’d make is to separate:

* **test scenario**
* **runtime behavior policy**

You do not want inbound agent production behavior to be defined entirely by the same object used for adversarial/jailbreak test turns.

So I’d define:

#### RuntimeScenario

* greeting
* goals
* business constraints
* response style
* tool-use policy
* escalation behavior
* knowledge refs

#### TestScenario

* turns
* assertions
* expected routing
* expected guardrail outcomes
* judge dimensions

Then an inbound agent can point to one runtime scenario and many test scenarios.

That separation will make the platform much cleaner long-term.

### 6) Inbound routing model

This is the biggest functional addition.

You want the harness to let a user create an inbound route such as:

* SIP DID → agent
* SIP DID → router agent → downstream agent
* WebRTC endpoint → agent
* HTTP playground → same agent

I would support these route types first:

#### Direct Route

One number / endpoint directly maps to one inbound agent.

Best for v1.

#### Router Route

One number goes to a lightweight front-door classifier that decides:

* which scenario/agent
* or whether to hand off to human

Best for v2.

#### Conditional Route

Route based on:

* time of day
* tenant/customer
* trunk
* SIP header/custom metadata
* DTMF branch

Useful soon after v1.

From your architecture docs, the LiveKit/SIP bridge and dispatch concepts are already central enough that this fits naturally. 

### 7) Guided “Add Inbound Agent” UX

This should become one of the best parts of the product.

Your README already mentions a visual flow builder and YAML sync, so the right move is to keep YAML as an advanced mode, not the primary setup path. 

I’d make the wizard:

#### Step 1: Agent basics

* agent name
* purpose
* greeting
* default voice
* default language
* test/prod environment

#### Step 2: Route setup

* choose SIP / WebRTC / HTTP
* assign DID/trunk or endpoint
* set route behavior
* choose business-hours handling
* choose fallback target

#### Step 3: Runtime behavior

* role
* boundaries
* goals
* prohibited actions
* escalation thresholds

#### Step 4: Knowledge

* upload docs
* link FAQs
* select retrieval method
* define “must not hallucinate” handling

#### Step 5: Skills

* lookup customer
* create ticket
* schedule callback
* transfer call
* verify identity
* collect DTMF
* send email/SMS

#### Step 6: MCP/tools

* connect MCP server or tool
* choose approved tools
* define confirmation rules
* define timeout/failure behavior

#### Step 7: Testing

* run sample inbound call
* run transcript simulation
* run jailbreak pack
* run routing check
* run latency check

#### Step 8: Deploy

* shared runtime
* dedicated runtime
* generate LiveKit deployment
* publish version

That flow would make the platform feel far more complete.

### 8) Knowledge / skills / MCP

This is currently the biggest conceptual gap between “test harness” and “real inbound agent platform.”

You specifically want guided adding of knowledge, skills, and MCP. That means these cannot just be config blobs hidden in scenario YAML. They need UI-backed domain objects.

I’d structure them like this:

#### Knowledge Pack

* title
* source type
* chunking/indexing settings
* retrieval mode
* freshness rules
* confidence/fallback behavior

#### Skill

* skill type
* input schema
* output schema
* approval policy
* retry behavior

#### MCP Binding

* server name
* transport
* auth
* allowed tools
* environment
* timeout budget
* audit/redaction rules

Then the inbound agent references these by ID.

That gives you reuse, governance, and much cleaner deployment.

### 9) Deployment model

Your deployment strategy currently documents a practical per-customer deployment on a droplet, with Cloudflare, Tailscale, self-hosted LiveKit/SIP options, and a path toward shared multi-tenancy later. That is a reasonable operational path. 

For the inbound harness feature, I’d support two deployment modes:

#### Shared Runtime

* one agent worker runtime
* agent selected by metadata/dispatch
* fastest iteration
* ideal for dev and staging

#### Dedicated Runtime

* one packaged/deployed LiveKit agent per inbound agent
* cleaner isolation
* better for customer production rollouts

The harness should let users develop in shared mode and promote to dedicated mode.

That promotion flow is the real product advantage:
**design once, test once, promote to standalone runtime without rewriting code.**

### 10) Testing strategy

Your CI is already extensive, but the new inbound feature needs a new test matrix. 

I would add test lanes specifically for inbound agents:

#### Contract tests

* inbound route config validation
* agent binding validation
* deployment export validation

#### Runtime tests

* metadata → correct agent resolution
* route → room dispatch behavior
* knowledge/skill attachment loading
* fallback behavior when tool unavailable

#### Voice tests

* inbound SIP answer path
* barge-in
* silence timeout
* DTMF capture
* transfer/handoff

#### Promotion tests

* shared runtime behavior equals dedicated runtime behavior for same scenario version

That last one matters a lot. It protects the “develop in harness, deploy standalone” promise.

## What I would change in the repo next

Here are the most important next implementation slices.

### Slice 1: introduce inbound domain objects

Add models, migrations, and API routes for:

* inbound agent
* inbound route
* deployment profile

Do this before UI work.

### Slice 2: enrich room/job metadata contract

Refactor the agent runtime so it can operate in:

* harness caller mode
* inbound agent mode

Keep one runtime kernel.

### Slice 3: build direct inbound routing first

Support:

* one route
* one inbound agent
* one shared runtime
* one test call path

No router agent yet.

### Slice 4: build guided knowledge/skills/MCP attachment

Even if the first version is simple, make these explicit product objects.

### Slice 5: add “deploy to LiveKit” promotion flow

Start by generating a deployment manifest/config package if full automated deployment is too much initially.

## Concrete risks to avoid

The biggest risk is **letting scenarios absorb everything**:

* routing
* deployment
* tools
* knowledge
* runtime policy
* test assertions

That will become hard to reason about quickly.

Second biggest risk is **building a second runtime** for inbound agents instead of extending the current agent kernel. Your current runtime is already good enough to become the core. 

Third biggest risk is **keeping the UI too test-centric**. If you want the platform to become an inbound agent harness, the UI needs to speak in terms of agents and routes, not just scenarios and runs.

## My recommendation in one line

Turn BotCheck from:

**“a platform that tests voicebots”**

into:

**“a platform that builds, routes, tests, and deploys inbound voice agents on LiveKit.”**

## Suggested target architecture for this feature

The clean target is:

* **API/control plane**

  * scenarios
  * inbound agents
  * inbound routes
  * knowledge packs
  * skills
  * MCP bindings
  * deployments

* **Runtime**

  * shared execution kernel
  * harness caller executor
  * inbound agent executor

* **LiveKit integration**

  * dispatch/route manager
  * metadata contract
  * deploy/export flow

* **UI**

  * add inbound agent wizard
  * route builder
  * knowledge/skills/MCP guided setup
  * test and promote flow

That is very achievable from where the repo already is.

If you want, I can turn this into a **phased build plan / developer handoff spec** with:

* proposed data model
* API endpoints
* runtime refactor plan
* UI wizard flow
* test plan
* deployment promotion design.
