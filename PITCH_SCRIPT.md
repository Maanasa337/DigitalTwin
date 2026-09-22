# TwinVoice: Pitch Script

**Length:** about 12 minutes (3 min story + 8 min live demo + 1 min close). There's a short version at the end.
**Setup:** app running, browser open at http://localhost:8088, logged in as `marcus` / `twinvoice`.

How to read this script:
- **SAY** is what you say out loud.
- **CLICK** is what you do on screen.
- **BEHIND THE SCENES** is how it works and where the data comes from. Use it when someone asks "how?"

---

## Part 1: The hook (1 minute)

**SAY:**
> "Picture a factory in Pune. Two production lines, ten machines: CNC mills, compressors, conveyors, a hydraulic press and injection moulders. It's Monday, 6 AM, and the morning shift is starting.
>
> Somewhere in that plant, a spindle bearing on CNC Mill 01 has started to crack. Nobody can hear it yet. Nobody can see it. In about seven hours that machine will stop, the whole line waits, and the plant loses a shift of production.
>
> Today, most plants find out when the machine breaks. Maintenance is either *too late*, after the breakdown, or *too early*, replacing parts that still had months of life left.
>
> We built **TwinVoice** so the plant finds out *hours before*: which machine, why, what to do about it, and when the best time to fix it is. And you can simply **ask it** in English, Hindi or Hinglish."

---

## Part 2: What TwinVoice is (1 minute)

**SAY:**
> "TwinVoice is a **digital twin** of the plant: a live virtual copy of every machine, updated every second from its sensors.
>
> On top of that twin we do five things:
> 1. **Watch.** Live health of every machine, with alarms.
> 2. **Predict.** How much life is left before a failure.
> 3. **Explain.** *Why* the AI thinks so, in plain words.
> 4. **Act.** Automatically raise a work order and plan the cheapest, safest time to fix it.
> 5. **Talk.** Every question and command also works through a voice-style assistant.
>
> It's 100% open source and runs on a single laptop. No cloud bill, and no data leaves the factory."

---

## Part 3: Where the data comes from (1 minute)

Draw or show this on a slide:

```
 MACHINES (sensors)                       TWINVOICE PLATFORM                           PEOPLE
 ─────────────────                        ──────────────────                           ──────
 10 machines, 5 types      MQTT       ┌─► Ingest ──► Time-series DB (every reading)
 vibration, temperature,  ─────────►  │           ├► Alarm engine ──► Alarms page
 current, pressure, power (Sparkplug B)│           └► WebSocket ────► Live dashboards      Technician
                                       │                                                   Manager
 Also speaks OPC UA and                ├─► Digital twin store (Eclipse Ditto) ─► Twin page  Engineer
 Modbus TCP, the same                  │
 protocols real PLCs use               └─► Background worker (every 30 s / 5 min / hourly)
                                              ├ AI prediction ──► Health + RUL
 Public research datasets                     ├ Explanation   ──► "Why?"
 (NASA, UCI) can be replayed                  ├ Work orders + optimiser ──► Maintenance plan
 as live machines                             ├ KPI rollups   ──► Production + Energy
                                              └ Reports       ──► PDF / HTML
```

**SAY:**
> "Where does the data come from? In this demo, from a **physics-based simulator** of the plant. It isn't random numbers: each machine wears out using real engineering equations. Bearing cracks grow by **Paris' law**, cutting tools wear by **Taylor's tool-life equation**, overheating follows **Arrhenius**, motors lose efficiency over time. So when a bearing fails in our simulator, the vibration rises the way a real bearing's does.
>
> The simulator talks to the platform in exactly the languages real factory equipment uses: **MQTT Sparkplug B**, **OPC UA** and **Modbus TCP**. To go live in a real plant, you swap the simulator for the plant's PLCs or an edge gateway. The platform doesn't change.
>
> We can also replay three public research datasets as if they were live machines: **NASA C-MAPSS** (jet engine degradation), **UCI AI4I 2020** (a milling-machine failure dataset) and **UCI MetroPT-3** (a real metro-train air compressor)."

**BEHIND THE SCENES (for Q&A):**

| Data | Source | Stored in |
|---|---|---|
| Sensor readings (every second) | Simulator → MQTT broker (Mosquitto) → Ingest service | TimescaleDB `telemetry` table, plus 1-minute and 1-hour rollups |
| Live machine state | Ingest → Eclipse Ditto | Ditto (MongoDB behind it) |
| Plant / line / machine / sensor registry | `fleet.yaml` via the seed script | PostgreSQL |
| Predictions (health, RUL) | Background worker, every 30 s | `predictions` table |
| Alarms | Alarm engine checks every reading against thresholds | `alarms` table |
| Work orders and schedules | Worker (every 5 min) + optimiser | `work_orders`, `schedules` |
| OEE and energy KPIs | Worker, hourly and at each shift change (06:00, 14:00, 22:00 IST) | `kpi_values` |
| Users and roles | Keycloak | Keycloak |
| Every action anyone takes | Audit logger | `audit_log` |

---

## Part 4: Live demo, "A day at Pune Plant" (8 minutes)

> **Before you start:** open the Simulation page and start the `demo_day` scenario (Scene 1). It plays an 8-hour shift at 60× speed, so one real minute equals one plant hour. Everything below happens live, on its own.

The `demo_day` scenario, so you know what's coming:

| Plant time | Real time | What happens |
|---|---|---|
| 0:30 | ~30 s | Cutting tool on **cnc-02** starts wearing fast |
| 1:00 | ~1 min | **compressor-01** starts overheating |
| 2:00 | ~2 min | A speed sensor on **conveyor-01** drops out (a faulty *sensor*, not a faulty machine) |
| 3:00 | ~3 min | An operator pushes **press-01** to 95% load |
| 4:00 | ~4 min | Heater band on **moulder-01** starts degrading |
| 4:30 | ~4.5 min | cnc-02's tool gets replaced, so its health recovers |

---

### Scene 1: The simulator, "our virtual factory" (Simulation page, engineers and admins only)

**CLICK:** Side menu → **Simulation** → pick scenario **demo_day** → **Start** → confirm.

**SAY:**
> "This is our control room for the virtual factory. I've just started an 8-hour production day at 60× speed. Watch this table: **damage per component** for every machine, and the **true remaining life**. That's the ground truth we use to grade our own AI.
>
> I can also break things on purpose."

**CLICK:** **Inject fault** card → Asset `cnc-01` → Failure mode `bearing_wear` → Onset *Gradual* → Severity 0.7 → **Inject**.

> "I've just planted a bearing crack in CNC Mill 01. Let's see if the platform catches it."

**Also point at:** the **Time scale** slider (speed the plant up or down), the **Live log**, the **Reset** button per machine, and **Export dataset**, which generates a labelled training dataset (CSV) from any scenario.

**BEHIND THE SCENES:** The simulator (Python + SimPy) models each machine's components. Every tick it adds wear using the physics equations, turns wear into sensor values (vibration, temperature, current…) with realistic noise, and publishes them over MQTT. It also serves the same values on OPC UA (port 4840) and Modbus (port 5020), so you can connect a real SCADA tool like UaExpert to it.

---

### Scene 2: Fleet overview, "the morning glance" (Fleet page, `/`)

**CLICK:** Side menu → **Fleet**.

**SAY:**
> "This is what the plant manager sees at 6 AM. One card per machine: a **health ring** from 0 to 100, **remaining useful life** with a range, live power draw, and open alarms. Green is fine, amber means watch it, red means act.
>
> See the **Live** dot at the top? That means these numbers are streaming in, not refreshed every few minutes."

**BEHIND THE SCENES:** Readings arrive by MQTT → the ingest service saves them in TimescaleDB and pushes them to the browser over a WebSocket. Every 30 seconds the background worker recalculates health and RUL for all 10 machines and pushes those too.

---

### Scene 3: Machine detail, "zoom into one machine" (`/machines/cnc-02` or `cnc-01`)

**CLICK:** Click the **cnc-02** card (or compressor-01).

**SAY:**
> "Every sensor on this machine, live, with a small trend line. Spindle vibration, temperature, load, tool wear, motor current. Each tile shows its **warning** and **alarm** limits, and a small dot for **data quality**: is the sensor itself trustworthy?
>
> Up here are health and RUL. RUL is never a single number. It's a **range**: '96 cycles, somewhere between 67 and 125.' We never pretend to be more certain than we are."

---

### Scene 4: Alarms, "the plant shouts" (Alarms page)

**CLICK:** Side menu → **Alarms**.

**SAY:**
> "When a value crosses its limit, an alarm opens here: compressor temperature, tool wear, and so on. Counters show how many are critical, warning, or info.
>
> The technician can **acknowledge** an alarm ('I'm on it') or **shelve** it ('known issue, hide for now'), one at a time or in bulk.
>
> The engine is smart about noise. It uses **hysteresis and deadbands**, so a value wobbling right on the limit doesn't open and close fifty alarms a minute. Alarm fatigue is a real problem in plants, and we designed against it."

---

### Scene 5: Telemetry Explorer, "look back in time" (Explorer page)

**CLICK:** Side menu → **Explorer** → choose `cnc-01`, a couple of sensors, time range **1h**/**24h**/**7d**.

**SAY:**
> "Any sensor, any machine, any time range. Last hour, last week, last month. Charts stay fast even over millions of readings because the database keeps ready-made **1-minute and 1-hour averages**. We already hold over a million readings in this demo."

---

### Scene 6: The digital twin itself (Twin page)

**CLICK:** Side menu → **Twin** → expand **Pune Plant → Machining Line → CNC Mill 01**.

**SAY:**
> "This is the twin: the plant's family tree, from plant to line to machine.
>
> Each machine is described in the **Asset Administration Shell** format. That's the official Industry 4.0 standard from Germany's Platform Industrie 4.0, so any other AAS-compliant system can read our twins. You get:
> - **Nameplate**: manufacturer, model, serial number, install date
> - **Technical data**: rated power, ideal cycle time
> - **Operational data**: live
> - **Maintenance history**
> - **Predictive maintenance**: live health and RUL"

**CLICK:** the tabs **Components & sensors** → **Live twin** → **Raw AAS JSON**.

> "**Components & sensors** lists every part and every sensor with its limits. **Live twin** is the machine's current state from our twin store. Watch the revision number go up as data arrives."

**Also point at** (top-right buttons):
- **Export** as **AASX** (the standard package) or **AAS JSON**. The API also exports to **DTDL** (Microsoft Azure Digital Twins) and **NGSI-LD** (FIWARE, the EU smart-city standard).
- **Import AASX**: bring in a machine from a supplier's file.
- **New asset**, **Clone** (add a second identical machine in one click), **Retire**.
- **Fidelity badge** (1 Status → 2 Telemetry → 3 Physics → 4 Predictive): how "smart" each twin is.
- **Send command**: set load, set speed, or reset maintenance, written back to the machine. This is the most dangerous action, so it's tier **T3**: the server must allow it *and* the user must type a **PIN**. (Marcus's PIN is `246810`. `TV_ALLOW_T3=true` must be set in `.env`.)

**BEHIND THE SCENES:** The registry lives in PostgreSQL. Live state lives in **Eclipse Ditto**, an open-source twin server from the Eclipse Foundation. Commands travel as MQTT messages to the machine, and the platform waits for the machine's acknowledgement before saying "done".

---

### Scene 7: Prediction and the model registry, "the brain" (Models page, engineers only)

**CLICK:** Side menu → **Models** → open the production model.

**SAY:**
> "Here's where the AI models live, like an app store for our predictions. Every model has a version, its accuracy metrics, and a **stage**: *candidate → staging → production*. An engineer promotes a model only after it proves itself. Nothing goes live by accident.
>
> Our AI pipeline has three layers:
> 1. **Anomaly detection** (Isolation Forest): 'something is unusual'.
> 2. **Failure-mode classifier** (LightGBM, with calibrated probabilities): 'it looks like *bearing wear*, 72% likely'.
> 3. **Remaining-life regressor** with **conformal prediction**: 'about 96 cycles, and we're 90% sure it's between 67 and 125.'
>
> Features come from sliding windows over the sensor data: averages, RMS, kurtosis, and frequency-domain features from an FFT, the same signals a vibration analyst would look at."

---

### Scene 8: Explainable AI, "why should I trust you?" (explanation card, Quality page)

> ⚠️ Read the presenter notes at the bottom before showing this scene live.

**SAY:**
> "A technician won't trust a black box. If the AI says 'replace the bearing', he wants to know *why*. So every prediction comes with an **explanation card**:
> - **In plain words**: 'Spindle vibration has been rising for 3 hours and kurtosis is spiking. This pattern matches bearing wear.'
> - A **waterfall chart** (SHAP) showing which sensor pushed the risk up, and by how much.
> - A **second opinion** from a completely different, see-through model (EBM). If the two disagree, we *say so* on screen.
> - A **reason card** from our maintenance knowledge base: likely cause, what to check, what to do. In **English and Hindi**.
> - **What would fix it** (counterfactual): 'If you reduce load from 85% to 70%, you gain about 280 hours of life.' We only suggest things the operator can actually change: load, speed, and so on.
> - A **confidence label** with reasons: low if a sensor looks faulty or the data looks unlike anything the model was trained on (drift).
>
> And the technician can **push back**: 'I disagree, I think the temperature sensor is faulty.' That flags the sensor, and future predictions treat it with lower confidence.
>
> If we use a language model to make the text friendlier, its output is **audited against the numbers**. If it changes a number or invents a repair, we throw it away and show our fixed template text instead. No hallucinations reach the shop floor."

**CLICK (optional):** `/explain/quality` shows how good the explanations are, measured with research metrics (deletion/insertion AUC, faithfulness, sparsity).

---

### Scene 9: Maintenance, "from warning to work order" (Maintenance page, Schedule page)

**CLICK:** Side menu → **Maintenance**.

**SAY:**
> "When a failure becomes likely, TwinVoice **raises the work order by itself**: which machine, which fault, what task. Nobody has to notice first.
>
> Open one and you see the **risk trade-off**: 'If you fix it now you lose 30 minutes of production. If you wait 24 hours, the chance of breakdown rises to X%.' The explanation from the previous screen is right here too, so the technician knows *why* the job exists."

**CLICK:** **Schedule** (`/maintenance/schedule`) → **Optimise**.

**SAY:**
> "Now the clever part. Press *Optimise*, and a solver (Google OR-Tools CP-SAT, the same kind of engine airlines use for crew rostering) builds the best maintenance plan for the week. It respects:
> - who is on shift, and who has the right **skills**
> - one job per technician, one job per line at a time
> - the **electricity tariff**, so it prefers cheaper off-peak hours
> - and the **risk** of each machine failing before its slot
>
> The Gantt chart colours each job by risk. A planner can still **drag** a job by hand, and the system re-checks it for conflicts and marks it as a manual change.
>
> When the technician **closes** the job, the platform sends a *maintenance reset* to the machine, and the machine's health goes back up. The plan exports to CSV, JSON, or **B2MML**, the ERP standard (ISA-95) for systems like SAP."

**BEHIND THE SCENES:** The worker checks every 5 minutes for machines whose *calibrated* failure probability is high, and raises at most one open order per machine per fault. Risk over time uses a Weibull curve fitted to the RUL estimate and its range.

---

### Scene 10: Production analytics, "is the plant making money?" (Production page)

**CLICK:** Side menu → **Production**.

**SAY:**
> "This is the plant manager's view. **OEE** (Overall Equipment Effectiveness) is the world standard for how productive a plant is. It's three numbers multiplied:
> - **Availability**: was the machine running when it should have been?
> - **Performance**: was it running at full speed?
> - **Quality**: were the parts good?
>
> Plus **MTBF** (average time between failures), **MTTR** (average time to repair), a **downtime Pareto** (the top reasons we lost time), and **plan vs actual** for each shift: Morning, Afternoon, Night.
>
> Hover on any number to see the **exact formula and inputs** behind it, per ISO 22400. No mystery numbers."

---

### Scene 11: Energy, "the hidden cost" (Energy page)

**CLICK:** Side menu → **Energy**.

**SAY:**
> "Energy is often a plant's second-biggest cost. Here: kWh per machine, **cost** using the actual tariff slots, **CO₂ emissions**, and **energy per part made**.
>
> We learn a **baseline** for each machine (how much energy it *should* use for the parts it makes). When it uses more than 3 standard deviations above that, we flag an **energy anomaly**. That catches problems like a motor slowly losing efficiency, where output looks normal but the power bill quietly grows. The method follows ISO 50001."

---

### Scene 12: The assistant, "just ask" (Assistant page or the round chat button)

**CLICK:** Click the round **chat button** (bottom-right, on every page) or go to **Assistant**.

**TYPE, one line at a time:**

| You type | It answers (real response from the running system) |
|---|---|
| `how is cnc one` | "CNC Mill 01 is at 98 percent health with 96 cycles of life left, between 67 and 125…" |
| `what if we reduce load to 70 percent` | "With load at 70 percent, remaining life goes from 902 to 1186 hours. This is a simulation, nothing has changed." |
| `what is the oee of line one` | "OEE for Machining Line … is 98.8 percent." |
| `cnc one ka status batao` | Same status answer: Hinglish is understood |
| `schedule bearing replacement for cnc one on friday morning` | "Creating work order: bearing replacement on CNC Mill 01, Friday 25 September 08:00. Say confirm or cancel." Then type **confirm** |

**SAY:**
> "Operators on the shop floor have gloves on and noise around them. They shouldn't need to click through five screens. They just ask.
>
> It understands **English, Hindi and Hinglish**. It remembers context: say 'how is CNC one', then 'what if we reduce load', and it knows you still mean CNC one.
>
> The *what-if* isn't a guess. It runs **500 simulations** of the machine's future from its current wear state, in under a second.
>
> Most importantly, **safety tiers**:
> - **T0 Query** ('how is…'): answers immediately.
> - **T1 Simulate** ('what if…'): answers immediately, clearly marked *hypothetical*.
> - **T2 Schedule** (create a work order, acknowledge an alarm, generate a report): it **reads everything back** ('Creating work order: bearing replacement on CNC Mill 01, Friday 9 AM, assigned to Ravi') and waits for you to say **confirm**. That catches the classic mistake: the right action on the wrong machine.
> - **T3 Actuate** (touching the real machine): confirmation **plus a PIN**, and it's switched off unless the plant enables it.
>
> Every answer shows its **source**: which model, which prediction, what time. It only says what the data says."

---

### Scene 13: Reports, "for the boss's inbox" (Reports page)

**CLICK:** Side menu → **Reports** → **Generate report** → type **Machine health** → machine `cnc-01` → **PDF**.

**SAY:**
> "Five report types: **Machine health**, **Weekly maintenance**, **Energy**, **Model benchmark** and **Incident**. Generate one now, or **schedule** it ('every Monday 6 AM'). Every report gets archived.
>
> The executive summary at the top is **checked against the actual figures** before it's printed, the same audit idea as the explanations."

---

### Scene 14: Built for real people (anywhere in the app)

**CLICK:** top bar → **language switch** (English ↔ हिंदी) → **dark mode** → user menu.

**SAY:**
> "The whole interface works in **Hindi**, has a **dark mode** for control rooms, and works on a **phone**: the side menu becomes a bottom bar.
>
> There are four roles, each seeing what they need: **Technician** (Ravi), **Manager** (Priya), **Engineer** (Marcus), **Admin**. Login is handled by Keycloak, an enterprise-grade identity server. And **every action is written to an audit log**: who did what, and when."

---

## Part 5: Close (1 minute)

**SAY:**
> "Let's go back to our Monday morning.
>
> Without TwinVoice: CNC Mill 01 breaks at 1 PM, the line stops, the team scrambles.
>
> With TwinVoice: at 7 AM the vibration trend flagged it. The AI said *bearing wear* and showed *why*. A work order raised itself. The optimiser put the repair in the afternoon's off-peak slot with the right technician. The supervisor confirmed it by just *asking*. And the machine never broke down.
>
> **Watch, predict, explain, act, talk**, all on open standards (AAS, OPC UA, MQTT, ISO 22400, ISO 50001), fully open source, and running on one laptop.
>
> Thank you."

---

## Short version (2 minutes, no demo)

> "Factories lose whole shifts to machines that break without warning. TwinVoice is a live digital twin of the plant. Sensor data streams in over the same protocols real machines use: MQTT, OPC UA and Modbus. Physics-based models and machine learning predict *how much life each machine has left*, with an honest range, and *explain why* in plain English or Hindi. When a failure is likely, it raises a work order automatically and an optimiser picks the cheapest, safest time to fix it, based on technician skills, shifts and electricity tariffs. Managers get OEE and energy dashboards with ISO-standard KPIs and automatic reports. And anyone can just *ask* the assistant, with safety read-backs and PINs before anything touches a real machine. It's open source, on open standards, and runs on one laptop."

---

## Likely questions, and simple answers

**"Is this real data?"**
> "The demo uses a physics-based simulator, so we can create failures on demand and know the true answer to grade our AI. The platform reads real industrial protocols, so connecting real machines means pointing it at the plant's PLCs or gateway. We also replay public datasets from NASA and UCI."

**"How accurate is it?"**
> "Because the simulator knows the *true* remaining life, we can measure our error exactly. RUL is always a range with 90% coverage (conformal prediction), not a single number that pretends to be precise."

**"What if a sensor is broken, not the machine?"**
> "That's exactly what the conveyor-01 event in the demo shows. Sensor faults (stuck, drift, offset, dropout) lower the confidence of the prediction, and a technician can flag a suspect sensor from the explanation card."

**"Can the AI damage a machine?"**
> "No. Anything that writes to a machine is tier T3: disabled by default, needs a read-back confirmation *and* a personal PIN, and is audit-logged."

**"Does it need the internet or a GPU?"**
> "No. Everything runs locally on one laptop with Docker. The optional language model is also local."

**"What does it cost?"**
> "The software is Apache-2.0 open source, and every dependency is OSI-licensed. The cost is the hardware and the integration."

**"What's next?"**
> "On-device speech recognition, failure-mode classifiers alongside the RUL models, and a user study with technicians."

---

## ⚠️ Presenter notes: honest status of the live system (read before you demo)

I ran the app on 21 Sep 2026 and checked every screen's data. Most things work live. These don't yet, so don't promise them on stage:

1. **Every machine is scored by the trained models.** Edge-bound machines (cnc-01, compressor-01, conveyor-01, press-01, moulder-01) show the **Edge** tag. The other five are scored every 30 s by the server with the same bundle for their asset type: LightGBM RUL with a conformal interval, IsolationForest health. On a calm plant, health still reads 94 to 100, so **start a fault scenario first** or the fleet looks boringly green. RUL confidence is mostly "low" because the intervals are wide (72 h of simulator data, 1–3 machines per type). Present RUL as indicative.
2. **Explanations and reason cards appear on every machine,** edge and server alike. The failure mode on the card is inferred from which sensors drive the prediction, matched against each mode's signature. The RUL models don't classify modes themselves, so say "the evidence points to…", not "the model classified…". A healthy machine shows the "No abnormal signature" card. The Explanation quality page (`/explain/quality`) shows importance, partial dependence and faithfulness metrics. Narration audits appear only when an LLM is configured (`TV_LLM_ENDPOINT`).
3. **Voice works in Chrome and Edge.** The mic button in the assistant uses the browser's speech recognition, and spoken questions are answered aloud. That recognition runs in the browser vendor's cloud, not on-device. Firefox has no mic button, only typing. Rehearse on the presenting laptop and allow microphone access beforehand.
4. **Always name the machine in assistant commands.** `list alarms` with no machine answers "That machine is not in the registry". `schedule … for it …` treats "it" as a machine name and asks "Injection Moulder 01 or 02?". Type `cnc one` instead of `it`. (Plain follow-ups like `what if we reduce load to 70 percent` do use context correctly.) Also, "Friday morning" is stored as 08:00 **UTC** (13:30 in Pune), so avoid showing the saved time on screen.
5. **Writing to a machine (T3)** needs `TV_ALLOW_T3=true` in `.env`, then `docker compose up -d`.
6. **Newly built, safe to show:** 3D plant layout (`/twin/3d`) and a 3D panel on each machine page; benchmark runner (`/models/benchmarks`: FD001 RMSE 12.2 / NASA score 232, AI4I AUC 0.97, all PRD targets met except MetroPT-3 lead time, which is 0 h, so don't claim early warning on MetroPT); ONNX download on the model page; edge runner (**Edge** tag, ~5 ms inference); Grafana dashboards (`/dashboards`, "Open dashboard" on a machine). Simulator-trained RUL models are weak (72 h of data, 1–3 machines per type), so present edge RUL as indicative.

---

## How to run it

```bash
# Start Docker Desktop first, then from the project folder:
docker compose up -d                      # first time: docker compose up -d --build
docker compose exec api python -m app.seed   # only once, on a fresh database
```

| Open | What |
|---|---|
| http://localhost:8088 | The app. Log in as `marcus` / `twinvoice` (engineer: sees every page) |
| http://localhost:8000/docs | The API, every endpoint |
| http://localhost:8000/api/v1/health | Health of every service |
| http://localhost:8081 | Keycloak (admin / admin) |

Demo users (password `twinvoice` for all): `ravi` technician · `priya` manager · `marcus` engineer (PIN 246810) · `admin` admin (PIN 135790).
