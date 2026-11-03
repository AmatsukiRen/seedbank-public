# Changelog

## Unreleased

- Restore visible header and footer close buttons in the dormancy/recovery dialog and support Escape, including while status is loading. Dismissal never applies a lifecycle choice. Three new UI regressions and a user-run entry are prepared; not yet executed. See [repair and acceptance steps](docs/fix-lifecycle-dialog-close.md).

## 0.0.1 — 2026-11-04 · Preview

Initial SeedBank candidate: local life archives, diary and memory views, explicit dormancy/recovery, model-service configuration, local Live2D presentation, chat adapters and manually invoked local text plugins.

### Fixed

- Require OneBot HTTP report signatures before dispatching QQ messages. Reject missing signing configuration and bound HTTP/event work queues.
- Persist QQ message/delivery identifiers across adapter restarts. Duplicate events do not regenerate or resend replies; uncertain sends are not automatically retried.
- Require explicit success fields in OneBot send receipts; empty or incomplete responses are not reported as delivered.
- Keep a visible character-model selection button on the companion stage.
- Exclude the unused Qt Virtual Keyboard plugin and library from the Windows archive.
- Preserve Unicode in packaged plugin/channel worker communication; return escaped plugin JSON independently of the Windows system codepage.

### Documentation and maintenance

- Publish the user-tested runtime from source commit 3e13707 without recompiling it; record updated release documents under their own commit. User-run packaging, archive/notice, isolated UI/plugin and two-cycle native Live2D checks passed on 2026-11-04.
- Remove unused Qt Virtual Keyboard, QML debugging/Quick 3D and PDF dependencies. Include LGPL/GPL texts, upstream source archives and collected source notices; retain untested rebuild instructions and independent SDK licensing information.
- Add three-language download instructions, character and Live2D credits, the creator's CC BY-NC-SA statement and model acquisition links. Demo model files are not bundled. Publication follows the maintainer's decision; no third-party approval is claimed.
- Add isolated QQ security regressions, a reproducible Windows dependency snapshot, manual-only CI, issue/PR templates and security reporting guidance.
- Restore a runnable five-page capture entry using artificial offline data; screenshots record the actual runtime and scenario.
- Repair protocol links left behind by the source migration and provide current implementation navigation.

### Scope

Test evidence is recorded in [acceptance](docs/acceptance.md). Offline tests do not prove live-service compatibility or long-term continuity. Release assembly updates documents and notices around the same executable; it does not rerun the application. SDK licensing and artwork rights remain independent of the software's MIT license; see [licensing review](docs/licensing-review.md).
