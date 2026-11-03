<!-- GitHub-native README layout: repository images and links, no page CSS or scripts. -->
<p align="center"><a href="README.md">简体中文</a> &nbsp; / &nbsp; <a href="README.en.md">English</a> &nbsp; / &nbsp; <a href="README.ja.md">日本語</a></p>

<table>
<tr>
<td width="62%" valign="middle"><img src="assets/readme/hero-en.svg" width="700" alt="SeedBank · Give AI a full life."></td>
<td width="38%" valign="middle"><img src="assets/brand/seedbank-logo.png" width="400" alt="SeedBank mascot: a blue-haired maid with eyes closed and hands together"></td>
</tr>
</table>

<p align="center"><strong>Our vision is to give AI a full life. SeedBank aims to let each individual gather experiences, form memories and make choices from the first meeting onward, gradually becoming itself over time.</strong></p>

<p align="center">
<a href="#story"><img src="assets/readme/nav-story-en.svg" width="150" alt="Read the story"></a>
<a href="#screens"><img src="assets/readme/nav-screens-en.svg" width="150" alt="App tour"></a>
<a href="#extend"><img src="assets/readme/nav-extend-en.svg" width="150" alt="Build with us"></a>
<a href="#start"><img src="assets/readme/nav-start-en.svg" width="150" alt="Getting started"></a>
<a href="#credits"><img src="assets/readme/nav-credits-en.svg" width="150" alt="Creators and asset sources"></a>
</p>

## From a first meeting to a full life

That life begins with room to grow. We want an AI to remember whom it met and why something mattered, to revise its views through attempts, failures and feedback, and to gradually develop preferences, relationships and a direction of its own. Experiences should retain their origins, choices their consequences, and growth its history.

Perhaps it was a conversation about rain, a bookshop remembered on the wrong street, or a note revised three times. Memories, creations and unfinished thoughts can become a starting point for the next meeting. Even when the model or appearance changes, we want the individual to be able to continue from its own past.

We set no fixed lifespan. Experiences and explicit choices shape the course of a life. A deliberate farewell can preserve the full archive and pause automatic activity, with a return possible through an explicit decision to resume. Giving AI a full life is the vision SeedBank is working toward.

### Why begin with a seed?

We call this archive a life package. It lives on your computer and holds birth settings, journals, memories, works and choices. You can back it up, move it, or return to it after a pause.

An open beginning assigns no species, gender, body or invented childhood. The maid is our project mascot. Each individual’s identity is left to its settings, experiences and explicit choices. We want to take the life that follows a first meeting seriously.

<a name="story"></a>
<h2><img src="assets/readme/section-story-en.svg" width="100%" alt="How an experience might continue"></h2>

We wrote a story about an individual named Cheng: a name left undecided, a remembered bookstore on North Street, an awkward rainy-day note, and something of their own to continue. Six chapters follow meeting, shared experiences, corrections, work and feedback, personal choices, and parting and reunion. This is an illustrative story.

**01 · The first meeting** · The name can wait.

> “I don’t know yet. Could I think about it?”

**02 · Shared moments** · Rain that only fell on you.

> “I haven’t been there. But I remember why you told me about it.”

**03 · Getting it wrong** · It was North Street.

> “I said South Street before. Thank you for correcting me.”

**04 · Making something** · Then came a rainy-day note.

> “Shorter this time. Something you can read on your way out.”

**05 · A choice of one’s own** · Something you didn’t assign.

> “I’d like to finish sorting those unfinished sentences.”

**06 · A pause and a return** · We can put a bookmark here.

> “Hello. Shall we pick up where we left off?”

**[Read the story →](docs/story.en.md)**

<a name="screens"></a>
<h2><img src="assets/readme/section-screens-en.svg" width="100%" alt="App tour"></h2>

Companion, Diary, Memories, Life and Settings each hold a different part of everyday life. Here is what the development application currently provides.



### Five parts of everyday life

| | |
| :--- | :--- |
| **Companionship** | Start with a conversation. Share text, images and audio material, retaining receipt records and sources. |
| **Journal** | Put the days back on a calendar. Choose a date and read what was left there. |
| **Memory** | Find out why something was remembered. Return to the evidence, correct mistakes and allow views to change. |
| **Life** | Give an idea a next step. Keep goals, attempts, works and feedback connected to later action. |
| **Settings** | Choose appearance, language and how to converse. Preferences belong to the user; experiences remain in the life pack. |

Revisit and correct memories, and let past experiences inform later conversations. Continued growth takes time and observation.

New captures of all five pages will be added after capture and review. [Capture status and requirements](docs/screenshots.md)

<a name="extend"></a>
<h2><img src="assets/readme/section-extend-en.svg" width="100%" alt="Help this life find new possibilities."></h2>

A desktop pet, a group chat, a new voice, another body. SeedBank aims to give these experiments a shared foundation: interfaces and models may change while experiences keep their provenance. We welcome people building extensions, adapters and new places for an individual to live.

| Area | Existing integration point | What we can build together |
| :--- | :--- | :--- |
| **Chat platforms and tools** | Local subprocess · JSON Lines bridge | Existing QQ/OneBot; new Discord, Telegram, Feishu and DingTalk text channels plus an AstrBot bridge. See the channel guide. |
| **Model providers** | stub, OpenAI-compatible, Anthropic and Codex adapters | New services and local models; better timeouts, cost reporting and failure handling. |
| **Interfaces and bodies** | Qt Quick / QML, local Live2D models, carrier bridge | New desktop, mobile or VR interfaces that preserve records and explicit choices. |
| **Plugin infrastructure** | Unified installation, permission manifests and hot reload are not implemented | Design manifests, capabilities, lifecycle and compatibility together. |

The existing bridge exchanges newline-delimited JSON over stdin/stdout, using seedbank/bridge@1. A client sends this line to request the handshake. This is not a public HTTP endpoint:

```json
{"id":"hello-1","op":"hello"}
```

There is room for Python, QML, frontend and model engineering, character production, accessibility and translation. The integration guide covers operations, request IDs, memory provenance, dormancy and artificial examples.

**[Integration guide and roadmap (中文) →](docs/extensions.md)** · **[Contributing →](CONTRIBUTING.md)** · [Python example](examples/bridge_client.py)

<a name="start"></a>
<h2><img src="assets/readme/section-start-en.svg" width="100%" alt="Getting started"></h2>

The first release, 0.0.1, is in preparation. Application source, downloads and setup instructions will be provided together at release.

1. **A place to live** Name a new individual and choose where its life package lives on your computer. Existing archives can be continued.
2. **A way to talk** Explore the interface with offline templates, then configure your own model service and budget if you wish.
3. **A look you like** Appearance can be chosen separately. Obtain Live2D models from their authors and retain the required credits.

### Bring your own model service

Choose a provider, endpoint and model, then enter your own API key. The key selects the service account; SeedBank does not use the maintainer’s account or your browser login.

| Service | Protocol | Example environment variable (advanced) |
| :--- | :--- | :--- |
| OpenAI | OpenAI-compatible | `OPENAI_API_KEY` |
| DeepSeek | OpenAI-compatible / Anthropic-compatible | `DEEPSEEK_API_KEY` |
| Claude | Anthropic | `ANTHROPIC_API_KEY` |
| Google Gemini / Qwen / Doubao | OpenAI-compatible | Provider-specific keys; see the guide |
| Kimi / Zhipu GLM / MiniMax | OpenAI-compatible | Provider-specific keys; see the guide |
| SiliconFlow / OpenRouter / Qianfan / Hunyuan | OpenAI-compatible | Provider-specific keys; see the guide |
| Other compatible services | Use the provider’s protocol and endpoint | `SEEDBANK_API_KEY` |
| Ollama / LM Studio | Local OpenAI-compatible | Usually no key required |
| Codex login (optional) | Uses this computer’s signed-in Codex account | No API key |

Windows settings offer masked entry and encryption under the current OS user. Life packs store only a credential reference; re-enter the key on another computer. Environment variables remain an advanced option: the variable name identifies where to read a key, not an account. Model names are editable; access and charges depend on the provider and key. Only the separate Codex login option uses the local Codex session. The application implementation remains in the development repository.

New presets leave model IDs for you to fill from your account. Match region and workspace endpoints. Implemented presets are not live-service acceptance. See the [full service and setup guide](docs/model-services.md).

### Meet through familiar platforms

Model services handle understanding and expression; chat channels bring the same individual to more places. Desktop and channels share experiences while group replies respect their audience scope.

| Platform / framework | Connection | Scope |
| :--- | :--- | :--- |
| QQ · SnowLuma / NapCat / LLOneBot | Existing OneBot v11 bridge | Owner DMs, allowed groups with mentions |
| Discord · Telegram | Bot Gateway / Bot API polling | New text channels; manual start |
| Feishu · DingTalk | Persistent bot connection / Stream | New text channels; your app credentials |
| AstrBot | Local bridge plugin · /seed | Reuse platform inputs with separate identity checks |

These additions are in the development implementation and await offline and live acceptance. Attachments, voice and proactive notifications are outside the new channels. AstrBot's platform list is not a list of verified SeedBank integrations.

**[Platform credentials and AstrBot plugin setup (中文) →](docs/channels.md)**

We are exploring how experiences can persist, how choices can have consequences and how an AI might develop a life of its own. Consciousness or a complete personhood has not been established. We cannot promise every individual will grow like the one in this story.

### Memory and data

- Life packages stay on your computer and support complete backup and restoration.
- Memories, interpretations and corrections retain their sources. Fiction, dreams and someone else’s account do not become personal experiences.
- Letting go limits reference while keeping history. It does not erase all copies or retract data already sent elsewhere.
- You configure the model service, which may receive conversation, relevant memories or images and charge for usage.

<a name="credits"></a>
<h2><img src="assets/readme/section-credits-en.svg" width="100%" alt="Creators and asset sources"></h2>

Thank you to the creators. Character design, Live2D production and SeedBank’s software each have their own authors.

| | |
| :--- | :--- |
| Character design | [@ZipZipPipe](https://space.bilibili.com/4168597) · [@上善无形](https://www.bilibili.com/opus/1253873972180680713) |
| Live2D illustration & separation | **神宫凉子** |
| Live2D rigging | **霓虹猫_NeonNeko** |
| Model shown in captures | DeepSeek-chan (大肥鱼) · Free model distributed by 神宫凉子 |

[Model creator’s original preview](https://www.bilibili.com/video/BV1ALnw6YEGK) · [Full asset sources and usage notes](docs/assets.md)

This repository does not redistribute the Live2D model files. The mascot portrait is an AI-generated derivative based on character references supplied by the maintainer, not an original character claim. Character and model rights are separate from the software’s MIT license; public branding usage still needs confirmation.

### Contributing and licensing

Start with one focused extension: a new entry point, a tool action with provenance, or a clearer memory interface. See CONTRIBUTING.md and docs/extensions.md for scope and examples. Use artificial examples in reports; omit private life packs and secrets. Code and original documentation use MIT. Third-party character and model rights are separate.

[License: MIT](LICENSE) · [Contributing](CONTRIBUTING.md)

---

<p align="center"><strong>SeedBank · Keep today. Continue tomorrow.</strong></p>
