# Third-party software and artwork

SeedBank's own source and original documentation are MIT licensed. That does **not** relicense Python, Qt, Live2D, other runtime dependencies, character artwork or models.

## Runtime software

The Windows candidate includes Python, PySide6 / Qt, shiboken6, live2d-py, PyOpenGL, Pillow, NumPy and channel SDK dependencies. PyInstaller supplies the executable bootloader. The candidate's `third-party/` directory contains distribution license files and an `inventory.json` of versions and upstream links collected from the build environment. This inventory describes bundled build dependencies, not a vulnerability audit or proof that every optional module is loaded.

- Python: [Python license](https://docs.python.org/3/license.html).
- PySide6 / Qt / shiboken6: LGPL/GPL/commercial terms vary by component. The LGPL distribution must preserve users' applicable rights, notices and ability to replace or relink covered libraries. SeedBank source and its build recipe are provided; this alone is not a full binary-distribution compliance determination. See [Qt licensing](https://www.qt.io/licensing/open-source-lgpl-obligations).
- live2d-py: MIT wrapper, Copyright (c) 2024 Arkueid. This does not turn the embedded Live2D Cubism components into MIT software.
- Live2D Cubism: Copyright Live2D Inc.; [SDK publication licensing](https://www.live2d.com/en/sdk/license/), [Proprietary Software License](https://www.live2d.com/eula/live2d-proprietary-software-license-agreement_en.html), [Open Software License](https://www.live2d.com/eula/live2d-open-software-license-agreement_en.html).

The follow-up Qt review found an unused QML debug profiler and its GPLv3/commercial Quick3DUtils dependency in the earlier private executable, and missing LGPL/GPL texts in its collected wheel notices. The packaging recipe excludes this debug dependency and the unused PDF reader, and supplies both license texts from Qt upstream. The user's 2026-11-04 checks passed for executable SHA256 `1da9030c942ec39cbd60d0f903213436f1f112d6b25926a02ab9fa20147a2759`, including archive exclusions, icon resources, ZIP notices and isolated application checks; see [dated acceptance](docs/acceptance.md). The original production receipt still records that no tests were run during production. Corresponding source, embedded third-party notices and the modified-library rebuild path remain pending. See [Qt redistribution work](docs/qt-redistribution.md). A wheel's commercial-license reference is not a commercial license held by this project.

## Before public binary publication

The current candidate remains private. Live2D's official licensing page distinguishes ordinary applications from **Expandable Applications**, including a specific AI/chatbot section. SeedBank accepts user-selected models; we therefore infer that it likely falls within that category. [The category's terms](https://www.live2d.com/en/sdk/license/expandable/) require review and a special agreement even for individuals or small businesses. Fully free applications may qualify under separately specified conditions. This is not an official project-specific classification or a claim that fees are necessarily due. No publisher approval is recorded here. Confirm applicable Qt redistribution requirements as well before publishing the binary. See the [dated licensing review](docs/licensing-review.md) and [unsent inquiry draft](docs/licensing-inquiry.md).

## Artwork

The depicted DeepSeek “大肥鱼 / whale girl” is a community fan character, not an official DeepSeek character. Original character “溟月”: **上善无形** ([creator statement](https://www.bilibili.com/opus/1253873972180680713)); DeepSeek maid redesign: **ZipZipPipe** ([profile](https://space.bilibili.com/4168597)). [ZipZipPipe's own statement](https://www.bilibili.com/opus/1247156596114456581), read on 2026-11-04, identifies **[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)**: attribution, noncommercial use and share alike. Retain source and license links and identify changes; this does not apply MIT to the artwork.

SeedBank's portrait is an AI-generated derivative from the maintainer's reference, subsequently processed with a local rounded-corner alpha mask. SeedBank's own protectable adaptation contributions follow CC BY-NC-SA 4.0; see the [portrait notice](assets/brand/NOTICE.md). The particular reference illustrator remains unverified. This is not an original character claim or a new grant from that illustrator, and does not imply endorsement.

The reference **DeepSeek-chan（大肥鱼） Live2D model** credits **[神宫凉子](https://space.bilibili.com/13737731)** for illustration, separation and distribution, and **霓虹猫_NeonNeko** for rigging. See the [creator's release video](https://www.bilibili.com/video/BV1KmxY66EZ3/) and [maintainer-supplied Bilibili Workshop acquisition page](https://gf.bilibili.com/item/detail/1109618072). The video's public metadata confirms the creator and credits; the acquisition page's current contents were not independently retrieved. The model has separate bundled usage terms: retain credits, do not resell or redistribute the full package without permission, and seek the required confirmation for product promotion. Personal-content revenue allowances do not override underlying character rights. Full provenance, terms summary and outstanding use questions are recorded in [docs/assets.md](docs/assets.md).

No third-party Live2D model, `.moc3`, model textures or motions are distributed in the application source or candidate ZIP. Users select their own local model and must follow its author's terms. The two egg directories are textual birth templates, not model assets.

## Seed template data

The existing `species.json` files in `eggs/open.egg` and `eggs/dafeiyu.egg` declare **CC-BY-SA-4.0**, rather than the application's MIT license. These declarations are preserved. Attribute the SeedBank project / AmatsukiRen, retain the source and license link, identify modifications and follow the license's share-alike requirements when distributing adapted template data. See [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). This template license does not grant rights in similarly named third-party character artwork or Live2D models.
