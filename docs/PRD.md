# Product Requirements Document (PRD)

## Voice-Driven Industrial Digital Twin and Predictive Maintenance Platform using Explainable AI

| Field | Value |
|---|---|
| Document version | 1.0 |
| Date | 17 September 2026 |
| Status | Draft for review |
| Working codename | **TwinVoice** (rename freely) |
| Cost constraint | **Zero spend.** Every runtime dependency, dataset, model weight and tool listed here is open-source (OSI-approved) or free-to-use (CC / public domain / NASA open data) and self-hostable on a Windows 11 laptop. Anything with a licence catch is flagged in Section 12. |

---

## Table of Contents

1. Executive Summary
2. Problem Statement and Goals
3. Market Research: Existing Platforms and Their Limitations
4. Research Landscape and Gaps (Academic State of the Art)
5. How This Platform Overcomes the Gaps (Differentiators)
6. Users, Personas and Use Cases
7. System Architecture
8. Functional Requirements (Module by Module, every feature explained)
9. Non-Functional Requirements
10. Data Requirements and Datasets
11. Open-Source Technology Stack (verified, with licences)
12. Licence Warnings (things that look free but are not)
13. Evaluation Plan and Success Metrics
14. Research Paper Plan
15. Target Company Relevance Map
16. Roadmap and Milestones
17. Risks and Mitigations
18. Glossary
19. Appendix A: Voice Command Grammar
20. Appendix B: Explanation Templates
21. Appendix C: References

---

## 1. Executive Summary

TwinVoice is a research-grade, fully open-source Industry 4.0 platform that combines four capabilities that no existing commercial or open-source product ships together:

1. **An industrial digital twin** (ISO 23247 layered architecture, Asset Administration Shell descriptions, Eclipse Ditto twin store, browser-based 3D representation) fed by a physics-based, stochastic **sensor simulator** so the platform runs without any physical hardware.
2. **A predictive maintenance engine** producing failure probability, **Remaining Useful Life (RUL) with calibrated uncertainty intervals**, and an optimised maintenance schedule.
3. **An explainable AI layer** that shows per-prediction feature attributions (SHAP), glass-box models (Explainable Boosting Machines), counterfactuals ("what would have to change to gain 40 cycles?"), and conformal confidence scores, and then **converts them into plain-language and spoken explanations** whose faithfulness to the underlying numbers is automatically audited.
4. **VoiceNav**: a fully offline voice interface (Whisper speech-to-text, local LLM intent routing via Ollama, Kokoro/Piper text-to-speech) with a **risk-tiered read-back confirmation protocol** for any command that changes state, and voice-triggered report generation.

The market analysis in Section 3 shows that commercial platforms (Siemens Senseye, PTC ThingWorx, IBM Maximo, Augury, C3 AI, and others) either charge USD 50k to 1.8M per year, provide "explainability" only as unverified LLM prose, are cloud-only, or have been shut down (AWS Monitron, AWS Lookout for Equipment, Bosch IoT Suite, SAP PAI). Open-source stacks (Eclipse Ditto, BaSyx, FIWARE, ThingsBoard CE) have no analytics layer. The academic survey in Section 4 found **no published 2024–2026 work that combines digital twin + predictive maintenance + explainable AI + an evaluated voice modality**, and two independent papers explicitly list voice-compatible explainability as an open problem.

The expected outcome is a runnable platform, a reproducible benchmark on public datasets (NASA C-MAPSS, AI4I 2020, MetroPT-3), a user study, and at least two publishable papers.

---

## 2. Problem Statement and Goals

### 2.1 Problem

Manufacturing plants lose an estimated 5 to 20 percent of productive capacity to unplanned downtime. Predictive maintenance (PdM) products exist, but plant operators report three recurring problems, each documented in Section 3:

- **Black-box predictions.** Systems flag a machine but do not say why, so technicians either ignore alerts (under-reliance) or replace healthy parts (over-reliance). Augury's lack of "the why" is a documented churn driver, and PTC's own leadership acknowledges the "magic black box" perception.
- **Hands are busy, eyes are on the machine.** Shop-floor technicians wear gloves, carry tools and stand in noisy environments; dashboards on tablets are a poor fit. No mainstream digital twin platform offers voice interaction.
- **Cost and lock-in.** Commercial platforms are priced for enterprises, require proprietary sensors or hyperscaler clouds, and have a track record of being discontinued.

### 2.2 Goals

| ID | Goal | Measurable target |
|---|---|---|
| G1 | Run a complete digital twin + PdM + XAI + voice loop on a single laptop with zero paid dependencies | `docker compose up` brings up the whole platform; no API keys required |
| G2 | Match published RUL accuracy on the standard benchmark | C-MAPSS FD001 RMSE ≤ 13.0 and NASA score ≤ 300 (state of the art is ≈ 11.0 / 195) |
| G3 | Make every prediction explainable and its confidence calibrated | 100 % of predictions carry SHAP attributions and a 90 % conformal interval whose empirical coverage is 88 to 92 % |
| G4 | Make explanations spoken and faithful | LLM-narrated explanations agree with SHAP top-3 feature ranking ≥ 90 % of the time, zero hallucinated features |
| G5 | Voice control that is safe | Intent accuracy ≥ 92 % at 70 dB machine noise; zero unconfirmed state-changing actions executed |
| G6 | Research output | Two papers submitted (see Section 14) and a public GitHub repository with reproducible experiments |

### 2.3 Non-Goals (v1)

- Connecting to real PLCs in a live factory (the OPC UA / MQTT / Modbus interfaces are built and tested against simulated devices only).
- Replacing a full CMMS / ERP (the platform exports work orders; it does not manage procurement or inventory).
- Photorealistic 3D (NVIDIA Omniverse class). The 3D layer is a lightweight web twin for context and state, not a rendering showcase.
- Multi-tenant SaaS operation.

---

## 3. Market Research: Existing Platforms and Their Limitations

Research date: September 2026. Sources are listed in Appendix C. Legend: ✅ documented native capability, ⚠️ partial or marketing-only, ❌ not found or explicitly absent.

### 3.1 Capability matrix

| Platform | Pricing | Digital twin model | PdM / RUL | Explainability shown to operators | Voice / NL copilot | Energy | Edge / offline |
|---|---|---|---|---|---|---|---|
| Siemens Insights Hub + Senseye | Paid tiers, quote-only for Senseye | ✅ asset model, no 3D | ✅ anomaly "Attention Index", no formal RUL | ⚠️ GenAI prose, no SHAP or confidence | ⚠️ text copilot; voice only in SIMATIC eaSie (process industry) | ✅ Energy Manager | ⚠️ Senseye is cloud-only |
| GE Vernova Proficy / SmartSignal | Enterprise, quote-only | ✅ asset templates ("blueprints") | ✅ similarity models, time-to-action | ⚠️ residual charts, rule "apparent cause" | ❌ | ⚠️ | ✅ CSense on-prem |
| PTC ThingWorx + Vuforia | Subscription; ≈ USD 50–150k/yr base (third-party estimate) | ✅ Thing Model, AR | ⚠️ Analytics licensed per core | ❌ | ❌ | ❌ | ⚠️ Kepware edge |
| Microsoft Azure Digital Twins + IoT Operations | Pay-per-use | ✅ DTDL graph; 3D Scenes Studio still "preview" | ❌ bring your own ML | ❌ | ❌ | ❌ | ✅ AIO on Arc K8s |
| AWS IoT TwinMaker + Monitron + Lookout for Equipment | Pay-per-use | ✅ | ⚠️ **Monitron closed 2024, Lookout for Equipment shuts down 7 Oct 2026** | ❌ | ⚠️ Bedrock demo only | ❌ | ⚠️ Greengrass v1 EOL |
| Bosch Nexeed / Bosch IoT Suite | Enterprise | ⚠️ AAS registry | ✅ | ❌ | ❌ | ⚠️ | ⚠️ on-prem MES |
| ABB Ability Genix | Enterprise | ✅ + Omniverse 3D (2026) | ✅ | ⚠️ copilot "contextualises" data | ⚠️ GPT-4 chat, no voice | ✅ | ✅ Genix Edge |
| Schneider EcoStruxure / AVEVA | Enterprise | ✅ | ✅ AVEVA Predictive Analytics | ⚠️ citation transparency, not model XAI | ⚠️ chat | ✅ | ⚠️ |
| Rockwell FactoryTalk GuardianAI | Per-product | ✅ Emulate3D (design-time) | ✅ VFD signatures only | ⚠️ failure type, no attribution | ⚠️ PLC-code copilot | ✅ | ✅ |
| Augury | ≈ USD 135–350k first year for 50 machines (third-party estimate) | ❌ | ✅ proprietary sensors + human analysts | ❌ **documented "black box" complaint** | ⚠️ chat with human analyst | ⚠️ | ❌ |
| C3 AI Reliability | ≈ USD 1.8M ACV | ⚠️ | ✅ | ✅ "evidence package" charts | ⚠️ chat | ❌ | ❌ |
| IBM Maximo Application Suite | AppPoints; SaaS from ≈ USD 3,150/mo | ⚠️ | ✅ Predict, Health scores | ⚠️ narrative, no attribution | ⚠️ chat | ⚠️ | ⚠️ |
| SAP APM | Enterprise | ⚠️ | ✅ | ❌ | ⚠️ Joule | ⚠️ | ❌ |
| NVIDIA Omniverse | ≈ USD 4,500/GPU/yr + RTX hardware | ✅ OpenUSD | ❌ | ❌ | ❌ | ⚠️ | ❌ |
| **Eclipse Ditto** (OSS, EPL-2.0) | Free | ✅ JSON Things, policies | ❌ | ❌ | ❌ | ❌ | ❌ backend only |
| **Eclipse BaSyx** (OSS, MIT/EPL) | Free | ✅ AAS submodels | ⚠️ DIY | ❌ | ❌ | ⚠️ | ✅ SDKs |
| **ThingsBoard CE** (Apache-2.0) | Free CE; PE paid | ⚠️ attributes only | ⚠️ forecasting (Trendz) is **PE-only** | ⚠️ LLM prose via cloud API | ❌ | ⚠️ | ⚠️ Edge is PE-only |
| **FIWARE Orion-LD** (AGPL) | Free | ✅ NGSI-LD | ❌ | ❌ | ❌ | ⚠️ | ⚠️ |
| **OpenTwins** (Apache-2.0) | Free | ✅ Ditto+Kafka+Influx+Grafana+Unity | ⚠️ ML hooks | ❌ | ❌ | ❌ | ❌ "not for production" |
| **NASA ProgPy** (NOSA) | Free | ❌ library | ✅ physics RUL with uncertainty | ✅ uncertainty inherent | ❌ | ❌ | ⚠️ library |

### 3.2 Documented limitations (with the evidence behind them)

1. **Explainability is prose, not attribution.** Siemens, IBM, ABB and AVEVA describe "explainable" recommendations that are generated by a cloud LLM with no published link to model internals. Only C3 AI and GE SmartSignal show evidence charts. No vendor was found publishing per-prediction feature attributions or calibrated confidence intervals to operators. SHAP and LIME appear almost exclusively in academic papers and GitHub demos.
2. **Voice is essentially absent.** Only Siemens SIMATIC eaSie (process industry) and one UK CMMS vendor claim voice. TU Delft's concept paper on voice-enabled PdM assistants lists domain jargon in speech-to-text and missing data interfaces as the unsolved problems.
3. **Open-source stacks stop at the model store.** Ditto, BaSyx, FIWARE and AASX Package Explorer hold twin state but ship no analytics, no ML, no UI. ThingsBoard CE paywalls forecasting and edge. OpenTwins bundles the pieces but its README says "not for production".
4. **Hyperscaler abandonment.** AWS retired Monitron and Lookout for Equipment (2024–2026), Bosch IoT Suite device services ended mid-2024, SAP Predictive Asset Insights was sunset in 2023. C3 AI reported a 46 % revenue decline and layoffs in FY26.
5. **Sensor lock-in and data hostage.** Augury restricts raw spectrum export; Senseye model export is undocumented.
6. **Long cold start.** Senseye needs roughly 120 hours of learning per asset.
7. **Energy and health live in separate apps** (Insights Hub Energy Manager, FactoryTalk Energy Manager, EcoStruxure). No platform correlates degradation predictions with energy-intensity drift as a first-class twin property.
8. **3D twins are decoupled from analytics** and require RTX GPUs (Omniverse) or are stuck in preview (Azure 3D Scenes Studio since 2022).
9. **Copilots are text-only and cloud-LLM-bound** (Azure OpenAI). Rockwell's edge Nemotron Nano is the only on-device SLM found.
10. **Pricing is opaque and enterprise-only.** Nothing serves SMEs, universities or research labs at zero cost with PdM included.
11. **No human feedback on explanations.** Senseye lets users rate insights, but no platform captures operator agreement with the *explanation* to recalibrate.
12. **No benchmark transparency.** No vendor publishes precision/recall on public datasets.
13. **Standards fragmentation.** DTDL (Azure), AAS (IDTA/Bosch/Siemens), NGSI-LD (FIWARE) and OpenUSD (NVIDIA) are mutually incompatible; no open platform bridges them.

---

## 4. Research Landscape and Gaps (Academic State of the Art)

Research date: September 2026, prioritising 2023–2026 literature. Full citations in Appendix C.

### 4.1 Explainable AI for predictive maintenance

- Cummins et al. (IEEE Access 2024) surveyed explainable PdM and found SHAP and LIME dominate, few comparative evaluations exist, and there is no standard explanation-quality metric or end-user validation.
- Solís-Martín et al. (2023) evaluated saliency XAI on C-MAPSS RUL regressors and found Grad-CAM most robust; time-series **regression** XAI remains understudied.
- Kobayashi and Alam (2023) framed "XAI inside a digital twin for RUL" but only conceptually.
- C-SHAP (2025/2026) and SurvCF(t) (July 2026) are the first works on concept-level temporal SHAP and counterfactuals for RUL. Counterfactual XAI for RUL is a brand-new field.
- **Gap:** No study delivers explanations verbally or tests them with technicians. No benchmark for stability of SHAP across sliding windows.

### 4.2 Industrial digital twins

- ISO 23247 implementations are few and lab-scale (Cao et al. 2025); AI integration and energy KPIs are listed as "next stages".
- OpenTwins (Computers in Industry 2023) is the reference open-source stack: Ditto + Kafka + InfluxDB + Grafana + Unity. No XAI, no voice.
- Wiener, Gamma and inverse-Gaussian degradation processes plus Paris-law crack growth and Arrhenius temperature models are the canonical synthetic degradation generators.
- **Gap:** No open, reproducible DT + PdM benchmark that uses documented stochastic degradation generators with *known causal drivers*, which would allow explainers to be scored against ground truth. "What-if" simulation in DT papers is GUI-driven, never natural-language-driven.

### 4.3 Voice and natural-language interaction in industry

- Bousdekis et al. (Frontiers in AI 2025) built a voice + AutoML assistant at Whirlpool (intent accuracy 95.3 %, evaluated with SUS, VUS, NASA-TLX) and **explicitly state that explainability approaches suited to voice interfaces are an open problem**.
- Mukherjee et al. (Procedia CIRP 2025) built an ASR → LLM → TTS dialogue with machine tools.
- "Technician 5.0" (Springer 2025/26) is the closest existing work: DT + RUL + text chatbot. No voice, no XAI method evaluated.
- Gill et al. (2025) and Xia (2026) use LLM agents validated against a DT sandbox, text only.
- Figliè et al. (2026) compared conversational and graphical industrial interfaces with 20 participants: conversation reduces effort, dashboards are better for overview.
- Whisper degrades in 64–79 dB machine noise (2025 evaluation); code-mixed Hindi-English Whisper adaptation exists (Interspeech 2025) but has no industrial application.
- **Gap:** Not found anywhere: (a) SHAP/counterfactual explanations spoken back and user-evaluated; (b) voice-triggered what-if simulation with narrated results; (c) a formal safety/confirmation protocol for voice-issued maintenance commands; (d) noise-robust intent recognition for PdM vocabulary; (e) multilingual (Hindi-English) shop-floor PdM assistant.

### 4.4 Edge AI, energy, evaluation

- TinyML bearing diagnosis on ESP32-S3 reaches 88 % accuracy at 45 ms (2025). FedCMAPSS (August 2026) is the new federated RUL benchmark. Nobody reports the latency or energy cost of computing *explanations* on edge hardware.
- Digital-twin energy-efficiency work (Politecnico di Milano, Journal of Manufacturing Systems 2025) links fault states to energy draw, but no paper computes ISO 22400 / ISO 50001 KPIs inside a PdM twin and feeds them to an explainer.
- Evaluation instruments that exist and are free to use: System Usability Scale (SUS), NASA-TLX, Hoffman's Explanation Satisfaction and Trust scales, XEQ scale (2024), Chatbot Usability Questionnaire (CUQ).

### 4.5 Benchmarks: the bar to reach

| Dataset | Metric | Published state of the art (2025–2026) | Simple baseline | This project's target |
|---|---|---|---|---|
| C-MAPSS FD001 | RMSE / NASA score | 11.02 / 194.6 (TTSNet) | LSTM ≈ 15.3 | ≤ 13.0 / ≤ 300 |
| C-MAPSS FD002 | RMSE | 13.25 (TTSNet), 13.96 (Bi-cLSTM 2026) | ≈ 20 | ≤ 17 |
| C-MAPSS FD003 | RMSE | 11.06 | ≈ 15 | ≤ 13.0 |
| C-MAPSS FD004 | RMSE | 14.25 (Bi-cLSTM 2026), 18.26 (TTSNet) | ≈ 22 | ≤ 19 |
| AI4I 2020 | ROC-AUC | 0.973 (LightGBM with in-fold SMOTE) | ≈ 0.95 | ≥ 0.96 |
| CWRU bearing | Accuracy | ≈ 99 % (beware leakage-inflated results) | 95 % | ≥ 97 % with leakage-safe split |

---

## 5. How This Platform Overcomes the Gaps (Differentiators)

| # | Gap in existing products | TwinVoice answer | Where specified |
|---|---|---|---|
| D1 | Explanations are LLM prose with no link to the model | Every prediction ships a **SHAP attribution vector, EBM glass-box breakdown, counterfactual and conformal interval**; the LLM only *narrates* these numbers and its narration is automatically audited for faithfulness | FR-XAI-01..08 |
| D2 | No voice on the shop floor | Fully offline **voice pipeline** (Whisper → local LLM intent router → Kokoro/Piper) with wake word, push-to-talk and noise augmentation | FR-VN-01..12 |
| D3 | Voice commands are unsafe | **Risk-tiered read-back confirmation protocol** (Query / Simulate / Schedule / Actuate) with schema validation against twin state before any action | FR-VN-07 |
| D4 | Open-source stacks have no analytics | One `docker compose` brings up twin store + simulator + PdM + XAI + dashboard + voice | Section 7, NFR-DEP |
| D5 | Cloud-only, hyperscaler abandonment | Everything self-hosted, licence-stable (Apache/MIT/EPL/BSD), models exported as ONNX | Section 11 |
| D6 | No RUL with uncertainty | Data-driven RUL (LSTM/TCN/GBM) + **physics prognostics (NASA ProgPy)** fused, with **MAPIE conformal intervals** | FR-PM-03..05 |
| D7 | Energy and health separated | Energy is a first-class twin property; **energy-intensity drift is an explanatory feature** for degradation; ISO 22400 and ISO 50001 KPIs are computed in the twin | FR-EN-01..06 |
| D8 | Long cold start | **Physics-informed synthetic pre-training** on the simulator plus transfer learning shortens per-asset learning | FR-DT-05, FR-PM-08 |
| D9 | 3D decoupled from analytics | Lightweight **React Three Fiber** twin with health, RUL and SHAP overlays on the 3D model, no GPU required | FR-DT-06..08 |
| D10 | No human feedback on explanations | Operators can **agree/disagree with each explanation** by voice or click; feedback is logged and used for recalibration and for the user study | FR-XAI-09 |
| D11 | No benchmark transparency | Built-in **benchmark runner** that reproduces C-MAPSS / AI4I numbers and publishes a report | FR-PM-09 |
| D12 | Standards fragmentation | Twin core stores AAS submodels natively and exposes **AAS JSON, DTDL and NGSI-LD adapters** | FR-DT-02 |
| D13 | Voice in noisy, multilingual plants | Noise-augmented training, **Hindi-English code-mixed** intent support | FR-VN-09, FR-VN-10 |
| D14 | What-if is GUI-only | **"Ask the twin"**: natural-language what-if scenarios run Monte-Carlo simulations and narrate the RUL distribution shift | FR-DT-09 |

---

## 6. Users, Personas and Use Cases

### 6.1 Personas

| Persona | Description | Primary needs |
|---|---|---|
| **Maintenance technician (Ravi)** | On the floor, gloves on, 75 dB environment, tablet clipped to belt | Ask "why is CNC-3 flagged?", hear the answer, confirm a work order by voice |
| **Plant / production manager (Priya)** | Office, wants OEE, downtime, energy cost, weekly report | Dashboard, scheduled PDF report, ask "what's the biggest energy waster this week?" |
| **Reliability engineer (Marcus)** | Tunes models, validates explanations, plans maintenance windows | Model benchmark page, SHAP global plots, schedule optimiser, what-if simulation |
| **Researcher / student (you)** | Runs experiments, writes papers | Reproducible benchmark runner, experiment logging, user-study instrumentation |
| **Energy manager (Lena)** | ISO 50001 compliance | Energy baseline, intensity KPIs, anomalies vs production volume |

### 6.2 Core use cases

| UC | Title | Flow |
|---|---|---|
| UC-1 | Voice health query | Technician: "Hey Twin, how is compressor two?" → System speaks: "Compressor two is at health 71 percent. Estimated remaining useful life 38 cycles, 90 percent range 29 to 47. Main driver: bearing vibration RMS rose 22 percent in the last 6 hours." |
| UC-2 | Explanation drill-down | "Why?" → SHAP top-3 narrated; "Show me" → dashboard opens waterfall plot on the 3D twin part; "What would fix it?" → counterfactual narrated |
| UC-3 | Voice-confirmed work order | "Schedule bearing replacement for compressor two on Friday" → System reads back: "Create maintenance order: replace bearing, compressor two, Friday 20 September, 08:00. Confirm?" → "Confirm" → order created, ID spoken |
| UC-4 | What-if | "What if we reduce load to 80 percent?" → simulator runs 500 Monte-Carlo trajectories → "Reducing load to 80 percent extends median RUL from 38 to 61 cycles." |
| UC-5 | Weekly report by voice | "Generate the weekly maintenance and energy report" → PDF produced, summary spoken, link on dashboard |
| UC-6 | Energy anomaly | Dashboard alarms: energy per unit up 12 % with flat output → explanation links to motor efficiency loss → PdM engine raises failure probability |
| UC-7 | Benchmark reproduction | Researcher runs `make benchmark` → C-MAPSS FD001–FD004 metrics, SHAP faithfulness scores and calibration plots exported |
| UC-8 | Explanation feedback | Technician: "That's wrong, the temperature sensor is faulty" → feedback logged, sensor flagged, explanation marked disputed |

---

## 7. System Architecture

### 7.1 Layered view (mapped to ISO 23247)

```
┌──────────────────────────────────────────────────────────────────────────┐
│ USER ENTITY (ISO 23247 layer 4)                                          │
│  Web dashboard (React + ECharts + React Three Fiber)  │  VoiceNav client │
│  Grafana OSS (embedded)  │  Report viewer (PDF/DOCX)                     │
├──────────────────────────────────────────────────────────────────────────┤
│ DIGITAL TWIN ENTITY (layer 3)                                            │
│  Twin Store: Eclipse Ditto (Things, policies, WoT)                       │
│  AAS submodels (basyx-python-sdk) │ Adapters: AAS JSON / DTDL / NGSI-LD  │
│  Predictive Maintenance Engine (FastAPI + scikit-learn/XGBoost/PyTorch   │
│     + NASA ProgPy + lifelines + MAPIE)                                   │
│  Explainable AI Service (SHAP, InterpretML EBM, DiCE, Captum, Quantus)   │
│  Voice/NL Service (faster-whisper, Ollama+Qwen3, Kokoro/Piper, Pipecat)  │
│  Analytics Service (OEE/ISO 22400, energy/ISO 50001, PM4Py optional)     │
│  Scheduler (OR-Tools CP-SAT)  │  Report Service (Jinja2 → WeasyPrint)    │
├──────────────────────────────────────────────────────────────────────────┤
│ DEVICE COMMUNICATION ENTITY (layer 2)                                    │
│  Eclipse Mosquitto MQTT (Sparkplug B payloads) │ OPC UA (asyncua)        │
│  Modbus TCP (pymodbus) │ MTConnect (optional)                            │
├──────────────────────────────────────────────────────────────────────────┤
│ OBSERVABLE MANUFACTURING ELEMENTS (layer 1)                              │
│  Sensor Simulator (SimPy + physics degradation models) │ OpenPLC v4      │
│  Optional real hardware: Raspberry Pi / ESP32 with ONNX Runtime          │
└──────────────────────────────────────────────────────────────────────────┘
      Storage: PostgreSQL 18 + TimescaleDB (telemetry, events, predictions)
      Cache/queue: Valkey │ Auth: Keycloak │ Object files: local FS / SeaweedFS
```

### 7.2 Data flow

1. **Simulator** emits per-machine telemetry (vibration RMS/kurtosis, temperature, current, power, pressure, RPM, torque, cycle count) at 1 Hz (configurable to 20 kHz bursts for vibration waveforms) as Sparkplug B MQTT messages.
2. **Ingest service** subscribes, validates schema, writes to TimescaleDB hypertables, and updates Ditto twin "features" (current state).
3. **PdM engine** runs on a sliding window (default 30 samples) every N seconds: anomaly score, failure probability, RUL point estimate and conformal interval, health index. Results are written back to the twin and to the `predictions` table.
4. **XAI service** computes SHAP values for each prediction (cached), EBM term contributions, and on demand a counterfactual. It emits an `explanation` object (JSON) with feature names, contributions, direction, units and confidence.
5. **Narration service** renders the explanation object into text with a deterministic template first and then optionally a local LLM paraphrase, and runs a faithfulness audit (rank agreement, sign agreement, hallucination check). Audited text goes to the dashboard and to TTS.
6. **VoiceNav** captures audio, transcribes, routes intent through the LLM tool-calling schema, applies the confirmation protocol, calls the appropriate service, and speaks the result.
7. **Analytics service** computes OEE, MTBF, MTTR, energy intensity, CO2 per unit, and stores KPIs.
8. **Report service** collects KPIs, predictions, explanations and charts into PDF/DOCX on demand or on schedule.

### 7.3 Repository layout (proposed)

```
DigitalTwin/
├── docker-compose.yml
├── docs/                      # this PRD, architecture, paper drafts
├── simulator/                 # SimPy + degradation physics, MQTT publisher
├── twin/                      # Ditto config, AAS submodels, adapters
├── ingest/                    # MQTT → TimescaleDB → Ditto
├── pdm/                       # training, inference, ProgPy fusion, conformal
├── xai/                       # SHAP/EBM/DiCE/Captum, faithfulness audit
├── voice/                     # STT, intent router, TTS, confirmation protocol
├── analytics/                 # OEE, energy KPIs, scheduler
├── reports/                   # Jinja2 templates, WeasyPrint
├── api/                       # FastAPI gateway, WebSocket hub, auth
├── web/                       # React + Vite + ECharts + React Three Fiber
├── edge/                      # ONNX export, Raspberry Pi/ESP32 runners
├── benchmarks/                # C-MAPSS, AI4I, MetroPT-3 runners, result tables
├── user_study/                # questionnaires, logging, analysis notebooks
└── data/                      # download scripts (no data committed)
```

---

## 8. Functional Requirements

Priority: **M** = must have (v1), **S** = should have, **C** = could have. Each requirement lists the open-source tool that implements it.

### 8.1 Module A: Industrial Dashboard

#### A.1 Machine Monitoring

| ID | Requirement | Priority | Tool |
|---|---|---|---|
| FR-MM-01 | **Fleet overview.** A grid/list of every machine showing name, type, line, live status (Running / Idle / Down / Maintenance), health index 0–100, RUL with interval, active alarms and energy draw. Sorting and filtering by line, status, health. Colour-blind-safe status palette. | M | React + ECharts |
| FR-MM-02 | **Machine detail page.** Live sensor tiles (value, unit, sparkline of last 10 min, threshold band), 3D twin panel, prediction panel, explanation panel, event timeline. All panels update over WebSocket with ≤ 1 s latency. | M | React, WebSocket (FastAPI) |
| FR-MM-03 | **Time-series explorer.** Select any sensors, any time range (from 1 min to 1 year), overlay predictions and alarms, zoom/pan, export CSV. Downsampling via Timescale continuous aggregates for ranges over 24 h. | M | ECharts, TimescaleDB |
| FR-MM-04 | **Alarm management.** Threshold alarms (static and adaptive, e.g. 3σ over rolling baseline), ML anomaly alarms, acknowledge / assign / comment, alarm history, alarm-shelving to suppress known issues. Each ML alarm links to its explanation. | M | FastAPI, PyOD/River |
| FR-MM-05 | **Grafana embedding.** Grafana OSS dashboards embedded via iframe for engineers who prefer them; provisioned dashboards versioned in the repo. | S | Grafana OSS 13 (AGPL, unmodified) |
| FR-MM-06 | **Mobile / tablet layout.** Dashboard usable at 768 px width with the voice button always visible. | M | Responsive CSS |
| FR-MM-07 | **Role-based views.** Technician sees their line and open orders; manager sees plant KPIs; engineer sees models. Roles from Keycloak. | S | Keycloak 26 |

#### A.2 Production Analytics

| ID | Requirement | Priority | Tool |
|---|---|---|---|
| FR-PA-01 | **OEE per ISO 22400-2.** OEE = Availability × Performance × Quality computed per machine, line and plant per shift/day/week. Availability = run time / planned time; Performance = (ideal cycle time × count) / run time; Quality = good count / total count. Inputs from the simulator's production counters and event log. | M | Own module (formulas are public) |
| FR-PA-02 | **Downtime Pareto.** Downtime by cause code (breakdown, changeover, starvation, blocked, planned maintenance) with drill-down to events. | M | ECharts |
| FR-PA-03 | **Reliability KPIs.** MTBF, MTTR, MTTF, failure rate per machine over selectable windows; trend lines. | M | Own module |
| FR-PA-04 | **Production vs plan.** Planned vs actual units per shift, cycle-time distribution histograms, first-pass yield. | S | ECharts |
| FR-PA-05 | **Process mining (optional).** Discover the actual production flow from event logs and highlight bottlenecks. | C | PM4Py (AGPL; keep unmodified) |
| FR-PA-06 | **KPI definitions page.** Every KPI shows its formula and data lineage on hover, so numbers are auditable. | M | React |

#### A.3 Energy Consumption

| ID | Requirement | Priority | Tool |
|---|---|---|---|
| FR-EN-01 | **Real-time power and cumulative energy** per machine, line, plant (kW, kWh), with tariff-based cost (configurable rate table) and CO2 (configurable emission factor, default from public grid factors). | M | Simulator, TimescaleDB |
| FR-EN-02 | **Energy intensity KPIs (ISO 50001 style).** kWh per unit produced, kWh per running hour, idle energy share, peak demand. Baseline period vs current period comparison with regression-adjusted baseline (energy = a + b × production). | M | scikit-learn linear model |
| FR-EN-03 | **Energy anomaly detection.** Flag energy per unit deviations from the regression baseline (residual > 3σ) and correlate with health index. | M | PyOD / River |
| FR-EN-04 | **Energy as an explanatory feature.** Specific energy, power-factor drift and current imbalance are inputs to the PdM models so SHAP can attribute degradation to energy signatures ("motor efficiency loss"). | M | PdM feature pipeline |
| FR-EN-05 | **Energy-aware scheduling.** The maintenance scheduler can prefer low-tariff windows and shows energy cost impact of a schedule. | S | OR-Tools |
| FR-EN-06 | **Energy report section.** Weekly energy report with intensity trend, top-5 consumers, anomalies, savings from maintenance actions. | M | Report service |

### 8.2 Module B: Digital Twin Layer

#### B.1 Virtual Machine Representation

| ID | Requirement | Priority | Tool |
|---|---|---|---|
| FR-DT-01 | **Twin store.** Each physical asset is a Ditto "Thing" with attributes (static: model, serial, install date, location) and features (dynamic: sensor values, health, RUL, alarms, energy). Twin updated within 200 ms of ingest. Policies restrict write access per role. | M | Eclipse Ditto 3.9 (EPL-2.0) |
| FR-DT-02 | **Asset Administration Shell.** Each asset carries AAS submodels: Nameplate, TechnicalData, OperationalData, MaintenanceHistory (custom), PredictiveMaintenance (custom: health, RUL, explanation reference). Export as AASX/JSON; import from AASX Package Explorer files. Adapters expose the same twin as DTDL JSON and NGSI-LD entity for interoperability demos. | M | basyx-python-sdk / aas-core3.0-python (MIT) |
| FR-DT-03 | **Twin hierarchy.** Plant → line → machine → component (motor, bearing, pump, spindle). Component-level twins carry their own health and RUL; machine health = weighted min of components. | M | Ditto relationships + AAS |
| FR-DT-04 | **Digital shadow vs twin distinction.** The platform is a *twin*, not a shadow: it writes back to the asset (simulated set-points: load, speed, maintenance reset) through OPC UA/MQTT command topics. Write-back gated by confirmation protocol. | M | asyncua, Mosquitto |
| FR-DT-05 | **Fidelity levels.** Each twin declares fidelity: L1 status only, L2 telemetry, L3 physics model, L4 predictive. Dashboard shows the badge. Synthetic pre-training available for L3+ twins. | S | Metadata |
| FR-DT-06 | **3D representation.** Browser-based 3D scene (glTF models, CC0 sources or Blender-made) per machine with components selectable; component colour maps to health; hovering shows RUL and top SHAP feature; alarms pulse. Runs at ≥ 30 fps on integrated graphics. | M | Three.js r18x + React Three Fiber 9 (MIT) |
| FR-DT-07 | **Plant layout view.** 2D/3D floor plan with machines positioned, status colours, click-through. | S | React Three Fiber |
| FR-DT-08 | **State history replay.** Scrub a timeline to replay twin state and 3D colouring for any past window (e.g. the 2 hours before a failure). | S | TimescaleDB |
| FR-DT-09 | **What-if simulation ("Ask the twin").** User (voice or form) sets a hypothetical change (load ±%, speed, ambient temperature, maintenance now vs later). System clones the twin state, runs N Monte-Carlo degradation trajectories (default 500) in the simulator and PdM model, and returns the RUL distribution before and after, the expected cost/energy impact, and a narrated summary. Completes in ≤ 10 s. | M | SimPy + PdM engine |
| FR-DT-10 | **Twin lifecycle.** Create, clone, retire twins from UI or API; twin schema versioning. | S | Ditto API |

#### B.2 Real-Time Sensor Simulation

| ID | Requirement | Priority | Tool |
|---|---|---|---|
| FR-SIM-01 | **Machine library.** At least 5 machine types with realistic sensor sets: CNC mill (spindle vibration, spindle temperature, spindle load, feed rate, tool wear), industrial compressor (discharge pressure, temperature, vibration, current), conveyor motor (current, vibration, belt speed, temperature), hydraulic press (pressure, oil temperature, cycle count, flow), injection moulding machine (barrel temperature zones, clamp force, cycle time, energy). Each with production counters, quality counter and power draw. | M | SimPy 4 (MIT) |
| FR-SIM-02 | **Physics-based degradation models.** Documented and parameterised: (a) Wiener process with drift for gradual wear; (b) Gamma process for monotone degradation; (c) Paris-law crack growth for bearings/shafts; (d) Arrhenius temperature acceleration; (e) Taylor tool-life for CNC tool wear; (f) motor efficiency loss coupling degradation to power draw. Each model records its *true* driver so XAI can be validated against ground truth. | M | NumPy/SciPy, NASA ProgPy models (pump, battery) |
| FR-SIM-03 | **Failure modes.** Per machine type ≥ 4 failure modes (e.g. bearing wear, misalignment, overheating, lubrication loss, tool breakage) with distinct sensor signatures; sudden and gradual variants; mixed-mode scenarios. | M | Simulator |
| FR-SIM-04 | **Noise and realism.** Sensor noise (Gaussian, drift, spikes), missing data, sampling jitter, sensor faults (stuck, offset), shift patterns, weekend idling, production-plan-driven load. | M | Simulator |
| FR-SIM-05 | **Scenario control.** REST/voice control: inject a fault, accelerate time (1× to 1000×), reset a machine after maintenance, set load. Scenario scripts stored as YAML for reproducible demos and experiments. | M | FastAPI |
| FR-SIM-06 | **Protocol realism.** Publish over MQTT with Sparkplug B topic/payload; also expose an OPC UA server (asyncua) and Modbus TCP map (pymodbus) per machine so ingestion is protocol-agnostic and the platform can later connect to real PLCs. Optional OpenPLC v4 program driving a machine. | M | Mosquitto, asyncua, pymodbus, OpenPLC (MIT) |
| FR-SIM-07 | **Vibration waveforms.** For bearing failure modes, generate 20 kHz bursts with characteristic defect frequencies (BPFO, BPFI, BSF) so FFT/envelope features are meaningful; optionally replay real CWRU/IMS waveforms. | S | NumPy, CWRU/IMS data |
| FR-SIM-08 | **Dataset replay mode.** Replay C-MAPSS, MetroPT-3, AI4I rows as live telemetry with time scaling, so benchmarks and live demo use the same pipeline. | M | Simulator |
| FR-SIM-09 | **Synthetic dataset export.** Export simulated runs with ground-truth RUL and true driver labels as Parquet/CSV for the XAI benchmark (Section 14, Paper 3). | M | pandas/pyarrow |

### 8.3 Module C: Predictive Maintenance Engine

#### C.1 Failure Prediction

| ID | Requirement | Priority | Tool |
|---|---|---|---|
| FR-PM-01 | **Feature pipeline.** Rolling-window statistics (mean, std, min, max, slope, kurtosis, RMS, crest factor), FFT band energies and envelope spectrum for vibration, energy features (specific energy, power factor), cycle counts. Configurable window and stride. Same code path for training and inference. | M | tsfresh (MIT), NumPy, SciPy |
| FR-PM-02 | **Anomaly detection.** Unsupervised health monitoring per machine using Isolation Forest / ECOD (batch) and streaming Half-Space Trees (online) with drift detection (ADWIN). Health index 0–100 derived from anomaly score calibrated on healthy baseline. | M | PyOD 3 (BSD), River (BSD) |
| FR-PM-03 | **Failure classification.** Supervised model predicting failure within horizon H (default 24 h / 30 cycles) and failure mode. Models: XGBoost/LightGBM (primary), Explainable Boosting Machine (glass-box), logistic regression baseline. Class imbalance handled with in-fold resampling. Output: probability per failure mode. | M | XGBoost 3 (Apache), LightGBM (MIT), InterpretML (MIT) |
| FR-PM-04 | **Model registry and versioning.** Every trained model stored with dataset hash, hyperparameters, metrics, SHAP explainer, conformal calibrator and ONNX export. Promote/rollback via UI. | M | MLflow (Apache-2.0) or lightweight own registry |
| FR-PM-08 | **Transfer and cold start.** Pre-train on simulator data and public datasets; fine-tune per asset with minimal data; report how many hours of data were needed to reach target accuracy (addresses the 120-hour cold-start problem). | S | PyTorch 2.9 |
| FR-PM-09 | **Benchmark runner.** `make benchmark` trains and evaluates on C-MAPSS FD001–FD004 (RMSE, NASA score), AI4I 2020 (AUC, F1), MetroPT-3 (event-level precision/recall, lead time) and outputs a Markdown/PDF report with leakage-safe splits and seeds. | M | benchmarks/ |

#### C.2 Remaining Useful Life Estimation

| ID | Requirement | Priority | Tool |
|---|---|---|---|
| FR-PM-05 | **Data-driven RUL.** Sequence models (LSTM, TCN, Transformer-lite) and gradient-boosted regressors on windowed features; piecewise-linear RUL target (cap 125 cycles, standard practice on C-MAPSS). Targets in Section 4.5. | M | PyTorch, Darts/NeuralForecast (Apache), XGBoost |
| FR-PM-06 | **Uncertainty.** Conformal prediction intervals (MAPIE, split-conformal or CQR) at 90 % with reported empirical coverage; optionally full predictive distribution (crepes). Survival-analysis alternative (Weibull AFT, Cox PH, random survival forests) gives a hazard curve. | M | MAPIE 1.x (BSD), crepes (BSD), lifelines (MIT) |
| FR-PM-07 | **Physics-informed fusion.** For twins with an L3 physics model, run NASA ProgPy state estimation (unscented Kalman / particle filter) and fuse with the data-driven estimate (inverse-variance weighting). Show both estimates and the fused one. | S | NASA ProgPy 1.8 (NOSA) |
| FR-PM-10 | **RUL presentation.** Every RUL shown as "point (low–high)" with units (cycles/hours), a horizon bar and colour by urgency; never a bare number. Confidence text is generated from the interval width. | M | UI |

#### C.3 Maintenance Scheduling

| ID | Requirement | Priority | Tool |
|---|---|---|---|
| FR-MS-01 | **Work order management.** Create / edit / close orders with type (corrective, preventive, predictive), priority, asset, tasks, parts, technician, planned window, actual times. Orders created automatically when failure probability exceeds a configurable threshold, with the explanation attached. | M | FastAPI + PostgreSQL |
| FR-MS-02 | **Schedule optimiser.** Given RUL intervals, technician availability, production plan and tariff windows, produce a schedule minimising expected downtime cost + risk of failure before service + energy cost, subject to constraints (no two orders on one line at once, skills). Solved with CP-SAT; re-planned when RUL changes materially. | M | Google OR-Tools (Apache-2.0) |
| FR-MS-03 | **Calendar and Gantt view.** Drag-and-drop adjustments; conflicts highlighted; changes re-scored. | S | React |
| FR-MS-04 | **Risk-of-delay explanation.** For each scheduled order, show probability of failure before the slot (from the RUL distribution) and what moving it earlier/later does. | M | PdM engine |
| FR-MS-05 | **Maintenance effect feedback.** After an order is closed, the twin resets the component degradation state, and the model observes the post-maintenance data to evaluate whether the prediction was correct (logged for the benchmark and user study). | M | Simulator + PdM |
| FR-MS-06 | **Export.** Work orders exportable as CSV/JSON and via a simple B2MML-like XML for future ERP/CMMS integration. | C | Own |

### 8.4 Module D: Explainable AI Layer

#### D.1 Feature Importance

| ID | Requirement | Priority | Tool |
|---|---|---|---|
| FR-XAI-01 | **Local attribution for every prediction.** TreeSHAP for GBMs (exact, fast), DeepSHAP/Integrated Gradients (Captum) for sequence models, KernelSHAP fallback. Output: per-feature contribution with sign, magnitude, base value, and the feature's current value and unit. Computed within 500 ms for tree models. | M | SHAP 0.52 (MIT), Captum (BSD) |
| FR-XAI-02 | **Global importance.** Mean absolute SHAP per feature per model, SHAP summary/beeswarm, partial dependence, and EBM shape functions; shown on the model page and in reports. | M | SHAP, InterpretML |
| FR-XAI-03 | **Temporal attribution.** For sequence models, attribution over time steps within the window (heatmap "which of the last 30 samples mattered"), with concept-level aggregation (trend, spike, level shift) following the C-SHAP idea. | S | Captum, own |
| FR-XAI-04 | **Glass-box parallel model.** An EBM is trained alongside every GBM; its additive term contributions are shown as an independent second opinion; disagreement between SHAP and EBM ranking is flagged. | M | InterpretML EBM |

#### D.2 Failure Reason Analysis

| ID | Requirement | Priority | Tool |
|---|---|---|---|
| FR-XAI-05 | **Failure-mode reasoning.** Combine the predicted failure mode, the top-k attributions and a curated knowledge base (per machine type: symptom → likely cause → recommended action, editable YAML) to output a structured "reason card": symptom, evidence (features + values), likely cause, recommended action, confidence. | M | Own rules + LLM optional |
| FR-XAI-06 | **Counterfactuals.** "What minimal change would move this machine back to healthy / extend RUL by X?" using DiCE with feasibility constraints (only actionable features: load, speed, temperature via cooling, lubrication interval). Presented as a table and narrated. | M | DiCE 0.11 (MIT) |
| FR-XAI-07 | **Narration with faithfulness audit.** Explanations rendered (1) by deterministic templates (always available) and (2) optionally by a local LLM for fluency. The audit module checks the LLM text against the explanation JSON: top-3 feature rank agreement, sign agreement, no feature names outside the schema, numeric values within tolerance. Failing narrations fall back to the template. Audit results are logged (this is Paper 2's dataset). | M | Ollama + Qwen3 (Apache-2.0), own audit |
| FR-XAI-08 | **Explanation quality metrics.** For each model, compute faithfulness (deletion/insertion, PGI), stability (SensitivityMax across adjacent windows), sparsity; on simulator data, agreement with the *true driver* label. Shown on the model page. | M | Quantus (MIT) or own |

#### D.3 Confidence Scores

| ID | Requirement | Priority | Tool |
|---|---|---|---|
| FR-XAI-10 | **Calibrated probabilities.** Failure probabilities calibrated by isotonic/Platt scaling; reliability diagram and Expected Calibration Error shown per model. | M | scikit-learn |
| FR-XAI-11 | **Prediction-level confidence.** A single confidence label (High / Medium / Low) derived from conformal interval width, model agreement (GBM vs EBM vs physics), data quality (missing/stuck sensors) and drift status. The derivation is shown on hover and spoken on request ("Confidence is medium because the two models disagree and sensor 4 has been stuck for 10 minutes"). | M | Own |
| FR-XAI-12 | **Drift and out-of-distribution flag.** Input drift (ADWIN/KS test) and OOD score (distance to training manifold) reduce confidence and trigger a "model may be stale" banner. | M | River, PyOD |
| FR-XAI-09 | **Human feedback on explanations.** Operators mark each explanation Agree / Disagree / Unsure with a reason (voice or click). Feedback stored with the explanation ID, surfaced to engineers, and used for (a) the user study, (b) flagging suspect sensors, (c) optional recalibration. | M | FastAPI + PostgreSQL |

### 8.5 Module E: VoiceNav Integration

#### E.1 Voice-Based Operations

| ID | Requirement | Priority | Tool |
|---|---|---|---|
| FR-VN-01 | **Fully offline speech-to-text.** faster-whisper (small or large-v3-turbo, INT8 on CPU) with streaming VAD; alternative Vosk for very low-end devices. Median transcription latency ≤ 1.5 s for a 5-second utterance on a 4-core laptop CPU. No audio leaves the machine. | M | faster-whisper (MIT), sherpa-onnx (Apache), Vosk (Apache) |
| FR-VN-02 | **Activation.** Push-to-talk button (always visible) and optional wake word ("Hey Twin") using openWakeWord with a **self-trained** model (bundled models are non-commercial). | M | openWakeWord (Apache code) |
| FR-VN-03 | **Text-to-speech.** Kokoro-82M (Apache-2.0) or Piper voices; speech starts ≤ 700 ms after response text is ready; adjustable rate; "repeat" and "slower" commands. | M | Kokoro via sherpa-onnx / Piper |
| FR-VN-04 | **Domain vocabulary.** Machine names, component names and units injected as Whisper initial prompt / hot-words and post-corrected with a fuzzy matcher against the twin registry (e.g. "CNC three" → `cnc-03`). | M | Own + rapidfuzz (MIT) |
| FR-VN-05 | **Dialogue state.** Multi-turn context: "how is compressor two?" → "why?" → "schedule it" resolves the referent. Context expires after 2 minutes of silence. | M | Own state machine |
| FR-VN-06 | **Barge-in and error handling.** User can interrupt TTS; low-confidence transcripts trigger "Did you mean…?"; unknown intents give a help prompt listing what the assistant can do. | M | Pipecat (BSD-2) pipeline |
| FR-VN-07 | **Risk-tiered confirmation protocol.** Every intent has a tier: **T0 Query** (execute immediately), **T1 Simulate** (execute, results are hypothetical), **T2 Schedule/Record** (read back full parameters, require "confirm"), **T3 Actuate/Write-back** (read back, require "confirm" + a second factor: on-screen tap or PIN; disabled by default in demo). Before executing T2/T3 the parameters are validated against twin state (asset exists, date in future, technician available). All voice actions are logged with transcript, intent JSON, confirmation and outcome. | M | Own |
| FR-VN-08 | **Audio feedback and accessibility.** Earcons for listening / thinking / done; visual transcript; full keyboard alternative for every voice action. | M | Web Audio |
| FR-VN-09 | **Noise robustness.** Intent classifier and STT evaluated with additive industrial noise at 55/65/75 dB SNR sweeps (MIMII / DCASE machine sounds, CC licences); training augmented accordingly. Report per-SNR word error rate and intent F1. | S | Own eval harness |
| FR-VN-10 | **Multilingual.** English primary; Hindi and Hindi-English code-mixed intents supported for the core command set (Whisper multilingual, intent examples in both). Response language follows the query. | S | Whisper, Qwen3 |
| FR-VN-11 | **Hands-free session on tablet.** Continuous listening mode with wake word for a defined session; auto-stop after inactivity. | S | openWakeWord |
| FR-VN-12 | **Edge deployment option.** The voice pipeline runs on a Raspberry Pi 5 (Whisper tiny/base via whisper.cpp, Piper) for a demo of an offline shop-floor unit. | C | whisper.cpp (MIT) |

#### E.2 Natural Language Commands

| ID | Requirement | Priority | Tool |
|---|---|---|---|
| FR-NL-01 | **Intent schema.** Intents are defined as function-calling tool schemas (JSON Schema): `get_machine_status`, `explain_prediction`, `get_counterfactual`, `run_what_if`, `create_work_order`, `list_alarms`, `acknowledge_alarm`, `get_kpi`, `generate_report`, `set_simulation_scenario`, `navigate_dashboard`, `help`. Full grammar in Appendix A. | M | Ollama tool calling |
| FR-NL-02 | **Hybrid router.** Deterministic first: spaCy rule/pattern matcher for the top-30 phrasings (fast, auditable). Fallback: local LLM (Qwen3-4B or Gemma 4 e4b via Ollama) with tool calling and constrained JSON output. Router returns intent + slots + confidence; LLM never executes anything itself. | M | spaCy (MIT), Ollama (MIT) |
| FR-NL-03 | **Grounded answers only.** Any factual answer must be built from data returned by a tool call (twin state, prediction, KPI). The LLM cannot answer from parametric memory; if a tool returns nothing, the assistant says so. Answers carry citations (asset ID, timestamp, model version) visible in the transcript. | M | Prompt + guardrail |
| FR-NL-04 | **Text chat parity.** Every voice command also works as typed chat in the dashboard; same router, same logs. | M | React |
| FR-NL-05 | **Dashboard navigation by voice.** "Open compressor two", "show energy for line one this week", "zoom to last hour" change the UI view. | M | Front-end command bus |
| FR-NL-06 | **Intent test suite.** ≥ 500 labelled utterances (≥ 10 per intent, paraphrases, noise-corrupted variants, Hindi-English) with target intent accuracy ≥ 92 %. | M | pytest |

#### E.3 Report Generation

| ID | Requirement | Priority | Tool |
|---|---|---|---|
| FR-RP-01 | **Report types.** (a) Machine health report; (b) Weekly maintenance report (orders, predictions, accuracy of last week's predictions); (c) Energy report (FR-EN-06); (d) Model benchmark report (FR-PM-09); (e) Incident report for a failure (timeline, explanations before failure, what was recommended, what was done). | M | Jinja2 (BSD) + WeasyPrint (BSD) |
| FR-RP-02 | **Formats.** PDF (primary), DOCX, Markdown; charts rendered with matplotlib/ECharts server-side export. | M | WeasyPrint, python-docx (MIT) |
| FR-RP-03 | **Triggers.** On demand (UI or voice), scheduled (cron in Celery beat), event-driven (after failure or after order closure). | M | Celery (BSD) + Valkey (BSD) |
| FR-RP-04 | **Narrative summary.** A 150-word executive summary generated by the local LLM from the report's KPI JSON, audited for numeric faithfulness (every number in the text must appear in the JSON). | S | Ollama, audit module |
| FR-RP-05 | **Spoken summary.** When triggered by voice, the summary is spoken and the file link shown. | M | TTS |
| FR-RP-06 | **Archive and access control.** Reports stored on local FS (or SeaweedFS), listed by date/type, role-restricted. | S | FastAPI, Keycloak |

### 8.6 Cross-cutting: Edge AI

| ID | Requirement | Priority | Tool |
|---|---|---|---|
| FR-EDGE-01 | **ONNX export** of every production model (GBM via onnxmltools, PyTorch via torch.onnx) and inference through ONNX Runtime with identical outputs (tolerance 1e-4). | M | ONNX Runtime (MIT) |
| FR-EDGE-02 | **Edge runner.** A small Python service that subscribes to MQTT, computes features, runs ONNX inference and TreeSHAP locally, and publishes predictions + explanations back; deployable on Raspberry Pi 4/5. Latency and energy per inference and per explanation logged (Paper opportunity 8). | S | edge/ |
| FR-EDGE-03 | **Store-and-forward.** Edge runner buffers when the broker is unreachable and replays on reconnect. | S | SQLite |
| FR-EDGE-04 | **Microcontroller demo (optional).** TinyML vibration classifier on ESP32-S3 (LiteRT micro) trained on CWRU; simulated in Renode/QEMU if no hardware. | C | LiteRT (Apache), Renode (MIT) |

---

## 9. Non-Functional Requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-DEP-01 | Deployment | Entire platform starts with one `docker compose up` on Windows 11 (Docker Engine/Compose Apache-2.0; Docker Desktop is free for personal/education use) or Podman Desktop. First start ≤ 10 minutes including model download. |
| NFR-DEP-02 | Hardware | Runs on 4-core CPU, 16 GB RAM, no GPU. GPU (CUDA/DirectML) optional for faster Whisper and LLM. |
| NFR-COST-01 | Cost | Zero paid services, zero API keys. CI must fail if a dependency with a non-approved licence is introduced (licence check via `pip-licenses` / `license-checker`). |
| NFR-PERF-01 | Latency | Telemetry ingest to dashboard ≤ 1 s; prediction + SHAP ≤ 2 s per machine per window; voice round-trip (end of speech to start of TTS) ≤ 3 s on CPU. |
| NFR-PERF-02 | Throughput | 50 simulated machines × 20 sensors at 1 Hz (1,000 points/s) sustained on one laptop; 10,000 points/s target with TimescaleDB batching. |
| NFR-REL-01 | Reliability | Services restart automatically; no data loss for ingest during service restarts (MQTT QoS 1 + persistent sessions). |
| NFR-SEC-01 | Security | Keycloak OIDC; role-based access; T3 voice actions need second factor; all voice audio processed locally and discarded after transcription unless the user opts into keeping it for the study. |
| NFR-PRIV-01 | Privacy | User-study data pseudonymised; consent form; no biometric voice profiles stored. |
| NFR-OBS-01 | Observability | Structured logs, Prometheus metrics endpoint, Grafana system dashboard; every prediction, explanation, voice action and confirmation traceable by ID. |
| NFR-REPRO-01 | Reproducibility | Seeds fixed; dataset download scripts with checksums; benchmark results regenerated by one command; experiment configs in YAML. |
| NFR-STD-01 | Standards | ISO 23247 layer mapping documented; AAS submodels valid against IDTA templates; Sparkplug B compliant payloads; OPC UA server browsable by UaExpert (free client). |
| NFR-A11Y-01 | Accessibility | WCAG 2.1 AA colour contrast; every voice function has a keyboard/click equivalent; screen-reader labels. |
| NFR-I18N-01 | Internationalisation | UI strings externalised; English and Hindi. |
| NFR-DOC-01 | Documentation | README quickstart, architecture doc, API reference (OpenAPI auto-generated), voice command cheat-sheet, dataset licences file. |
| NFR-LIC-01 | Licensing of this project | Platform released under Apache-2.0; GPL/AGPL components (Grafana, PM4Py, Piper fork, scikit-survival) kept as unmodified separate services so they do not force relicensing. |

---

## 10. Data Requirements and Datasets

All datasets are free to download. Licences verified September 2026.

| Dataset | Use in project | Licence | Where |
|---|---|---|---|
| NASA C-MAPSS FD001–FD004 | Primary RUL benchmark, replay mode | NASA open data (attribution) | NASA PCoE repository / PHM Society mirror |
| NASA N-CMAPSS (DS01–DS08) | Stretch benchmark with flight profiles (≈ 15 GB) | NASA open data | PHM datasets S3 mirror |
| AI4I 2020 (UCI #601) | Tabular failure classification, XAI demos, 5 failure modes | CC BY 4.0 | UCI ML Repository |
| MetroPT-3 (UCI #791) | Real compressor data with failure reports; live-replay demo | CC BY 4.0 | UCI ML Repository |
| Hydraulic systems condition monitoring (UCI #447) | Hydraulic press twin, multi-target condition classes | CC BY 4.0 | UCI |
| NASA IMS bearings | Run-to-failure vibration; bearing twin, waveform replay | NASA open data | NASA PCoE |
| CWRU bearing | Fault classification, edge TinyML demo | No explicit licence, de-facto free for research | CWRU / Zenodo mirror |
| FEMTO / PRONOSTIA | Bearing RUL | NASA repository terms | PHM datasets mirror |
| NASA Milling | CNC tool wear twin | NASA open data | NASA |
| Tennessee Eastman (Rieth et al.) | Process fault scenarios (optional) | CC0 | Harvard Dataverse |
| MIMII / DCASE machine sounds | Noise augmentation for voice robustness | CC BY-SA / check each | Zenodo |
| Synthetic (own simulator) | Ground-truth-driver XAI benchmark, cold-start experiments | Apache-2.0 (ours) | Generated |

Avoid: Bosch Production Line (Kaggle competition rules, not CC), Microsoft Azure PdM Kaggle re-host (licence unstated).

### 10.1 Data model (core tables)

- `assets` (id, type, line, aas_id, fidelity, 3d_model_ref)
- `telemetry` (hypertable: time, asset_id, sensor, value, quality)
- `waveforms` (time, asset_id, channel, sample_rate, blob_ref)
- `events` (time, asset_id, kind: state_change | alarm | maintenance | failure, payload)
- `predictions` (id, time, asset_id, model_version, health, p_fail_by_mode, rul_point, rul_low, rul_high, confidence_label, drift_flag)
- `explanations` (id, prediction_id, method, attributions_json, counterfactual_json, template_text, llm_text, audit_json)
- `explanation_feedback` (id, explanation_id, user, verdict, reason, time)
- `work_orders` (id, asset_id, type, priority, tasks, technician, planned_start, planned_end, actual_start, actual_end, status, explanation_id)
- `kpis` (time, scope, name, value, formula_version)
- `voice_sessions` / `voice_actions` (transcript, intent_json, tier, confirmed, outcome, latencies)
- `models` (version, dataset_hash, params, metrics_json, onnx_ref, explainer_ref, calibrator_ref)

---

## 11. Open-Source Technology Stack (verified September 2026)

| Layer | Primary choice | Licence | Alternative | Notes |
|---|---|---|---|---|
| Twin store | Eclipse Ditto 3.9 | EPL-2.0 | ThingsBoard CE 4.3 (Apache-2.0) | Ditto needs MongoDB (SSPL; unmodified use as a database is fine) |
| Asset descriptions | basyx-python-sdk / aas-core3.0-python | MIT | Eclipse BaSyx Java V2 (EPL-2.0), FA³ST (Apache-2.0) | AASX Package Explorer (Apache-2.0, Windows) for authoring |
| Messaging | Eclipse Mosquitto 2.1 | EPL/EDL | NATS JetStream (Apache-2.0) | Sparkplug B via Eclipse Tahu (EPL-2.0) |
| OPC UA / Modbus | opcua-asyncio 2.x, pymodbus 3.x | LGPL-3 / BSD-3 | open62541 (MPL-2.0) | |
| Soft PLC | OpenPLC Runtime v4 | MIT | — | v3 was GPL and is EOL |
| Simulation | SimPy 4.1, NumPy, SciPy | MIT / BSD | NASA ProgPy models | |
| Database | PostgreSQL 18 + TimescaleDB Community | PostgreSQL Licence + Apache/TSL | QuestDB 10 (Apache-2.0), InfluxDB 2 OSS (MIT) | TSL features free to self-host; cannot be resold as DBaaS |
| Cache / queue | Valkey 8 | BSD-3 | Redis 8 (AGPL) | |
| Backend | FastAPI 0.14x, Celery 5.6 | MIT / BSD | Django 6.1 | |
| Auth | Keycloak 26 | Apache-2.0 | — | |
| ML | scikit-learn 1.9, XGBoost 3.4, LightGBM 4.6, PyTorch 2.9, tsfresh, River, PyOD, Darts | BSD / Apache / MIT | NeuralForecast | Avoid Merlion (archived), Prophet (maintenance mode) |
| Survival / physics | lifelines 0.30, NASA ProgPy 1.8 | MIT / NOSA 1.3 | scikit-survival (GPL-3) | |
| Uncertainty | MAPIE 1.x, crepes | BSD-3 | — | |
| XAI | SHAP 0.52, InterpretML 0.7, DiCE 0.11, Captum 0.9, Quantus | MIT / BSD | ELI5 (MIT), dalex (GPL-3) | Avoid Alibi ≥ 0.9.6 (BSL) |
| Experiment tracking | MLflow | Apache-2.0 | own JSON registry | |
| Scheduling | Google OR-Tools | Apache-2.0 | PuLP + CBC (MIT/EPL) | |
| STT | faster-whisper 1.2, whisper.cpp 1.9 | MIT | Vosk (Apache), Parakeet-TDT-0.6b-v3 (CC BY 4.0 weights, GPU), Moonshine (MIT) | |
| Wake word | openWakeWord (self-trained model) | Apache-2.0 code | none (push-to-talk) | Bundled models are CC BY-NC-SA |
| TTS | Kokoro-82M via sherpa-onnx | Apache-2.0 | Piper 1.8 (GPL-3 fork, MIT voices), MeloTTS (MIT) | |
| Voice pipeline | Pipecat | BSD-2 | LiveKit Agents (Apache-2.0) | Vocode is dormant |
| NLU / LLM | Ollama 0.33 + Qwen3-4B / Gemma 4 e4b | MIT + Apache-2.0 | Phi-4-mini (MIT), Mistral Apache checkpoints | Avoid Llama (community licence, not OSI) |
| Rule NLU | spaCy 3.8, rapidfuzz | MIT | Rasa OSS 3.6 (Apache, maintenance mode) | |
| Frontend | React 19, Vite, TypeScript, Apache ECharts 6, React Three Fiber 9, Three.js r18x | MIT / Apache | Recharts 3, Babylon.js 8 | |
| Dashboards | Grafana OSS 13 | AGPL-3.0 | Apache Superset 6 (Apache-2.0) | Embed unmodified |
| 3D assets | Poly Haven, Sketchfab CC0 filter, Smithsonian 3D, Blender 5 | CC0 / GPL tool | own models | Check each Sketchfab model's tag |
| Reports | Jinja2, WeasyPrint 69, python-docx, matplotlib | BSD / MIT | ReportLab (BSD), Pandoc (GPL CLI) | WeasyPrint needs GTK/Pango on Windows (free) |
| Edge | ONNX Runtime 1.2x, LiteRT, whisper.cpp | MIT / Apache | OpenVINO (Apache), EdgeX Foundry 4 | |
| Containers | Docker Engine + Compose | Apache-2.0 | Podman Desktop (Apache-2.0) | |
| Object storage | Local filesystem | — | SeaweedFS (Apache-2.0), Garage (AGPL) | MinIO is effectively end-of-life |
| CI | GitHub Actions (free for public repos) | — | — | |

---

## 12. Licence Warnings (looks free, has a catch)

1. **Coqui XTTS-v2 weights** are non-commercial (CPML) and the company is defunct. Use Kokoro or Piper.
2. **Redis 7.4–7.x** are RSAL/SSPL. Use Redis ≥ 8 (AGPL) or Valkey (BSD).
3. **InfluxDB 3 Enterprise** free licence is hobbyist-only; InfluxDB 3 Core has a 72-hour query window. Use TimescaleDB, QuestDB or InfluxDB 2 OSS.
4. **TimescaleDB** compression/continuous aggregates are under the Timescale Licence: free to self-host, forbidden to resell as a service.
5. **Grafana OSS** is AGPL: fine unmodified; publishing modified source is required if you modify and serve it.
6. **Picovoice Porcupine** is proprietary; Personal tier is non-commercial. Not used.
7. **openWakeWord** bundled models are CC BY-NC-SA; train your own (free Colab notebook).
8. **Rasa Pro / Developer Edition** is proprietary with a conversation cap; only Rasa OSS 3.6 (maintenance mode) is Apache.
9. **Llama 3.x / 4** use the Meta community licence (not OSI). Prefer Qwen3, Gemma 4, Mistral Apache checkpoints, Phi-4.
10. **Browser Web Speech API** sends audio to Google/Apple servers by default and is unavailable in Firefox. Not used for STT.
11. **Alibi / Alibi-Detect** moved to BSL in 2024. Not used.
12. **MinIO** repository archived April 2026. Not used.
13. **Redpanda** is BSL. Use Mosquitto/NATS/Kafka.
14. **Piper** active fork is GPL-3; run as a separate service, do not link into Apache code.
15. **Kokoro** phonemiser may pull espeak-ng (GPL-3); same isolation approach.
16. **Docker Desktop** is free only for personal use, education, or small companies; Engine/Compose are Apache.
17. **Wokwi** simulator is proprietary with a free tier. Use Renode/QEMU for MCU simulation.
18. **NASA ProgPy** NOSA is OSI-approved but GPL-incompatible; fine as an isolated service.
19. **PM4Py (AGPL), dalex (GPL), scikit-survival (GPL)** are optional and kept unmodified.
20. **ThingsBoard PE** features (Trendz, Edge, white-label) are paid; only CE is used.
21. **Datasets:** Bosch Kaggle data (competition rules) and Microsoft Azure PdM Kaggle re-host (licence unstated) are excluded; CWRU has no explicit licence but is universally used for research.
22. **Stale projects** (LIME, OmniXAI, Merlion, Vocode, PyCaret 3, Prophet) are avoided for core features.

---

## 13. Evaluation Plan and Success Metrics

### 13.1 Model metrics

| Area | Metric | Target |
|---|---|---|
| RUL (C-MAPSS) | RMSE, NASA score, 90 % interval coverage | See Section 4.5; coverage 88–92 % |
| Failure classification (AI4I, MetroPT-3) | AUC, F1, precision at fixed recall, lead time | AUC ≥ 0.96; MetroPT-3 event recall ≥ 0.9 with ≥ 2 h lead |
| Calibration | Expected Calibration Error | ≤ 0.05 |
| Anomaly | AUC on injected faults, false alarms per machine-day | ≤ 0.5 false alarms/day |

### 13.2 Explanation metrics

| Metric | How | Target |
|---|---|---|
| Faithfulness | Deletion/insertion curves (Quantus) | Report; compare SHAP vs EBM vs IG |
| Ground-truth agreement | On simulator data, does the top-1 attributed feature match the true driver? | ≥ 80 % |
| Stability | SHAP top-3 Jaccard between adjacent windows | ≥ 0.7 |
| Narration faithfulness | Rank agreement, sign agreement, hallucinated-feature rate | ≥ 90 %, ≥ 95 %, 0 % |

### 13.3 Voice metrics

| Metric | Target |
|---|---|
| Word error rate at 55 / 65 / 75 dB SNR | ≤ 10 / 15 / 25 % |
| Intent accuracy (500-utterance suite) | ≥ 92 % |
| End-to-end latency (speech end → TTS start), CPU | ≤ 3 s |
| Unconfirmed T2/T3 executions | 0 |
| False-execution rate under injected ASR noise | ≤ 1 % |

### 13.4 User study (n ≈ 20–30, within-subject)

Conditions: dashboard only; dashboard + text explanation; voice + spoken explanation. Tasks: diagnose four seeded scenarios, two with deliberately wrong predictions (to measure appropriate reliance). Instruments: SUS (or VUS/CUQ for voice), NASA-TLX, Hoffman Explanation Satisfaction and Trust scales, XEQ; objective: decision accuracy, time-to-decision, over-/under-reliance rate. Ethics: consent form, pseudonymised logs.

---

## 14. Research Paper Plan

Ranked by novelty × feasibility. All venues have a free route (arXiv preprint, or no-APC journal/conference).

| # | Working title | Core experiment | Venue (free route) | Platform feature it depends on |
|---|---|---|---|---|
| 1 | *Say Why: Voice-Delivered Explanations for Remaining Useful Life Predictions: a Controlled User Study* | Section 13.4 study | PHM Society Conference / IJPHM (open access, no APC); arXiv | FR-XAI-01, 07; FR-VN-01..07 |
| 2 | *Faithful or Fluent? Auditing LLM Narratives of SHAP Attributions in Predictive Maintenance* | 500+ narrations × 3 open LLMs, with/without constrained prompting; rank/sign/hallucination metrics | World Conference on Explainable AI (Springer CCIS) or IJPHM; arXiv | FR-XAI-07 |
| 3 | *Ground-Truth Explanations from Physics-Based Digital Twins: Benchmarking SHAP, Grad-CAM and Counterfactuals for RUL* | Simulator datasets with known drivers; Quantus metrics; temporal stability | PHM Society / arXiv | FR-SIM-02, 09; FR-XAI-08 |
| 4 | *Ask the Twin: Natural-Language What-If Scenarios over a Stochastic Degradation Digital Twin* | Intent → Monte-Carlo → narrated RUL shift; latency and comprehension | *Digital Twin* (Taylor & Francis, open access, no APC) / IEEE ETFA | FR-DT-09 |
| 5 | *Read-Back and Risk Tiers: A Confirmation Protocol for Voice-Commanded Digital Twin Actions* | False-execution rate under noise sweeps, completion time vs baseline | IEEE INDIN / ETFA; arXiv | FR-VN-07, 09 |
| 6 | *Hinglish on the Shop Floor: Noise-Robust Code-Mixed Intent Recognition for PdM Assistants* | Whisper fine-tune with machine noise; per-SNR WER and intent F1 | Interspeech / ICASSP workshop; arXiv | FR-VN-09, 10 |
| 7 | *Explaining Degradation through Energy: Linking ISO 22400/50001 KPIs to RUL Explanations in a Digital Twin* | Energy features ablation, SHAP ranking of energy features | IEEE ETFA / *Energies* | FR-EN-04 |
| 8 | *How Expensive Is "Why"? Latency and Energy of On-Device SHAP for Vibration PdM on Raspberry Pi* | ONNX inference vs explanation latency/energy | TinyML workshops / *Discover IoT* | FR-EDGE-02 |
| 9 | *An Open-Source ISO 23247-Aligned Digital Twin with Explainable and Conversational Access: Reference Implementation* | Architecture, reproducibility, latency budget | *Digital Twin* (open access) / SoftwareX | Whole platform |

Recommended first two: Paper 2 (needs only the XAI + narration modules and no human subjects) and Paper 1 (flagship).

---

## 15. Target Company Relevance Map

| Company | Their current stack (from Section 3) | What in TwinVoice speaks to them |
|---|---|---|
| Siemens | Insights Hub, Senseye, Industrial Copilot, AAS champion | AAS-native twin, offline copilot with attributions, cold-start reduction |
| Bosch | Nexeed, AAS/Catena-X, acquired Uptake 2026 | AAS submodels, on-prem edge, explainable PdM |
| BMW / Mercedes-Benz / VW Group | Omniverse-based factory twins, Siemens/ABB stacks | Lightweight web 3D twin with analytics inside, energy KPIs per line, voice on the shop floor |
| Continental / Schaeffler | Schaeffler runs Siemens Industrial Copilot; bearings are Schaeffler's core product | Bearing degradation physics, envelope-spectrum features, edge vibration inference |
| ABB | Genix, Genix Copilot (cloud GPT-4) | Local LLM copilot grounded in twin state; calibrated confidence |
| Schneider Electric | EcoStruxure energy focus, AVEVA predictive | Energy-aware PdM, ISO 50001 KPIs inside the twin |

---

## 16. Roadmap and Milestones

| Phase | Weeks | Deliverables |
|---|---|---|
| 0 Setup | 1–2 | Repo, docker compose skeleton (Mosquitto, PostgreSQL/Timescale, Ditto, FastAPI, React), dataset download scripts, licence check in CI |
| 1 Simulator + Twin | 3–6 | 5 machine types, degradation models, Sparkplug B publishing, Ditto twins, AAS submodels, basic dashboard (FR-MM-01/02, FR-SIM-01..06, FR-DT-01..03) |
| 2 PdM engine | 7–10 | Feature pipeline, anomaly, failure classification, RUL with MAPIE intervals, benchmark runner reproducing C-MAPSS/AI4I numbers (FR-PM-*) |
| 3 XAI layer | 11–13 | SHAP/EBM/DiCE, reason cards, template narration, faithfulness audit, explanation metrics (FR-XAI-*) |
| 4 VoiceNav | 14–17 | STT/TTS, hybrid router, confirmation protocol, intent test suite, dashboard navigation (FR-VN-*, FR-NL-*) |
| 5 Analytics, scheduling, reports | 18–20 | OEE/energy KPIs, OR-Tools scheduler, PDF reports with spoken summary (FR-PA-*, FR-EN-*, FR-MS-*, FR-RP-*) |
| 6 3D + what-if | 21–23 | React Three Fiber twin overlays, replay, "Ask the twin" (FR-DT-06..09) |
| 7 Evaluation + papers | 24–30 | Paper 2 experiments, user study (Paper 1), edge latency study, submissions |

---

## 17. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Local LLM too slow on CPU | Voice latency > 3 s | Deterministic spaCy router handles 80 % of commands; use Qwen3-0.6B/1.7B for routing, larger model only for narration; cache narrations |
| Whisper accuracy in noise | Wrong intents | Noise augmentation, domain hot-words, fuzzy asset matching, confirmation protocol as safety net |
| SHAP on sequence models is slow | Explanation latency | TreeSHAP on GBM as primary; DeepSHAP batched and cached; explanation computed asynchronously with "pending" state |
| Simulator unrealistic | Weak external validity | Replay real datasets (MetroPT-3, C-MAPSS, IMS) through the same pipeline; document physics sources |
| Scope too large for the team | Missed milestones | Priorities M/S/C; phases 1–4 alone produce a publishable system |
| Licence drift in dependencies | Zero-cost promise broken | Automated licence scan in CI against allow-list |
| User-study recruitment | Underpowered study | n = 20 with within-subject design; students as proxy technicians, clearly stated as limitation |
| WeasyPrint on Windows needs GTK | Report build fails | Run report service in Docker (Linux) |

---

## 18. Glossary

- **AAS**: Asset Administration Shell, the Industry 4.0 standard digital description of an asset (IDTA).
- **C-MAPSS**: NASA turbofan degradation simulation dataset, the standard RUL benchmark.
- **Conformal prediction**: distribution-free method producing prediction intervals with guaranteed coverage.
- **Counterfactual explanation**: minimal change to inputs that flips the prediction.
- **DTDL**: Digital Twins Definition Language (Microsoft Azure).
- **EBM**: Explainable Boosting Machine, a glass-box additive model (InterpretML).
- **ISO 22400**: KPI definitions for manufacturing operations management (OEE, MTBF, etc.).
- **ISO 23247**: Digital twin framework for manufacturing (four-layer reference architecture).
- **ISO 50001**: Energy management systems standard.
- **NGSI-LD**: ETSI context information API used by FIWARE.
- **OEE**: Overall Equipment Effectiveness = Availability × Performance × Quality.
- **RUL**: Remaining Useful Life.
- **SHAP**: SHapley Additive exPlanations, feature attribution method.
- **Sparkplug B**: MQTT topic/payload specification for industrial data.
- **STT / TTS**: Speech-to-text / text-to-speech.
- **XAI**: Explainable Artificial Intelligence.

---

## 19. Appendix A: Voice Command Grammar

| Intent | Tier | Example utterances | Slots | Response |
|---|---|---|---|---|
| `get_machine_status` | T0 | "How is compressor two?", "Status of CNC three", "Kya haal hai conveyor one ka?" | asset | health, RUL with interval, top driver, alarms |
| `explain_prediction` | T0 | "Why?", "Why is it flagged?", "What's causing that?" | asset (from context) | top-3 attributions in words, confidence reason |
| `get_counterfactual` | T0 | "What would fix it?", "How do I extend its life?" | asset, target (optional) | actionable changes and expected RUL gain |
| `run_what_if` | T1 | "What if we reduce load to 80 percent?", "What if we service it next week instead?" | asset, parameter, value | before/after RUL distribution, cost, energy |
| `list_alarms` | T0 | "Any alarms on line one?", "What's critical right now?" | scope, severity | list |
| `acknowledge_alarm` | T2 | "Acknowledge the alarm on press four" | alarm | read-back → confirm |
| `create_work_order` | T2 | "Schedule bearing replacement for compressor two on Friday morning" | asset, task, date/time, technician (optional) | read-back → confirm → order ID |
| `get_kpi` | T0 | "What's the OEE of line two this week?", "Biggest energy consumer today?" | kpi, scope, period | value with formula on screen |
| `generate_report` | T2 | "Generate the weekly maintenance report", "Incident report for the press failure" | type, scope, period | read-back → confirm → spoken summary, link |
| `set_simulation_scenario` | T1/T3 | "Inject a bearing fault on conveyor one", "Speed up time ten x" | scenario, asset | read-back for T3 |
| `navigate_dashboard` | T0 | "Open compressor two", "Show energy for line one", "Go back" | view, asset, period | UI changes |
| `give_feedback` | T2 | "That explanation is wrong, sensor four is faulty" | explanation (context), verdict, reason | logged, confirmed verbally |
| `help` | T0 | "What can you do?" | — | list of capabilities |
| `repeat` / `cancel` / `confirm` | control | — | — | — |

Confirmation phrasing (T2): "Creating work order: **replace bearing** on **compressor two**, **Friday 20 September 08:00**, assigned to **Ravi**. Say *confirm* or *cancel*." Only the exact words "confirm" / "yes, confirm" (and Hindi equivalents "haan, confirm") execute.

---

## 20. Appendix B: Explanation Templates

**Status (T0):**
"{asset} is at health {health} percent. Estimated remaining useful life is {rul} {unit}, ninety percent range {low} to {high}. Confidence {confidence_label}. {n_alarms} active alarms."

**Why (top-3 SHAP):**
"The main reason is {feature_1} at {value_1} {unit_1}, which is {direction_1} than normal and accounts for {share_1} percent of the risk. Second, {feature_2} … Third, {feature_3} …"

**Confidence reason:**
"Confidence is {label} because {reasons: interval width | model disagreement | sensor quality | drift}."

**Counterfactual:**
"If {feature} were reduced from {current} to {target} {unit}, the predicted remaining life would rise from {rul} to {rul_cf} {unit}. This is achievable by {action from knowledge base}."

**Faithfulness audit rules for LLM paraphrase:** (1) the three feature names mentioned must be the top-3 by absolute SHAP; (2) each direction word must match the sign; (3) any number must match the JSON within 5 %; (4) no feature outside the schema; (5) no recommendation not present in the reason card. Any violation → use template text and log the failure.

---

## 21. Appendix C: References

### Market / product sources (accessed September 2026)
- Siemens Insights Hub, Senseye, Industrial Copilot press releases and blog (siemens.com, press.siemens.com, blog.siemens.com).
- GE Vernova SmartSignal documentation Q2 2026; ARC Advisory blog on SmartSignal roadmap.
- PTC subscription-only notice (community.ptc.com), ThingWorx Analytics licensing article CS271439; Automation World "Beyond the black box of predictive maintenance".
- Microsoft Learn: Azure Digital Twins overview and models; Azure IoT Operations pricing; ZEISS Digital Innovation blog on ADT learning curve.
- AWS blogs: Monitron and Lookout for Equipment retirement notices; AWS service availability notice October 2025.
- Bosch Nexeed documentation; Bosch IoT Suite discontinuation notice; Bosch press release on Uptake acquisition (March 2026).
- ABB Genix and Omniverse announcement (April 2026); Microsoft customer story on Genix Edge.
- Schneider Electric Machine Expert Twin; AVEVA Predictive Analytics and AI Assistant pages.
- Rockwell FactoryTalk GuardianAI user manual and product page; FactoryTalk Energy Manager.
- Augury alternatives analyses (f7i.ai, tractian.com); rfp.wiki and machinecdn pricing estimates (third-party).
- C3 AI Reliability product page; C3 AI 10-Q (SEC, January 2026).
- IBM Maximo Predict documentation; Maximo licensing analyses (redresscompliance, facilio).
- Eclipse Ditto overview and 3.9.0 release notes; Eclipse BaSyx wiki; ThingsBoard CE vs PE; OpenTwins GitHub and Computers in Industry paper; NASA ProgPy GitHub.
- TU Delft: "Concept of a voice-enabled digital assistant for predictive maintenance" (2020).

### Academic sources
- Cummins et al., "Explainable Predictive Maintenance: A Survey", IEEE Access 2024 (arXiv 2401.07871).
- Solís-Martín et al., "On the Soundness of XAI in PHM", 2023 (arXiv 2303.05517).
- Kobayashi & Alam, "Explainable, Interpretable & Trustworthy AI for Intelligent Digital Twin: RUL case study", 2023 (arXiv 2301.06676).
- Jutte et al., "C-SHAP for time series", 2025/2026 (arXiv 2504.11159).
- Karazian et al., "SurvCF(t): Counterfactual explanations for survival analysis in PdM", July 2026 (arXiv 2607.16969).
- Cao et al., "Implementation of ISO 23247 for digital twins of production systems", 2025 (arXiv 2508.14580).
- Eichelberger et al., "Digital twin and the Asset Administration Shell", Software & Systems Modeling 2024/25.
- Ismail et al., "A systematic review of digital twin-driven predictive maintenance", 2025 (arXiv 2509.24443).
- Robles, Martín, Díaz, "OpenTwins", Computers in Industry 152, 2023.
- Bousdekis et al., "Augmented intelligence with voice assistance and AutoML in Industry 5.0", Frontiers in AI 2025.
- Mukherjee et al., "A LLM-based voice user interface for voice dialogues between user and industrial machines", Procedia CIRP 134, 2025.
- "Technician 5.0: Hybrid framework integrating chatbot, digital twin and ML for human-centric PdM", Springer 2025/26.
- Gill et al., "Leveraging LLM agents and digital twins for fault handling in process plants", 2025 (arXiv 2505.02076).
- Xia, "Integrating LLM agents with digital twins for industrial autonomous systems", 2026 (arXiv 2606.20761).
- Figliè et al., "Comparing LLM-based conversational and graphical interfaces for industrial decision tasks", 2026 (arXiv 2605.31224).
- "Evaluating several ASR systems in environmental and industrial noise", Springer 2025; Biswas et al., Whisper for Hindi-English code-mix, Interspeech 2025.
- FedCMAPSS benchmark, August 2026 (arXiv 2608.26433); TinyML bearing diagnosis on ESP32-S3, Science China Tech. Sci. 2025.
- Zeynivand et al., "Digital twin-based energy efficiency monitoring and failure analysis", Journal of Manufacturing Systems 83, 2025.
- Hoffman et al., "Measures for explainable AI", Frontiers in Computer Science 2023; Wijekoon et al., "XEQ scale", 2024 (arXiv 2407.10662).
- TTSNet (Sensors 2025), TransKAN (2025), Bi-cLSTM (arXiv 2603.00745, 2026), MKDPINN (arXiv 2504.13797) for C-MAPSS state of the art.
- Quantus XAI evaluation toolkit; F-Fidelity (arXiv 2410.02970).

### Standards
- ISO 23247 parts 1–4 (2021) and 5–6 (2024–2026); NIST analysis of ISO 23247.
- ISO 22400-1/-2 manufacturing KPIs; ISO 50001 energy management.
- IDTA Asset Administration Shell specifications; Eclipse Sparkplug 3.0; OPC UA companion specifications (ISA-95, Machinery); MTConnect 2.5.
