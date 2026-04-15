"""
agent/graph.py — Grafo LangGraph do agente de busca científica.

Fontes suportadas:
  - arXiv         (física, CS, matemática, biologia quantitativa)
  - PubMed        (biomedicina, bioquímica, biologia molecular)
  - Semantic Scholar (multi-área, grafo de citações)
  - CrossRef      (DOI lookup, metadados de qualquer revista)
  - Playwright    (Nature, Wiley, ACS — sites que precisam de JS)

Modelo: qwen3:14b via Ollama (cabe em 16 GB VRAM com folga)
"""

from __future__ import annotations

import json
import re
import time
from typing import Annotated, Any, Literal

import arxiv
import httpx
from Bio import Entrez
from langchain_ollama import ChatOllama
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from playwright.sync_api import sync_playwright
from pydantic import BaseModel
from semanticscholar import SemanticScholar

# ---------------------------------------------------------------------------
# Estado compartilhado do grafo
# ---------------------------------------------------------------------------

class AgentState(BaseModel):
    query: str = ""
    area: str = ""                          # classificação da query
    source: str = ""                        # fonte escolhida pelo roteador
    raw_results: list[dict[str, Any]] = []  # resultados brutos
    articles: list[dict[str, Any]] = []     # artigos parseados e rankeados
    error: str = ""
    messages: Annotated[list, add_messages] = []


# ---------------------------------------------------------------------------
# LLM local
# ---------------------------------------------------------------------------

llm = ChatOllama(
    model="qwen3:14b",
    temperature=0.1,
    num_ctx=8192,
)


# ---------------------------------------------------------------------------
# Nó 1 — Roteador
# Decide qual fonte usar com base na query
# ---------------------------------------------------------------------------

ROUTER_PROMPT = """Você é um especialista em literatura científica.
Analise a query abaixo e responda em JSON com dois campos:
- "area": uma das categorias ["network_theory", "biotechnology", "biology", "computational_chemistry", "other"]
- "source": a MELHOR fonte para essa query, uma de ["arxiv", "pubmed", "semantic_scholar", "crossref", "playwright_nature"]

Regras de roteamento:
- arxiv → física de redes, teoria de grafos, bioinformática computacional, química computacional (DFT, MD)
- pubmed → biologia molecular, genômica, biotecnologia, ensaios clínicos, bioquímica
- semantic_scholar → revisões multi-área, papers altamente citados, busca por autor/citação
- crossref → busca por DOI exato ou título exato de artigo
- playwright_nature → quando a query mencionar Nature, Science, Cell, Wiley, ACS ou exigir acesso a texto completo

Responda APENAS com o JSON, sem texto extra.

Query: {query}
"""

def router_node(state: AgentState) -> AgentState:
    prompt = ROUTER_PROMPT.format(query=state.query)
    response = llm.invoke(prompt)
    text = response.content.strip()

    # Remove bloco de raciocínio <think>...</think> do qwen3
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    try:
        data = json.loads(text)
        return state.model_copy(update={
            "area": data.get("area", "other"),
            "source": data.get("source", "semantic_scholar"),
        })
    except json.JSONDecodeError:
        return state.model_copy(update={
            "area": "other",
            "source": "semantic_scholar",
            "error": f"Router parse error: {text[:200]}",
        })


# ---------------------------------------------------------------------------
# Nó 2a — arXiv
# ---------------------------------------------------------------------------

def search_arxiv(state: AgentState) -> AgentState:
    client = arxiv.Client()
    search = arxiv.Search(
        query=state.query,
        max_results=15,
        sort_by=arxiv.SortCriterion.Relevance,
    )
    results = []
    for paper in client.results(search):
        results.append({
            "title": paper.title,
            "authors": [a.name for a in paper.authors],
            "abstract": paper.summary,
            "year": paper.published.year if paper.published else None,
            "doi": paper.doi or "",
            "url": paper.entry_id,
            "source": "arXiv",
        })
    return state.model_copy(update={"raw_results": results})


# ---------------------------------------------------------------------------
# Nó 2b — PubMed (via Biopython Entrez)
# ---------------------------------------------------------------------------

Entrez.email = "scholar_agent@local"  # obrigatório pela política do NCBI

def search_pubmed(state: AgentState) -> AgentState:
    handle = Entrez.esearch(db="pubmed", term=state.query, retmax=15, sort="relevance")
    record = Entrez.read(handle)
    handle.close()

    ids = record.get("IdList", [])
    if not ids:
        return state.model_copy(update={"raw_results": []})

    handle = Entrez.efetch(db="pubmed", id=ids, rettype="xml", retmode="xml")
    records = Entrez.read(handle)
    handle.close()

    results = []
    for article in records.get("PubmedArticle", []):
        medline = article.get("MedlineCitation", {})
        art = medline.get("Article", {})

        title = str(art.get("ArticleTitle", ""))
        abstract_texts = art.get("Abstract", {}).get("AbstractText", [])
        abstract = " ".join(str(t) for t in abstract_texts) if abstract_texts else ""

        authors_list = art.get("AuthorList", [])
        authors = []
        for a in authors_list:
            last = a.get("LastName", "")
            fore = a.get("ForeName", "")
            authors.append(f"{fore} {last}".strip())

        pub_date = art.get("Journal", {}).get("JournalIssue", {}).get("PubDate", {})
        year = pub_date.get("Year", None)

        pmid = str(medline.get("PMID", ""))
        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""

        results.append({
            "title": title,
            "authors": authors,
            "abstract": abstract,
            "year": int(year) if year and year.isdigit() else None,
            "doi": "",
            "url": url,
            "source": "PubMed",
        })
    return state.model_copy(update={"raw_results": results})


# ---------------------------------------------------------------------------
# Nó 2c — Semantic Scholar
# ---------------------------------------------------------------------------

def search_semantic_scholar(state: AgentState) -> AgentState:
    sch = SemanticScholar()
    papers = sch.search_paper(state.query, limit=15, fields=[
        "title", "authors", "abstract", "year", "externalIds", "url",
        "citationCount", "publicationTypes",
    ])
    results = []
    for p in papers:
        doi = (p.externalIds or {}).get("DOI", "")
        results.append({
            "title": p.title or "",
            "authors": [a["name"] for a in (p.authors or [])],
            "abstract": p.abstract or "",
            "year": p.year,
            "doi": doi,
            "url": p.url or "",
            "citation_count": p.citationCount or 0,
            "source": "Semantic Scholar",
        })
    return state.model_copy(update={"raw_results": results})


# ---------------------------------------------------------------------------
# Nó 2d — CrossRef (DOI/título exato)
# ---------------------------------------------------------------------------

def search_crossref(state: AgentState) -> AgentState:
    url = "https://api.crossref.org/works"
    params = {"query": state.query, "rows": 15, "select": "title,author,abstract,published,DOI,URL"}
    resp = httpx.get(url, params=params, timeout=15)
    items = resp.json().get("message", {}).get("items", [])

    results = []
    for item in items:
        title = " ".join(item.get("title", []))
        authors = [
            f"{a.get('given','')} {a.get('family','')}".strip()
            for a in item.get("author", [])
        ]
        year_parts = item.get("published", {}).get("date-parts", [[None]])
        year = year_parts[0][0] if year_parts and year_parts[0] else None
        results.append({
            "title": title,
            "authors": authors,
            "abstract": item.get("abstract", ""),
            "year": year,
            "doi": item.get("DOI", ""),
            "url": item.get("URL", ""),
            "source": "CrossRef",
        })
    return state.model_copy(update={"raw_results": results})


# ---------------------------------------------------------------------------
# Nó 2e — Playwright (Nature, Wiley, ACS, etc.)
# ---------------------------------------------------------------------------

NATURE_SEARCH = "https://www.nature.com/search?q={query}&article_type=research-article&order=relevance"

def search_playwright_nature(state: AgentState) -> AgentState:
    results = []
    query_encoded = state.query.replace(" ", "+")
    url = NATURE_SEARCH.format(query=query_encoded)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ))
        page.goto(url, wait_until="networkidle", timeout=30000)
        time.sleep(2)

        # Fecha cookie banner se aparecer
        try:
            page.click("button[data-cc-action='accept']", timeout=3000)
        except Exception:
            pass

        articles = page.query_selector_all("article.u-full-height")
        for art in articles[:15]:
            title_el = art.query_selector("h3 a, h2 a")
            title = title_el.inner_text().strip() if title_el else ""
            href = title_el.get_attribute("href") if title_el else ""
            full_url = f"https://www.nature.com{href}" if href.startswith("/") else href

            abstract_el = art.query_selector("p.c-card__summary, p.article-item__teaser")
            abstract = abstract_el.inner_text().strip() if abstract_el else ""

            authors_el = art.query_selector_all("span.c-author-list__author, ul.c-author-list li")
            authors = [a.inner_text().strip() for a in authors_el]

            year_el = art.query_selector("time")
            year_text = year_el.get_attribute("datetime") if year_el else ""
            year = int(year_text[:4]) if year_text and year_text[:4].isdigit() else None

            if title:
                results.append({
                    "title": title,
                    "authors": authors,
                    "abstract": abstract,
                    "year": year,
                    "doi": "",
                    "url": full_url,
                    "source": "Nature (Playwright)",
                })

        browser.close()

    return state.model_copy(update={"raw_results": results})


# ---------------------------------------------------------------------------
# Nó 3 — Parser + ranker com LLM
# ---------------------------------------------------------------------------

PARSER_PROMPT = """Você é um pesquisador sênior especializado em {area}.
Analise estes artigos científicos e retorne um JSON com a lista "articles".

Para cada artigo inclua:
- title (string)
- authors (lista de strings)
- year (int ou null)
- abstract_pt (resumo em português, máximo 3 frases)
- relevance_score (0.0 a 1.0 — quão relevante é para a query)
- relevance_reason (1 frase explicando o score)
- doi (string, pode ser vazio)
- url (string)
- source (string)

Ordene por relevance_score decrescente. Inclua apenas artigos com score >= 0.3.

Query original: {query}

Artigos brutos:
{raw}

Responda APENAS com o JSON, sem texto extra.
"""

def parser_ranker_node(state: AgentState) -> AgentState:
    if not state.raw_results:
        return state.model_copy(update={"articles": [], "error": "Nenhum resultado encontrado."})

    raw_text = json.dumps(state.raw_results[:15], ensure_ascii=False, indent=2)
    prompt = PARSER_PROMPT.format(
        area=state.area,
        query=state.query,
        raw=raw_text,
    )
    response = llm.invoke(prompt)
    text = response.content.strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # Remove markdown code fences se o modelo incluir
    text = re.sub(r"^```(?:json)?\n?", "", text).rstrip("```").strip()

    try:
        data = json.loads(text)
        articles = data.get("articles", data) if isinstance(data, dict) else data
        return state.model_copy(update={"articles": articles})
    except json.JSONDecodeError:
        # Fallback: devolve os resultados brutos sem ranking
        fallback = [{
            "title": r.get("title", ""),
            "authors": r.get("authors", []),
            "year": r.get("year"),
            "abstract_pt": r.get("abstract", "")[:300],
            "relevance_score": 0.5,
            "relevance_reason": "Sem ranking (fallback)",
            "doi": r.get("doi", ""),
            "url": r.get("url", ""),
            "source": r.get("source", ""),
        } for r in state.raw_results[:10]]
        return state.model_copy(update={"articles": fallback})


# ---------------------------------------------------------------------------
# Roteamento condicional — qual nó de busca ativar
# ---------------------------------------------------------------------------

SOURCE_MAP: dict[str, str] = {
    "arxiv":              "search_arxiv",
    "pubmed":             "search_pubmed",
    "semantic_scholar":   "search_semantic_scholar",
    "crossref":           "search_crossref",
    "playwright_nature":  "search_playwright_nature",
}

def route_to_source(state: AgentState) -> str:
    return SOURCE_MAP.get(state.source, "search_semantic_scholar")


# ---------------------------------------------------------------------------
# Montagem do grafo
# ---------------------------------------------------------------------------

def build_graph() -> Any:
    g = StateGraph(AgentState)

    g.add_node("router",                   router_node)
    g.add_node("search_arxiv",             search_arxiv)
    g.add_node("search_pubmed",            search_pubmed)
    g.add_node("search_semantic_scholar",  search_semantic_scholar)
    g.add_node("search_crossref",          search_crossref)
    g.add_node("search_playwright_nature", search_playwright_nature)
    g.add_node("parser_ranker",            parser_ranker_node)

    g.set_entry_point("router")

    g.add_conditional_edges(
        "router",
        route_to_source,
        {
            "search_arxiv":             "search_arxiv",
            "search_pubmed":            "search_pubmed",
            "search_semantic_scholar":  "search_semantic_scholar",
            "search_crossref":          "search_crossref",
            "search_playwright_nature": "search_playwright_nature",
        },
    )

    for node in SOURCE_MAP.values():
        g.add_edge(node, "parser_ranker")

    g.add_edge("parser_ranker", END)

    return g.compile()


graph = build_graph()
