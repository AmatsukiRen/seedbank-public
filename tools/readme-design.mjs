// Code-native GitHub README typography and navigation. No raster image edits.
function escapeXml(value) {
  return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function svgDocument(width, height, title, body) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="title">
<title id="title">${escapeXml(title)}</title>
<defs><style>text{font-family:"Segoe UI","Microsoft YaHei","Noto Sans CJK SC","Yu Gothic",sans-serif} .mono{font-family:Consolas,"Courier New",monospace}</style></defs>
${body}
</svg>\n`;
}

export function renderReadmeAssets(d) {
  const output = [];
  const lang = d.lang;
  const english = lang === "en";
  const motto = d.heroTitle;
  const title = "SeedBank · " + motto.join(english ? " " : "");
  output.push([`assets/readme/hero-${lang}.svg`, svgDocument(700, 440, title, `
<rect width="700" height="440" fill="#ffffff"/>
<rect x="16" y="16" width="668" height="408" rx="14" fill="#eff4ff" stroke="#193c92" stroke-width="2"/>
<path d="M40 57H660" fill="none" stroke="#c2cfe7" stroke-width="2"/>
<text x="40" y="43" font-size="14" letter-spacing="2" fill="#2450bd" class="mono">SEEDBANK / A PLACE TO BECOME</text>
<text x="38" y="165" font-size="105" font-weight="800" letter-spacing="-7" fill="#182e55">Seed<tspan fill="#2450bd">Bank</tspan></text>
<rect x="42" y="188" width="88" height="7" rx="3" fill="#c52182"/>
<text x="40" y="263" font-size="${english?36:42}" font-weight="750" fill="#182e55">${escapeXml(motto[0])}</text>
<text x="40" y="322" font-size="${english?36:42}" font-weight="750" fill="#2450bd">${escapeXml(motto[1])}</text>
<path d="M40 356H660" fill="none" stroke="#c2cfe7" stroke-width="2"/>
<text x="40" y="393" font-size="16" letter-spacing="1.3" class="mono" fill="#50627c">MEMORY / CHOICE / CONTINUITY</text>
`)]);

  const navs=[
    ["story",d.readmeStory,"STORY",true],
    ["screens",d.nav[2],"ON SCREEN",false],
    ["start",d.nav[3],"BEGIN",false],
    ["credits",d.creditRoles[0].replace("Character design","Creators").replace("キャラクターデザイン","クレジット").replace("人设","创作者署名"),"CREDITS",false]
  ];
  for(const [name,label,englishLabel,primary] of navs) {
    output.push([`assets/readme/nav-${name}-${lang}.svg`,svgDocument(290,92,label,`
<rect x="5" y="7" width="280" height="80" rx="10" fill="#cbd9f5"/>
<rect x="1" y="1" width="280" height="80" rx="10" fill="${primary?"#2450bd":"#ffffff"}" stroke="#2450bd" stroke-width="2"/>
<text x="18" y="29" font-size="12" letter-spacing="1.5" class="mono" fill="${primary?"#dbe6ff":"#50627c"}">${englishLabel}</text>
<text x="18" y="59" font-size="${english?20:22}" font-weight="700" fill="${primary?"#ffffff":"#193c92"}">${escapeXml(label)}</text>
<path d="M248 36H263V51M245 54L263 36" fill="none" stroke="${primary?"#ffffff":"#c52182"}" stroke-width="2.5"/>
`)]);}
  const sections=[["story",d.readmeSections[1],"STORY"],["screens",d.readmeSections[2],"ON SCREEN"],["start",d.readmeSections[4],"BEGIN"],["credits",d.readmeSections[6],"CREDITS"]];
  for (const [name,title,label] of sections) {
    output.push([`assets/readme/section-${name}-${lang}.svg`,svgDocument(1200,120,title,`
<rect width="1200" height="120" rx="12" fill="#eff4ff"/>
<rect width="7" height="120" rx="3" fill="#2450bd"/>
<text x="32" y="36" class="mono" font-size="15" letter-spacing="2" fill="#2450bd">${label}</text>
<text x="30" y="86" font-size="34" font-weight="750" fill="#182e55">${escapeXml(title)}</text>
<rect x="1104" y="30" width="56" height="6" rx="3" fill="#c52182"/>
<path d="M1104 50H1160M1104 68H1160M1104 86H1160" fill="none" stroke="#c2cfe7" stroke-width="2"/>
`)]);}
  return output;
}

export function renderReadme(d, locales) {
  const s=d.readmeSections;
  const e=escapeXml;
  const graphic=(id,index)=>`<a name="${id}"></a>\n<h2><img src="assets/readme/section-${id}-${d.lang}.svg" width="100%" alt="${e(s[index])}"></h2>`;
  const navLabels=[d.readmeStory,d.nav[2],d.nav[3],d.readmeSections[6]];
  const readmeOnly = d.lang==="zh-CN"
    ? "当前这里是 GitHub 仓库首页。下方图形与内容可直接阅读；独立网页设计需要下载仓库后打开 site/index.html，点击 HTML 文件在 GitHub 上只会显示源码。"
    : d.lang==="en"
    ? "This is the GitHub repository front page. Its graphics and content are readable here. To view the separate website design, download the repository and open site/en.html; opening HTML on GitHub shows source code."
    : "ここは GitHub のリポジトリのトップページです。以下の画像と文章はこのまま読めます。独立したウェブページは、リポジトリをダウンロードして site/ja.html を開いてください。GitHub 上の HTML はソース表示です。";
  const previewSource = d.lang==="zh-CN"?"网页源文件":d.lang==="en"?"Website source":"ウェブページのソース";
  return `<!-- GitHub-native README layout: repository images and links, no page CSS or scripts. -->
<p align="center">${locales.map(l=>`<a href="${l.readme}">${l.lang==="zh-CN"?"简体中文":l.lang==="en"?"English":"日本語"}</a>`).join(" &nbsp; / &nbsp; ")}</p>

<table>
<tr>
<td width="62%" valign="middle"><img src="assets/readme/hero-${d.lang}.svg" width="700" alt="${e("SeedBank · "+d.heroTitle.join(d.lang==="en"?" ":""))}"></td>
<td width="38%" valign="middle"><img src="assets/brand/seedbank-logo.png" width="400" alt="${e(d.heroArt)}"></td>
</tr>
</table>

<p align="center"><strong>${e(d.readmeIntro)}</strong></p>

<p align="center">
${["story","screens","start","credits"].map((id,i)=>`<a href="#${id}"><img src="assets/readme/nav-${id}-${d.lang}.svg" width="180" alt="${e(navLabels[i])}"></a>`).join("\n")}
</p>

> ${d.draft}

${readmeOnly}

## ${d.readmeHook}

${d.readmeBody}

### ${s[0]}

${d.whyParas[2]}

${d.birthText}

${graphic("story",1)}

${d.readmeStoryText}

${d.chapters.map((c,i)=>`**${String(i+1).padStart(2,"0")} · ${c.label}** · ${c.title}\n\n> ${c.quote}`).join("\n\n")}

**[${d.readmeStory} →](docs/${d.storyFile})**

${graphic("screens",2)}

${d.galleryIntro}

<a href="assets/screenshots/idle.png"><img src="assets/screenshots/idle.png" width="100%" alt="${e(d.shotAlt[0])}"></a>

<table>
<tr>
<td width="50%"><a href="assets/screenshots/wave.png"><img src="assets/screenshots/wave.png" alt="${e(d.shotAlt[1])}"></a></td>
<td width="50%"><a href="assets/screenshots/small.png"><img src="assets/screenshots/small.png" alt="${e(d.shotAlt[2])}"></a></td>
</tr>
<tr><td><strong>${d.shots[1][1]}</strong> · ${d.shots[1][3]}</td><td><strong>${d.shots[2][1]}</strong> · ${d.shots[2][3]}</td></tr>
</table>

[${d.screenshotSource}](docs/screenshots.md) · DeepSeek-chan（大肥鱼） / 神宫凉子 / 霓虹猫_NeonNeko

### ${s[3]}

| | |
| :--- | :--- |
${d.features.map(f=>`| **${f[0]}** | ${f[1]} |`).join("\n")}

${d.featuresNote}

${graphic("start",4)}

${d.startNotice}

${d.readmeLocal}

${d.steps.map((f,i)=>`${i+1}. **${f[0]}** ${f[1]}`).join("\n")}

${d.readmeStatus}

${d.faq[3][1]}

### ${s[5]}

${d.readmeData.map(t=>"- "+t).join("\n")}

${graphic("credits",6)}

${d.creditsIntro}

| | |
| :--- | :--- |
| ${d.creditRoles[0]} | [@ZipZipPipe](https://space.bilibili.com/4168597) · [@上善无形](https://www.bilibili.com/opus/1253873972180680713) |
| ${d.creditRoles[1]} | **神宫凉子** |
| ${d.creditRoles[2]} | **霓虹猫_NeonNeko** |
| ${d.creditRoles[3]} | ${d.modelSource} |

[${d.creditsLink}](https://www.bilibili.com/video/BV1ALnw6YEGK) · [${d.assetsLink}](docs/assets.md)

${d.creditsNote}

### ${s[7]}

${d.readmeContribute}

[MIT](LICENSE) · [Design](docs/design.md) · [${previewSource}](site/${d.file}) · [0.0.1](docs/release-plan.md) · [Acceptance steps](docs/acceptance.md)

---

<p align="center"><strong>SeedBank · ${e(d.footer)}</strong></p>
`;
}
