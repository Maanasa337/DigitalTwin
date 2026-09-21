"""M9 NLU tests: grammar, router, slots, fuzzy matching, tiers, narration and the intent suite."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from twinvoice_nlu import fuzzy, narrate, rules, tiers
from twinvoice_nlu.router import route
from twinvoice_nlu.schema import load_catalogue
from twinvoice_nlu.slots import parse_asset, parse_datetime, parse_number, parse_period
from twinvoice_nlu.suite import NOISE_LEVELS, generate, score_slots

NOW = datetime(2026, 9, 19, 10, 0, tzinfo=UTC)  # a Saturday
CAT = load_catalogue()


def routed(text: str, **kwargs):
    return route(text, now=NOW, **kwargs)


# ── Catalogue ─────────────────────────────────────────────────────────


def test_catalogue_covers_every_prd_intent():
    """FR-NL-01: the twelve named intents plus give_feedback from Appendix A."""
    expected = {
        "get_machine_status",
        "explain_prediction",
        "get_counterfactual",
        "run_what_if",
        "create_work_order",
        "list_alarms",
        "acknowledge_alarm",
        "get_kpi",
        "generate_report",
        "set_simulation_scenario",
        "navigate_dashboard",
        "give_feedback",
        "help",
    }
    assert {i.name for i in CAT.intents} == expected


def test_every_intent_has_a_valid_tier():
    assert all(intent.tier in tiers.TIERS for intent in CAT.intents)


def test_state_changing_intents_are_gated():
    """Anything that writes must be T2 or above — this is the safety invariant of FR-VN-07."""
    for name in ("create_work_order", "acknowledge_alarm", "generate_report", "give_feedback"):
        assert tiers.needs_confirmation(CAT.tier(name)), name
    assert tiers.needs_second_factor(CAT.tier("set_simulation_scenario"))
    assert not tiers.needs_confirmation(CAT.tier("get_machine_status"))
    assert not tiers.needs_confirmation(CAT.tier("run_what_if"))


def test_tool_schemas_are_wellformed():
    for tool in CAT.tools():
        function = tool["function"]
        assert function["name"] and function["description"]
        required = function["parameters"]["required"]
        assert set(required) <= set(function["parameters"]["properties"])


# ── Rule matching ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        ("How is compressor two?", "get_machine_status"),
        ("Status of CNC three", "get_machine_status"),
        ("Kya haal hai conveyor one ka?", "get_machine_status"),
        ("Why?", "explain_prediction"),
        ("What's causing that?", "explain_prediction"),
        ("What would fix it?", "get_counterfactual"),
        ("What if we reduce load to 80 percent?", "run_what_if"),
        ("Any alarms on line one?", "list_alarms"),
        ("What's critical right now?", "list_alarms"),
        ("Acknowledge the alarm on press four", "acknowledge_alarm"),
        ("Schedule bearing replacement for compressor two on Friday morning", "create_work_order"),
        ("What's the OEE of line two this week?", "get_kpi"),
        ("Generate the weekly maintenance report", "generate_report"),
        ("Inject a bearing fault on conveyor one", "set_simulation_scenario"),
        ("Open compressor two", "navigate_dashboard"),
        ("That explanation is wrong, sensor four is faulty", "give_feedback"),
        ("What can you do?", "help"),
    ],
)
def test_appendix_a_examples_route_by_rule(text, intent):
    """Every example utterance printed in PRD Appendix A must match deterministically."""
    result = routed(text)
    assert result.intent == intent, f"{text!r} -> {result.intent}"
    assert result.router == "rules"
    assert result.confidence >= rules.RELAXED_CONFIDENCE


def test_relaxed_match_survives_filler():
    result = routed("hey twin how is compressor two please")
    assert result.intent == "get_machine_status"
    assert result.confidence == rules.RELAXED_CONFIDENCE


def test_unknown_utterance_falls_back_to_help_without_an_llm():
    result = routed("what is the capital of france")
    assert result.router == "none"
    assert not result.understood


def test_control_words_are_exact_only():
    assert routed("confirm").control == "confirm"
    assert routed("haan confirm").control == "confirm"
    assert routed("cancel").control == "cancel"
    # A sentence that merely contains "confirm" must never execute a pending read-back.
    assert routed("confirm the order for compressor two later").control is None


# ── Slots ─────────────────────────────────────────────────────────────


def test_asset_slot_is_captured_and_spoken_digits_expanded():
    assert routed("how is compressor two").slots["asset"] == "compressor 2"
    assert parse_asset("the CNC three machine") == "cnc 3"


def test_kpi_and_period_slots_are_canonical():
    result = routed("what is the oee of line two this week")
    assert result.slots["kpi"] == "oee"
    assert result.slots["scope"] == "line 2"
    assert result.slots["period"] == "week"
    assert result.slots["period_start"] == datetime(2026, 9, 14, tzinfo=UTC)  # Monday


def test_period_bounds():
    assert parse_period("today", NOW).start == datetime(2026, 9, 19, tzinfo=UTC)
    assert parse_period("last week", NOW).start == datetime(2026, 9, 7, tzinfo=UTC)
    assert parse_period("yesterday", NOW).end == datetime(2026, 9, 19, tzinfo=UTC)


def test_number_slot_handles_words_and_percent():
    assert parse_number("80 percent") == 80.0
    assert parse_number("eighty") == 80.0
    assert parse_number("do") == 2.0
    assert parse_number("not a number") is None


def test_datetime_resolves_forward_only():
    """ "Friday morning" said on a Saturday means the coming Friday, never yesterday."""
    resolved = parse_datetime("friday morning", NOW)
    assert resolved == datetime(2026, 9, 25, 8, 0, tzinfo=UTC)
    assert resolved > NOW
    assert parse_datetime("tomorrow", NOW) == datetime(2026, 9, 20, 8, 0, tzinfo=UTC)


def test_datetime_respects_the_plants_timezone():
    """Resolution happens in the caller's timezone: 10:00 UTC is already 15:30 in the plant."""
    ist = NOW.astimezone(timezone(timedelta(hours=5, minutes=30)))
    resolved = parse_datetime("tomorrow", ist)
    assert resolved.tzinfo == ist.tzinfo
    assert (resolved.hour, resolved.day) == (8, 20)


def test_what_if_parameter_is_inferred_from_the_verb():
    assert routed("what if we reduce load to 80 percent").slots["parameter"] == "load"
    assert routed("what if we reduce speed to 70 percent").slots["parameter"] == "speed"
    assert routed("what if we service it next week instead").slots["parameter"] == "maintenance_at"


def test_feedback_verdict_is_inferred():
    assert routed("that explanation is wrong").slots["verdict"] == "disagree"
    assert routed("that explanation is right").slots["verdict"] == "agree"


def test_navigate_maps_a_view_to_a_route():
    assert routed("show energy").slots["view"] == "/analytics/energy"
    assert routed("go back").slots["view"] == "back"


def test_missing_required_slot_is_reported():
    """A required slot with no context fallback is named, so the assistant can ask for it."""
    result = routed("generate the report")
    assert result.intent != "generate_report" or "type" in result.missing


# ── Fuzzy asset resolution ────────────────────────────────────────────

REFS = [
    fuzzy.AssetRef(id="1", code="cnc-01", name="CNC Mill 01"),
    fuzzy.AssetRef(id="2", code="cnc-03", name="CNC Mill 03"),
    fuzzy.AssetRef(id="3", code="comp-02", name="Compressor 02"),
    fuzzy.AssetRef(id="4", code="conv-01", name="Conveyor 01"),
]


def test_spoken_form_strips_codes_to_what_a_person_says():
    assert fuzzy.spoken("cnc-03") == "cnc 3"
    assert fuzzy.spoken("CNC Mill 03") == "cnc mill 3"


@pytest.mark.parametrize(
    ("query", "code"),
    [("cnc three", "cnc-03"), ("compressor two", "comp-02"), ("conveyor one", "conv-01"), ("CNC Mill 01", "cnc-01")],
)
def test_resolve_matches_spoken_references(query, code):
    match, _ = fuzzy.resolve(query, REFS)
    assert match is not None and match.code == code


def test_unknown_reference_returns_alternatives_not_a_guess():
    match, alternatives = fuzzy.resolve("hydraulic press nine", REFS)
    assert match is None
    assert len(alternatives) <= 2


# ── Tiers and read-back ───────────────────────────────────────────────


def test_readback_names_every_parameter():
    """FR-VN-07: the operator must hear the asset, the task, the time and the assignee."""
    text = tiers.readback(
        "create_work_order",
        {
            "task": "replace bearing",
            "asset_label": "Compressor 02",
            "when": datetime(2026, 9, 25, 8, 0, tzinfo=UTC),
            "technician_label": "Ravi",
        },
    )
    assert "replace bearing" in text
    assert "Compressor 02" in text
    assert "08:00" in text
    assert "Ravi" in text
    assert text.endswith("Say confirm or cancel.")


def test_readback_is_available_in_hindi():
    text = tiers.readback("acknowledge_alarm", {"asset_label": "Press 04", "severity": "critical"}, "hi")
    assert "Press 04" in text
    assert "Confirm ya cancel" in text


def test_only_exact_words_confirm():
    assert tiers.is_confirm("confirm")
    assert tiers.is_confirm("Yes, confirm!")
    assert tiers.is_confirm("haan confirm")
    assert not tiers.is_confirm("confirm it later")
    assert not tiers.is_confirm("yes")
    assert tiers.is_cancel("cancel")
    assert tiers.is_cancel("nahi")


# ── Grounded narration ────────────────────────────────────────────────


def test_narration_is_built_only_from_tool_output():
    text = narrate.compose(
        "get_machine_status",
        {
            "asset": "Compressor 02",
            "health_pct": 62.4,
            "rul": 118,
            "rul_unit": "cycles",
            "rul_interval": [96, 140],
            "top_driver": "spindle vibration",
            "open_alarms": 1,
        },
    )
    assert "Compressor 02" in text
    assert "62" in text and "118" in text
    assert "96" in text and "140" in text
    assert "1 alarm open" in text


def test_empty_tool_result_says_so_rather_than_inventing():
    assert narrate.compose("get_machine_status", None) == narrate.EMPTY["en"]
    assert narrate.compose("get_kpi", {}) == narrate.EMPTY["en"]


def test_what_if_answer_is_marked_hypothetical():
    text = narrate.compose(
        "run_what_if",
        {"change": "load at 80 percent", "baseline_rul": 118, "rul": 152, "rul_unit": "cycles"},
        hypothetical=True,
    )
    assert "152" in text
    assert "nothing has changed" in text


def test_citations_only_carry_provenance_keys():
    assert narrate.citations({"asset": "cnc-01", "at": "t", "model_version": "3", "health_pct": 9}) == {
        "asset": "cnc-01",
        "at": "t",
        "model_version": "3",
    }


# ── The intent suite (FR-NL-06) ───────────────────────────────────────

SUITE = generate()


def test_suite_meets_the_prd_size_requirement():
    """≥ 500 labelled utterances, ≥ 10 per intent, all three languages represented."""
    assert len(SUITE) >= 500
    per_intent: dict[str, int] = {}
    for utterance in SUITE:
        per_intent[utterance.intent] = per_intent.get(utterance.intent, 0) + 1
    assert min(per_intent.values()) >= 10, per_intent
    assert {u.lang for u in SUITE} == {"en", "hi", "hinglish"}
    assert any(u.noise_variant for u in SUITE)


def test_clean_intent_accuracy_meets_target():
    """FR-NL-06 / G5: ≥ 92 % intent accuracy on the clean suite."""
    clean = [u for u in SUITE if not u.noise_variant]
    correct = sum(routed(u.text).intent == u.intent for u in clean)
    accuracy = correct / len(clean)
    assert accuracy >= 0.92, f"clean intent accuracy {accuracy:.3f} over {len(clean)} utterances"


@pytest.mark.parametrize("level", sorted(NOISE_LEVELS))
def test_noisy_intent_accuracy_meets_target(level):
    """G5: ≥ 92 % at machine noise, measured on transcripts that noise has already damaged."""
    noisy = [u for u in SUITE if u.split == level]
    correct = sum(routed(u.text).intent == u.intent for u in noisy)
    accuracy = correct / len(noisy)
    assert accuracy >= 0.92, f"{level}: {accuracy:.3f} over {len(noisy)} utterances"


def test_clean_slot_accuracy_meets_target():
    """Routing to the right intent with the wrong machine is still the wrong action.

    FR-NL-06 sets a target for intent accuracy only, so slots went unmeasured and a greedy capture
    could hand `create_work_order` an asset of "cnc one to replace" without any test noticing.
    """
    clean = [u for u in SUITE if not u.noise_variant]
    matched = expected = 0
    for utterance in clean:
        got, want = score_slots(utterance, routed(utterance.text).slots, CAT.get(utterance.intent))
        matched += got
        expected += want

    assert expected > 300, "the suite should pin down a few hundred slot values"
    accuracy = matched / expected
    assert accuracy >= 0.95, f"clean slot accuracy {accuracy:.3f} over {expected} labelled slots"


def test_a_machine_reference_is_never_split_by_a_following_clause():
    """The failure this guards: a literal widened for noise eats the index off an asset."""
    # The router normalises a spoken index to a digit, so "press four" comes back as "press 4".
    cases = [
        ("raise a work order on press four to filter change", "asset", "press 4"),
        ("create a work order for compressor two", "asset", "compressor 2"),
        ("what if we reduce load to 80 percent on compressor two", "asset", "compressor 2"),
        ("schedule bearing replacement for compressor two on friday morning", "asset", "compressor 2"),
    ]
    for text, slot, want in cases:
        got = routed(text).slots.get(slot)
        assert str(got) == want, f"{text!r}: {slot} was {got!r}, expected {want!r}"


def test_a_task_never_swallows_the_word_that_introduced_it():
    slots = routed("raise a work order on cnc one to replace the spindle bearing").slots
    assert slots.get("asset") == "cnc 1"
    assert slots.get("task") == "replace the spindle bearing"


def test_no_state_changing_intent_is_ever_reached_by_a_query():
    """A read-only phrasing must never route to a writing intent — the worst failure mode there is."""
    queries = [u for u in SUITE if CAT.tier(u.intent) in ("T0", "T1")]
    leaked = [
        (u.text, routed(u.text).intent)
        for u in queries
        if tiers.needs_confirmation(CAT.tier(routed(u.text).intent) or "T0")
    ]
    assert not leaked, leaked[:5]
