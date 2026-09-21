"""TwinVoice XAI — explanation pipeline for the predictive-maintenance models.

Modules:
    labels        — feature -> human label/unit/direction/actionable range (feature_labels.yaml)
    attribution   — TreeSHAP / KernelSHAP / integrated gradients normalised to one Explanation schema
    glassbox      — EBM second opinion and SHAP-vs-EBM top-3 agreement
    reason_card   — failure mode + top attributions -> knowledge-base reason card
    counterfactual— constrained search over actionable features ("what would make this healthy")
    templates     — deterministic en/hi narration templates
    audit         — checks an LLM paraphrase against the attributions it claims to describe
    confidence    — interval width + model agreement + sensor quality + drift -> label and reasons
    quality       — deletion/insertion AUC, PGI, sensitivity, sparsity, truth agreement, stability
    drift         — feature drift (ADWIN-style + KS) and Mahalanobis OOD
"""

from twinvoice_xai.attribution import Attribution, ExplanationResult, explain_kernel, explain_tree
from twinvoice_xai.audit import AuditResult, audit_narration
from twinvoice_xai.confidence import ConfidenceResult, assess_confidence
from twinvoice_xai.counterfactual import CounterfactualResult, search_counterfactual
from twinvoice_xai.labels import FeatureLabel, FeatureLabels, load_labels
from twinvoice_xai.reason_card import ReasonCard, build_reason_card
from twinvoice_xai.templates import narrate

__version__ = "0.1.0"

__all__ = [
    "Attribution",
    "AuditResult",
    "ConfidenceResult",
    "CounterfactualResult",
    "ExplanationResult",
    "FeatureLabel",
    "FeatureLabels",
    "ReasonCard",
    "assess_confidence",
    "audit_narration",
    "build_reason_card",
    "explain_kernel",
    "explain_tree",
    "load_labels",
    "narrate",
    "search_counterfactual",
]
