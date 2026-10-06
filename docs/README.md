# Documentation

![AcroBuild](assets/Acrobuild_logo.png)

The current documentation is intentionally small. Source code remains the final
authority for implemented behavior.

## Reading order

| Need | Read |
| --- | --- |
| Understand the system | [Architecture](ARCHITECTURE.md) |
| Change customer chat or property behavior | [Chat and property flow](CHAT_FLOW.md), then [AGENTS.md](../AGENTS.md) |
| Install, run, test, or troubleshoot | [Development guide](DEVELOPMENT.md) |
| Check implemented scope or limitations | [Product status](PRODUCT_STATUS.md) |
| Review the current frontend inventory and UX risks | [UI/UX frontend audit](UI_UX_FRONTEND_AUDIT.md) |
| Work with the property API | [CS API integration](integrations/CS_API.md) |
| Understand the compiled compatibility layer | [Compiled runtime](runtime/COMPILED_RUNTIME.md) |
| Review historical acceptance artifacts | [Evidence index](evidence/README.md) |
| Review dependency exceptions | [Security advisories](../requirements/SECURITY_ADVISORIES.md) |

The root [README](../README.md) is the shortest project entry point.
[AGENTS.md](../AGENTS.md) contains coding-agent rules rather than general product
documentation. [CHANGELOG.md](../CHANGELOG.md) is historical and may describe
behavior that later changed.

## Source material

`AcroBuild_AI_Simple_Feature_Matrix.xlsx` is a local, ignored product-requirement
workbook. Preserve it when present, but do not treat it as proof of implemented
behavior. Client PDFs are not currently present in this checkout; if supplied,
keep them as source material and do not infer that every requested feature exists.

## Evidence policy

Human-facing guides stay at the top of `docs/`. Generated transcripts and large
acceptance exports live under `docs/evidence/`. Live-result files are snapshots
of a particular catalogue and date; rerun the owning script before using them as
current operational evidence.
