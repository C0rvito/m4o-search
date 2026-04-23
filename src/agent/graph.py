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

import asyncio
import json
import operator
import os
import re
import time
from typing import Annotated, Any

import arxiv
import httpx
from Bio import Entrez
from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from playwright.async_api import async_playwright
from pydantic import BaseModel

# Carrega variáveis de ambiente do arquivo .env
load_dotenv()

# ---------------------------------------------------------------------------
# Estado compartilhado do grafo
# ---------------------------------------------------------------------------

class AgentState(BaseModel):
    query: str = ""
    area: str = ""                          # classificação da query
    sources: list[str] = []                 # fontes escolhidas pelo roteador
    raw_results: Annotated[list[dict[str, Any]], operator.add] = []  # resultados brutos acumulados
    articles: list[dict[str, Any]] = []     # artigos parseados e rankeados
    error: str = ""
    messages: Annotated[list, add_messages] = []


# ---------------------------------------------------------------------------
# LLM local
# ---------------------------------------------------------------------------

llm = ChatOllama(
    model=os.getenv("OLLAMA_MODEL", "qwen3:14b"),
    temperature=float(os.getenv("OLLAMA_TEMPERATURE", "0.1")),
    num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "8192")),
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
)


# ---------------------------------------------------------------------------
# Nó 1 — Roteador
# Decide qual fonte usar com base na query
# ---------------------------------------------------------------------------

ROUTER_PROMPT = """Você é um especialista em literatura científica.
Analise a query abaixo e responda em JSON com dois campos:
- "area": uma das categorias ["network_theory", "biotechnology", "biology", "computational_chemistry", "other"]
- "sources": uma LISTA com as 1 a 3 MELHORES fontes para essa query, escolhidas de ["arxiv", "pubmed", "semantic_scholar", "crossref", "playwright_nature"]

Regras de roteamento:
- arxiv → física de redes, teoria de grafos, bioinformática computacional, química computacional (DFT, MD)
- pubmed → biologia molecular, genômica, biotecnologia, ensaios clínicos, bioquímica
- semantic_scholar → revisões multi-área, papers altamente citados, busca por autor/citação
- crossref → busca por DOI exato ou título exato de artigo
- playwright_nature → quando a query mencionar Nature, Science, Cell, Wiley, ACS ou exigir acesso a texto completo

Responda APENAS com o JSON, sem texto extra.

Query: {query}
"""

async def router_node(state: AgentState | dict) -> dict[str, Any]:
    if isinstance(state, dict):
        state = AgentState(**state)
    prompt = ROUTER_PROMPT.format(query=state.query)
    
    for attempt in range(3):
        try:
            response = await llm.ainvoke(prompt)
            text = response.content if isinstance(response.content, str) else "".join(str(c) for c in response.content)
            text = text.strip()

            # Remove bloco de raciocínio <think>...</think> do qwen3
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
            # Remove markdown code fences
            text = re.sub(r"^```(?:json)?\n?", "", text).rstrip("```").strip()

            data = json.loads(text)
            sources = data.get("sources", data.get("source", ["semantic_scholar"]))
            if isinstance(sources, str):
                sources = [sources]
            
            return {
                "area": data.get("area", "other"),
                "sources": sources,
            }
        except (json.JSONDecodeError, Exception) as e:
            if attempt == 2:
                return {
                    "area": "other",
                    "sources": ["semantic_scholar"],
                    "error": f"Erro no Roteador (LLM): {str(e)}",
                }
            await asyncio.sleep(1)
    
    return {}


# ---------------------------------------------------------------------------
# Nó 2a — arXiv
# ---------------------------------------------------------------------------

async def search_arxiv(state: AgentState | dict) -> dict[str, Any]:
    if isinstance(state, dict):
        state = AgentState(**state)
    try:
        def sync_search():
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
            return results

        results = await asyncio.to_thread(sync_search)
        return {"raw_results": results}
    except Exception as e:
        return {"error": f"Erro no arXiv: {str(e)}"}


# ---------------------------------------------------------------------------
# Nó 2b — PubMed (via Biopython Entrez)
# ---------------------------------------------------------------------------

Entrez.email = os.getenv("ENTREZ_EMAIL", "scholar_agent@local")

async def search_pubmed(state: AgentState | dict) -> dict[str, Any]:
    if isinstance(state, dict):
        state = AgentState(**state)
    try:
        def sync_search():
            handle = Entrez.esearch(db="pubmed", term=state.query, retmax=15, sort="relevance")
            record: Any = Entrez.read(handle)
            handle.close()

            if not isinstance(record, dict):
                return []

            ids = record.get("IdList", [])
            if not ids:
                return []

            handle = Entrez.efetch(db="pubmed", id=ids, rettype="xml", retmode="xml")
            data: Any = Entrez.read(handle)
            handle.close()

            if not isinstance(data, dict):
                return []

            records = data.get("PubmedArticle", []) + data.get("PubmedBookArticle", [])
            
            results = []
            for article in records:
                article_dict: Any = article
                medline = article_dict.get("MedlineCitation", {})
                art = medline.get("Article", {})
                if not art:
                    art = article_dict.get("BookDocument", {})

                title = str(art.get("ArticleTitle", art.get("BookTitle", "")))
                abstract_data = art.get("Abstract", {})
                abstract_texts = abstract_data.get("AbstractText", [])
                abstract = " ".join(str(t) for t in abstract_texts) if abstract_texts else ""

                authors = []
                author_list = art.get("AuthorList", [])
                for a in author_list:
                    last = a.get("LastName", "")
                    fore = a.get("ForeName", "")
                    authors.append(f"{fore} {last}".strip())

                pub_date = art.get("Journal", {}).get("JournalIssue", {}).get("PubDate", {})
                year = pub_date.get("Year", None)
                if not year:
                    year = art.get("ArticleDate", [{}])[0].get("Year", None)

                pmid = str(medline.get("PMID", article_dict.get("BookDocument", {}).get("PMID", "")))
                url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""

                results.append({
                    "title": title,
                    "authors": authors,
                    "abstract": abstract,
                    "year": int(year) if year and str(year).isdigit() else None,
                    "doi": "",
                    "url": url,
                    "source": "PubMed",
                })
            return results

        results = await asyncio.to_thread(sync_search)
        return {"raw_results": results}
    except Exception as e:
        return {"error": f"Erro no PubMed: {str(e)}"}


# ---------------------------------------------------------------------------
# Nó 2c — Semantic Scholar (Direto via HTTPX para evitar bugs de lib)
# ---------------------------------------------------------------------------

async def search_semantic_scholar(state: AgentState | dict) -> dict[str, Any]:
    if isinstance(state, dict):
        state = AgentState(**state)
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": state.query,
        "limit": 15,
        "fields": "title,authors,abstract,year,externalIds,url,citationCount"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, timeout=15)
            if resp.status_code == 429:
                return {"error": "Semantic Scholar: Limite de requisições excedido (429)."}
            
            resp.raise_for_status()
            data = resp.json().get("data", [])

            results = []
            for p in data:
                doi = (p.get("externalIds", {}) or {}).get("DOI", "")
                results.append({
                    "title": p.get("title", ""),
                    "authors": [a.get("name") for a in (p.get("authors", []) or [])],
                    "abstract": p.get("abstract", ""),
                    "year": p.get("year"),
                    "doi": doi,
                    "url": p.get("url", ""),
                    "citation_count": p.get("citationCount", 0),
                    "source": "Semantic Scholar",
                })
            return {"raw_results": results}
    except Exception as e:
        return {"error": f"Erro no Semantic Scholar: {str(e)}"}


# ---------------------------------------------------------------------------
# Nó 2d — CrossRef (DOI/título exato)
# ---------------------------------------------------------------------------

async def search_crossref(state: AgentState | dict) -> dict[str, Any]:
    if isinstance(state, dict):
        state = AgentState(**state)
    url = "https://api.crossref.org/works"
    params = {"query": state.query, "rows": 15, "select": "title,author,abstract,published,DOI,URL"}
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, timeout=15)
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
        return {"raw_results": results}
    except Exception as e:
        return {"error": f"Erro no CrossRef: {str(e)}"}


# ---------------------------------------------------------------------------
# Nó 2e — Playwright (Nature, Wiley, ACS, etc.)
# ---------------------------------------------------------------------------

NATURE_SEARCH = "https://www.nature.com/search?q={query}&article_type=research-article&order=relevance"

async def search_playwright_nature(state: AgentState | dict) -> dict[str, Any]:
    if isinstance(state, dict):
        state = AgentState(**state)
    results = []
    query_encoded = state.query.replace(" ", "+")
    url = NATURE_SEARCH.format(query=query_encoded)

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page(user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ))
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            try:
                await page.click("button[data-cc-action='accept']", timeout=3000)
            except Exception:
                pass

            articles = await page.query_selector_all("article.u-full-height")
            for art in articles[:15]:
                title_el = await art.query_selector("h3 a, h2 a")
                title = (await title_el.inner_text()).strip() if title_el else ""
                href = await title_el.get_attribute("href") if title_el else None
                full_url = f"https://www.nature.com{href}" if href and href.startswith("/") else (href or "")

                abstract_el = await art.query_selector("p.c-card__summary, p.article-item__teaser")
                abstract = (await abstract_el.inner_text()).strip() if abstract_el else ""

                authors_el = await art.query_selector_all("span.c-author-list__author, ul.c-author-list li")
                authors = [(await a.inner_text()).strip() for a in authors_el]

                year_el = await art.query_selector("time")
                year_text = await year_el.get_attribute("datetime") if year_el else ""
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

            await browser.close()
        return {"raw_results": results}
    except Exception as e:
        return {"error": f"Erro no Playwright/Nature: {str(e)}"}


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

async def parser_ranker_node(state: AgentState | dict) -> dict[str, Any]:
    if isinstance(state, dict):
        state = AgentState(**state)
    if not state.raw_results:
        return {"articles": [], "error": state.error or "Nenhum resultado encontrado."}

    raw_text = json.dumps(state.raw_results[:15], ensure_ascii=False, indent=2)
    prompt = PARSER_PROMPT.format(
        area=state.area,
        query=state.query,
        raw=raw_text,
    )

    for attempt in range(3):
        try:
            response = await llm.ainvoke(prompt)
            text = response.content if isinstance(response.content, str) else "".join(str(c) for c in response.content)
            text = text.strip()
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
            text = re.sub(r"^```(?:json)?\n?", "", text).rstrip("```").strip()

            data = json.loads(text)
            
            # Garantir que articles seja uma lista
            if isinstance(data, dict):
                articles = data.get("articles", [])
                if not isinstance(articles, list):
                    # Se 'articles' existir mas não for lista, talvez seja um único objeto ou o próprio data seja o que queremos
                    articles = [articles] if articles else []
            elif isinstance(data, list):
                articles = data
            else:
                articles = []

            # Validar e limpar cada artigo
            cleaned_articles = []
            for art in articles:
                if not isinstance(art, dict):
                    continue
                cleaned_articles.append({
                    "title": str(art.get("title", "Sem título")),
                    "authors": art.get("authors", []) if isinstance(art.get("authors"), list) else [],
                    "year": art.get("year"),
                    "abstract_pt": str(art.get("abstract_pt", art.get("abstract", ""))),
                    "relevance_score": float(art.get("relevance_score", 0.0)) if str(art.get("relevance_score", 0.0)).replace(".","",1).isdigit() else 0.0,
                    "relevance_reason": str(art.get("relevance_reason", "")),
                    "doi": str(art.get("doi", "")),
                    "url": str(art.get("url", "")),
                    "source": str(art.get("source", ", ".join(state.sources))),
                })

            return {"articles": cleaned_articles}
        except (json.JSONDecodeError, Exception) as e:
            if attempt == 2:
                fallback = [{
                    "title": r.get("title", ""),
                    "authors": r.get("authors", []),
                    "year": r.get("year"),
                    "abstract_pt": r.get("abstract", "")[:300],
                    "relevance_score": 0.5,
                    "relevance_reason": f"Sem ranking (fallback - erro no LLM: {str(e)})",
                    "doi": r.get("doi", ""),
                    "url": r.get("url", ""),
                    "source": r.get("source", ""),
                } for r in state.raw_results[:10]]
                return {"articles": fallback, "error": f"Erro no Ranker (LLM): {str(e)}"}
            await asyncio.sleep(1)

    return {}


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

def route_to_source(state: AgentState | dict) -> list[str]:
    if isinstance(state, dict):
        state = AgentState(**state)
    valid_sources = [s for s in state.sources if s in SOURCE_MAP]
    return valid_sources if valid_sources else ["semantic_scholar"]


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
        SOURCE_MAP,  # type: ignore
    )

    for node in SOURCE_MAP.values():
        g.add_edge(node, "parser_ranker")

    g.add_edge("parser_ranker", END)

    return g.compile()


graph = build_graph()
