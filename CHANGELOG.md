# Changelog

## 0.0.1 — Unreleased

Initial SeedBank candidate: local life archives, diary and memory views, explicit dormancy/recovery, model-service configuration, local Live2D presentation, chat adapters and manually invoked local text plugins.

### Fixed

- Require OneBot HTTP report signatures before dispatching QQ messages. Reject missing signing configuration and bound HTTP/event work queues.
- Persist QQ message/delivery identifiers across adapter restarts. Duplicate events do not regenerate or resend replies; uncertain sends are not automatically retried.
- Require explicit success fields in OneBot send receipts; empty or incomplete responses are not reported as delivered.
- Keep a visible character-model selection button on the companion stage.
- Exclude the unused Qt Virtual Keyboard plugin and library from the Windows archive.
- Preserve Unicode in packaged plugin/channel worker communication; return escaped plugin JSON independently of the Windows system codepage.

### Documentation and maintenance

- Add isolated QQ security regressions, a reproducible Windows dependency snapshot, manual-only CI, issue/PR templates and security reporting guidance.
- Restore a runnable five-page capture entry using artificial offline data; screenshots record the actual runtime and scenario.
- Repair protocol links left behind by the source migration and provide current implementation navigation.

### Scope

Test evidence is recorded in [acceptance](docs/acceptance.md). Offline tests do not prove live-service compatibility or long-term continuity. SDK publication conditions and character/branding permissions remain separate release requirements; see [licensing review](docs/licensing-review.md).
