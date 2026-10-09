#!/usr/bin/env python3
"""Build the documentation site in site/pages into a static folder.

Pages are Markdown with a small front matter block. Links between pages are
written as relative .md links, so the sources also read correctly on GitHub;
the build rewrites them to the site's URLs. Every output link is relative, so
the site works under /pinyon-shift/ on GitHub Pages or at a domain root.

    python site/build.py [--out site/_build]
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import markdown
from markdown.extensions.toc import slugify

SITE = Path(__file__).resolve().parent
ROOT = SITE.parent
REPO = "arcanite24/pinyon-shift"
REPO_URL = f"https://github.com/{REPO}"
SECTIONS = ["Start", "Playing", "Technical", "Project"]

# Files copied from the repository into the site, by output name.
STATIC_FROM_REPO = {
    "img/logo.png": "launcher/PinyonShift.Launcher/Branding/logo-light.png",
    "img/launcher-ready.png": ".github/launcher-ready.png",
    "img/launcher-settings.png": ".github/launcher-settings.png",
    "favicon.ico": "launcher/PinyonShift.Launcher/Branding/pinyon-shift.ico",
}

MD_LINK = re.compile(r'href="(?!https?:|mailto:|#)([^"#]+?)\.md(#[^"]*)?"')


@dataclass
class Page:
    source: Path
    slug: str  # "" for the home page
    title: str
    section: str
    order: int
    description: str
    body: str

    @property
    def depth(self) -> int:
        return 0 if not self.slug else 1

    @property
    def output(self) -> Path:
        return Path(self.slug, "index.html") if self.slug else Path("index.html")


def read_page(path: Path) -> Page:
    text = path.read_text(encoding="utf-8")
    meta: dict[str, str] = {}
    if text.startswith("---\n"):
        header, text = text[4:].split("\n---\n", 1)
        for line in header.splitlines():
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    slug = "" if path.stem == "index" else path.stem
    section = meta.get("section", "Start")
    if section not in SECTIONS:
        raise SystemExit(f"{path.name}: unknown section {section!r}")
    return Page(path, slug, meta["title"], section, int(meta.get("order", "99")),
                meta.get("description", ""), text)


def latest_release() -> dict | None:
    """The latest release's tag, date and launcher asset, or None offline."""
    request = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                     headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.load(response)
    except (OSError, ValueError) as error:
        print(f"warning: latest release unavailable ({error}); building without it", file=sys.stderr)
        return None
    asset = next((a for a in data.get("assets", []) if a["name"].endswith(".zip")), None)
    return {
        "tag": data["tag_name"],
        "date": data["published_at"][:10],
        "url": data["html_url"],
        "asset": asset and {"name": asset["name"], "url": asset["browser_download_url"],
                            "size": f"{asset['size'] / 1e6:.0f} MB"},
    }


def release_block(release: dict | None) -> str:
    latest = f"{REPO_URL}/releases/latest"
    if not release or not release["asset"]:
        return (f'<div class="release"><div class="release-main"><p class="release-label">Latest release</p>'
                f'<a class="button" href="{latest}">Download from GitHub Releases</a></div></div>')
    asset = release["asset"]
    return f"""<div class="release">
  <div class="release-main">
    <p class="release-label">Latest release</p>
    <p class="release-version">{html.escape(release['tag'])} <span>{release['date']}</span></p>
  </div>
  <div class="release-actions">
    <a class="button" href="{asset['url']}">{html.escape(asset['name'])} <span>{asset['size']}</span></a>
    <a class="quiet-link" href="{release['url']}">Release notes</a>
    <a class="quiet-link" href="{REPO_URL}/releases">All releases</a>
  </div>
</div>"""


def render_markdown(text: str) -> tuple[str, list[dict]]:
    converter = markdown.Markdown(
        extensions=["tables", "fenced_code", "codehilite", "toc", "attr_list", "md_in_html"],
        extension_configs={
            "codehilite": {"guess_lang": False, "css_class": "code"},
            "toc": {"toc_depth": "2-3", "slugify": slugify, "permalink": "#",
                    "permalink_class": "anchor", "permalink_title": "Link to this section"},
        },
    )
    body = converter.convert(text)
    return body, converter.toc_tokens


def flatten_toc(tokens: list[dict]) -> list[dict]:
    items = []
    for token in tokens:
        if token["level"] == 1:
            items += flatten_toc(token["children"])
            continue
        items.append(token)
        items += [child for child in token["children"] if child["level"] == 3]
    return items


def rewrite_links(body: str, page: Page, slugs: set[str]) -> str:
    prefix = "../" * page.depth

    def replace(match: re.Match) -> str:
        target, anchor = match.group(1), match.group(2) or ""
        name = Path(target).name
        stem = "" if name == "index" else name
        if "/" in target or stem and stem not in slugs:
            raise SystemExit(f"{page.source.name}: link to {target}.md is not a site page; "
                             f"use a full {REPO_URL} URL")
        return f'href="{prefix}{stem + "/" if stem else ""}{anchor}"' if stem or anchor \
            else f'href="{prefix or "./"}"'

    return MD_LINK.sub(replace, body)


def page_href(prefix: str, page: Page) -> str:
    return prefix + (page.slug + "/" if page.slug else "") or "./"


def nav_html(pages: list[Page], current: Page | None, prefix: str) -> str:
    parts = []
    for section in SECTIONS:
        entries = [p for p in pages if p.section == section]
        if not entries:
            continue
        parts.append(f'<p class="nav-section">{section}</p><ul>')
        for page in entries:
            attrs = ' aria-current="page"' if page is current else ""
            parts.append(f'<li><a href="{page_href(prefix, page)}"{attrs}>{html.escape(page.title)}</a></li>')
        if section == "Project":
            parts.append(f'<li><a href="{REPO_URL}/blob/main/docs/ROADMAP.md">Roadmap '
                         f'<span class="ext" aria-hidden="true">↗</span></a></li>')
            parts.append(f'<li><a href="{REPO_URL}/blob/main/CHANGELOG.md">Changelog '
                         f'<span class="ext" aria-hidden="true">↗</span></a></li>')
        parts.append("</ul>")
    return "\n".join(parts)


def toc_html(items: list[dict]) -> str:
    if len(items) < 2:
        return ""
    links = "".join(
        f'<li class="toc-l{item["level"]}"><a href="#{item["id"]}">{item["name"]}</a></li>'
        for item in items)
    return f'<nav class="toc" aria-label="On this page"><p>On this page</p><ul>{links}</ul></nav>'


def pager_html(pages: list[Page], current: Page) -> str:
    index = pages.index(current)
    prefix = "../" * current.depth
    cells = []
    for offset, label, cls in ((-1, "Previous", "prev"), (1, "Next", "next")):
        position = index + offset
        if 0 <= position < len(pages):
            page = pages[position]
            cells.append(f'<a class="pager-{cls}" href="{page_href(prefix, page)}"><span>{label}</span>'
                         f'{html.escape(page.title)}</a>')
        else:
            cells.append("<span></span>")
    return f'<nav class="pager" aria-label="Pages">{"".join(cells)}</nav>'


def build(out: Path) -> None:
    pages = sorted((read_page(p) for p in (SITE / "pages").glob("*.md")),
                   key=lambda p: (SECTIONS.index(p.section), p.order, p.title))
    slugs = {p.slug for p in pages if p.slug}
    template = (SITE / "template.html").read_text(encoding="utf-8")
    release = latest_release()

    if out.exists():
        shutil.rmtree(out)
    (out / "img").mkdir(parents=True)
    for name in ("style.css", "site.js"):
        shutil.copyfile(SITE / "static" / name, out / name)
    for name, source in STATIC_FROM_REPO.items():
        shutil.copyfile(ROOT / source, out / name)

    for page in pages:
        text = page.body.replace("{{release}}", release_block(release))
        body, toc = render_markdown(text)
        body = rewrite_links(body, page, slugs)
        body = body.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")
        prefix = "../" * page.depth
        body = body.replace('src="img/', f'src="{prefix}img/')
        version = release["tag"] if release else ""
        source = page.source.relative_to(ROOT).as_posix()
        values = {
            "title": "Pinyon Shift" if not page.slug else f"{page.title} · Pinyon Shift",
            "description": html.escape(page.description, quote=True),
            "root": prefix or "./",
            "nav": nav_html(pages, page, prefix),
            "toc": toc_html(flatten_toc(toc)),
            "content": body,
            "pager": pager_html(pages, page),
            "repo": REPO_URL,
            "version": html.escape(version),
            "edit": f'<a href="{REPO_URL}/edit/main/{source}">Edit this page on GitHub</a>',
            "page_class": "home" if not page.slug else "doc",
        }
        rendered = re.sub(r"\{\{(\w+)\}\}", lambda m: values[m.group(1)], template)
        target = out / page.output
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")

    (out / ".nojekyll").write_text("", encoding="utf-8")
    # GitHub Pages serves 404.html at any depth, so its links are absolute.
    base = os.environ.get("SITE_BASE", "/pinyon-shift/")
    missing = {
        "title": "Not found · Pinyon Shift", "description": "", "root": base,
        "nav": nav_html(pages, None, base), "toc": "", "pager": "", "repo": REPO_URL,
        "content": f'<h1>Page not found</h1><p>Nothing lives at this address. '
                   f'Start from the <a href="{base}">overview</a>.</p>',
        "version": html.escape(release["tag"] if release else ""), "edit": "",
        "page_class": "doc",
    }
    (out / "404.html").write_text(re.sub(r"\{\{(\w+)\}\}", lambda m: missing[m.group(1)], template),
                                  encoding="utf-8")
    print(f"built {len(pages)} pages into {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=SITE / "_build")
    build(parser.parse_args().out.resolve())


if __name__ == "__main__":
    main()
