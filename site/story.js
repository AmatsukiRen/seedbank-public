// Local presentation only. Languages are static pages; no requests or storage.
(() => {
  const controls = document.querySelector(".story-controls");
  const book = document.querySelector(".story-book");
  const mode = document.querySelector(".reading-mode");
  if (!controls || !book || !mode) return;
  const tabs = [...controls.querySelectorAll('[role="tab"]')];
  const panels = tabs.map(tab => document.getElementById(tab.getAttribute("aria-controls")));
  if (!tabs.length || panels.some(panel => !panel)) return;
  let active = 0;
  let showAll = false;
  function select(index, focus = false) {
    active = index;
    tabs.forEach((tab, i) => {
      const chosen = i === active;
      tab.setAttribute("aria-selected", String(chosen));
      tab.tabIndex = chosen ? 0 : -1;
      panels[i].hidden = !showAll && !chosen;
      if (showAll) {
        panels[i].removeAttribute("role");
        panels[i].removeAttribute("tabindex");
        panels[i].setAttribute("aria-labelledby", "chapter-heading-" + i);
      } else {
        panels[i].setAttribute("role", "tabpanel");
        panels[i].setAttribute("aria-labelledby", tab.id);
        panels[i].tabIndex = 0;
      }
    });
    if (focus) tabs[index].focus();
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => select(index));
    tab.addEventListener("keydown", event => {
      let next;
      if (event.key === "ArrowDown" || event.key === "ArrowRight") next = (index + 1) % tabs.length;
      else if (event.key === "ArrowUp" || event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = tabs.length - 1;
      else return;
      event.preventDefault();
      select(next, true);
    });
  });
  mode.addEventListener("click", () => {
    showAll = !showAll;
    controls.hidden = showAll;
    book.classList.toggle("enhanced", !showAll);
    mode.textContent = showAll ? mode.dataset.one : mode.dataset.all;
    mode.setAttribute("aria-expanded", String(showAll));
    select(active);
  });
  // Keep an explicitly linked chapter visible on arrival.
  const linkedChapter = panels.findIndex(panel => "#" + panel.id === window.location.hash);
  select(linkedChapter >= 0 ? linkedChapter : 0);
  book.classList.add("enhanced");
  controls.hidden = false;
  mode.hidden = false;
  window.addEventListener("hashchange", () => {
    const index = panels.findIndex(panel => "#" + panel.id === window.location.hash);
    if (index >= 0) select(index);
  });
  // Language changes keep the current section; anchor-only links still work without JS.
  document.querySelectorAll(".languages a").forEach(link => {
    link.addEventListener("click", () => {
      const hash = window.location.hash;
      if (hash) link.href = link.getAttribute("href").split("#")[0] + hash;
    });
  });
})();

