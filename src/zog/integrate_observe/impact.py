"""Deterministic relationship reachability over build-trace's public traversal API."""
from copy import deepcopy

from .observer import (
    BUILD_TRACE_SCHEMA_VERSION,
    COMPLETENESS_FIELDS,
    ObservationError,
    SCHEMA_VERSION,
)


REVERSE_SELECTORS = frozenset({"package", "package-output", "soname", "path"})
TRANSITIVE_PACKAGE_RELATIONS = (
    "declares-runtime-dependency",
    "declares-build-dependency",
    "declares-test-dependency",
    "used-build-output",
)
MAX_DEPTH = 8
MAX_PACKAGES = 500


def _expect_mapping(value, name):
    if not isinstance(value, dict):
        raise ObservationError("invalid-observation", f"{name} must be a JSON object.")
    return value


def _expect_traversal(value):
    _expect_mapping(value, "build-trace response")
    if (
        value.get("schema_version") != BUILD_TRACE_SCHEMA_VERSION
        or value.get("kind") != "relationship-traversal"
    ):
        raise ObservationError(
            "unsupported-build-trace-contract",
            "Expected build-trace schema 1 relationship-traversal response.",
        )
    if value.get("direction") != "reverse":
        raise ObservationError(
            "invalid-observation",
            "Impact analysis requires reverse relationship traversal.",
        )
    points = value.get("points")
    if not isinstance(points, list) or len(points) != 1 or value.get("has_more"):
        raise ObservationError(
            "invalid-observation",
            "A one-snapshot relationship traversal must return exactly one complete point.",
        )
    return points[0]


def _completeness(point):
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
    coverage = point.get("coverage")
    if not isinstance(coverage, list):
        raise ObservationError(
            "invalid-observation", "build-trace relationship coverage is malformed."
        )
    return {
        "reference_closure_complete": point["reference_closure_complete"],
        "missing_record_count": point["missing_record_count"],
        "declared_gap_free": point["declared_gap_free"],
        "declared_gap_count": point["declared_gap_count"],
        "declared_gap_reason_count": point["declared_gap_reason_count"],
        "declared_gap_summary": deepcopy(point["declared_gap_summary"]),
    }


def _subject_packages(row):
    subject = row.get("subject")
    if not isinstance(subject, dict):
        return []
    if subject.get("kind") == "package":
        package = subject.get("package")
        return [package] if isinstance(package, str) and package else []
    if subject.get("kind") == "artifact":
        packages = subject.get("packages", [])
        if not isinstance(packages, list):
            return []
        return sorted(
            {
                package
                for package in packages
                if isinstance(package, str) and package
            }
        )
    return []


def _coverage_key(row):
    if isinstance(row, dict) and isinstance(row.get("record"), str):
        return ("record", row["record"])
    if isinstance(row, dict):
        return (
            "value",
            row.get("family"),
            row.get("outcome"),
            row.get("observation_count"),
        )
    return ("value", repr(row))


class ImpactAnalyzer:
    """Compute bounded literal reverse reachability without provider or causal inference."""

    def __init__(self, trace, *, max_packages=100):
        if (
            not isinstance(max_packages, int)
            or isinstance(max_packages, bool)
            or not 1 <= max_packages <= MAX_PACKAGES
        ):
            raise ValueError(f"max_packages must be between 1 and {MAX_PACKAGES}")
        self.trace = trace
        self.max_packages = max_packages

    def _query(self, snapshot, selector_kind, selector_value, relation):
        raw = self.trace.relationship_traversal(
            [snapshot],
            "reverse",
            selector_kind,
            selector_value,
            relation=relation,
            limit=1,
        )
        point = _expect_traversal(raw)
        if point.get("snapshot") != snapshot:
            raise ObservationError(
                "invalid-observation",
                "build-trace relationship traversal returned a different snapshot.",
            )
        relationships = point.get("relationships")
        if not isinstance(relationships, list):
            raise ObservationError(
                "invalid-observation",
                "build-trace relationship traversal returned malformed relationships.",
            )
        if point.get("relationship_count") != len(relationships):
            raise ObservationError(
                "invalid-observation",
                "build-trace relationship count differs from returned relationships.",
            )
        evidence = _completeness(point)
        return point, relationships, evidence

    def impact(
        self,
        snapshot,
        selector_kind,
        selector_value,
        *,
        relation=None,
        max_depth=3,
    ):
        if selector_kind not in REVERSE_SELECTORS:
            raise ObservationError(
                "invalid-impact-selector",
                "Impact selector kind must be package, package-output, soname, or path.",
            )
        if (
            not isinstance(selector_value, str)
            or not selector_value
            or len(selector_value) > 8192
        ):
            raise ObservationError(
                "invalid-impact-selector", "Impact selector value must be a nonempty string."
            )
        if (
            not isinstance(max_depth, int)
            or isinstance(max_depth, bool)
            or not 1 <= max_depth <= MAX_DEPTH
        ):
            raise ObservationError(
                "invalid-impact-depth",
                f"Impact max_depth must be between 1 and {MAX_DEPTH}.",
            )

        query_cache = {}
        query_evidence = []
        coverage = {}
        snapshot_identity = None
        completeness = None

        def query(kind, value, rel):
            nonlocal snapshot_identity, completeness
            key = (kind, value, rel)
            if key in query_cache:
                return query_cache[key]
            point, relationships, point_completeness = self._query(
                snapshot, kind, value, rel
            )
            identity = {
                "generation": point.get("generation"),
                "generation_record": point.get("generation_record"),
                "generation_id": point.get("generation_id"),
                "root_inventory_digest": point.get("root_inventory_digest"),
                "record_set_digest": point.get("record_set_digest"),
            }
            if snapshot_identity is None:
                snapshot_identity = identity
                completeness = point_completeness
            elif identity != snapshot_identity or point_completeness != completeness:
                raise ObservationError(
                    "inconsistent-impact-evidence",
                    "Repeated traversal of one immutable snapshot returned inconsistent identity or completeness.",
                )
            for row in point["coverage"]:
                coverage[_coverage_key(row)] = deepcopy(row)
            query_evidence.append(
                {
                    "selector": {"kind": kind, "value": value},
                    "relation": rel,
                    "relationship_count": len(relationships),
                    "coverage": deepcopy(point["coverage"]),
                }
            )
            query_cache[key] = relationships
            return relationships

        direct_rows = query(selector_kind, selector_value, relation)
        package_depth = {}
        queue = []
        edges = []
        edge_keys = set()
        unattributed = []

        def add_edge(source, package, depth, row):
            record = row.get("record")
            key = (
                source.get("kind"),
                source.get("value"),
                package,
                row.get("relation"),
                record,
            )
            if key in edge_keys:
                return
            edge_keys.add(key)
            edges.append(
                {
                    "from": deepcopy(source),
                    "to": {"kind": "package", "value": package},
                    "depth": depth,
                    "relation": row.get("relation"),
                    "record": record,
                    "relationship": deepcopy(row),
                }
            )

        root = {"kind": selector_kind, "value": selector_value}
        for row in direct_rows:
            packages = _subject_packages(row)
            if not packages:
                unattributed.append(deepcopy(row))
                continue
            for package in packages:
                add_edge(root, package, 1, row)
                if package not in package_depth:
                    if len(package_depth) >= self.max_packages:
                        raise ObservationError(
                            "impact-limit-exceeded",
                            f"Impact analysis exceeded the {self.max_packages}-package bound.",
                        )
                    package_depth[package] = 1
                    queue.append(package)

        index = 0
        while index < len(queue):
            target_package = queue[index]
            index += 1
            depth = package_depth[target_package]
            if depth >= max_depth:
                continue
            for rel in TRANSITIVE_PACKAGE_RELATIONS:
                for row in query("package", target_package, rel):
                    packages = _subject_packages(row)
                    if not packages:
                        unattributed.append(deepcopy(row))
                        continue
                    for package in packages:
                        next_depth = depth + 1
                        add_edge(
                            {"kind": "package", "value": target_package},
                            package,
                            next_depth,
                            row,
                        )
                        prior = package_depth.get(package)
                        if prior is None:
                            if len(package_depth) >= self.max_packages:
                                raise ObservationError(
                                    "impact-limit-exceeded",
                                    f"Impact analysis exceeded the {self.max_packages}-package bound.",
                                )
                            package_depth[package] = next_depth
                            queue.append(package)
                        elif next_depth < prior:
                            package_depth[package] = next_depth
                            queue.append(package)

        packages = [
            {"package": package, "depth": depth}
            for package, depth in sorted(
                package_depth.items(), key=lambda item: (item[1], item[0])
            )
        ]
        edges.sort(
            key=lambda edge: (
                edge["depth"],
                edge["from"]["kind"],
                edge["from"]["value"],
                edge["to"]["value"],
                edge.get("relation") or "",
                edge.get("record") or "",
            )
        )
        query_evidence.sort(
            key=lambda item: (
                item["selector"]["kind"],
                item["selector"]["value"],
                item.get("relation") or "",
            )
        )

        return {
            "schema_version": SCHEMA_VERSION,
            "kind": "impact",
            "snapshot": snapshot,
            **(snapshot_identity or {}),
            "selector": root,
            "relation": relation,
            "max_depth": max_depth,
            "max_packages": self.max_packages,
            "package_count": len(packages),
            "packages": packages,
            "edge_count": len(edges),
            "edges": edges,
            "unattributed_relationships": unattributed,
            "evidence_completeness": deepcopy(completeness or {}),
            "coverage": [
                coverage[key]
                for key in sorted(coverage, key=lambda value: repr(value))
            ],
            "query_evidence": query_evidence,
            "interpretation": {
                "chronology_inferred": False,
                "provider_resolution_performed": False,
                "causation_inferred": False,
                "reachability_computed": True,
                "blast_radius_scored": False,
                "severity_assigned": False,
                "policy_evaluated": False,
            },
            "semantics": {
                "direct_matches": "literal reverse canonical relationship fields",
                "transitive_package_relations": list(TRANSITIVE_PACKAGE_RELATIONS),
                "provider_resolution": "not-performed",
            },
        }
