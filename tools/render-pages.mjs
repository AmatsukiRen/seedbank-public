// Regenerates authored static pages and documentation. No browser, model or test calls.
// Usage by the maintainer: node tools/render-pages.mjs
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { renderReadme, renderReadmeAssets } from "./readme-design.mjs";
const root = new URL("../", import.meta.url);
const locales = [
  {
    "lang": "zh-CN",
    "file": "index.html",
    "label": "简中",
    "readme": "README.md"
  },
  {
    "lang": "en",
    "file": "en.html",
    "label": "EN",
    "readme": "README.en.md"
  },
  {
    "lang": "ja",
    "file": "ja.html",
    "label": "日本語",
    "readme": "README.ja.md"
  }
];
const renderPage = function(d, locales) {
const e = s => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
const p = a=>a.map(s=>`<p>${e(s)}</p>`).join("\n");
const links=locales.map(l=>`<a href="${l.file}" lang="${l.lang}" hreflang="${l.lang}" ${l.lang===d.lang?'aria-current="page"':''}>${l.label}</a>`).join("");
return `<!doctype html>
<html lang="${d.lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<meta name="robots" content="noindex, nofollow">
<meta name="description" content="${e(d.description)}">
<title>${e(d.title)}</title>
<link rel="icon" type="image/png" href="../assets/brand/seedbank-logo.png">
${locales.map(l=>`<link rel="alternate" hreflang="${l.lang}" href="${l.file}">`).join("\n")}
<link rel="stylesheet" href="style.css">
<script src="story.js" defer></script>
</head>
<body id="top">
<a class="skip-link" href="#main">${e(d.skip)}</a>
<div class="draft-strip">${e(d.draft)}</div>
<header class="site-header wrap">
<a class="brand" href="${d.file}" aria-label="SeedBank"><img src="../assets/brand/seedbank-logo.png" width="44" height="44" alt=""><span>SeedBank<span class="brand-mark" aria-hidden="true">✳</span></span></a>
<nav class="main-nav" aria-label="${e(d.nav[0])}">
${["idea","story","screens","start"].map((id,i)=>`<a href="#${id}">${e(d.nav[i])}</a>`).join("")}
<a href="#extend">${e(d.extensions.nav)}</a>
</nav>
<nav class="languages" aria-label="${e(d.language)}">${links}</nav>
</header>
<main id="main">
<section class="hero wrap" aria-labelledby="hero-title">
<div class="hero-copy">
<h1 id="hero-title">${e(d.heroTitle[0])}<span>${e(d.heroTitle[1])}</span></h1>
<p class="hero-lead">${e(d.heroText)}</p>
<div class="hero-actions"><a class="button primary" href="#story">${e(d.heroPrimary)} <span aria-hidden="true">↗</span></a><a class="text-link" href="#screens">${e(d.heroSecondary)} <span aria-hidden="true">↘</span></a></div>
</div>
<figure class="portrait-board">
<div class="portrait"><img src="../assets/brand/seedbank-logo.png" width="1254" height="1254" fetchpriority="high" alt="${e(d.heroArt)}"></div>
<figcaption><span class="portrait-wordmark">SeedBank</span><span>${e(d.heroCaption)}</span></figcaption>
</figure>
</section>
<section class="idea wrap" id="idea" aria-labelledby="idea-title">
<div class="idea-heading"><span class="seed-symbol" aria-hidden="true">✳</span><h2 id="idea-title">${e(d.whyTitle)}</h2></div>
<div class="idea-body">${p(d.whyParas)}</div>
<aside class="birth-note"><h3>${e(d.birthTitle)}</h3><p>${e(d.birthText)}</p></aside>
</section>
<section class="story-section" id="story" aria-labelledby="story-title">
<div class="wrap">
<div class="section-heading"><h2 id="story-title">${e(d.storyTitle)}</h2><p>${e(d.storyIntro)}</p></div>
<div class="story-toolbar"><a class="text-link" href="../docs/${d.storyFile}">${e(d.storyLink)} <span aria-hidden="true">↗</span></a><button class="reading-mode" type="button" hidden data-all="${e(d.storyReadAll)}" data-one="${e(d.storyReadOne)}" aria-controls="story-panels" aria-expanded="false">${e(d.storyReadAll)}</button></div>
<div class="story-book">
<div class="story-controls" role="tablist" aria-label="${e(d.chapterLabel)}" aria-orientation="vertical" hidden>
${d.chapters.map((c,i)=>`<button id="chapter-tab-${i}" type="button" role="tab" aria-controls="chapter-${i}" aria-selected="${i===0}" tabindex="${i===0?0:-1}"><span class="chapter-number" aria-hidden="true">${String(i+1).padStart(2,"0")}</span><span>${e(c.label)}</span></button>`).join("\n")}
</div>
<div class="story-panels" id="story-panels">
${d.chapters.map((c,i)=>`<article class="story-panel" id="chapter-${i}" aria-labelledby="chapter-heading-${i}">
<div class="chapter-topline"><span>${e(c.label)}</span><span aria-hidden="true">${String(i+1).padStart(2,"0")} / 06</span></div>
<h3 id="chapter-heading-${i}">${e(c.title)}</h3><blockquote>${e(c.quote)}</blockquote>
<div class="story-prose">${p(c.paras)}</div><p class="story-meaning">${e(c.meaning)}</p>
</article>`).join("\n")}
</div>
</div>
</div>
</section>
<section class="screens-section wrap" id="screens" aria-labelledby="screens-title">
<div class="section-heading"><h2 id="screens-title">${e(d.galleryTitle)}</h2><p>${e(d.galleryIntro)}</p></div>
${d.shots.length ? `<div class="screens-grid">
${d.shots.map((s,i)=>`<figure class="screen ${i===0?"screen-main":""}"><a class="screen-image" href="../assets/screenshots/${s[0]}.png" aria-label="${e(s[1]+": "+d.galleryOriginal)}"><img src="../assets/screenshots/${s[0]}.png" width="1280" height="840" loading="lazy" alt="${e(d.shotAlt[i])}"></a><figcaption><div><strong>${e(s[1])}</strong><span>${e(s[2])}</span></div><span class="image-size">${e(s[3])}</span></figcaption></figure>`).join("\n")}
</div>` : ""}
<p class="caption">${e(d.galleryHint)} <a href="../docs/screenshots.md">${e(d.screenshotSource)} ↗</a></p>
</section>
<section class="features-section wrap" aria-labelledby="features-title">
<h2 id="features-title">${e(d.featuresTitle)}</h2>
<div class="feature-list">${d.features.map((f,i)=>`<article class="feature"><span class="feature-index" aria-hidden="true">${String(i+1).padStart(2,"0")}</span><h3>${e(f[0])}</h3><p>${e(f[1])}</p></article>`).join("\n")}</div>
<p class="caption">${e(d.featuresNote)}</p>
</section>
<section class="extend-section wrap" id="extend" aria-labelledby="extend-title">
<div class="section-heading"><span class="extend-kicker">BUILD WITH US</span><h2 id="extend-title">${e(d.extensions.title)}</h2><p>${e(d.extensions.intro)}</p></div>
<p class="extend-status">${e(d.extensions.status)}</p>
<div class="extend-routes">${d.extensions.routes.map((r,i)=>`<article><span class="feature-index" aria-hidden="true">${String(i+1).padStart(2,"0")}</span><h3>${e(r[0])}</h3><p class="extend-existing">${e(r[1])}</p><p>${e(r[2])}</p></article>`).join("\n")}</div>
<div class="protocol-note"><p>${e(d.extensions.protocol)}</p><pre><code>{"id":"hello-1","op":"hello"}</code></pre></div>
<p>${e(d.extensions.invite)}</p>
<div class="hero-actions"><a class="button primary" href="../docs/extensions.md">${e(d.extensions.guide)} ↗</a><a class="text-link" href="../CONTRIBUTING.md">${e(d.extensions.contribute)} ↗</a></div>
</section>
<section class="start-section" id="start" aria-labelledby="start-title"><div class="wrap">
<h2 id="start-title">${e(d.startTitle)}</h2>
<ol class="steps">${d.steps.map(s=>`<li><h3>${e(s[0])}</h3><p>${e(s[1])}</p></li>`).join("\n")}</ol>
<p class="release-note">${e(d.startNotice)}</p>
<div class="faq"><h3>${e(d.faqTitle)}</h3><div>${d.faq.map(f=>`<details><summary>${e(f[0])}</summary><p>${e(f[1])}</p></details>`).join("\n")}</div></div>
</div></section>
<section class="credits-section wrap" aria-labelledby="credits-title">
<h2 id="credits-title">${e(d.creditsTitle)}</h2><p class="credits-intro">${e(d.creditsIntro)}</p>
<dl class="credits">
<div><dt>${e(d.creditRoles[0])}</dt><dd><a href="https://space.bilibili.com/4168597">@ZipZipPipe ↗</a><a href="https://www.bilibili.com/opus/1253873972180680713">@上善无形 ↗</a></dd></div>
<div><dt>${e(d.creditRoles[1])}</dt><dd>神宫凉子</dd></div>
<div><dt>${e(d.creditRoles[2])}</dt><dd>霓虹猫_NeonNeko</dd></div>
<div><dt>${e(d.creditRoles[3])}</dt><dd>${e(d.modelSource)}</dd></div>
</dl>
<div class="credits-links"><a href="https://www.bilibili.com/video/BV1ALnw6YEGK">${e(d.creditsLink)} ↗</a><a href="../docs/assets.md">${e(d.assetsLink)} ↗</a></div>
<p class="caption">${e(d.creditsNote)}</p>
</section>
</main>
<footer class="site-footer wrap"><div><a class="footer-brand" href="#top">SeedBank<span aria-hidden="true">✳</span></a><p>${e(d.footer)}</p></div><a href="#top">${e(d.top)} ↑</a></footer>
</body>
</html>
`;
};
const renderStory = function story(d, locales) {
return `# ${d.storyTitle}

${locales.map(l=>`[${l.lang==="zh-CN"?"简体中文":l.lang==="en"?"English":"日本語"}](${l.lang==="zh-CN"?"story.md":`story.${l.lang}.md`})`).join(" · ")}

> ${d.storyIntro}

${d.chapters.map((c,i)=>`## ${String(i+1).padStart(2,"0")} · ${c.label}

### ${c.title}

> ${c.quote}

${c.paras.join("\n\n")}

*${c.meaning}*
`).join("\n")}
---

${d.faq[3][1]}

[SeedBank](../${d.readme}) · [${d.readmePreview}](../site/${d.file})
`;
};
for (const locale of locales) {
  const data = JSON.parse(readFileSync(new URL("site/content/" + locale.lang + ".json", root), "utf8"));
  writeFileSync(new URL("site/" + locale.file, root), renderPage(data, locales), "utf8");
  writeFileSync(new URL(locale.readme, root), renderReadme(data, locales), "utf8");
  mkdirSync(new URL("assets/readme/", root), { recursive: true });
  for (const [path, svg] of renderReadmeAssets(data)) {
    writeFileSync(new URL(path, root), svg, "utf8");
  }
  writeFileSync(new URL("docs/" + data.storyFile, root), renderStory(data, locales), "utf8");
}
