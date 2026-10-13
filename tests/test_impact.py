import unittest

from zog.integrate_observe import ImpactAnalyzer, ObservationError


SNAPSHOT = "sha256:" + "a" * 64


def relation(record, subject, rel, target):
    return {
        "record": record,
        "availability": "available",
        "canonical_kind": "relationship-observation",
        "subject": subject,
        "relation": rel,
        "target": target,
    }


ROOT_CONSUMER = relation(
    "sha256:" + "1" * 64,
    {
        "kind": "artifact",
        "path": "/usr/bin/consumer",
        "digest": "sha256:" + "b" * 64,
        "packages": ["consumer"],
    },
    "needs-library",
    {"kind": "soname", "value": "libfoo.so.7"},
)
PROVIDER = relation(
    "sha256:" + "2" * 64,
    {
        "kind": "artifact",
        "path": "/usr/lib/libfoo.so.7",
        "digest": "sha256:" + "c" * 64,
        "packages": ["libfoo"],
    },
    "provides-soname",
    {"kind": "soname", "value": "libfoo.so.7"},
)
APP_DEPENDS = relation(
    "sha256:" + "3" * 64,
    {"kind": "package", "package": "app", "output_record": "sha256:" + "d" * 64},
    "declares-runtime-dependency",
    {"kind": "package", "value": "consumer"},
)
SHELL_DEPENDS = relation(
    "sha256:" + "4" * 64,
    {"kind": "package", "package": "shell", "output_record": "sha256:" + "e" * 64},
    "declares-runtime-dependency",
    {"kind": "package", "value": "app"},
)
CYCLE = relation(
    "sha256:" + "5" * 64,
    {"kind": "package", "package": "consumer", "output_record": "sha256:" + "f" * 64},
    "declares-runtime-dependency",
    {"kind": "package", "value": "shell"},
)


class FakeTrace:
    def __init__(self, *, two_direct=False):
        self.two_direct = two_direct

    def _rows(self, selector_kind, selector_value, rel):
        if selector_kind == "soname" and selector_value == "libfoo.so.7":
            rows = [ROOT_CONSUMER, PROVIDER]
            if self.two_direct:
                rows.append(
                    relation(
                        "sha256:" + "6" * 64,
                        {
                            "kind": "artifact",
                            "path": "/usr/bin/second",
                            "digest": "sha256:" + "7" * 64,
                            "packages": ["second"],
                        },
                        "needs-library",
                        {"kind": "soname", "value": "libfoo.so.7"},
                    )
                )
            if rel is None:
                return rows
            return [row for row in rows if row["relation"] == rel]
        if selector_kind == "package" and rel == "declares-runtime-dependency":
            if selector_value == "consumer":
                return [APP_DEPENDS]
            if selector_value == "app":
                return [SHELL_DEPENDS]
            if selector_value == "shell":
                return [CYCLE]
        return []

    def relationship_traversal(
        self,
        snapshots,
        direction,
        selector_kind,
        selector_value,
        *,
        relation=None,
        cursor=None,
        limit=20,
    ):
        self.assertions = (snapshots, direction, cursor, limit)
        rows = self._rows(selector_kind, selector_value, relation)
        family = "elf-interfaces" if selector_kind == "soname" else "declared-package-dependencies"
        outcome = "complete" if family == "elf-interfaces" else "partial"
        return {
            "schema_version": 1,
            "kind": "relationship-traversal",
            "direction": "reverse",
            "selector": {"kind": selector_kind, "value": selector_value},
            "relation": relation,
            "snapshot_count": 1,
            "order": "caller-supplied",
            "chronology": "not-inferred",
            "match_semantics": "literal-canonical-fields-only",
            "points": [{
                "snapshot": SNAPSHOT,
                "generation": "generation-a",
                "generation_record": "sha256:" + "8" * 64,
                "generation_id": '["host","project","generation-a"]',
                "root_inventory_digest": "sha256:" + "9" * 64,
                "record_set_digest": "sha256:" + "0" * 64,
                "relationships": rows,
                "relationship_count": len(rows),
                "coverage": [{
                    "record": "sha256:" + ("a" if family == "elf-interfaces" else "b") * 64,
                    "family": family,
                    "outcome": outcome,
                    "observation_count": len(rows),
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
            }],
            "has_more": False,
            "next_cursor": None,
            "authority": "build-record",
        }


class ImpactTests(unittest.TestCase):
    def test_soname_impact_computes_bounded_reverse_reachability(self):
        result = ImpactAnalyzer(FakeTrace()).impact(
            SNAPSHOT,
            "soname",
            "libfoo.so.7",
            relation="needs-library",
            max_depth=3,
        )
        self.assertEqual(result["kind"], "impact")
        self.assertEqual(
            result["packages"],
            [
                {"package": "consumer", "depth": 1},
                {"package": "app", "depth": 2},
                {"package": "shell", "depth": 3},
            ],
        )
        self.assertEqual(result["package_count"], 3)
        self.assertEqual(result["edge_count"], 3)
        self.assertTrue(result["evidence_completeness"]["reference_closure_complete"])
        self.assertFalse(result["evidence_completeness"]["declared_gap_free"])
        self.assertEqual(
            {row["family"] for row in result["coverage"]},
            {"elf-interfaces", "declared-package-dependencies"},
        )
        self.assertTrue(result["interpretation"]["reachability_computed"])
        self.assertFalse(result["interpretation"]["provider_resolution_performed"])
        self.assertFalse(result["interpretation"]["causation_inferred"])
        self.assertFalse(result["interpretation"]["blast_radius_scored"])

    def test_relation_filter_avoids_treating_provider_as_consumer(self):
        filtered = ImpactAnalyzer(FakeTrace()).impact(
            SNAPSHOT, "soname", "libfoo.so.7", relation="needs-library", max_depth=1
        )
        unfiltered = ImpactAnalyzer(FakeTrace()).impact(
            SNAPSHOT, "soname", "libfoo.so.7", max_depth=1
        )
        self.assertEqual([row["package"] for row in filtered["packages"]], ["consumer"])
        self.assertEqual(
            [row["package"] for row in unfiltered["packages"]],
            ["consumer", "libfoo"],
        )

    def test_cycles_do_not_expand_forever(self):
        result = ImpactAnalyzer(FakeTrace()).impact(
            SNAPSHOT,
            "soname",
            "libfoo.so.7",
            relation="needs-library",
            max_depth=8,
        )
        self.assertEqual(result["package_count"], 3)
        self.assertEqual(
            {row["to"]["value"] for row in result["edges"]},
            {"consumer", "app", "shell"},
        )

    def test_depth_one_is_direct_only(self):
        result = ImpactAnalyzer(FakeTrace()).impact(
            SNAPSHOT,
            "soname",
            "libfoo.so.7",
            relation="needs-library",
            max_depth=1,
        )
        self.assertEqual(result["packages"], [{"package": "consumer", "depth": 1}])
        self.assertEqual(result["edge_count"], 1)

    def test_package_bound_fails_closed(self):
        analyzer = ImpactAnalyzer(FakeTrace(two_direct=True), max_packages=1)
        with self.assertRaises(ObservationError) as caught:
            analyzer.impact(
                SNAPSHOT,
                "soname",
                "libfoo.so.7",
                relation="needs-library",
                max_depth=1,
            )
        self.assertEqual(caught.exception.code, "impact-limit-exceeded")

    def test_invalid_depth_is_rejected(self):
        with self.assertRaises(ObservationError) as caught:
            ImpactAnalyzer(FakeTrace()).impact(
                SNAPSHOT, "package", "consumer", max_depth=0
            )
        self.assertEqual(caught.exception.code, "invalid-impact-depth")


if __name__ == "__main__":
    unittest.main()
