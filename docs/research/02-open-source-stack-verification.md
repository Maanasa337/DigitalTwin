# Free / Open-Source Stack Verification (as of 17 September 2026)

Verified via ~35 web searches. "Free self-host?" means zero cost for a builder running it locally on own hardware (including commercial demo use unless noted). Data licences CC / public-domain / NASA open data with attribution are all fine for this project.

---

## 1. Datasets (predictive maintenance / RUL)

| Dataset | Version / size | License | Free? | Notes / gotchas | URL |
|---|---|---|---|---|---|
| NASA C-MAPSS (Turbofan, FD001–FD004) | 2008 release | NASA open data; attribution requested | Yes | Canonical RUL benchmark. Old ti.arc.nasa.gov links dead — use NASA PCoE page or PHM Society mirror | https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/ ; https://data.phmsociety.org/nasa/ |
| N-CMAPSS (Turbofan Data Set 2, 2021) | DS01–DS08, ~15 GB HDF5 | Same NASA terms | Yes | Realistic flight profiles; large. https://phm-datasets.s3.amazonaws.com/NASA/17.+Turbofan+Engine+Degradation+Simulation+Data+Set+2.zip | |
| PHM 2008 Challenge | 2008 | NASA open data | Yes | Test RUL labels not public | https://data.nasa.gov/dataset/phm-2008-challenge |
| AI4I 2020 (UCI #601) | 10,000 rows, 5 failure modes | CC BY 4.0 | Yes | Synthetic milling machine data; ideal for tabular XAI demos | https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset |
| Kaggle "Machine Predictive Maintenance Classification" (shivamb) | same as AI4I | CC0 | Yes | Re-host of AI4I 2020 | https://www.kaggle.com/datasets/shivamb/machine-predictive-maintenance-classification |
| Microsoft Azure PdM sample (Kaggle) | 100 machines, hourly telemetry | License not stated on Kaggle; original repo archived | Demo only | Treat as unknown licence for redistribution | https://www.kaggle.com/datasets/arnabbiswas1/microsoft-azure-predictive-maintenance |
| NASA IMS Bearing | 3 run-to-failure sets, 20 kHz | NASA open data | Yes | https://phm-datasets.s3.amazonaws.com/NASA/4.+Bearings.zip | https://data.nasa.gov/dataset/ims-bearings |
| CWRU Bearing | 12k/48k .mat files | No explicit licence (free for research, widely used) | Yes | Zenodo mirror https://zenodo.org/records/10987113 | https://engineering.case.edu/bearingdatacenter/download-data-file |
| FEMTO / PRONOSTIA (PHM 2012) | 17 bearings run-to-failure | NASA-repo terms | Yes | https://phm-datasets.s3.amazonaws.com/NASA/10.+FEMTO+Bearing.zip | |
| NASA Milling | 16 tools, 167 runs | NASA open data | Yes | Tool-wear regression; PyPHM loader | https://data.nasa.gov/dataset/milling-wear |
| MetroPT-3 (UCI #791) | Metro train APU, 15 sensors | CC BY 4.0 | Yes | Real industrial compressor data with failure reports | https://archive.ics.uci.edu/dataset/791/metropt+3+dataset |
| Hydraulic systems (UCI #447) | 17 sensors, 2,205 cycles | CC BY 4.0 | Yes | Multi-target condition classification | https://archive.ics.uci.edu/dataset/447/condition+monitoring+of+hydraulic+systems |
| SECOM (UCI #179) | 1,567 × 590 | CC BY 4.0 | Yes | Semiconductor pass/fail | https://archive.ics.uci.edu/dataset/179/secom |
| Tennessee Eastman (Rieth et al.) | 20 faults | CC0 | Yes | Process-fault detection | https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/6C3JR1 |
| Bosch Production Line (Kaggle) | 14.3 GB | Kaggle competition rules — not CC | Personal/research only | Avoid for anything shipped | https://www.kaggle.com/c/bosch-production-line-performance |

---

## 2. Sensor simulation / digital-twin core

| Tool | Version | License | Free self-host? | Notes | URL |
|---|---|---|---|---|---|
| Eclipse Ditto | 3.9.0 (May 2026) | EPL-2.0 | Yes | Digital-twin "Things" API, MQTT/Kafka/AMQP, policies. Needs MongoDB | https://eclipse.dev/ditto/ |
| Eclipse BaSyx | V2 line, active | EPL-2.0 / MIT (python-sdk) | Yes | AAS-based I4.0 middleware; heavier than Ditto | https://eclipse.dev/basyx/ |
| OpenTwins | main branch | Apache-2.0 | Yes | Ditto + Kafka + InfluxDB + Grafana + Kubeflow; "not for production" | https://github.com/ertis-research/opentwins |
| ThingsBoard CE | 4.3 (Jan 2026) | Apache-2.0 (CE only) | Yes | PE (paid) adds white-labeling, LoRaWAN, reporting, advanced RBAC, Edge, Trendz | https://thingsboard.io/ce-vs-pe-diff/ |
| Node-RED | 5.0.7 (Sep 2026) | Apache-2.0 | Yes | Flow-based wiring | https://nodered.org/ |
| SimPy | 4.1.1 | MIT | Yes | Discrete-event simulation | https://simpy.readthedocs.io/ |
| Eclipse Mosquitto | 2.1 (Oct 2025) | EPL-2.0 / EDL-1.0 | Yes | MQTT 5 broker; Windows installer | https://mosquitto.org/ |
| Eclipse Paho (Python) | paho-mqtt 2.1 | EPL / EDL | Yes | 2.x has breaking callback API | https://github.com/eclipse-paho/paho.mqtt.python |
| open62541 (OPC UA, C) | 1.5.5 (Jul 2026) | MPL-2.0 | Yes | | https://open62541.org/ |
| opcua-asyncio (asyncua) | 2.0.1 | LGPL-3.0 | Yes | Python OPC UA client+server | https://github.com/FreeOpcUa/opcua-asyncio |
| Eclipse Milo (Java) | 1.1.5 | EPL-2.0 | Yes | | https://github.com/eclipse-milo/milo |
| pymodbus | 3.15.0 | BSD-3 | Yes | TCP/RTU simulators | https://github.com/pymodbus-dev/pymodbus |
| Apache Kafka | 4.3.1 | Apache-2.0 | Yes | KRaft-only; heavy for demo | https://kafka.apache.org/ |
| Redpanda Community | 25.x | BSL 1.1 (not OSI) | Free, not OSS | | https://docs.redpanda.com/current/get-started/licensing/overview/ |
| NATS Server | 2.12.x | Apache-2.0 (CNCF) | Yes | Lightweight alt to Kafka | https://nats.io/ |

---

## 3. Time-series storage

| Tool | Version | License | Free self-host? | Notes | URL |
|---|---|---|---|---|---|
| InfluxDB 3 Core | 3.x GA | MIT OR Apache-2.0 | Yes | Single node, ~72-hour query window by design | https://github.com/influxdata/influxdb |
| InfluxDB 3 Enterprise | 3.x | Proprietary; free "at-home" licence only | Not for commercial | | https://docs.influxdata.com/influxdb3/which-influxdb-3/ |
| InfluxDB 2 OSS | 2.7.x | MIT | Yes | Still maintained; safest Influx choice for unlimited history | https://docs.influxdata.com/influxdb/v2/ |
| TimescaleDB (TigerData) | 2.2x | Apache-2.0 core + Timescale License (TSL) for compression, continuous aggregates, retention | Yes — Community Edition free; cannot resell as DBaaS | Use `timescale/timescaledb-ha` image | https://www.tigerdata.com/legal/licenses |
| PostgreSQL | 18.6 | PostgreSQL License | Yes | | https://www.postgresql.org/ |
| QuestDB | 10.x | Apache-2.0 | Yes | ILP ingest, SQL, Grafana plugin | https://questdb.com/ |
| ClickHouse | 26.8 LTS | Apache-2.0 | Yes | OLAP; overkill for single-machine demo | https://clickhouse.com/ |
| VictoriaMetrics | 1.13x | Apache-2.0 | Yes | Prometheus-compatible | https://victoriametrics.com/ |

---

## 4. Dashboards / visualization / 3D

| Tool | Version | License | Free? | Notes | URL |
|---|---|---|---|---|---|
| Grafana OSS | 13.2.2 (Sep 2026) | AGPL-3.0 | Yes | Fine to self-host/embed unmodified; AGPL obligations only if modified and served | https://grafana.com/grafana/download |
| Apache Superset | 6.1.0 | Apache-2.0 | Yes | | https://superset.apache.org/ |
| Three.js | r184 | MIT | Yes | | https://threejs.org/ |
| React Three Fiber | 9.3.0 | MIT | Yes | React 19 required | https://github.com/pmndrs/react-three-fiber |
| Babylon.js | 8.56 | Apache-2.0 | Yes | | https://www.babylonjs.com/ |
| Recharts | 3.9.1 | MIT | Yes | | https://recharts.org/ |
| Apache ECharts | 6.0 | Apache-2.0 | Yes | Best for dense industrial charts | https://echarts.apache.org/ |
| Plotly.js | 3.x | MIT | Yes | | https://github.com/plotly/plotly.js |
| Blender | 5.x | GPL-2.0+ | Yes | Output models are yours | https://www.blender.org/ |
| Poly Haven | — | CC0 | Yes | | https://polyhaven.com/license |
| Sketchfab (CC0 filter) | — | CC0 / CC-BY per model | Yes | Verify each model's tag | https://sketchfab.com/tags/cc0 |
| Free CC0 Industrial 3D Models (itch.io) | 12 props | CC0 | Yes | | https://3dmodelscc0.itch.io/free-cc0-industrial-3d-models |
| Smithsonian Open Access 3D | — | CC0 | Yes | Historic machines | https://3d.si.edu/ |

---

## 5. ML / predictive maintenance

| Tool | Version | License | Notes | URL |
|---|---|---|---|---|
| scikit-learn | 1.9.x | BSD-3 | | https://scikit-learn.org/ |
| XGBoost | 3.4.1 | Apache-2.0 | Native SHAP | https://xgboost.ai/ |
| LightGBM | 4.6.0 | MIT | | https://lightgbm.readthedocs.io/ |
| PyTorch | 2.9.1 | BSD-3 | CPU works | https://pytorch.org/ |
| TensorFlow | 2.21 | Apache-2.0 | TFLite deprecated → LiteRT | https://www.tensorflow.org/ |
| River (online ML) | 0.25.0 | BSD-3 | Streaming drift/anomaly | https://riverml.xyz/ |
| tsfresh | 0.21.2 | MIT | Feature extraction | https://github.com/blue-yonder/tsfresh |
| sktime | 1.1.0 | BSD-3 | | https://www.sktime.net/ |
| Darts | 0.44.1 | Apache-2.0 | Forecasting + anomaly | https://github.com/unit8co/darts |
| PyOD | 3.6.x | BSD-2 | 60+ detectors | https://github.com/yzhao062/pyod |
| Merlion | 2.0.2 — archived Mar 2026 | BSD-3 | Avoid | https://github.com/salesforce/Merlion |
| NeuralForecast | 3.x | Apache-2.0 | N-BEATS/TFT/PatchTST | https://github.com/Nixtla/neuralforecast |
| Prophet | 1.4.x — maintenance mode | MIT | Stagnant | https://github.com/facebook/prophet |
| PyCaret | 3.4.0 frozen | MIT | Churn risk | https://github.com/pycaret/pycaret |
| lifelines | 0.30.3 | MIT | Survival/RUL | https://lifelines.readthedocs.io/ |
| scikit-survival | 0.28.0 | GPL-3.0 | Random survival forests | https://scikit-survival.readthedocs.io/ |
| NASA ProgPy | 1.8 (May 2025) | NOSA 1.3 (OSI-approved, GPL-incompatible) | Physics-based prognostics; 2024 NASA Software of the Year | https://github.com/nasa/progpy |
| PyPHM | GitHub only | MIT | Loaders for Milling, IMS | https://github.com/tvhahn/PyPHM |

---

## 6. Explainable AI + conformal

| Tool | Version | License | Notes | URL |
|---|---|---|---|---|
| SHAP | 0.52.0 (May 2026) | MIT | Python ≥3.12 | https://github.com/shap/shap |
| LIME | 0.2.0.1 — unmaintained | BSD-2 | Prefer SHAP | https://github.com/marcotcr/lime |
| Captum | 0.9.0 | BSD-3 | PyTorch attribution | https://github.com/meta-pytorch/captum |
| InterpretML (EBM) | 0.7.x | MIT | Glass-box models | https://interpret.ml/ |
| DiCE | 0.11 | MIT | Counterfactuals | https://github.com/interpretml/DiCE |
| Alibi / Alibi-Detect | ≤0.9.6 Apache-2.0; from Jan 2024 BSL 1.1 | NOT free for production | Pin 0.9.6 or skip | https://pypi.org/project/alibi/ |
| ELI5 (eli5-org fork) | 0.15/0.16 | MIT | | https://github.com/eli5-org/eli5 |
| TimeSHAP | 1.0.x, low activity | MIT | | https://github.com/feedzai/timeshap |
| OmniXAI | 1.3.2 (2024), stale | Apache-2.0 | Optional | https://github.com/salesforce/OmniXAI |
| dalex | 1.8.0 | GPL-3.0 | | https://dalex.drwhy.ai/python/ |
| MAPIE | 1.4.x | BSD-3 | Conformal intervals | https://github.com/scikit-learn-contrib/MAPIE |
| crepes | 0.9.1 | BSD-3 | Conformal predictive systems | https://github.com/henrikbostrom/crepes |

---

## 7. Voice

| Tool | Version | License | Free/offline? | Notes | URL |
|---|---|---|---|---|---|
| OpenAI Whisper (incl. large-v3-turbo) | 20250625 | MIT (code + weights) | Yes | | https://github.com/openai/whisper |
| faster-whisper | 1.2.1 | MIT | Yes | CTranslate2, INT8 on CPU | https://github.com/SYSTRAN/faster-whisper |
| whisper.cpp | 1.9.4 | MIT | Yes | | https://github.com/ggml-org/whisper.cpp |
| Vosk | 0.3.x | Apache-2.0 | Yes | Tiny models, streaming | https://alphacephei.com/vosk/ |
| NVIDIA Parakeet-TDT-0.6b-v3 | v3 | CC-BY-4.0 weights | Yes | Top of Open ASR leaderboard; GPU preferred | https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3 |
| NVIDIA Canary-Qwen-2.5B | 2025 | CC-BY-4.0 (older canary-1b = CC-BY-NC) | Yes | Check each card | https://huggingface.co/nvidia/canary-qwen-2.5b |
| Moonshine | tiny/base | MIT | Yes | Ultra-low latency edge STT | https://huggingface.co/UsefulSensors/moonshine |
| Kyutai STT | 1B/2.6B | CC-BY-4.0 | Yes | Streaming; GPU | https://kyutai.org/next/stt/ |
| wav2vec2 | — | Apache-2.0 | Yes | Fine-tuning base | https://huggingface.co/facebook/wav2vec2-base-960h |
| SpeechBrain | 1.0.x | Apache-2.0 | Yes | | https://speechbrain.github.io/ |
| sherpa-onnx | 1.13.x | Apache-2.0 | Yes | STT+TTS+VAD+KWS in one runtime | https://github.com/k2-fsa/sherpa-onnx |
| openWakeWord | 0.6.x | Code Apache-2.0; pre-trained models CC-BY-NC-SA 4.0 | Train own model for commercial | | https://github.com/dscripka/openWakeWord |
| Picovoice Porcupine | 3.x | Proprietary SDK | Not fully free | Personal tier non-commercial | https://picovoice.ai/docs/porcupine/ |
| Piper TTS | 1.8.0 | Original MIT (archived); active fork GPL-3.0 | Yes | Fast CPU TTS | https://github.com/OHF-Voice/piper1-gpl |
| Kokoro-82M | v1.0 | Apache-2.0 weights; G2P may call espeak-ng (GPL-3) | Yes | Best quality/size ratio | https://huggingface.co/hexgrad/Kokoro-82M |
| Coqui TTS (idiap fork) | 0.27.5 | Code MPL-2.0; XTTS-v2 weights CPML non-commercial | Code yes; XTTS weights no | Company dead | https://github.com/idiap/coqui-ai-TTS |
| MeloTTS | 0.1.x | MIT | Yes | | https://github.com/myshell-ai/MeloTTS |
| espeak-ng | 1.52 | GPL-3.0 | Yes | Fallback / phonemizer | https://github.com/espeak-ng/espeak-ng |
| Browser Web Speech API | Chrome 139+ has optional on-device mode | Free; not OSS | Default streams audio to Google/Apple; Firefox lacks it | | https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API |
| Rasa Open Source | 3.6.x — maintenance mode | Apache-2.0 | Yes | | https://github.com/RasaHQ/rasa |
| Rasa Pro / Developer Edition | 3.14+ | Proprietary EULA; free key ≤1,000 conversations/month | Free but not OSS | | https://rasa.com/rasa-pro-developer-edition-license-key-request |
| spaCy | 3.8.x | MIT | Yes | | https://spacy.io/ |
| Ollama | 0.33.1 | MIT | Yes | Native tool calling | https://ollama.com/ |
| llama.cpp | rolling | MIT | Yes | | https://github.com/ggml-org/llama.cpp |
| Qwen3 / Qwen3.5 | 2025–26 | Apache-2.0 | Yes | Best small tool-callers | https://huggingface.co/Qwen |
| Gemma 4 | Apr 2026 | Apache-2.0 (Gemma 3 was custom terms) | Yes | | https://ai.google.dev/gemma |
| Phi-4 / Phi-4-mini | 2025 | MIT | Yes | | https://huggingface.co/microsoft |
| Mistral | — | Apache-2.0 for most; some MRL research-only | Check card | | https://mistral.ai/ |
| Llama 3.x / 4 | — | Llama Community License (not OSI) | Free but not OSS | | https://www.llama.com/ |
| DeepSeek R1 / V3 | — | MIT | Yes | Too large for CPU except distills | https://huggingface.co/deepseek-ai |
| Pipecat | 0.0.9x | BSD-2 | Yes | Local plugins | https://github.com/pipecat-ai/pipecat |
| LiveKit Agents | 1.x | Apache-2.0 | Yes | WebRTC; heavier | https://github.com/livekit/agents |
| Vocode | 0.1.x — dormant since Nov 2024 | MIT | Avoid | | https://github.com/vocodedev/vocode-core |

---

## 8. Backend / app

| Tool | Version | License | Notes | URL |
|---|---|---|---|---|
| FastAPI | 0.141.x | MIT | WebSockets built-in | https://fastapi.tiangolo.com/ |
| Django | 6.1 | BSD-3 | | https://www.djangoproject.com/ |
| Spring Boot | 4.1.1 | Apache-2.0 | | https://spring.io/projects/spring-boot |
| Node.js | 24.21 LTS | MIT | | https://nodejs.org/ |
| Celery | 5.6.x | BSD-3 | | https://docs.celeryq.dev/ |
| Redis | 8.x | AGPL-3.0 (OSI) since May 2025; 7.4–7.x were RSALv2/SSPL | | https://redis.io/legal/licenses/ |
| Valkey | 8.x/9.x | BSD-3 | Drop-in fork; safest | https://valkey.io/ |
| RabbitMQ | 4.3.5 | MPL-2.0 | | https://www.rabbitmq.com/ |
| Docker Engine / Compose v2 | 28.x / 2.4x | Apache-2.0 | | https://github.com/docker/compose |
| Docker Desktop (Windows) | 4.4x | Proprietary; free for personal/education/OSS/small companies | Alternatives: Podman Desktop, Rancher Desktop | https://docs.docker.com/subscription/desktop-license/ |
| Keycloak | 26.7.3 | Apache-2.0 | | https://www.keycloak.org/ |
| MinIO | community repo archived Apr 2026 | AGPL-3.0 | Effectively dead; use Garage / SeaweedFS / RustFS | https://github.com/minio/minio |
| PostgreSQL | 18.6 | PostgreSQL License | | https://www.postgresql.org/ |

---

## 9. Edge AI

| Tool | Version | License | Notes | URL |
|---|---|---|---|---|
| ONNX Runtime | 1.25/1.26 | MIT | DirectML on Windows | https://onnxruntime.ai/ |
| LiteRT (ex-TFLite) | 1.x/2.x | Apache-2.0 | | https://github.com/google-ai-edge/LiteRT |
| OpenVINO | 2026.2 | Apache-2.0 | Intel CPU/iGPU/NPU | https://github.com/openvinotoolkit/openvino |
| Eclipse Kura | 5.6.2 | EPL-2.0 | Java OSGi gateway | https://eclipse.dev/kura/ |
| EdgeX Foundry | 4.0 LTS | Apache-2.0 | Device services | https://www.edgexfoundry.org/ |
| KubeEdge | 1.23 | Apache-2.0 | Overkill for demo | https://kubeedge.io/ |
| openBalena | — | Apache-2.0; balenaCloud first 10 devices free | | https://www.balena.io/open |
| Wokwi | web + VS Code ext | Proprietary; free tier | Not OSS | https://wokwi.com/license |
| Renode / QEMU | — | MIT / GPL-2 | MCU simulation | https://renode.io/ |

---

## 10. Report generation

| Tool | Version | License | Notes | URL |
|---|---|---|---|---|
| ReportLab (open-source) | 4.4.x | BSD-3 | ReportLab PLUS is paid | https://pypi.org/project/reportlab/ |
| WeasyPrint | 69.0 | BSD-3 | Needs Pango on Windows | https://weasyprint.org/ |
| python-docx | 1.2.0 | MIT | | https://python-docx.readthedocs.io/ |
| Jinja2 | 3.1.6 | BSD-3 | | https://jinja.palletsprojects.com/ |
| Pandoc | 3.10 | GPL-2.0+ | CLI use fine | https://pandoc.org/ |
| TeX Live | 2026 | LPPL/GPL mix | | https://tug.org/texlive/ |
| matplotlib | 3.10.x | PSF-style | | https://matplotlib.org/ |

---

## 11. Process / production analytics

| Tool | Version | License | Notes | URL |
|---|---|---|---|---|
| OEE libs | No mature PyPI lib | — | Implement ISO 22400-2 formulas yourself | |
| ISO 22400 | standard is paid; formulas public | — | | https://www.iso.org/standard/54497.html |
| PM4Py | 2.7.22 | AGPL-3.0 | Process mining | https://github.com/process-intelligence-solutions/pm4py |
| OpenPLC Runtime v4 | 4.1.10 / Editor 4.2.11 | MIT (v3 was GPL-3, EOL) | IEC 61131-3 soft-PLC | https://github.com/Autonomy-Logic/openplc-runtime |
| ISA-95 | Standard paid; B2MML schemas free | — | | https://opcfoundation.org/markets-collaboration/isa-95/ |

---

## 12. Standards & AAS tooling

| Tool | Version | License | Notes | URL |
|---|---|---|---|---|
| Eclipse AASX Package Explorer & Server | 2026.02 | Apache-2.0 | Windows-only editor | https://github.com/eclipse-aaspe/package-explorer |
| FA³ST Service (Fraunhofer IOSB) | 1.1+ | Apache-2.0 | Java AAS server | https://github.com/FraunhoferIOSB/FAAAST-Service |
| aas-core3.0-python | 1.x | MIT | | https://github.com/aas-core-works/aas-core3.0-python |
| basyx-python-sdk | 2.x | MIT | | https://pypi.org/project/basyx-python-sdk/ |
| OPC UA companion specs | — | Free (OPC Foundation); NodeSets MIT | | https://reference.opcfoundation.org/ |
| ISO 23247 | Parts 1–6 | Paid ISO PDFs; NIST analysis free | 4-layer model | https://www.ap238.org/iso23247/ |
| MTConnect + cppagent | 2.5 / 2.7.0 | Free standard; cppagent Apache-2.0 | | https://github.com/mtconnect/cppagent |
| Sparkplug B (Eclipse Tahu) | 3.0.0 | EFSL spec; Tahu EPL-2.0 | MQTT payload/topic standard | https://sparkplug.eclipse.org/specification/ |

---

## RECOMMENDED FREE STACK (Windows 11 dev box, zero spend)

| Layer | Primary | Alternative |
|---|---|---|
| Datasets | NASA C-MAPSS + AI4I 2020 + MetroPT-3 | N-CMAPSS, IMS/FEMTO bearings, Tennessee Eastman |
| Sensor sim / PLC | SimPy + pymodbus/asyncua → Mosquitto MQTT (Sparkplug B) | OpenPLC v4 + Node-RED |
| Twin core | Eclipse Ditto 3.9 | ThingsBoard CE 4.3 or BaSyx/FA³ST if AAS compliance matters |
| Time-series DB | TimescaleDB Community on PostgreSQL 18 | QuestDB 10; InfluxDB 2 OSS |
| Messaging / cache | Mosquitto + Valkey | NATS JetStream |
| Backend | FastAPI + Celery + WebSockets | Django 6.1 |
| Auth | Keycloak 26.7 | — |
| Object storage | Local FS / SeaweedFS | Garage — not MinIO |
| ML | scikit-learn + XGBoost + LightGBM + tsfresh; lifelines + NASA ProgPy; PyOD + River | PyTorch LSTM/TCN via Darts or NeuralForecast |
| XAI | SHAP + InterpretML EBM + DiCE + MAPIE | Captum; crepes |
| STT | faster-whisper small/turbo on CPU; sherpa-onnx | Vosk; Parakeet-TDT (GPU) |
| Wake word | openWakeWord with self-trained model | push-to-talk |
| NLU / routing | Ollama + Qwen3-4B/Gemma-4-e4b tool calling | spaCy rule matcher; Rasa OSS 3.6 |
| TTS | Kokoro-82M via sherpa-onnx | Piper |
| Voice pipeline | Pipecat | LiveKit Agents |
| Dashboards | Grafana OSS 13 embedded | Apache Superset 6 |
| 3D twin | React Three Fiber + Three.js + CC0 GLTF, Blender | Babylon.js 8 |
| Charts | Apache ECharts 6 | Recharts 3 / Plotly.js |
| Edge inference | ONNX Runtime | OpenVINO, LiteRT |
| Reports | Jinja2 → HTML → WeasyPrint PDF, python-docx | ReportLab |
| Standards | AAS via basyx-python-sdk; Sparkplug B; OPC UA via asyncua; ISO 23247 | MTConnect cppagent |
| Containers | Docker Engine + Compose | Podman Desktop |

---

## LICENSE WARNINGS (looks open, has a catch)

1. Coqui XTTS-v2 weights — CPML non-commercial; company defunct.
2. Redis 7.4–7.x are RSALv2/SSPL; Redis 8+ is AGPL. Use Redis ≥8 or Valkey.
3. InfluxDB 3 Enterprise free licence is at-home only; 3 Core has ~72-hour query window; InfluxDB 2 OSS has neither limit.
4. TimescaleDB — compression/continuous aggregates are TSL; free to self-host; forbidden to resell as DBaaS.
5. Grafana OSS — AGPL; unmodified self-host/embedding fine.
6. Porcupine — SDK proprietary; custom wake words need Console; Personal tier non-commercial.
7. openWakeWord — bundled models CC-BY-NC-SA; train your own.
8. Rasa — OSS 3.6 maintenance mode (Apache); Pro is proprietary with caps.
9. Llama 3.x/4 — Meta Community License (not OSI). Prefer Qwen3 / Gemma 4 / Mistral Apache / Phi-4 / DeepSeek.
10. Web Speech API — streams audio to Google/Apple by default; Firefox lacks it; not OSS.
11. Alibi / Alibi-Detect — BSL 1.1 since Jan 2024.
12. MinIO — archived Apr 2026; use SeaweedFS/Garage/RustFS.
13. Redpanda — BSL 1.1.
14. Piper — active fork GPL-3.0.
15. Kokoro — phonemizer may pull espeak-ng (GPL-3).
16. Docker Desktop — proprietary; free only for personal/education/small orgs.
17. Wokwi — proprietary; free tier.
18. NASA ProgPy — NOSA 1.3 GPL-incompatible.
19. PM4Py (AGPL), dalex (GPL), scikit-survival (GPL) — fine as unmodified libraries.
20. ThingsBoard — CE Apache; PE features paid.
21. Bosch Kaggle data — competition rules; Microsoft Azure PdM Kaggle — licence not stated; CWRU — no explicit licence.
22. Merlion (archived), Vocode (dormant), LIME/OmniXAI (stale), Prophet (maintenance), PyCaret 3 (frozen) — avoid for core features.
