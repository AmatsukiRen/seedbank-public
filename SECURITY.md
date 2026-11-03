# Security / 安全问题

SeedBank can access private life archives, model credentials and explicitly enabled chat channels. Please report vulnerabilities privately, using an artificial reproduction without real conversations, life packs, keys or tokens.

## Reporting

When private vulnerability reporting is enabled, use GitHub's **Security → Report a vulnerability** for [this repository](https://github.com/AmatsukiRen/seedbank-public/security/advisories/new).

Use the private reporting entry above. If GitHub does not offer that entry for your account, open an Issue asking only for a private contact method; do not include exploit details or sensitive attachments in that Issue.

Include the affected version/commit, operating system, relevant component, expected and actual behavior, impact and a minimal artificial reproduction. Redact headers, paths, account identifiers and credentials. Do not test against another person's installation or public service.

## Scope and support

Security fixes target the current development branch and the latest released version. Version 0.0.1 is a preview, not a stable security-audited release.

Local plugins run with the user's operating-system permissions and are **not sandboxed**. Only enable plugins from a trusted source. Chat adapters are opt-in; QQ HTTP reports require a shared signing secret in addition to owner/group checks. Platform tokens and model API keys have separate purposes.

## 中文说明

发现安全问题时请使用上方 GitHub 私密漏洞报告入口，并使用人工数据复现。公开 Issue 只适合普通问题；不要上传真实生命包、聊天、密钥或漏洞利用细节。若入口不可用，请仅请求私下联系方式，不附漏洞细节。
