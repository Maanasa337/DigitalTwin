"""Tests for the XAI library: attribution shaping, reason cards, counterfactuals, narration audit."""

from __future__ import annotations

import numpy as np
import pytest

from twinvoice_xai.attribution import Attribution, build_attributions, concept_segments, temporal_attribution
from twinvoice_xai.audit import audit_narration, pass_rate
from twinvoice_xai.confidence import assess_confidence, interval_width_ratio
from twinvoice_xai.counterfactual import search_counterfactual
from twinvoice_xai.drift import adwin_change_point, ks_statistic, mahalanobis_ood
from twinvoice_xai.glassbox import agreement, top3_jaccard
from twinvoice_xai.labels import load_labels
from twinvoice_xai.quality import (
    deletion_auc,
    insertion_auc,
    sparsity,
    truth_top1_agreement,
    window_jaccard,
)
from twinvoice_xai.reason_card import build_reason_card
from twinvoice_xai.templates import narrate, status_context, why

FEATURES = ["spindle.vib_rms", "bearing.temp", "motor.current", "coolant_temp"]


def make_attributions(contributions: list[float], values: list[float] | None = None) -> list[Attribution]:
    return build_attributions(FEATURES, np.array(values or [4.2, 71.0, 12.5, 30.0]), np.array(contributions))


# ── Labels and attribution shaping ────────────────────────────────────

def test_labels_resolve_suffixed_features():
    labels = load_labels()
    assert labels.get("spindle.vib_rms").label == "Spindle vibration"
    assert labels.get("spindle.vib_rms_std").label == "Spindle vibration variability"
    assert labels.get("spindle.vib_rms").unit == "mm/s"


def test_derived_statistics_are_not_actionable():
    """An operator can set coolant_temp; they cannot set its rolling standard deviation."""
    labels = load_labels()
    assert labels.get("coolant_temp").actionable is True
    assert labels.get("coolant_temp_std").actionable is False


def test_attributions_rank_by_absolute_contribution_and_share_sums_to_one():
    attributions = make_attributions([0.1, -0.6, 0.3, 0.0])
    assert [a.feature for a in attributions] == [
        "bearing.temp", "motor.current", "spindle.vib_rms", "coolant_temp",
    ]
    assert [a.rank for a in attributions] == [1, 2, 3, 4]
    assert attributions[0].direction == "lowering"
    assert attributions[2].direction == "raising"
    assert sum(a.share for a in attributions) == pytest.approx(1.0)


def test_all_zero_contributions_do_not_divide_by_zero():
    attributions = make_attributions([0.0, 0.0, 0.0, 0.0])
    assert all(a.share == 0.0 for a in attributions)
    assert all(a.direction == "neutral" for a in attributions)


def test_build_attributions_rejects_length_mismatch():
    with pytest.raises(ValueError, match="length mismatch"):
        build_attributions(FEATURES, np.array([1.0, 2.0]), np.array([0.1, 0.2]))


def test_temporal_attribution_weights_sum_to_one_per_feature():
    contributions = np.array([[1.0, 0.0], [3.0, 0.0], [0.0, 0.0]])
    result = temporal_attribution(np.zeros((3, 2)), contributions, ["a", "b"], [0.0, 1.0, 2.0])
    assert sum(w for _, w in result["a"]) == pytest.approx(1.0)
    assert "b" not in result  # a feature contributing nothing gets no series at all


@pytest.mark.parametrize(
    ("series", "expected"),
    [
        ([1, 1, 1, 1, 1, 1, 1, 1], "steady"),
        ([1, 2, 3, 4, 5, 6, 7, 8], "trend"),
        ([1, 1, 1, 1, 1, 1, 40, 1], "spike"),
    ],
)
def test_concept_segments(series, expected):
    assert concept_segments(np.array(series, dtype=float)) == expected


# ── Glass-box agreement ───────────────────────────────────────────────

def test_top3_jaccard_and_disagreement_flag():
    assert top3_jaccard(["a", "b", "c"], ["a", "b", "c"]) == 1.0
    assert top3_jaccard(["a", "b", "c"], ["d", "e", "f"]) == 0.0
    assert agreement(["a", "b", "c"], ["d", "e", "f"])["disagreement"] is True
    assert agreement(["a", "b", "c"], ["a", "b", "z"])["disagreement"] is False


# ── Reason card ───────────────────────────────────────────────────────

def test_reason_card_marks_evidence_that_supports_the_mode():
    card = build_reason_card("bearing_wear", make_attributions([0.6, 0.3, 0.1, 0.0]), mode_probability=0.8)
    assert card is not None
    assert "bearing" in card.likely_cause.lower()
    supporting = {e["feature"] for e in card.evidence if e["supports_mode"]}
    assert supporting == {"spindle.vib_rms", "bearing.temp", "motor.current"}
    assert card.parts == ["bearing-6206", "grease-nlgi2"]


def test_reason_card_confidence_drops_when_evidence_does_not_match():
    matching = build_reason_card("overheating", make_attributions([0.0, 0.0, 0.0, 1.0]), mode_probability=0.9)
    mismatched = build_reason_card("overheating", make_attributions([1.0, 0.0, 0.0, 0.0]), mode_probability=0.9)
    assert matching is not None and mismatched is not None
    assert matching.confidence > mismatched.confidence


def test_unknown_failure_mode_yields_no_card_rather_than_invented_advice():
    assert build_reason_card("no_such_mode", make_attributions([1.0, 0, 0, 0])) is None


def test_hindi_knowledge_base_has_the_same_modes_as_english():
    from twinvoice_xai.reason_card import load_kb

    assert set(load_kb("hi")) == set(load_kb("en"))


# ── Counterfactuals ───────────────────────────────────────────────────

def test_counterfactual_only_varies_actionable_features():
    """RUL here rises as load_pct falls, so the search must find a load reduction."""
    names = ["spindle.vib_rms", "load_pct", "coolant_temp"]
    x = np.array([4.0, 95.0, 40.0])

    def predict(row: np.ndarray) -> float:
        row = np.asarray(row).reshape(-1)
        return 200.0 - row[1]

    result = search_counterfactual(
        predict, x, names, target="rul>=150", satisfied=lambda v: v >= 150.0, max_features_changed=1
    )
    assert result.found
    assert [c.feature for c in result.changes] == ["load_pct"]
    assert result.changes[0].to <= 50.0
    assert result.outcome["rul_point"] >= 150.0
    assert "Load" in result.action_text


def test_counterfactual_reports_not_found_when_target_is_unreachable():
    names = ["load_pct"]
    result = search_counterfactual(
        lambda row: 1.0, np.array([50.0]), names, target="rul>=999", satisfied=lambda v: v >= 999.0
    )
    assert result.found is False
    assert result.changes == []
    assert result.feasibility_score == 0.0


def test_counterfactual_with_no_actionable_feature_in_the_vector():
    result = search_counterfactual(
        lambda row: 0.0, np.array([1.0]), ["spindle.vib_rms"], target="healthy", satisfied=lambda v: True
    )
    assert result.found is False


# ── Narration templates ───────────────────────────────────────────────

def test_status_narration_english_and_hindi_differ_but_carry_the_same_numbers():
    context = status_context("CNC-01", 42.0, 120.0, 90.0, 160.0, "cycles")
    english = narrate("status", context, "en")
    hindi = narrate("status", status_context("CNC-01", 42.0, 120.0, 90.0, 160.0, "cycles", "hi"), "hi")
    assert "120" in english and "120" in hindi
    assert english != hindi


def test_status_narration_omits_rul_when_there_is_none():
    text = narrate("status", status_context("CNC-01", 80.0, None, None, None, "cycles"))
    assert "remaining useful life" not in text
    assert "80" in text


def test_why_narration_names_the_top_driver():
    text = why(make_attributions([0.1, 0.8, 0.05, 0.0]))
    assert "Bearing temperature" in text
    assert "raising" in text


def test_unknown_narration_kind_raises():
    with pytest.raises(ValueError, match="unknown narration kind"):
        narrate("nonsense", {})


# ── Narration audit ───────────────────────────────────────────────────

ATTRIBUTIONS = make_attributions([0.1, 0.8, 0.4, 0.0], [4.2, 71.0, 12.5, 30.0])


def test_audit_passes_a_faithful_narration():
    text = (
        "Bearing temperature at 71 is raising the risk, followed by Motor current at 12.5 "
        "and Spindle vibration at 4.2."
    )
    result = audit_narration(text, ATTRIBUTIONS)
    assert result.passed
    assert result.rank_agreement == 1.0
    assert result.hallucinated_features == []


def test_audit_fails_when_the_narration_drops_the_top_drivers():
    result = audit_narration("Everything looks broadly acceptable today.", ATTRIBUTIONS)
    assert not result.passed
    assert result.rank_agreement == 0.0


def test_audit_fails_on_a_flipped_direction():
    """Reversing the sign reverses the advice, so this can never be shown to an operator."""
    text = "Bearing temperature at 71 is lowering the risk, with Motor current at 12.5 and Spindle vibration at 4.2."
    result = audit_narration(text, ATTRIBUTIONS)
    assert not result.passed
    assert result.sign_agreement < 1.0


def test_audit_fails_on_an_invented_number():
    text = "Bearing temperature at 500 is raising the risk, with Motor current at 12.5 and Spindle vibration at 4.2."
    result = audit_narration(text, ATTRIBUTIONS)
    assert not result.passed
    assert result.numeric_within_tolerance is False


def test_audit_tolerates_numbers_within_five_percent():
    text = "Bearing temperature at 72 is raising the risk, with Motor current at 12.5 and Spindle vibration at 4.2."
    assert audit_narration(text, ATTRIBUTIONS).numeric_within_tolerance is True


def test_audit_flags_a_feature_the_explanation_never_mentioned():
    text = (
        "Bearing temperature at 71 is raising the risk, with Motor current at 12.5 and Spindle vibration at 4.2, "
        "and hydraulic pressure is a concern."
    )
    result = audit_narration(text, ATTRIBUTIONS)
    assert "hydraulic pressure" in result.hallucinated_features
    assert not result.passed


def test_audit_flags_a_recommendation_the_reason_card_does_not_support():
    text = "Bearing temperature at 71 is raising the risk. Replace the gearbox immediately."
    result = audit_narration(text, ATTRIBUTIONS, recommended_actions=["Re-grease and re-check vibration"])
    assert result.unsupported_recommendation is True
    assert not result.passed


def test_pass_rate():
    good = audit_narration(
        "Bearing temperature at 71 is raising the risk, with Motor current at 12.5 and Spindle vibration at 4.2.",
        ATTRIBUTIONS,
    )
    bad = audit_narration("Nothing in particular.", ATTRIBUTIONS)
    assert pass_rate([good, bad]) == 0.5
    assert pass_rate([]) == 1.0


# ── Confidence ────────────────────────────────────────────────────────

def test_interval_width_ratio_guards_a_zero_point_estimate():
    assert interval_width_ratio(0.0, 1.0, 2.0) is None
    assert interval_width_ratio(100.0, 90.0, 110.0) == pytest.approx(0.2)


def test_confidence_is_high_when_nothing_is_wrong():
    result = assess_confidence(rul_point=100, rul_low=95, rul_high=105, model_agreement=1.0)
    assert result.label == "high"
    assert len(result.reasons) == 1


def test_confidence_names_each_problem_separately():
    result = assess_confidence(
        rul_point=100,
        rul_low=10,
        rul_high=250,
        model_agreement=0.2,
        degraded_sensors=["spindle.vib_rms"],
        drift_flag=True,
    )
    assert result.label == "low"
    joined = " ".join(result.reasons).lower()
    assert "interval" in joined and "glass-box" in joined and "quality" in joined and "drifted" in joined


def test_confidence_without_an_interval_still_reacts_to_other_signals():
    result = assess_confidence(model_agreement=0.1, drift_flag=True)
    assert result.label in ("medium", "low")
    assert result.signals["interval_width_ratio"] is None


# ── Quality metrics ───────────────────────────────────────────────────

def test_deletion_and_insertion_reward_a_faithful_explanation():
    """A model driven entirely by feature 0, explained as such, should score well on both."""

    def predict(X: np.ndarray) -> float:
        return float(np.asarray(X).reshape(-1)[0] * 10)

    x = np.array([5.0, 1.0, 1.0, 1.0])
    faithful = np.array([1.0, 0.0, 0.0, 0.0])
    misleading = np.array([0.0, 0.0, 0.0, 1.0])

    assert deletion_auc(predict, x, faithful) < deletion_auc(predict, x, misleading)
    assert insertion_auc(predict, x, faithful) > insertion_auc(predict, x, misleading)


def test_sparsity_rewards_concentrated_attributions():
    assert sparsity(np.array([1.0, 0.0, 0.0, 0.0])) == 0.75
    assert sparsity(np.array([1.0, 1.0, 1.0, 1.0])) == 0.0
    assert sparsity(np.array([0.0, 0.0])) == 1.0


def test_truth_top1_agreement_against_known_drivers():
    contributions = np.array([[0.9, 0.1], [0.1, 0.9], [0.9, 0.1]])
    assert truth_top1_agreement(contributions, [0, 1, 0]) == 1.0
    assert truth_top1_agreement(contributions, [1, 1, 0]) == pytest.approx(2 / 3)


def test_window_jaccard_measures_stability_between_windows():
    assert window_jaccard([["a", "b", "c"], ["a", "b", "c"]]) == 1.0
    assert window_jaccard([["a", "b", "c"], ["x", "y", "z"]]) == 0.0
    assert window_jaccard([["a", "b", "c"]]) == 1.0


# ── Drift and OOD ─────────────────────────────────────────────────────

def test_ks_statistic_is_zero_for_identical_samples_and_one_for_disjoint():
    same = np.arange(100, dtype=float)
    assert ks_statistic(same, same) == 0.0
    assert ks_statistic(np.zeros(50), np.ones(50)) == pytest.approx(1.0)


def test_adwin_finds_a_level_shift_and_ignores_a_flat_series():
    shifted = np.concatenate([np.zeros(50), np.ones(50) * 10])
    assert adwin_change_point(shifted) is not None
    assert adwin_change_point(np.zeros(100)) is None


def test_mahalanobis_grows_with_distance_from_the_training_centre():
    reference = np.random.default_rng(0).normal(size=(200, 3))
    mean, cov = reference.mean(axis=0), np.cov(reference, rowvar=False)
    near = mahalanobis_ood(mean, mean, cov)
    far = mahalanobis_ood(mean + 10, mean, cov)
    assert far > near
