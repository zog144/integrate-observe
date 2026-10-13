import unittest

from zog.integrate_observe import ObservationError, VerificationHistoryAnalyzer


A = "sha256:" + "a" * 64
B = "sha256:" + "b" * 64
C = "sha256:" + "c" * 64
D1 = "sha256:" + "1" * 64
D2 = "sha256:" + "2" * 64
E1 = "sha256:" + "3" * 64
E2 = "sha256:" + "4" * 64


def definition(digest):
    return {
        "record": "sha256:" + digest[7] * 64,
        "availability": "available",
        "check_id": "check/native",
        "definition_digest": digest,
    }


def explicit_environment(digest, *, contract="image-build-verification-environment-v1"):
    return {
        "availability": "available",
        "contract": contract,
        "digest": digest,
        "descriptor": {"runtime": {"executor": "box-control-build-job-v1"}},
    }


def execution(
    record_char,
    definition_digest,
    outcome,
    environment_digest,
    *,
    environment_contract="image-build-verification-environment-v1",
    producer_policy_digest=None,
):
    row = {
        "record": "sha256:" + record_char * 64,
        "availability": "available",
        "check_id": "check/native",
        "definition_digest": definition_digest,
        "outcome": outcome,
        "environment": explicit_environment(
            environment_digest, contract=environment_contract
        ),
    }
    if producer_policy_digest is not None:
        row["producer_policy_digest"] = producer_policy_digest
    return row


def legacy_execution(record_char, definition_digest, outcome, environment_digest):
    return {
        "record": "sha256:" + record_char * 64,
        "availability": "available",
        "check_id": "check/native",
        "definition_digest": definition_digest,
        "outcome": outcome,
        "environment": {
            "availability": "legacy-opaque",
            "digest": environment_digest,
        },
        "environment_digest": environment_digest,
    }


def unavailable_execution(record_char, definition_digest, outcome):
    return {
        "record": "sha256:" + record_char * 64,
        "availability": "available",
        "check_id": "check/native",
        "definition_digest": definition_digest,
        "outcome": outcome,
        "environment": {"availability": "unavailable"},
    }


def old_projection_execution(record_char, definition_digest, outcome, environment_digest):
    return {
        "record": "sha256:" + record_char * 64,
        "availability": "available",
        "check_id": "check/native",
        "definition_digest": definition_digest,
        "outcome": outcome,
        "environment_digest": environment_digest,
    }


class FakeTrace:
    def __init__(self, points):
        self._points = points

    def verification_history(
        self, snapshots, check_id, *, definition_digest=None, cursor=None, limit=20
    ):
        self.last = (list(snapshots), check_id, definition_digest, cursor, limit)
        points = [self._points[snapshot] for snapshot in snapshots]
        return {
            "schema_version": 1,
            "kind": "verification-history",
            "check_id": check_id,
            "definition_digest": definition_digest,
            "snapshot_count": len(snapshots),
            "order": "caller-supplied",
            "chronology": "not-inferred",
            "points": points,
            "has_more": False,
            "next_cursor": None,
            "authority": "build-record",
        }


def point(position, snapshot, definitions, executions, *, coverage_outcome="complete"):
    return {
        "position": position,
        "snapshot": snapshot,
        "generation": f"generation-{position}",
        "generation_record": "sha256:" + str(position) * 64,
        "generation_id": f'["host","project","generation-{position}"]',
        "root_inventory_digest": "sha256:" + str(position + 4) * 64,
        "record_set_digest": "sha256:" + str(position + 6) * 64,
        "definitions": definitions,
        "definition_count": len(definitions),
        "executions": executions,
        "execution_count": len(executions),
        "coverage": [{
            "record": "sha256:" + str(position + 7) * 64,
            "family": "verification-commands",
            "outcome": coverage_outcome,
            "observation_count": len(executions),
        }],
        "coverage_availability": "recorded",
        "reference_closure_complete": True,
        "missing_record_count": 0,
        "declared_gap_free": False,
        "declared_gap_count": 2,
        "declared_gap_reason_count": 3,
        "declared_gap_summary": [{
            "category": "upstream-identity",
            "record_count": 2,
            "reason_count": 3,
        }],
    }


class VerificationHistoryTests(unittest.TestCase):
    def test_same_explicit_environment_pass_to_fail_is_factual_not_regression(self):
        trace = FakeTrace({
            A: point(1, A, [definition(D1)], [execution("a", D1, "PASS", E1)]),
            B: point(2, B, [definition(D1)], [execution("b", D1, "FAIL", E1)]),
        })
        transition = VerificationHistoryAnalyzer(trace).history(
            [A, B], "check/native"
        )["transitions"][0]
        self.assertEqual(transition["definition"]["state"], "same")
        self.assertEqual(transition["environment"]["state"], "same")
        self.assertEqual(
            transition["environment"]["before"]["availability"], "explicit"
        )
        self.assertEqual(
            transition["environment"]["after"]["availability"], "explicit"
        )
        self.assertEqual(transition["outcomes"]["state"], "changed")
        self.assertEqual(transition["outcomes"]["value_set_state"], "changed")
        self.assertEqual(transition["outcomes"]["multiplicity_state"], "same")
        self.assertEqual(transition["outcomes"]["distinct_before"], ["PASS"])
        self.assertEqual(transition["outcomes"]["distinct_after"], ["FAIL"])
        self.assertEqual(transition["outcomes"]["counts_before"], {"PASS": 1})
        self.assertEqual(transition["outcomes"]["counts_after"], {"FAIL": 1})
        self.assertEqual(
            transition["factual_transition"],
            "stable-definition-changed-outcome-set",
        )
        self.assertEqual(transition["comparability"]["status"], "comparable")
        self.assertFalse(transition["regression_classified"])

    def test_explicit_contract_is_part_of_environment_identity(self):
        trace = FakeTrace({
            A: point(1, A, [definition(D1)], [execution("a", D1, "PASS", E1)]),
            B: point(2, B, [definition(D1)], [
                execution(
                    "b",
                    D1,
                    "PASS",
                    E1,
                    environment_contract="image-build-verification-environment-v2",
                )
            ]),
        })
        transition = VerificationHistoryAnalyzer(trace).history(
            [A, B], "check/native"
        )["transitions"][0]
        self.assertEqual(transition["environment"]["state"], "changed")
        self.assertEqual(transition["comparability"]["status"], "not-comparable")
        self.assertIn(
            "environment-changed", transition["comparability"]["reason_codes"]
        )

    def test_producer_policy_digest_does_not_define_execution_comparability(self):
        trace = FakeTrace({
            A: point(1, A, [definition(D1)], [
                execution("a", D1, "PASS", E1, producer_policy_digest="sha256:" + "5" * 64)
            ]),
            B: point(2, B, [definition(D1)], [
                execution("b", D1, "FAIL", E1, producer_policy_digest="sha256:" + "6" * 64)
            ]),
        })
        transition = VerificationHistoryAnalyzer(trace).history(
            [A, B], "check/native"
        )["transitions"][0]
        self.assertEqual(transition["environment"]["state"], "same")
        self.assertEqual(transition["comparability"]["status"], "comparable")

    def test_repeated_pass_changes_multiplicity_not_outcome_value_set(self):
        trace = FakeTrace({
            A: point(1, A, [definition(D1)], [execution("a", D1, "PASS", E1)]),
            B: point(2, B, [definition(D1)], [
                execution("b", D1, "PASS", E1),
                execution("c", D1, "PASS", E1),
            ]),
        })
        transition = VerificationHistoryAnalyzer(trace).history(
            [A, B], "check/native"
        )["transitions"][0]
        self.assertEqual(transition["execution"]["state"], "multiple")
        self.assertEqual(transition["outcomes"]["state"], "changed")
        self.assertEqual(transition["outcomes"]["value_set_state"], "same")
        self.assertEqual(transition["outcomes"]["multiplicity_state"], "changed")
        self.assertEqual(transition["outcomes"]["before"], ["PASS"])
        self.assertEqual(transition["outcomes"]["after"], ["PASS", "PASS"])
        self.assertEqual(transition["outcomes"]["distinct_before"], ["PASS"])
        self.assertEqual(transition["outcomes"]["distinct_after"], ["PASS"])
        self.assertEqual(transition["outcomes"]["counts_before"], {"PASS": 1})
        self.assertEqual(transition["outcomes"]["counts_after"], {"PASS": 2})
        self.assertEqual(
            transition["factual_transition"],
            "stable-definition-same-outcome-set",
        )
        self.assertEqual(transition["comparability"]["status"], "comparable")
        self.assertFalse(transition["regression_classified"])

    def test_changed_definition_is_not_comparable_even_when_both_pass(self):
        trace = FakeTrace({
            A: point(1, A, [definition(D1)], [execution("a", D1, "PASS", E1)]),
            B: point(2, B, [definition(D2)], [execution("b", D2, "PASS", E1)]),
        })
        transition = VerificationHistoryAnalyzer(trace).history(
            [A, B], "check/native"
        )["transitions"][0]
        self.assertEqual(transition["definition"]["state"], "changed")
        self.assertEqual(transition["factual_transition"], "definition-changed")
        self.assertEqual(transition["comparability"]["status"], "not-comparable")
        self.assertIn(
            "definition-changed", transition["comparability"]["reason_codes"]
        )
        self.assertEqual(transition["outcomes"]["before"], ["PASS"])
        self.assertEqual(transition["outcomes"]["after"], ["PASS"])

    def test_changed_explicit_environment_blocks_comparability(self):
        trace = FakeTrace({
            A: point(1, A, [definition(D1)], [execution("a", D1, "PASS", E1)]),
            B: point(2, B, [definition(D1)], [execution("b", D1, "FAIL", E2)]),
        })
        transition = VerificationHistoryAnalyzer(trace).history(
            [A, B], "check/native"
        )["transitions"][0]
        self.assertEqual(transition["environment"]["state"], "changed")
        self.assertEqual(transition["factual_transition"], "environment-changed")
        self.assertEqual(transition["comparability"]["status"], "not-comparable")

    def test_matching_legacy_opaque_digests_are_not_comparable(self):
        trace = FakeTrace({
            A: point(1, A, [definition(D1)], [legacy_execution("a", D1, "PASS", E1)]),
            B: point(2, B, [definition(D1)], [legacy_execution("b", D1, "FAIL", E1)]),
        })
        transition = VerificationHistoryAnalyzer(trace).history(
            [A, B], "check/native"
        )["transitions"][0]
        self.assertEqual(transition["environment"]["state"], "legacy-opaque")
        self.assertEqual(
            transition["factual_transition"], "environment-legacy-opaque"
        )
        self.assertEqual(
            transition["comparability"]["status"], "insufficient-evidence"
        )
        self.assertIn(
            "legacy-opaque-environment",
            transition["comparability"]["reason_codes"],
        )
        self.assertFalse(
            transition["comparability"][
                "comparable_under_stable_definition_and_environment"
            ]
        )

    def test_explicit_vs_legacy_environment_is_insufficient_evidence(self):
        trace = FakeTrace({
            A: point(1, A, [definition(D1)], [legacy_execution("a", D1, "PASS", E1)]),
            B: point(2, B, [definition(D1)], [execution("b", D1, "PASS", E1)]),
        })
        transition = VerificationHistoryAnalyzer(trace).history(
            [A, B], "check/native"
        )["transitions"][0]
        self.assertEqual(transition["environment"]["state"], "legacy-opaque")
        self.assertEqual(
            transition["comparability"]["status"], "insufficient-evidence"
        )

    def test_unavailable_environment_is_insufficient_evidence(self):
        trace = FakeTrace({
            A: point(1, A, [definition(D1)], [unavailable_execution("a", D1, "PASS")]),
            B: point(2, B, [definition(D1)], [execution("b", D1, "PASS", E1)]),
        })
        transition = VerificationHistoryAnalyzer(trace).history(
            [A, B], "check/native"
        )["transitions"][0]
        self.assertEqual(transition["environment"]["state"], "unavailable")
        self.assertEqual(
            transition["comparability"]["status"], "insufficient-evidence"
        )
        self.assertIn(
            "environment-unavailable", transition["comparability"]["reason_codes"]
        )

    def test_multiple_explicit_environments_are_ambiguous(self):
        trace = FakeTrace({
            A: point(1, A, [definition(D1)], [
                execution("a", D1, "PASS", E1),
                execution("b", D1, "PASS", E2),
            ]),
            B: point(2, B, [definition(D1)], [execution("c", D1, "PASS", E1)]),
        })
        transition = VerificationHistoryAnalyzer(trace).history(
            [A, B], "check/native"
        )["transitions"][0]
        self.assertEqual(transition["environment"]["state"], "ambiguous")
        self.assertEqual(
            transition["environment"]["before"]["availability"], "multiple-explicit"
        )
        self.assertEqual(transition["comparability"]["status"], "ambiguous")
        self.assertIn(
            "environment-ambiguous", transition["comparability"]["reason_codes"]
        )

    def test_missing_execution_is_insufficient_evidence_not_skip(self):
        trace = FakeTrace({
            A: point(1, A, [definition(D1)], [execution("a", D1, "PASS", E1)]),
            B: point(2, B, [definition(D1)], []),
        })
        transition = VerificationHistoryAnalyzer(trace).history(
            [A, B], "check/native"
        )["transitions"][0]
        self.assertEqual(transition["execution"]["state"], "missing-after")
        self.assertEqual(transition["environment"]["state"], "missing-after")
        self.assertEqual(transition["outcomes"]["state"], "missing-after")
        self.assertEqual(
            transition["comparability"]["status"], "insufficient-evidence"
        )
        self.assertIn(
            "execution-missing", transition["comparability"]["reason_codes"]
        )

    def test_multiple_executions_same_explicit_environment_remain_comparable(self):
        trace = FakeTrace({
            A: point(1, A, [definition(D1)], [
                execution("a", D1, "PASS", E1),
                execution("b", D1, "FAIL", E1),
            ]),
            B: point(2, B, [definition(D1)], [
                execution("c", D1, "PASS", E1),
                execution("d", D1, "PASS", E1),
            ], coverage_outcome="partial"),
        })
        result = VerificationHistoryAnalyzer(trace).history([A, B], "check/native")
        transition = result["transitions"][0]
        self.assertEqual(transition["execution"]["state"], "multiple")
        self.assertEqual(transition["environment"]["state"], "same")
        self.assertEqual(transition["outcomes"]["before"], ["FAIL", "PASS"])
        self.assertEqual(transition["outcomes"]["after"], ["PASS", "PASS"])
        self.assertEqual(transition["outcomes"]["value_set_state"], "changed")
        self.assertEqual(transition["outcomes"]["multiplicity_state"], "changed")
        self.assertEqual(
            transition["outcomes"]["distinct_before"], ["FAIL", "PASS"]
        )
        self.assertEqual(transition["outcomes"]["distinct_after"], ["PASS"])
        self.assertEqual(
            transition["outcomes"]["counts_before"], {"FAIL": 1, "PASS": 1}
        )
        self.assertEqual(transition["outcomes"]["counts_after"], {"PASS": 2})
        self.assertEqual(transition["comparability"]["status"], "comparable")
        self.assertFalse(transition["execution"]["representative_execution_selected"])
        self.assertEqual(result["points"][1]["coverage"][0]["outcome"], "partial")

    def test_multiple_definitions_are_ambiguous(self):
        trace = FakeTrace({
            A: point(
                1,
                A,
                [definition(D1), definition(D2)],
                [execution("a", D1, "PASS", E1)],
            ),
            B: point(2, B, [definition(D1)], [execution("b", D1, "PASS", E1)]),
        })
        transition = VerificationHistoryAnalyzer(trace).history(
            [A, B], "check/native"
        )["transitions"][0]
        self.assertEqual(transition["definition"]["state"], "ambiguous")
        self.assertEqual(transition["comparability"]["status"], "ambiguous")
        self.assertEqual(
            transition["factual_transition"], "ambiguous-multiple-definitions"
        )

    def test_three_points_preserve_caller_order_and_adjacent_transitions(self):
        trace = FakeTrace({
            A: point(1, A, [definition(D1)], [execution("a", D1, "PASS", E1)]),
            B: point(2, B, [definition(D1)], [execution("b", D1, "PASS", E1)]),
            C: point(3, C, [definition(D2)], [execution("c", D2, "PASS", E1)]),
        })
        result = VerificationHistoryAnalyzer(trace).history(
            [A, B, C], "check/native"
        )
        self.assertEqual([row["snapshot"] for row in result["points"]], [A, B, C])
        self.assertEqual(len(result["transitions"]), 2)
        self.assertEqual(
            result["transitions"][0]["factual_transition"],
            "stable-definition-same-outcome-set",
        )
        self.assertEqual(
            result["transitions"][1]["factual_transition"],
            "definition-changed",
        )
        self.assertEqual(result["chronology"], "not-inferred")

    def test_pre_013_flat_environment_projection_is_rejected(self):
        trace = FakeTrace({
            A: point(1, A, [definition(D1)], [
                old_projection_execution("a", D1, "PASS", E1)
            ]),
            B: point(2, B, [definition(D1)], [
                old_projection_execution("b", D1, "PASS", E1)
            ]),
        })
        with self.assertRaises(ObservationError) as caught:
            VerificationHistoryAnalyzer(trace).history([A, B], "check/native")
        self.assertEqual(
            caught.exception.code, "unsupported-build-trace-contract"
        )

    def test_duplicate_or_single_snapshot_sequence_is_rejected(self):
        analyzer = VerificationHistoryAnalyzer(FakeTrace({}))
        with self.assertRaises(ObservationError):
            analyzer.history([A], "check/native")
        with self.assertRaises(ObservationError):
            analyzer.history([A, A], "check/native")


if __name__ == "__main__":
    unittest.main()
