# integrate-observe: source and dependency notices

The first-party software and documentation in this public repository are licensed
at your option under `BSD-3-Clause OR GPL-3.0-only`. See [LICENSE](LICENSE)
and the complete texts under [LICENSES](LICENSES/).

## Dependencies

`integrate-observe` consumes the separate public API exposed by
`zog.build_trace`; this repository does not vendor build-trace, build-record
or image-build, and its source does not grant additional rights to their code.
The public Zog PyPI distribution is assembled from component repositories by
release-build; this component is not independently published to PyPI.

Build tooling (setuptools) and any dependencies acquired at installation or
build time retain their respective licenses and notices. A downstream
distribution must review the actual packages and artifacts it redistributes.

## Scope of this public export

The tests use synthetic observation records; no production result archives,
live credentials, host state or private operational evidence are included.
Historical private branches, tags, issues, logs and unpublished handoff
records are not part of the public Git history.
