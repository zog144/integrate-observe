"""Caller-ordered verification history and conservative comparability analysis."""
from copy import deepcopy

from .observer import (
    BUILD_TRACE_SCHEMA_VERSION,
    COMPLETENESS_FIELDS,
    ObservationError,
    SCHEMA_VERSION,
)


MAX_HISTORY = 100


def _expect_mapping(value, name):
    if not isinstance(value, dict):
        raise ObservationError("invalid-observation", f"{name} must be a JSON object.")
    return value


def _expect_history(value, check_id):
    _expect_mapping(value, "build-trace response")
    if (
        value.get("schema_version") != BUILD_TRACE_SCHEMA_VERSION
        or value.get("kind") != "verification-history"
    ):
        raise ObservationError(
            "unsupported-build-trace-contract",
            "Expected build-trace schema 1 verification-history response.",
        )
    if value.get("check_id") != check_id:
        raise ObservationError(
            "invalid-observation",
            "build-trace verification history returned a different logical check.",
        )
    if value.get("order") != "caller-supplied" or value.get("chronology") != "not-inferred":
        raise ObservationError(
            "invalid-observation",
            "build-trace verification history must preserve caller order without inferred chronology.",
        )
    points = value.get("points")
    if not isinstance(points, list):
        raise ObservationError(
            "invalid-observation",
            "build-trace verification history points must be a JSON array.",
        )
    return points


def _point_completeness(point):
    missing = [field for field in COMPLETENESS_FIELDS if field not in point]
    if missing:
        raise ObservationError(
            "unsupported-build-trace-contract",
            "build-trace 0.12 completeness fields are required: " + ", ".join(missing),
        )
    if not isinstance(point["reference_closure_complete"], bool) or not isinstance(
        point["declared_gap_free"], bool
    ):
        raise ObservationError(
            "invalid-observation", "build-trace completeness booleans are malformed."
        )
    for field in (
        "missing_record_count",
        "declared_gap_count",
        "declared_gap_reason_count",
    ):
        if (
            not isinstance(point[field], int)
            or isinstance(point[field], bool)
            or point[field] < 0
        ):
            raise ObservationError(
                "invalid-observation", "build-trace completeness counts are malformed."
            )
    if not isinstance(point["declared_gap_summary"], list):
        raise ObservationError(
            "invalid-observation", "build-trace declared-gap summary is malformed."
        )
    return {
        "reference_closure_complete": point["reference_closure_complete"],
        "missing_record_count": point["missing_record_count"],
        "declared_gap_free": point["declared_gap_free"],
        "declared_gap_count": point["declared_gap_count"],
        "declared_gap_reason_count": point["declared_gap_reason_count"],
        "declared_gap_summary": deepcopy(point["declared_gap_summary"]),
    }


def _strings(rows, field):
    values = []
    for row in rows:
        value = row.get(field)
        if isinstance(value, str) and value:
            values.append(value)
    return sorted(values)


def _unique_strings(rows, field):
    return sorted(set(_strings(rows, field)))


def _environment_side(rows):
    """Summarize build-trace 0.13 environment evidence without reinterpreting it."""
    if not rows:
        return {
            "availability": "no-executions",
            "explicit_identities": [],
            "legacy_digests": [],
            "unavailable_count": 0,
            "digests": [],
        }

    explicit = set()
    legacy = set()
    unavailable = 0
    for row in rows:
        environment = row.get("environment")
        if not isinstance(environment, dict):
            raise ObservationError(
                "unsupported-build-trace-contract",
                "build-trace 0.13 execution environment projection is required.",
            )
        availability = environment.get("availability")
        if availability == "available":
            contract = environment.get("contract")
            digest = environment.get("digest")
            descriptor = environment.get("descriptor")
            if (
                not isinstance(contract, str)
                or not contract
                or not isinstance(digest, str)
                or not digest
                or not isinstance(descriptor, dict)
            ):
                raise ObservationError(
                    "invalid-observation",
                    "build-trace explicit execution environment is malformed.",
                )
            explicit.add((contract, digest))
        elif availability == "legacy-opaque":
            digest = environment.get("digest")
            if not isinstance(digest, str) or not digest:
                raise ObservationError(
                    "invalid-observation",
                    "build-trace legacy execution environment is malformed.",
                )
            legacy.add(digest)
        elif availability == "unavailable":
            unavailable += 1
        else:
            raise ObservationError(
                "invalid-observation",
                "build-trace execution environment availability is unsupported.",
            )

    identities = [
        {"contract": contract, "digest": digest}
        for contract, digest in sorted(explicit)
    ]
    if explicit and not legacy and unavailable == 0:
        availability = "explicit" if len(explicit) == 1 else "multiple-explicit"
    elif legacy and not explicit and unavailable == 0:
        availability = "legacy-opaque"
    elif unavailable == len(rows):
        availability = "unavailable"
    else:
        availability = "mixed"

    return {
        "availability": availability,
        "explicit_identities": identities,
        "legacy_digests": sorted(legacy),
        "unavailable_count": unavailable,
        "digests": sorted({digest for _, digest in explicit} | legacy),
    }


def _environment_pair(before_rows, after_rows):
    before = _environment_side(before_rows)
    after = _environment_side(after_rows)

    if before["availability"] == "no-executions" and after["availability"] == "no-executions":
        state, reasons = "missing-both", ["environment-missing"]
    elif before["availability"] == "no-executions":
        state, reasons = "missing-before", ["environment-missing"]
    elif after["availability"] == "no-executions":
        state, reasons = "missing-after", ["environment-missing"]
    elif (
        before["availability"] in {"multiple-explicit", "mixed"}
        or after["availability"] in {"multiple-explicit", "mixed"}
    ):
        state, reasons = "ambiguous", ["environment-ambiguous"]
    elif (
        before["availability"] == "legacy-opaque"
        or after["availability"] == "legacy-opaque"
    ):
        state, reasons = "legacy-opaque", ["legacy-opaque-environment"]
    elif (
        before["availability"] == "unavailable"
        or after["availability"] == "unavailable"
    ):
        state, reasons = "unavailable", ["environment-unavailable"]
    else:
        before_identity = before["explicit_identities"][0]
        after_identity = after["explicit_identities"][0]
        if before_identity == after_identity:
            state, reasons = "same", []
        else:
            state, reasons = "changed", ["environment-changed"]

    return {
        "state": state,
        "before": before,
        "after": after,
        "before_digests": before["digests"],
        "after_digests": after["digests"],
        "reason_codes": reasons,
    }


def _pair_state(before_values, after_values):
    before = set(before_values)
    after = set(after_values)
    if not before and not after:
        return "missing-both"
    if not before:
        return "missing-before"
    if not after:
        return "missing-after"
    if len(before) != 1 or len(after) != 1:
        return "ambiguous"
    return "same" if before == after else "changed"


def _execution_state(before_count, after_count):
    if before_count == 0 and after_count == 0:
        return "missing-both"
    if before_count == 0:
        return "missing-before"
    if after_count == 0:
        return "missing-after"
    if before_count > 1 or after_count > 1:
        return "multiple"
    return "present-both"


def _outcome_state(before_outcomes, after_outcomes):
    """Preserve exact execution evidence while separating values from multiplicity."""
    if not before_outcomes and not after_outcomes:
        exact_state = value_set_state = multiplicity_state = "missing-both"
    elif not before_outcomes:
        exact_state = value_set_state = multiplicity_state = "missing-before"
    elif not after_outcomes:
        exact_state = value_set_state = multiplicity_state = "missing-after"
    else:
        exact_state = "same" if before_outcomes == after_outcomes else "changed"
        before_values = sorted(set(before_outcomes))
        after_values = sorted(set(after_outcomes))
        value_set_state = "same" if before_values == after_values else "changed"
        before_counts = {value: before_outcomes.count(value) for value in before_values}
        after_counts = {value: after_outcomes.count(value) for value in after_values}
        multiplicity_state = (
            "same"
            if sorted(before_counts.values()) == sorted(after_counts.values())
            else "changed"
        )
        return {
            "state": exact_state,
            "value_set_state": value_set_state,
            "multiplicity_state": multiplicity_state,
            "before": before_outcomes,
            "after": after_outcomes,
            "distinct_before": before_values,
            "distinct_after": after_values,
            "counts_before": before_counts,
            "counts_after": after_counts,
        }

    return {
        "state": exact_state,
        "value_set_state": value_set_state,
        "multiplicity_state": multiplicity_state,
        "before": before_outcomes,
        "after": after_outcomes,
        "distinct_before": sorted(set(before_outcomes)),
        "distinct_after": sorted(set(after_outcomes)),
        "counts_before": {
            value: before_outcomes.count(value)
            for value in sorted(set(before_outcomes))
        },
        "counts_after": {
            value: after_outcomes.count(value)
            for value in sorted(set(after_outcomes))
        },
    }


def _coverage_state(before, after):
    before_recorded = bool(before.get("coverage"))
    after_recorded = bool(after.get("coverage"))
    if before_recorded and after_recorded:
        return "recorded-both"
    if before_recorded:
        return "missing-after"
    if after_recorded:
        return "missing-before"
    return "missing-both"


def _comparability(definition_state, environment, execution_state):
    reasons = []
    if definition_state == "changed":
        reasons.append("definition-changed")
    elif definition_state.startswith("missing"):
        reasons.append("definition-missing")
    elif definition_state == "ambiguous":
        reasons.append("multiple-definitions")

    reasons.extend(environment["reason_codes"])

    if execution_state.startswith("missing"):
        reasons.append("execution-missing")

    if any(reason in reasons for reason in ("multiple-definitions", "environment-ambiguous")):
        status = "ambiguous"
    elif any(reason in reasons for reason in ("definition-changed", "environment-changed")):
        status = "not-comparable"
    elif reasons:
        status = "insufficient-evidence"
    else:
        status = "comparable"

    return {
        "status": status,
        "comparable_under_stable_definition_and_environment": status == "comparable",
        "reason_codes": reasons,
    }


def _transition(before, after, check_id):
    before_definitions = _unique_strings(before["definitions"], "definition_digest")
    after_definitions = _unique_strings(after["definitions"], "definition_digest")
    environment = _environment_pair(before["executions"], after["executions"])
    before_outcomes = _strings(before["executions"], "outcome")
    after_outcomes = _strings(after["executions"], "outcome")

    definition_state = _pair_state(before_definitions, after_definitions)
    environment_state = environment["state"]
    execution_state = _execution_state(
        before["execution_count"], after["execution_count"]
    )
    outcomes = _outcome_state(before_outcomes, after_outcomes)
    comparability = _comparability(
        definition_state, environment, execution_state
    )

    if definition_state == "changed":
        factual_transition = "definition-changed"
    elif definition_state == "ambiguous":
        factual_transition = "ambiguous-multiple-definitions"
    elif definition_state.startswith("missing"):
        factual_transition = "definition-missing"
    elif execution_state.startswith("missing"):
        factual_transition = "execution-missing"
    elif environment_state == "changed":
        factual_transition = "environment-changed"
    elif environment_state == "ambiguous":
        factual_transition = "ambiguous-environment-evidence"
    elif environment_state == "legacy-opaque":
        factual_transition = "environment-legacy-opaque"
    elif environment_state == "unavailable":
        factual_transition = "environment-unavailable"
    elif environment_state.startswith("missing"):
        factual_transition = "environment-missing"
    elif outcomes["value_set_state"] == "same":
        factual_transition = "stable-definition-same-outcome-set"
    else:
        factual_transition = "stable-definition-changed-outcome-set"

    return {
        "check_id": check_id,
        "before": {
            "position": before["position"],
            "snapshot": before["snapshot"],
            "generation_record": before["generation_record"],
        },
        "after": {
            "position": after["position"],
            "snapshot": after["snapshot"],
            "generation_record": after["generation_record"],
        },
        "definition": {
            "state": definition_state,
            "before_digests": before_definitions,
            "after_digests": after_definitions,
        },
        "environment": environment,
        "execution": {
            "state": execution_state,
            "before_count": before["execution_count"],
            "after_count": after["execution_count"],
            "multiple_before": before["execution_count"] > 1,
            "multiple_after": after["execution_count"] > 1,
            "representative_execution_selected": False,
        },
        "outcomes": outcomes,
        "coverage": {
            "state": _coverage_state(before, after),
            "before": deepcopy(before["coverage"]),
            "after": deepcopy(after["coverage"]),
        },
        "factual_transition": factual_transition,
        "comparability": comparability,
        "regression_classified": False,
        "causation_inferred": False,
    }


class VerificationHistoryAnalyzer:
    """Preserve caller ordering and assess adjacent verification comparability."""

    def __init__(self, trace, *, page_limit=20):
        if (
            not isinstance(page_limit, int)
            or isinstance(page_limit, bool)
            or not 1 <= page_limit <= 100
        ):
            raise ValueError("page_limit must be between 1 and 100")
        self.trace = trace
        self.page_limit = page_limit

    def history(self, snapshots, check_id):
        if (
            not isinstance(snapshots, (list, tuple))
            or not 2 <= len(snapshots) <= MAX_HISTORY
        ):
            raise ObservationError(
                "invalid-history-sequence",
                "Provide between 2 and 100 caller-ordered snapshot identities.",
            )
        snapshots = list(snapshots)
        if len(set(snapshots)) != len(snapshots):
            raise ObservationError(
                "invalid-history-sequence",
                "Verification-history snapshots must not contain duplicates.",
            )
        if not isinstance(check_id, str) or not check_id or len(check_id) > 8192:
            raise ObservationError(
                "invalid-history-check",
                "Verification-history check_id must be a nonempty string.",
            )

        points = []
        cursor = None
        seen = set()
        while True:
            raw = self.trace.verification_history(
                snapshots,
                check_id,
                cursor=cursor,
                limit=self.page_limit,
            )
            page_points = _expect_history(raw, check_id)
            for point in page_points:
                _expect_mapping(point, "verification-history point")
                if point.get("snapshot") not in snapshots:
                    raise ObservationError(
                        "invalid-observation",
                        "build-trace verification history returned an unexpected snapshot.",
                    )
                definitions = point.get("definitions")
                executions = point.get("executions")
                coverage = point.get("coverage")
                if not isinstance(definitions, list) or not isinstance(executions, list):
                    raise ObservationError(
                        "invalid-observation",
                        "build-trace verification definitions/executions are malformed.",
                    )
                if not isinstance(coverage, list):
                    raise ObservationError(
                        "invalid-observation",
                        "build-trace verification coverage is malformed.",
                    )
                if point.get("definition_count") != len(definitions):
                    raise ObservationError(
                        "invalid-observation",
                        "build-trace verification definition count differs from returned definitions.",
                    )
                if point.get("execution_count") != len(executions):
                    raise ObservationError(
                        "invalid-observation",
                        "build-trace verification execution count differs from returned executions.",
                    )
                points.append({
                    "position": point.get("position"),
                    "snapshot": point.get("snapshot"),
                    "generation": point.get("generation"),
                    "generation_record": point.get("generation_record"),
                    "generation_id": point.get("generation_id"),
                    "root_inventory_digest": point.get("root_inventory_digest"),
                    "record_set_digest": point.get("record_set_digest"),
                    "definitions": deepcopy(definitions),
                    "definition_count": len(definitions),
                    "executions": deepcopy(executions),
                    "execution_count": len(executions),
                    "coverage": deepcopy(coverage),
                    "coverage_availability": point.get(
                        "coverage_availability", "not-recorded-in-snapshot"
                    ),
                    **_point_completeness(point),
                })
            if not raw.get("has_more"):
                break
            next_cursor = raw.get("next_cursor")
            if (
                not isinstance(next_cursor, str)
                or not next_cursor
                or next_cursor in seen
            ):
                raise ObservationError(
                    "invalid-pagination",
                    "build-trace returned an unusable verification-history cursor.",
                )
            seen.add(next_cursor)
            cursor = next_cursor

        positions = [point["position"] for point in points]
        if positions != list(range(1, len(snapshots) + 1)):
            raise ObservationError(
                "invalid-observation",
                "build-trace verification-history points do not preserve the complete caller sequence.",
            )
        if [point["snapshot"] for point in points] != snapshots:
            raise ObservationError(
                "invalid-observation",
                "build-trace verification-history points do not preserve caller order.",
            )

        transitions = [
            _transition(points[index], points[index + 1], check_id)
            for index in range(len(points) - 1)
        ]

        return {
            "schema_version": SCHEMA_VERSION,
            "kind": "verification-history",
            "check_id": check_id,
            "snapshot_count": len(snapshots),
            "order": "caller-supplied",
            "chronology": "not-inferred",
            "points": points,
            "transitions": transitions,
            "interpretation": {
                "release_baseline_selected": False,
                "chronology_inferred": False,
                "representative_execution_selected": False,
                "definition_changes_treated_as_regressions": False,
                "environment_changes_treated_as_regressions": False,
                "missing_execution_treated_as_skip_or_failure": False,
                "regression_classified": False,
                "causation_inferred": False,
                "severity_assigned": False,
                "policy_evaluated": False,
            },
        }
