# Third-party software and artwork

SeedBank's own source and original documentation are MIT licensed. That does **not** relicense Python, Qt, Live2D, other runtime dependencies, character artwork or models.

## Runtime software

The Windows candidate includes Python, PySide6 / Qt, shiboken6, live2d-py, PyOpenGL, Pillow, NumPy and channel SDK dependencies. PyInstaller supplies the executable bootloader. The candidate's `third-party/` directory contains distribution license files and an `inventory.json` of versions and upstream links collected from the build environment. This inventory describes bundled build dependencies, not a vulnerability audit or proof that every optional module is loaded.

- Python: [Python license](https://docs.python.org/3/license.html).
- PySide6 / Qt / shiboken6: LGPL/GPL/commercial terms vary by component. The LGPL distribution must preserve users' applicable rights, notices and ability to replace or relink covered libraries. SeedBank source and its build recipe are provided; this alone is not a full binary-distribution compliance determination. See [Qt licensing](https://www.qt.io/licensing/open-source-lgpl-obligations).
- live2d-py: MIT wrapper, Copyright (c) 2024 Arkueid. This does not turn the embedded Live2D Cubism components into MIT software.
- Live2D Cubism: Copyright Live2D Inc.; [SDK publication licensing](https://www.live2d.com/en/sdk/license/), [Proprietary Software License](https://www.live2d.com/eula/live2d-proprietary-software-license-agreement_en.html), [Open Software License](https://www.live2d.com/eula/live2d-open-software-license-agreement_en.html).

## Before public binary publication

The current candidate remains private. Live2D's official licensing page distinguishes ordinary applications from **Expandable Applications**, including a specific AI/chatbot section. Because SeedBank accepts user-selected models and supports extension, its applicable category and publication terms need confirmation with Live2D; this is a project-specific unresolved classification, not a claim that a fee is necessarily due or that an exemption applies. No publisher approval is recorded here. Confirm applicable Qt redistribution requirements as well before publishing the binary.

## Artwork

The brand image is derived from the maintainer's supplied character reference. Character design: **ZipZipPipe** and **上善无形**. The reference Live2D model's illustration and separation: **神宫凉子**; rigging: **霓虹猫_NeonNeko**. Full links, scope and unresolved public brand permission are recorded in [docs/assets.md](docs/assets.md).

No third-party Live2D model, `.moc3`, model textures or motions are distributed in the application source or candidate ZIP. Users select their own local model and must follow its author's terms. The two egg directories are textual birth templates, not model assets.
