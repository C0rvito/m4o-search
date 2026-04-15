"""
agent/exporter.py — Exporta artigos para .bib (BibTeX) e .md (Markdown).
"""

from __future__ import annotations

import re
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any


OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slug(text: str, max_len: int = 40) -> str:
    """Transforma título em slug para usar como chave BibTeX."""
    s = re.sub(r"[^\w\s-]", "", text.lower())
    s = re.sub(r"[\s_-]+", "_", s).strip("_")
    return s[:max_len]


def _bibtex_key(article: dict[str, Any]) -> str:
    first_author = (article.get("authors") or ["unknown"])[0].split()[-1].lower()
    year = article.get("year") or "xxxx"
    title_slug = _slug(article.get("title", "untitled"), max_len=20)
    return f"{first_author}{year}_{title_slug}"


def _escape_bibtex(s: str) -> str:
    return s.replace("{", r"\{").replace("}", r"\}").replace("&", r"\&")


# ---------------------------------------------------------------------------
# BibTeX
# ---------------------------------------------------------------------------

def article_to_bibtex(article: dict[str, Any]) -> str:
    key = _bibtex_key(article)
    title = _escape_bibtex(article.get("title", ""))
    authors = " and ".join(article.get("authors", []))
    year = str(article.get("year", ""))
    doi = article.get("doi", "")
    url = article.get("url", "")
    journal = article.get("source", "Unknown")

    lines = [f"@article{{{key},"]
    lines.append(f'  title     = {{{title}}},')
    if authors:
        lines.append(f'  author    = {{{authors}}},')
    if year:
        lines.append(f'  year      = {{{year}}},')
    lines.append(f'  journal   = {{{journal}}},')
    if doi:
        lines.append(f'  doi       = {{{doi}}},')
    if url:
        lines.append(f'  url       = {{{url}}},')
    lines.append("}")
    return "\n".join(lines)


def export_bibtex(articles: list[dict[str, Any]], query: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = _slug(query, max_len=30)
    path = OUTPUT_DIR / f"{slug}_{timestamp}.bib"

    entries = [article_to_bibtex(a) for a in articles]
    path.write_text("\n\n".join(entries), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

def article_to_markdown(article: dict[str, Any], index: int) -> str:
    title = article.get("title", "Sem título")
    authors = ", ".join(article.get("authors", [])[:5])
    if len(article.get("authors", [])) > 5:
        authors += " et al."
    year = article.get("year", "s.d.")
    source = article.get("source", "")
    score = article.get("relevance_score", 0)
    reason = article.get("relevance_reason", "")
    abstract = article.get("abstract_pt", article.get("abstract", ""))
    doi = article.get("doi", "")
    url = article.get("url", "")

    doi_line = f"**DOI:** `{doi}`  \n" if doi else ""
    url_line = f"**URL:** {url}  \n" if url else ""

    abstract_wrapped = textwrap.fill(abstract, width=80)

    return (
        f"### {index}. {title}\n\n"
        f"**Autores:** {authors}  \n"
        f"**Ano:** {year} · **Fonte:** {source}  \n"
        f"**Relevância:** {score:.0%} — {reason}  \n"
        f"{doi_line}"
        f"{url_line}\n"
        f"> {abstract_wrapped}\n"
    )


def export_markdown(
    articles: list[dict[str, Any]],
    query: str,
    area: str,
    source_used: str,
) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = _slug(query, max_len=30)
    path = OUTPUT_DIR / f"{slug}_{timestamp}.md"

    header = (
        f"# Resultados: {query}\n\n"
        f"**Área classificada:** {area}  \n"
        f"**Fonte utilizada:** {source_used}  \n"
        f"**Data:** {datetime.now().strftime('%d/%m/%Y %H:%M')}  \n"
        f"**Total de artigos:** {len(articles)}\n\n"
        "---\n\n"
    )

    body = "\n\n".join(
        article_to_markdown(a, i + 1) for i, a in enumerate(articles)
    )

    path.write_text(header + body, encoding="utf-8")
    return path
