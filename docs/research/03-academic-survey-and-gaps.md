# Academic Survey: Voice-Driven Industrial Digital Twin + Predictive Maintenance + XAI (state of the art as of September 2026)

Method: 32 WebSearch/WebFetch calls, prioritising 2023–2026 arXiv / IEEE / Elsevier / MDPI / Springer / Frontiers / PHM Society. Surveys located first, then specific works. Where a claim rests on an abstract or search snippet only, it is noted.

---

## THEME 1 — Explainable AI for Predictive Maintenance (XAI-PdM)

### Key papers
1. **Explainable Predictive Maintenance: A Survey of Current Methods, Challenges and Opportunities** — Cummins, Sommers, Ramezani, Mittal, Jabour, Seale, Rahimi — 2024 — IEEE Access 12:57574–57602 (OA) — https://arxiv.org/abs/2401.07871 — PRISMA survey; SHAP/LIME dominate, few comparative evaluations, no standard explanation-quality metric, little end-user validation.
2. **On the Soundness of XAI in Prognostics and Health Management (PHM)** — Solís-Martín, Galán-Páez, Borrego-Díaz — 2023 — arXiv 2303.05517 — https://arxiv.org/abs/2303.05517 — Evaluates saliency XAI on DCNN RUL regressor (C-MAPSS); Grad-CAM most robust; time-series *regression* XAI understudied.
3. **Explainable, Interpretable & Trustworthy AI for Intelligent Digital Twin: Case Study on RUL** — Kobayashi & Alam — 2023 — arXiv 2301.06676 — https://arxiv.org/pdf/2301.06676 — First explicit XAI-in-DT-for-RUL framing; SHAP/LIME on C-MAPSS; mostly conceptual.
4. **C-SHAP for time series: high-level temporal explanations** — Jutte, Ahmed, Linssen, van Keulen — 2025 (v2 Apr 2026) — arXiv 2504.11159 — https://arxiv.org/abs/2504.11159 — Concept-level SHAP over temporal patterns; PdM case.
5. **SurvCF(t): Counterfactual Explanations for Survival Analysis in PdM Multivariate Time Series** — Karazian, Papapetrou, Magnússon, Frisk, Lindgren — Jul 2026 — arXiv 2607.16969 — https://arxiv.org/abs/2607.16969 — Minimal, plausible, temporally-consistent counterfactuals; C-MAPSS, N-CMAPSS, Scania Component_X.
6. **Application of SHAP-based explainable ML in RUL prediction for aircraft engine systems** — 2026 — Int. J. Machine Learning & Cybernetics — https://link.springer.com/article/10.1007/s13042-026-03246-7.
7. **Explainable AI for predictive maintenance: A review and standardized evaluation framework** — 2025 — (ResearchGate 398123644) — confirms "absence of robust explanation assessment measures".
8. **Vibration spectrogram analysis for bearing fault diagnosis based on Grad-CAM** — 2024 — J. Mech. Sci. Tech. — https://link.springer.com/article/10.1007/s12206-024-1010-3.
9. Supporting: F-Fidelity (arXiv 2410.02970), Quantus toolkit (30+ metrics), "Enhancing the Interpretability of SHAP Values Using LLMs" (arXiv 2409.00079), ContextualSHAP (arXiv 2512.07178).

### Metrics used in XAI-RUL work
RMSE, NASA/Saxena asymmetric scoring function (PHM08 score), MAE/R²; explanation quality (rarely): faithfulness correlation, PGI/deletion-insertion, sensitivity/stability, sparsity, plausibility.

### Gaps
- Almost no comparative studies with explanation-quality metrics on PdM benchmarks.
- Time-series regression (RUL) XAI under-evaluated.
- Very few studies test explanations with actual technicians; none deliver explanations verbally.
- Explanation stability across sliding windows has no standard benchmark.
- Counterfactual XAI for RUL just appeared (2026) — open field.

---

## THEME 2 — Industrial Digital Twins

### Key papers
1. **Implementation of ISO 23247 for digital twins of production systems** — Cao, Söderlund, Fang, Chen, Erdal et al. — Aug 2025 — arXiv 2508.14580 — Real-time ISO 23247 DT on a lab drone factory; AI integration and environmental KPIs are "next stages".
2. **Digital twin and the asset administration shell** — Eichelberger, Niederée et al. — 2024/25 — Software & Systems Modeling 24(3) — https://link.springer.com/article/10.1007/s10270-024-01255-0.
3. **Digital twins in manufacturing: a taxonomy** — 2025 — Digital Twin (T&F, OA) — https://www.tandfonline.com/doi/full/10.1080/27525783.2025.2496645.
4. **A Systematic Review of Digital Twin-Driven Predictive Maintenance** — Ismail et al. — Sep 2025 — arXiv 2509.24443.
5. **OpenTwins** — Robles, Martín, Díaz — 2023 — Computers in Industry 152 — https://www.sciencedirect.com/science/article/pii/S0166361523001574 — Ditto + Kafka-ML + Grafana + Unity; no XAI, no voice.
6. **Towards a Distributed Digital Twin Framework for PdM in IIoT** — 2024 — Sensors — https://www.mdpi.com/1424-8220/24/8/2663.
7. **Residual Life Prediction of Rolling Bearings Driven by Digital Twins** — 2025 — Symmetry — https://www.mdpi.com/2073-8994/17/3/406 — simulated data "cannot fully reflect real-life degradation".
8. **Adaptive Wiener-process RUL prediction** — 2024 — PMC11367272 — Wiener/Gamma/inverse-Gaussian processes as canonical synthetic-degradation generators.
9. **Digital-Twin framework for RUL of piezoelectric vibration sensors** — 2023 — Sensors 23(19):8173.
10. Also: IIC/IDTA white paper "Digital Twin and AAS Concepts" (2024); "Continuously Updating Digital Twins using LLMs" arXiv 2506.12091; "Digital Twin AI: from LLMs to World Models" arXiv 2601.01321.

### Gaps
- ISO 23247 implementations few and lab-scale; none with XAI or voice.
- No open reproducible DT + PdM benchmark with documented stochastic degradation generators and ground-truth RUL for XAI validation.
- "What-if" simulation is GUI-driven; natural-language-triggered what-if only conceptual.
- Most "DTs" in PdM papers are actually shadows.

---

## THEME 3 — Voice / natural-language interaction in industry

### Key papers
1. **Augmented intelligence with voice assistance and AutoML in Industry 5.0** — Bousdekis et al. — 2025 — Frontiers in AI — https://www.frontiersin.org/journals/artificial-intelligence/articles/10.3389/frai.2025.1538840/full — STT/TTS assistant + AutoML at Whirlpool; SUS, VUS, NASA-TLX, intent accuracy 95.3%; **explicitly states lack of explainability approaches suited to voice interfaces as open problem**.
2. **A LLM-based voice user interface for voice dialogues between user and industrial machines** — Mukherjee, Häfner et al. — 2025 — Procedia CIRP 134:378–383 — https://www.sciencedirect.com/science/article/pii/S2212827125004925.
3. **Technician 5.0: Hybrid Framework Integrating Chatbot, Digital Twin, and ML for Human-Centric PdM** — 2025/26 — Springer — https://link.springer.com/chapter/10.1007/978-981-95-5271-9_9 — **closest existing work**; text chatbot, no voice, no XAI evaluated.
4. **Leveraging LLM Agents and Digital Twins for Fault Handling in Process Plants** — Gill et al. — 2025 — arXiv 2505.02076.
5. **Integrating LLM Agents with Digital Twins for Industrial Autonomous Systems** — Xia — Jun 2026 — arXiv 2606.20761.
6. **Comparing LLM-Based Conversational and Graphical Interfaces for Industrial Decision Tasks** — Figliè et al. — May 2026 — arXiv 2605.31224 — 20 participants; conversational reduces effort, dashboards better for overview.
7. **Factory Operators' Perspectives on Cognitive Assistants** — 2024 — arXiv 2409.20192.
8. **Safe integration of LLMs into industrial process control** — 2026 — Autonomous Intelligent Systems — https://link.springer.com/article/10.1007/s43684-026-00136-1; **Neuro-Symbolic Verification for Preventing LLM Hallucinations in Process Control** — Processes 14(2):322, 2026.
9. **Human-in-the-loop and LLMs in smart manufacturing** — 2026 — J. Manufacturing Systems.
10. **Cross-domain digital twin architecture for PdM via ML and LLMs** — 2026 — Computers & Industrial Engineering (LLM explains alarms; no voice).
11. Noise: **Evaluating several ASR systems in environmental and industrial noise** — 2025 — Springer (Whisper tested at 64–79 dB); **Context-aware data augmentation for speech command recognition in industrial environments** — 2025.
12. Multilingual: **Adapting Whisper for low-resource Hindi-English code-mix speech** — Biswas et al. — Interspeech 2025 — https://www.isca-archive.org/interspeech_2025/biswas25_interspeech.pdf.

### Done vs NOT done
Done: voice command of machine tools/cobots; LLM chat over DT; text chatbot + DT + RUL; LLM agents validated in DT sandboxes; SUS/NASA-TLX evaluation of one voice+AutoML assistant.
NOT found: (a) XAI explanations converted to spoken explanations and user-evaluated; (b) voice-triggered what-if simulation with narrated results; (c) Hindi-English shop-floor PdM assistant; (d) formal safety/confirmation protocol for voice-issued commands with evaluation; (e) noise-robustness of intent recognition for PdM vocabulary; (f) voice vs dashboard for trust calibration in PdM alerts.

---

## THEME 4 — Edge AI for PdM

1. **Edge-deployable TinyML with transfer learning for bearing fault diagnosis** — 2025 — Science China Tech. Sci. — ESP32-S3, 88.28% accuracy, 45 ms, 17.7 mJ.
2. **IoT device for detecting abnormal motor vibrations using TinyML** — 2025 — Discover IoT.
3. **From TinyML to Tiny Deep Learning: A Survey** — 2025 — arXiv 2506.18927.
4. **FedCMAPSS: Benchmark for Federated Learning in RUL Estimation** — Aug 2026 — arXiv 2608.26433.
5. **Using Federated ML in PdM of Jet Engines** — 2025 — arXiv 2502.05321.
6. **Fed-Joint** — 2025 — arXiv 2503.13404.
Gap: no work reports edge latency/energy of *explanations*; FL + XAI untouched for PdM.

---

## THEME 5 — Energy-aware PdM

1. **A novel approach to digital twin-based energy efficiency monitoring and failure analysis** — Zeynivand, Esmaili, Cristaldi, Gruosso — Dec 2025 — J. Manufacturing Systems 83:612–625 — https://www.sciencedirect.com/science/article/pii/S0278612525002572.
2. **Energy Efficiency Model-Based PdM for Induction Motor Fault Prediction Using DT** — 2023.
3. **Analysis of DT Applications in Energy Efficiency: Systematic Review** — 2025 — Sustainability 17(8):3560.
4. **Digital twin-based multi-view energy efficiency prediction for machining systems** — 2026 — Digital Twin (T&F OA).
5. Standards: ISO 50001, ISO 22400-1/-2 (34 KPIs incl. OEE, MTBF, MTTR, energy intensity).
Gap: energy signature as an explanatory feature for degradation plus ISO 22400/50001 KPI reporting via natural language is absent.

---

## THEME 6 — Benchmarks and the bar to match

**C-MAPSS (RMSE / NASA score), 2024–2026**
- TTSNet, 2025, Sensors: FD001 11.02 / 194.6; FD002 13.25 / 874.1; FD003 11.06 / 200.1; FD004 18.26 / 1968.5.
- TransKAN, 2025: FD001 11.36, FD003 11.28.
- Bi-cLSTM, Mar 2026, arXiv 2603.00745: FD002 13.96, FD004 14.25.
- Enhanced Mamba + MHA, 2025, Scientific Reports; Mamba-attention self-supervised (RESS 2025).
- MKDPINN, arXiv 2504.13797: avg RMSE 12.71, avg score 622.
- Practical bar for a student project: FD001 RMSE ≈ 11–13, score < 250; FD003 ≈ 11–13; FD002/FD004 ≈ 13–19. Simple LSTM ≈ 15–16.
**N-CMAPSS**: Bi-LSTM 2024: DS01 6.22, DS02 9.08, DS03 10.19, DS07 11.73; CruiseBench (Jul 2026, arXiv 2607.19380).
**AI4I 2020**: LightGBM AUC 0.973 with in-fold SMOTE; AI4I-PMDI (2024) harder variant.
**Bearing**: CWRU multi-label benchmark arXiv 2407.14625; leakage warning arXiv 2509.22267.

---

## THEME 7 — Human trust & evaluation instruments

1. **Hoffman, Mueller, Klein, Litman — Measures for XAI** — 2023 — Frontiers Computer Science — Explanation Satisfaction Scale, Goodness checklist, Trust scale; https://xaitk.org/capabilities/satisfaction-scale.
2. **XEQ Scale** — Wijekoon et al. — 2024/25 — arXiv 2407.10662.
3. **Trust, distrust, and appropriate reliance in (X)AI** — 2025 — Cognitive Systems Research.
4. **Towards Human-centered XAI: survey of user studies** — Rong et al. — 2023 — IEEE TPAMI.
5. **The effectiveness of XAI on human factors in trust models** — 2025 — Scientific Reports.
6. **The Right Voice for the Right Task** — 2026 — Int. J. HCI — CUQ + NASA-TLX.
Recommended bundle: SUS (or CUQ/VUS), NASA-TLX, Hoffman Satisfaction + Trust, XEQ, plus objective measures (decision accuracy, time-to-decision, appropriate-reliance rate).
Gap: no study measures explanation satisfaction for *spoken* explanations in maintenance; industrial HCI sample sizes ~20.

---

## THEME 8 — Does any 2024–2026 paper combine DT + PdM + XAI + voice/LLM?

**No paper found combining all four with an evaluated voice modality.** Closest partial overlaps: Technician 5.0 (DT + RUL + text chatbot); Bousdekis 2025 (voice + AutoML, quality control, lists voice-compatible XAI as unsolved); Cross-domain DT via ML + LLM (CIE 2026, text); Kobayashi & Alam 2023 (DT + RUL + SHAP, no interaction); Gill 2025 / Xia 2026 (LLM agents + DT, no XAI/voice); "Explainable Intelligence in Digital Twins" (Springer chapter 2026); US patent 12424205 on voice-assistant DT simulation (commercial).

---

# TOP 10 RESEARCH GAPS / PAPER OPPORTUNITIES (ranked novelty × feasibility)

1. **Spoken XAI for RUL user study.** "Say Why: Voice-Delivered Explanations for RUL Predictions — A Controlled User Study". Venue: PHM Society / IJPHM (OA, no APC); arXiv. Experiment: C-MAPSS FD001 model + SHAP & counterfactual → LLM verbalisation → TTS; within-subject n≈20–30; SUS/VUS, NASA-TLX, Hoffman, XEQ, appropriate reliance.
2. **Faithfulness of LLM-verbalised explanations.** "Faithful or Fluent? Auditing LLM Narratives of SHAP Attributions in PdM". Venue: xAI World Conference (Springer CCIS) or IJPHM. Experiment: 500 narratives across 3 open LLMs; rank/sign agreement, hallucinated-feature rate.
3. **Voice-triggered what-if simulation.** "Ask the Twin". Venue: Digital Twin (T&F OA) or IEEE ETFA. Experiment: intents → parameter change → Monte-Carlo RUL → spoken summary.
4. **Synthetic-truth XAI benchmark.** "Ground-Truth Explanations from Physics-Based Digital Twins". Venue: PHM Society / arXiv + xAI conf. Experiment: known drivers; Quantus metrics; temporal stability.
5. **Safety protocol for voice commands.** "Read-Back and Risk Tiers". Venue: IEEE INDIN / Safety Science. Experiment: risk tiers, read-back, neuro-symbolic validation; false-execution rate under noise sweeps.
6. **Noise-robust Hindi-English PdM intents.** "Hinglish on the Shop Floor". Venue: Interspeech / ICASSP workshops. Experiment: Whisper fine-tune with machine-noise; ~30 PdM intents; WER & F1 per SNR.
7. **Energy signature as explanatory channel.** "Explaining Degradation through Energy". Venue: IEEE ETFA / Energies. Experiment: power draw coupled to degradation; OEE/energy intensity; SHAP ranking.
8. **Voice vs dashboard for trust calibration.** "Does Talking to the Twin Calibrate Trust?" Venue: Int. J. HCI / IJPHM. Experiment: 2×2 modality × explanation; seeded false alarms.
9. **Edge cost of explanations.** "How Expensive Is 'Why'?" Venue: Discover IoT / TinyML workshops. Experiment: quantised model on Pi/ESP32; KernelSHAP vs DeepSHAP vs Grad-CAM latency/energy.
10. **Open reference architecture.** "An Open-Source ISO 23247-Aligned Digital Twin with Explainable and Conversational Access". Venue: Digital Twin (OA) / SoftwareX. Experiment: map components to ISO 23247; reproducibility; latency budget.

Free/OA venues: PHM Society Conference & IJPHM (no APC), arXiv, Digital Twin (T&F, OA no APC), IEEE ETFA/INDIN/ICPS (conference fee, arXiv-able), xAI World Conference (Springer CCIS), Frontiers/MDPI (APC — check waivers).
