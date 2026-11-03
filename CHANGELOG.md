# Changelog

## Unreleased — opt-in group observation

- Add separate observation groups, silent source recording, bounded batch summaries, persistent daily call allowances and source-scoped recall. Preserve normal allowlisted mention replies. See [behavior and platform limits](docs/group-observation.md).
- Add four-language settings, paged source/note review and withdrawal from future recall. No model weight training, historical-message scraping or unsolicited group sends.
- Current revision awaits user-run offline and packaged checks. The earlier 15-case draft result does not cover the subsequent changes. Published 0.0.2 assets are unchanged.

## 0.0.2 — 2026-11-04 · One life across channels

- Give the channel, runtime self-knowledge, WorkBuddy and dialog fixes below a separate version and Release page. The application, Windows metadata, archive names and three-language download links now identify 0.0.2; the 0.0.1 release remains available.
- Reuse the same life-pack format. Existing individuals can continue in 0.0.2 without being recreated. Model and platform credentials remain local to each user.
- Keep the release as a preview. Actual-platform delivery, WorkBuddy account calls and native Live2D are outside this revision's isolated acceptance scope; dated results are recorded in [acceptance](docs/acceptance.md).

## 0.0.1 — 2026-11-04 · Channels and runtime self-knowledge revision

- Follow up across Telegram, Discord, Feishu and DingTalk: accept allowlisted bare mentions, preserve literal Telegram text, require a Telegram message receipt, and expose generation/delivery stages. Count AstrBot handoff separately from platform delivery. Prompt v44 and new cross-channel persistence/privacy cases passed isolated integration checks. See [channels](docs/channels.md) and [exact acceptance scope](docs/acceptance.md).

- Accept OneBot CQ-string group mentions as well as message arrays, and respond to a bare allowed mention. Reject incomplete login receipts and show local QQ processing/delivery diagnostics. Verify shared-pack persistence and desktop recall without real QQ traffic. See [QQ group replies](docs/qq-group-replies.md).

- Provide per-turn birth identity, actual inbound channel and local connection observations to the model. Keep private identity and other-channel activity out of group prompts; never infer online status from saved settings or chat text. See [runtime self-knowledge](docs/runtime-self-knowledge.md).
- Preserve original user speech under prompt pressure by omitting the optional new-project schema before evicting it. Add isolated regression coverage for runtime state, privacy and long follow-up conversations.

- Add an experimental text provider using the official CodeBuddy CLI signed into the user's WorkBuddy account. Require an explicit model ID; desktop authentication and model selection are not imported.
- Add separate usage receipts, bounded activity calls, tool-disabled ephemeral requests, failure handling and four-language settings. The 50-case offline WorkBuddy/Codex/preset/UI suite passed on 2026-11-04; no real CodeBuddy call has been made. See [setup and limitations](docs/workbuddy.md).

## 0.0.1 — 2026-11-04 · Dialog-close artifact revision

- Restore visible header and footer close buttons in the dormancy/recovery dialog and support Escape, including while status is loading. Dismissal never applies a lifecycle choice. Runtime source: `b51bb5c`. The maintainer requested updating the existing preview assets; three new UI regressions and a user-run entry are prepared but have not been executed. See [repair and acceptance steps](docs/fix-lifecycle-dialog-close.md).
- Preserve the initial Git tag. The attached source ZIP follows the repaired executable; artifact revision and current hashes are recorded separately. Original acceptance below remains historical.

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
