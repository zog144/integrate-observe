# World/Comparison design — v0.2

## World

A World is not a release. It is a caller-selected immutable observation snapshot plus
its build-trace projection. Selection establishes the *role* of baseline/candidate for
one comparison; it does not establish historical chronology.

The World stores build-trace's canonical generation and observation identities rather
than copying image-build or build-record internals.

## Evidence completeness

The first real-host acceptance showed that one aggregate completeness boolean was
insufficient. Version 0.2 therefore treats three dimensions independently.

### Reference closure

`reference_closure_complete` answers only whether every canonical reference reachable
from the selected snapshot is present. Missing records are graph-integrity facts.

### Declared gaps

`declared_gap_free`, counts and summaries describe reachable canonical records that
are present but explicitly say some fact is unknown, external or otherwise incomplete.
A declared gap does not make reference closure incomplete.

The `declared-gaps` collection is projected by build-trace and is included in factual
WorldComparison set changes. The exact canonical reason text is evidence; the category
is a build-trace presentation classification.

### Observation coverage

Coverage describes whether a collector examined its declared scope and with what
outcome. Complete zero-count coverage is different from unavailable, partial,
not-performed or absent coverage. Coverage is not canonical-reference integrity and is
not equivalent to declared provenance completeness.

## Comparison

Comparison is deterministic over two explicitly selected Worlds. It has four layers:

1. **Canonical set changes** — exact added/removed record identities from build-trace,
   including declared-gap rows.
2. **Safe pairings** — package source observations are paired only when unique on each
   side; verification executions are grouped by logical check ID and definition digest
   without choosing a representative execution.
3. **Evidence-completeness comparison** — baseline/candidate reference closure,
   declared gaps and observation coverage remain separate factual state.
4. **Interpretation boundaries** — explicit flags remain false for chronology,
   provider resolution, regression, causation, blast radius, severity and policy.

A later integration-analysis layer may interpret these facts, but v0.2 remains a
reliable answer to the narrower question: *what recorded observations and evidence
conditions differ between these two caller-selected worlds?*

## Schema boundary

integrate-observe output schema 2 requires build-trace's schema-1 v0.12 completeness
contract. It intentionally rejects the older v0.11 snapshot shape containing only
`metadata_closure_complete`; that field mixed reference closure with declared gaps and
must not be reconstructed under the old name.


## Impact reachability — v0.3

Impact analysis is a single-World query over build-trace's public
`relationship_traversal` API. It does not read build-record storage directly.

The root is a caller-supplied literal reverse selector: package, package-output,
SONAME or path. An optional relationship filter narrows the first hop. Subject packages
from those canonical rows form depth 1.

Further depths follow only explicit package-oriented relationships:

- `declares-runtime-dependency`;
- `declares-build-dependency`;
- `declares-test-dependency`;
- `used-build-output`.

This is intentionally not provider resolution. A package that provides a SONAME is
not automatically paired with artifacts that need that SONAME. The caller can request
`soname + needs-library` to start from literal consumers without asserting which
package satisfies them.

Reachability is breadth-first, cycle-safe and bounded by caller depth and package-count
limits. Exact relationship rows remain attached to edges. Query-specific coverage and
snapshot completeness are retained so zero matches under partial coverage do not become
negative proof.

The output states `reachability_computed: true` while keeping provider resolution,
causation, blast-radius scoring, severity and policy false.


## Verification history and comparability — v0.4

Verification history is a caller-ordered query over build-trace's public
`verification_history` API. The caller supplies 2–100 unique canonical snapshots and
one logical check ID. Snapshot order is preserved exactly but is not asserted to be
historical chronology.

Every point retains all matching verification definitions and executions, verification
coverage, generation identity, reference-closure state and declared-gap state. No
representative execution is selected.

Adjacent points are assessed along separate factual dimensions:

1. definition-digest state;
2. environment-digest state;
3. execution presence and multiplicity;
4. ordered-by-value outcome sets;
5. verification coverage.

Comparability is deliberately conservative. Stable definition and environment identity
plus recorded executions on both sides is `comparable`. Changed definition or
environment is `not-comparable`. Missing definition/environment/execution evidence is
`insufficient-evidence`. Multiple definitions or multiple distinct environment
identities are `ambiguous`.

Multiple executions with one stable definition/environment remain preserved as an
execution set. The analyzer does not choose a representative run.

The factual transition vocabulary includes
`stable-definition-same-outcome-set`,
`stable-definition-changed-outcome-set`, `definition-changed`,
`definition-missing`, `environment-changed`, `environment-missing`,
`execution-missing`, and ambiguity states.

No transition is a regression verdict in v0.4. In particular, a same-definition,
same-environment PASS-to-FAIL transition is useful evidence but remains
`regression_classified: false` until a separate regression contract is designed and
accepted against real production evidence.


## Verification environment compatibility — v0.4.1

Build-trace 0.13 distinguishes canonical execution-environment evidence from the
historical opaque environment digest.

For each execution, integrate-observe consumes only build-trace's public
`environment` projection:

- `availability = available`: explicit contract, digest and descriptor;
- `availability = legacy-opaque`: historical opaque producer digest;
- `availability = unavailable`: no usable environment identity.

Two adjacent history points satisfy the environment-comparability requirement only
when all executions on each side resolve to exactly one explicit environment identity
and the pair has the same `contract + digest`. Descriptor bytes remain preserved in
the execution rows as evidence, but canonical build-record validation is authoritative
for descriptor/digest agreement.

An identical legacy opaque digest does not establish comparability. Legacy-to-explicit,
legacy-to-legacy and unavailable cases remain `insufficient-evidence`. Multiple
different explicit environments, or mixed explicit/legacy/unavailable evidence within
one point, are `ambiguous`.

The separate `producer_policy_digest` does not participate in environment
comparability. It records broader producer policy and may legitimately change while the
execution-relevant environment remains stable.

A build-trace execution row that lacks the 0.13 `environment` projection is rejected
with `unsupported-build-trace-contract` rather than silently falling back to the old
flat `environment_digest` field.

This compatibility pass does not classify regressions. A stable-definition,
same-explicit-environment PASS-to-FAIL remains a factual comparable outcome-set change
with `regression_classified: false`.


## Outcome value and multiplicity semantics — v0.4.2

Production v2 acceptance produced one historical PASS execution in the baseline
snapshot and historical PASS plus a new explicit-v2 PASS execution in the refreshed
snapshot. The evidence arrays were therefore `[PASS]` and `[PASS, PASS]`.

Those arrays differ, but the observed outcome value set does not. Version 0.4.2 keeps
that distinction explicit instead of treating execution multiplicity as a changed
verification result.

The transition `outcomes` object retains:

- `before` / `after`: sorted per-execution outcome arrays, including repeats;
- `state`: compatibility field comparing those exact arrays;
- `distinct_before` / `distinct_after`: unique outcome values;
- `value_set_state`: comparison of the unique outcome values;
- `counts_before` / `counts_after`: exact count for each outcome value;
- `multiplicity_state`: comparison of repetition patterns independently of the
  outcome labels.

For example:

```text
[PASS] -> [PASS, PASS]
state: changed
value_set_state: same
multiplicity_state: changed
factual transition: stable-definition-same-outcome-set
```

while:

```text
[PASS] -> [FAIL]
state: changed
value_set_state: changed
multiplicity_state: same
factual transition: stable-definition-changed-outcome-set
```

Execution count remains separately available in the transition's `execution` object.

The factual `stable-definition-same-outcome-set` /
`stable-definition-changed-outcome-set` choice is driven only by
`value_set_state`. Environment ambiguity, definition changes and missing evidence
continue to take precedence in the factual transition vocabulary.

This pass does not deduplicate executions, select a representative execution, infer
flakiness, classify regressions, or reinterpret mixed legacy/v2 environment evidence.
