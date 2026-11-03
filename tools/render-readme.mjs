// Generate GitHub READMEs, SVG headings and long-form stories. No HTML site.
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { renderReadme, renderReadmeAssets } from "./readme-design.mjs";
const root = new URL("../", import.meta.url);
const locales = [
  {lang: "zh-CN", readme: "README.md"},
  {lang: "en", readme: "README.en.md"},
  {lang: "ja", readme: "README.ja.md"}
];
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

[SeedBank](../${d.readme})
`;
};
for (const locale of locales) {
  const data = JSON.parse(readFileSync(new URL("docs/content/" + locale.lang + ".json", root), "utf8"));
  writeFileSync(new URL(locale.readme, root), renderReadme(data, locales), "utf8");
  mkdirSync(new URL("assets/readme/", root), { recursive: true });
  for (const [path, svg] of renderReadmeAssets(data)) writeFileSync(new URL(path, root), svg, "utf8");
  writeFileSync(new URL("docs/" + data.storyFile, root), renderStory(data, locales), "utf8");
}
