"""
tui.py — Interface TUI do agente de busca científica.

Uso:
    python tui.py

Atalhos:
    Enter       Executar busca
    s           Salvar artigos selecionados (.bib + .md)
    q           Sair
    ↑↓          Navegar na lista
    espaço      Selecionar/deselecionar artigo
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Log,
    ProgressBar,
    Static,
)

from agent.exporter import export_bibtex, export_markdown
from agent.graph import AgentState, graph


# ---------------------------------------------------------------------------
# Painel de detalhes do artigo
# ---------------------------------------------------------------------------

class ArticleDetail(Static):
    DEFAULT_CSS = """
    ArticleDetail {
        height: auto;
        padding: 1 2;
        border: solid $accent;
        margin: 1 0;
    }
    """

    def show(self, article: dict[str, Any]) -> None:
        title = article.get("title", "")
        authors = ", ".join(article.get("authors", [])[:4])
        if len(article.get("authors", [])) > 4:
            authors += " et al."
        year = article.get("year", "s.d.")
        source = article.get("source", "")
        score = article.get("relevance_score", 0)
        reason = article.get("relevance_reason", "")
        abstract = article.get("abstract_pt", article.get("abstract", ""))[:400]
        doi = article.get("doi", "")
        url = article.get("url", "")

        text = (
            f"[bold]{title}[/bold]\n"
            f"[dim]{authors} · {year} · {source}[/dim]\n"
            f"[green]Relevância: {score:.0%}[/green] — {reason}\n"
        )
        if doi:
            text += f"DOI: [link={doi}]{doi}[/link]\n"
        if url:
            text += f"URL: [link={url}]{url}[/link]\n"
        text += f"\n{abstract}…"

        self.update(text)


# ---------------------------------------------------------------------------
# App principal
# ---------------------------------------------------------------------------

class ScholarAgentApp(App):
    TITLE = "Scholar Agent"
    SUB_TITLE = "LangGraph + Ollama qwen3:14b"
    CSS = """
    Screen {
        layout: vertical;
    }
    #top-bar {
        height: 5;
        padding: 0 1;
    }
    #search-input {
        width: 1fr;
    }
    #run-btn {
        width: 14;
        margin-left: 1;
    }
    #status-bar {
        height: 3;
        padding: 0 2;
        content-align: left middle;
    }
    #progress {
        width: 1fr;
        margin: 0 1;
    }
    #main-area {
        height: 1fr;
        layout: horizontal;
    }
    #results-panel {
        width: 2fr;
        border: solid $panel;
        padding: 0 1;
    }
    #side-panel {
        width: 1fr;
        padding: 0 1;
    }
    #log-panel {
        height: 8;
        border: solid $panel;
        margin-top: 1;
    }
    #save-btn {
        margin-top: 1;
        width: 100%;
    }
    #selection-info {
        height: 2;
        content-align: left middle;
        padding: 0 1;
        color: $text-muted;
    }
    DataTable {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Sair"),
        Binding("s", "save", "Salvar"),
        Binding("enter", "run_search", "Buscar", show=False),
        Binding("space", "toggle_select", "Selecionar", show=False),
    ]

    articles: reactive[list[dict]] = reactive([])
    selected: reactive[set[int]] = reactive(set)
    running: reactive[bool] = reactive(False)
    last_state: AgentState | None = None

    # ------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header()

        with Horizontal(id="top-bar"):
            yield Input(placeholder="Query científica… ex: graph neural networks protein folding", id="search-input")
            yield Button("Buscar", id="run-btn", variant="primary")

        with Horizontal(id="status-bar"):
            yield Label("Pronto.", id="status-label")
            yield ProgressBar(total=100, id="progress", show_eta=False)

        with Horizontal(id="main-area"):
            with Vertical(id="results-panel"):
                yield Label(" Resultados", classes="panel-title")
                yield DataTable(id="results-table", cursor_type="row")

            with Vertical(id="side-panel"):
                yield ArticleDetail(id="detail-panel")
                yield Label("", id="selection-info")
                yield Button("Salvar selecionados (.bib + .md)", id="save-btn", variant="success")
                with Container(id="log-panel"):
                    yield Log(id="agent-log", auto_scroll=True)

        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#results-table", DataTable)
        table.add_columns("#", "Título", "Ano", "Fonte", "Score")
        self.query_one("#progress", ProgressBar).update(progress=0)

    # ------------------------------------------------------------------
    # Eventos de UI

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run-btn":
            self.action_run_search()
        elif event.button.id == "save-btn":
            self.action_save()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.action_run_search()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        idx = event.cursor_row
        if 0 <= idx < len(self.articles):
            self.query_one("#detail-panel", ArticleDetail).show(self.articles[idx])

    # ------------------------------------------------------------------
    # Ações

    def action_run_search(self) -> None:
        if self.running:
            return
        query = self.query_one("#search-input", Input).value.strip()
        if not query:
            return

        self.running = True
        self.articles = []
        self.selected = set()
        table = self.query_one("#results-table", DataTable)
        table.clear()

        log = self.query_one("#agent-log", Log)
        log.clear()
        log.write_line(f"[Iniciando busca] {query}")

        self._set_status("Consultando roteador LLM…", progress=10)
        threading.Thread(target=self._run_agent, args=(query,), daemon=True).start()

    def _run_agent(self, query: str) -> None:
        try:
            state = AgentState(query=query)
            result: AgentState = graph.invoke(state)
            self.last_state = result
            self.call_from_thread(self._on_agent_done, result)
        except Exception as exc:
            self.call_from_thread(self._on_agent_error, str(exc))

    def _on_agent_done(self, state: AgentState) -> None:
        log = self.query_one("#agent-log", Log)
        log.write_line(f"Área detectada: {state.area}")
        log.write_line(f"Fonte utilizada: {state.source}")
        log.write_line(f"Resultados brutos: {len(state.raw_results)}")
        log.write_line(f"Artigos após ranking: {len(state.articles)}")

        if state.error:
            log.write_line(f"[AVISO] {state.error}")

        self.articles = state.articles
        self._populate_table(state.articles)
        self._set_status(
            f"Encontrados {len(state.articles)} artigos via {state.source}",
            progress=100,
        )
        self.running = False

    def _on_agent_error(self, error: str) -> None:
        log = self.query_one("#agent-log", Log)
        log.write_line(f"[ERRO] {error}")
        self._set_status("Erro durante a busca.", progress=0)
        self.running = False

    def _populate_table(self, articles: list[dict]) -> None:
        table = self.query_one("#results-table", DataTable)
        table.clear()
        for i, a in enumerate(articles):
            title = (a.get("title") or "")[:60]
            year = str(a.get("year") or "—")
            source = (a.get("source") or "")[:18]
            score = f"{a.get('relevance_score', 0):.0%}"
            table.add_row(str(i + 1), title, year, source, score)

    def action_toggle_select(self) -> None:
        table = self.query_one("#results-table", DataTable)
        idx = table.cursor_row
        if idx < 0 or idx >= len(self.articles):
            return
        sel = set(self.selected)
        if idx in sel:
            sel.discard(idx)
        else:
            sel.add(idx)
        self.selected = sel
        info = self.query_one("#selection-info", Label)
        info.update(f"{len(self.selected)} artigo(s) selecionado(s)")

    def action_save(self) -> None:
        if not self.last_state:
            return
        indices = self.selected if self.selected else set(range(len(self.articles)))
        to_save = [self.articles[i] for i in sorted(indices) if i < len(self.articles)]
        if not to_save:
            return

        bib_path = export_bibtex(to_save, self.last_state.query)
        md_path = export_markdown(
            to_save,
            self.last_state.query,
            self.last_state.area,
            self.last_state.source,
        )

        log = self.query_one("#agent-log", Log)
        log.write_line(f"Salvo: {bib_path}")
        log.write_line(f"Salvo: {md_path}")
        self._set_status(f"Exportado → {bib_path.name} + {md_path.name}", progress=100)

    def _set_status(self, msg: str, progress: int = 0) -> None:
        self.query_one("#status-label", Label).update(msg)
        self.query_one("#progress", ProgressBar).update(progress=progress)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ScholarAgentApp().run()
