# Security And Scale

## Current Security Posture

The pilot baseline has input length and upload-size limits, optional JWT authentication, a process-local rate limiter, source citations, source-label integrity, opt-in external research, approved-domain filtering, PDF parsing, and user-scoped analytics reads.

This is not yet sufficient for a production financial-institution deployment. The application lacks organization-level authorization, document ACLs, centralized audit logs, encryption/key-management design, durable job processing, operational monitoring, and backup/retention controls.

## Data Handling Rules For Pilots

- Use only approved, non-sensitive policy documents until contractual and security controls are in place.
- Do not enable web research without a documented approved-domain list and a customer acknowledgement that prompts go to the configured provider.
- Do not treat the local hash index as a security boundary or as a semantic-evaluation substitute.
- Do not ingest customer account data, secrets, or PHI in the initial finance pilot.

## Threats And Controls

| Threat | Current control | Required production control |
| --- | --- | --- |
| Prompt injection in sources | Model prompt treats context as untrusted | source sanitization, policy tests, restricted tool permissions |
| Unsupported answer | citations and no-answer routing | evaluated answer policies and human review queues |
| Tenant leakage | user-scoped analytics | organization/document ACLs and permission-aware retrieval |
| Data egress | web disabled by default | DPA, source governance, redaction, egress logs |
| Upload abuse | extension and size checks | malware scan, content-type validation, object isolation |
| Lost data | local SQLite files | managed database, encrypted backups, restore drills |
| Rate abuse | in-memory limiter | distributed rate limiting and WAF controls |

## Scale Plan

### 10 users

The current FastAPI, Streamlit, SQLite, and local index architecture is suitable for a tightly managed paid proof of value with a small corpus.

### 1,000 users

Move data to a managed relational database, place uploads in object storage, run index work in a queue, add Redis or equivalent distributed limits/cache, and centralize logs/traces. Make API instances stateless.

### 100,000 users

Use organization-sharded data, asynchronous ingestion workers, versioned indexes, regional deployment, workload isolation, SLOs, capacity tests, alerting, and disaster-recovery exercises. Re-evaluate retrieval architecture based on evaluation quality, cost, and latency rather than adopting a vector database by default.
