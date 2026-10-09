// Mobile menu, theme switch, code copy buttons and the current section in
// the page outline. The site works without it.
(() => {
  const root = document.documentElement;

  const menu = document.querySelector(".menu-button");
  const setMenu = (open) => {
    document.body.classList.toggle("nav-open", open);
    menu.setAttribute("aria-expanded", String(open));
  };
  menu.addEventListener("click", () => setMenu(!document.body.classList.contains("nav-open")));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setMenu(false);
  });

  const dark = () => root.dataset.theme
    ? root.dataset.theme === "dark"
    : matchMedia("(prefers-color-scheme: dark)").matches;
  document.querySelector(".theme-button").addEventListener("click", () => {
    const theme = dark() ? "light" : "dark";
    root.dataset.theme = theme;
    try { localStorage.setItem("theme", theme); } catch (error) { /* private mode */ }
  });

  for (const block of document.querySelectorAll(".prose .code")) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "copy";
    button.textContent = "Copy";
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(block.querySelector("pre").innerText.replace(/\n$/, ""));
        button.textContent = "Copied";
      } catch (error) {
        button.textContent = "Select and copy";
      }
      setTimeout(() => { button.textContent = "Copy"; }, 1600);
    });
    block.append(button);
  }

  const links = [...document.querySelectorAll(".toc a")];
  const headings = links.map((link) => document.getElementById(link.hash.slice(1))).filter(Boolean);
  if (headings.length && "IntersectionObserver" in window) {
    const visible = new Set();
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) visible.add(entry.target); else visible.delete(entry.target);
      }
      const current = headings.find((heading) => visible.has(heading));
      if (!current) return;
      for (const link of links) link.classList.toggle("active", link.hash === `#${current.id}`);
    }, { rootMargin: "-56px 0px -65% 0px" });
    headings.forEach((heading) => observer.observe(heading));
  }
})();
