# Changelog

## Unreleased

- Defaulted API and demo requests to strict source-backed mode: extractive citations or abstention, with no LLM, model-knowledge, or video fallback.
- Added a deterministic strict-mode smoke corpus, evaluation runner, and a 100-case paid-pilot release gate.

## 2026-07-22 - Finance-first paid-pilot baseline

### Added

- Terra Policy Desk finance-first demo positioning.
- PDF text extraction through `pypdf` and clear rejection of unreadable PDFs.
- Regression tests for grounding, PDF extraction, web filtering, source integrity, and analytics isolation.
- Living product, architecture, roadmap, decision, testing, and security documentation.

### Changed

- Hash retrieval now requires meaningful evidence and uses strongest grounded evidence for routing confidence.
- Default web research is disabled.
- Web results are strictly filtered by configured approved domains.
- `kb` and `web` answer labels require citations.
- Analytics summary and recent views are scoped to the current user.

### Preserved

- Finance and healthcare remain separate code and knowledge-base domains.
- Existing API contracts remain compatible; request-level overrides still work.
