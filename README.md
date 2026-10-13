# integrate-observe

**Documentation:** [Design and interface guide](docs/integrate-observe/design.md). This guide and the README describe the current factual contracts and interpretation boundaries.

`integrate-observe` is the cross-generation integration observation layer for Zog.
Version 0.4.2 refines caller-ordered verification history so outcome values,
outcome multiplicity and execution count remain separate facts. It retains build-trace
0.13's versioned execution-environment compatibility rules, the factual
World/Comparison foundation and deterministic impact reachability.

The program does **not** read image-build state or build-record storage directly.
Its build-evidence dependency is the public `zog.build_trace.BuildTrace` surface.
World/Comparison/Impact retain the build-trace 0.12 factual contracts; version 0.4.1
verification-history requires build-trace 0.13's explicit environment projection,
normally backed by build-record 0.8 or a compatible canonical implementation.

## Python namespace and release assembly

The canonical installed import is:

```python
import zog.integrate_observe
```

This repository owns only `src/zog/integrate_observe/`. It intentionally does not
provide `src/zog/__init__.py`; release-build owns the aggregate top-level package when
assembling the public PyPI distribution `zog`. This component repository is not
published as an independent public PyPI project.

The established executable remains `integrate-observe`, backed by the stable callable
`zog.integrate_observe.cli:main`. A module invocation uses
`python -m zog.integrate_observe`.

## Boundary

The intended ownership is:

- **image-build** produces build and observation facts and owns snapshot publication;
- **build-record** stores canonical immutable provenance and observation records;
- **build-trace** exposes those records read-only;
- **integrate-observe** selects a caller-declared baseline/candidate and compares their
  observed worlds;
- future Skiff reasoning consumes integration facts rather than inventing them.

Version 0.4.2 still does not infer chronology, resolve SONAME providers, select a
representative verification execution, label an outcome change a regression, infer
causation, score blast radius, assign severity, evaluate release policy, or persist
human findings/decisions. `impact` computes literal relationship reachability;
`verification-history` computes factual comparability only.

## Public model

A `world` binds one caller-selected canonical snapshot to its generation identity,
root-inventory digest, record-set digest and collection summaries. Evidence completeness
is explicit:

- `reference_closure_complete` and `missing_record_count` describe canonical graph
  integrity;
- `declared_gap_free`, gap counts and `declared_gap_summary` describe facts that are
  present but explicitly incomplete/unknown;
- `coverage` describes what observation collectors examined and whether that collection
  was complete, partial, unavailable, not performed or not applicable.

A World may therefore have complete canonical reference closure while still carrying
honest provenance gaps and unavailable verification coverage.

A `world-comparison` contains:

- identity comparison for baseline/candidate;
- build-trace canonical collection summaries;
- exact added/removed canonical records for verification definitions/executions,
  relationships, source provenance, coverage and declared gaps;
- source-provenance changes paired only when each side has exactly one observation for
  the same package;
- verification execution-set changes grouped by logical check ID + definition digest,
  retaining every observed outcome rather than selecting one;
- independent baseline/candidate evidence-completeness state;
- explicit negative interpretation flags documenting what was *not* inferred.

`declared_gap_changes` exposes build-trace's exact canonical gap rows, including exact
reason strings and presentation categories. A reduced gap count is only a factual
change; integrate-observe does not call it an improvement or release-readiness signal.

## Output schema

Version 0.4.2 retains `schema_version: 2` for `world`, `world-comparison`, `impact`,
`verification-history` and CLI error objects. The 0.4.2 outcome refinement is
additive: existing per-execution outcome arrays and their exact comparison remain,
while distinct-value and multiplicity fields are added. This is intentional: the ambiguous v0.1 `metadata_closure_complete` field was
removed rather than silently redefined.

Build-trace remains schema 1; integrate-observe validates the build-trace 0.12
completeness fields explicitly and rejects the older 0.11 completeness shape.

## Use

Install a compatible `zog.build_trace` companion from the approved Zog distribution, then:

```sh
python -m zog.integrate_observe \
  --project-root PROJECT \
  --host-id HOST \
  --record-store RECORDS \
  --record-project-id PROJECT_ID \
  world sha256:SNAPSHOT

python -m zog.integrate_observe \
  --project-root PROJECT \
  --host-id HOST \
  --record-store RECORDS \
  --record-project-id PROJECT_ID \
  compare sha256:BASELINE_SNAPSHOT sha256:CANDIDATE_SNAPSHOT

python -m zog.integrate_observe \
  --project-root PROJECT \
  --host-id HOST \
  --record-store RECORDS \
  --record-project-id PROJECT_ID \
  impact sha256:SNAPSHOT soname libfoo.so.7 \
  --relation needs-library --max-depth 3

python -m zog.integrate_observe \
  --project-root PROJECT \
  --host-id HOST \
  --record-store RECORDS \
  --record-project-id PROJECT_ID \
  verification-history image-build/installed-native-tools/command/0 \
  sha256:BASELINE_SNAPSHOT sha256:CANDIDATE_SNAPSHOT
```

Canonical snapshot operations no longer require `PROJECT/state/image-build` to exist;
build-trace 0.12 validates owner state lazily for operations that actually need it.
Every successful invocation writes one JSON object to stdout. The CLI still requires
explicit snapshot roots: integrate-observe does not choose releases, chronology or a
known-good baseline.

## Library

```python
from zog.build_trace import BuildTrace
from zog.integrate_observe import IntegrationObserver

trace = BuildTrace(
    project_root,
    host_id=host_id,
    record_store=record_store,
    record_project_id=project_id,
)
observer = IntegrationObserver(trace)
world = observer.world(snapshot_id)
comparison = observer.compare(baseline_snapshot_id, candidate_snapshot_id)

from zog.integrate_observe import ImpactAnalyzer, VerificationHistoryAnalyzer
impact = ImpactAnalyzer(trace).impact(
    candidate_snapshot_id, "soname", "libfoo.so.7",
    relation="needs-library", max_depth=3,
)
history = VerificationHistoryAnalyzer(trace).history(
    [baseline_snapshot_id, candidate_snapshot_id],
    "image-build/installed-native-tools/command/0",
)
```

`IntegrationObserver` is duck-typed against build-trace's public methods so tests can
exercise integration semantics without importing build-record or image-build.

## Validation

```sh
python -m unittest discover -s tests -v
```

The controlled fixture still models the initial interface/test example: `libfoo`
changes from providing `libfoo.so.7` to `libfoo.so.8`, a consumer continues to need
`libfoo.so.7`, and the same logical verification check changes from a PASS set to a
FAIL set. It now also verifies that declared gaps change independently from complete
reference closure and complete ELF observation coverage.

The initial real-host evaluation motivated the 0.2 completeness split: complete
canonical reference closure does not imply that all observed evidence is known.
Detailed operational acceptance records are retained outside this public source.

## Impact reachability

`impact` starts from one literal reverse selector supported by build-trace
(`package`, `package-output`, `soname`, or `path`). Direct matches are canonical
relationship rows. Their subject packages become a bounded breadth-first frontier;
transitive package reachability follows only recorded `declares-runtime-dependency`,
`declares-build-dependency`, `declares-test-dependency`, and `used-build-output`
relationships.

For a SONAME change, pass `--relation needs-library` when the intended first hop is
recorded consumers. Without that filter, literal reverse SONAME matching may also
include `provides-soname` rows; integrate-observe does not silently decide which
provider satisfies which consumer.

Every query retains build-trace relationship-family coverage and the snapshot's
reference-closure/declared-gap state. Cycles are bounded, package count is capped, and
no package is assigned severity. This is deterministic graph reachability, not causal
attribution or compatibility judgment.

The initial production acceptance compared two retained generation snapshots and
confirmed that relationship, source-provenance and verification changes remain
factual observations rather than inferred impact or regression verdicts.
Detailed operational records are retained outside this public source.

## Verification history and comparability

`verification-history` accepts 2–100 unique snapshot roots in caller-supplied order
and one logical check ID. It preserves every matching definition and execution from
build-trace; caller order is presentation order only and does not become inferred
chronology.

Adjacent points are compared across independent dimensions:

- definition digest: same, changed, missing or ambiguous;
- build-trace 0.13 execution-environment evidence;
- execution presence/count, retaining multiple executions;
- full outcome lists, including repeated outcomes;
- distinct outcome-value sets and per-outcome counts;
- multiplicity of repeated outcome evidence, independent of outcome labels;
- verification coverage;
- canonical reference closure and declared evidence gaps.

A transition is `comparable` only when definition identity is stable, executions
exist on both sides, and every execution on each side resolves to one explicit
environment identity with the same **environment contract + digest** across the pair.
A changed explicit environment is `not-comparable`. Legacy opaque environment
digests—even identical ones—are `insufficient-evidence`; unavailable environment
evidence is also insufficient. Mixed or multiple explicit environments are
`ambiguous`. Multiple executions alone remain comparable when all executions share
the same explicit environment identity.

`producer_policy_digest` is retained in each execution row by build-trace but is not
used as execution-environment identity. It may change because broader producer policy
changed while execution-relevant conditions remained identical.

Outcome reporting separates three facts. `outcomes.state` preserves the exact
sorted per-execution outcome-array comparison; `outcomes.value_set_state` compares
only distinct outcome values; `outcomes.multiplicity_state` compares the repetition
pattern independently of the labels. The exact arrays, distinct arrays and per-value
counts are all retained.

The factual `stable-definition-*-outcome-set` transition follows
`value_set_state`. Therefore `[PASS] -> [PASS, PASS]` means the same outcome set
with additional execution evidence, while `[PASS] -> [FAIL]` means the outcome set
changed even though both sides contain one execution.

Even a comparable stable-definition PASS-to-FAIL transition remains a factual
`stable-definition-changed-outcome-set`; version 0.4.2 does not classify it as a
regression.

The legacy-history acceptance demonstrated that matching PASS outcomes alone
cannot make a pair comparable when definitions or environment identities are
not established.

The v2 acceptance demonstrated that explicit environment evidence can pass through
image-build, build-record and build-trace to integrate-observe. The 0.4.2 outcome
refinement distinguishes `[PASS] -> [PASS, PASS]` (increased evidence multiplicity)
from a changed outcome value set. Independent compatible-v2-generation acceptance
remains outstanding.

## Next development

Wait for or produce through normal image-build operation a second independently
produced v2 generation with the same logical check definition and explicit environment
contract+digest as another v2 generation, then complete Level B production history
acceptance. Only after that factual substrate exists should a separately explicit
regression classifier be added. Provider resolution, blast-radius scoring and
release/baseline policy remain deferred.

## Public source licensing

This source is available under `BSD-3-Clause OR GPL-3.0-only`; see [LICENSE](LICENSE),
[LICENSES](LICENSES/) and [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).
This repository has a new clean public Git history. Earlier private Git history,
handoff records and deployment evidence were not imported.
