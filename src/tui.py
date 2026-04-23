"""
tui.py — Interface TUI refinada do agente de busca científica.
Tema: Catppuccin Mocha
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from textual import work
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
    LoadingIndicator,
)
from textual.coordinate import Coordinate
from rich.markup import escape
from rich.text import Text

from agent.exporter import export_bibtex, export_markdown, OUTPUT_DIR
from agent.graph import AgentState, graph


# ---------------------------------------------------------------------------
# Helpers de Renderização
# ---------------------------------------------------------------------------

def render_score_bar(score: float, width: int = 10) -> Text:
    """Renderiza uma barra de progresso simples com caracteres de bloco."""
    filled = int(score * width)
    bar = "█" * filled + "░" * (width - filled)
    color = "green" if score > 0.7 else "yellow" if score > 0.4 else "red"
    return Text(f"{bar} {score:.0%}", style=color)


# ---------------------------------------------------------------------------
# Painel de detalhes do artigo
# ---------------------------------------------------------------------------

class ArticleDetail(Static):
    """Widget para exibição detalhada de um artigo."""
    
    DEFAULT_CSS = """
    ArticleDetail {
        height: auto;
        padding: 1 2;
        border: round $primary;
        margin: 1 0;
        background: $surface;
        transition: width 300ms in_out_cubic;
    }
    #detail-relevance-label {
        margin-top: 1;
        text-style: bold;
        color: $accent;
    }
    #detail-relevance-bar {
        width: 100%;
        margin-bottom: 1;
    }
    .detail-metadata {
        color: $text;
        opacity: 0.7;
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("", id="detail-title")
        yield Label("", id="detail-metadata", classes="detail-metadata")
        yield Label("󰓥 Relevância", id="detail-relevance-label")
        yield ProgressBar(id="detail-relevance-bar", show_eta=False, show_percentage=True)
        yield Static("", id="detail-body")

    def show(self, article: dict[str, Any]) -> None:
        title = article.get("title", "Sem título")
        authors_list = article.get("authors", [])
        if not isinstance(authors_list, list):
            authors_list = []
        authors = ", ".join(authors_list[:4])
        if len(authors_list) > 4:
            authors += " et al."
        
        year = article.get("year") or "s.d."
        source = article.get("source", "")
        
        try:
            score = float(article.get("relevance_score", 0))
        except (ValueError, TypeError):
            score = 0.0
            
        reason = article.get("relevance_reason", "")
        abstract = str(article.get("abstract_pt", article.get("abstract", "")))[:800]
        doi = article.get("doi", "")
        url = article.get("url", "")

        # Atualiza elementos individuais
        self.query_one("#detail-title", Label).update(f"[bold $primary]{escape(title)}[/bold $primary]")
        self.query_one("#detail-metadata", Label).update(
            f"󰔱 {escape(authors)}  |  󰃭 {year}  |  󰈙 {escape(source)}"
        )
        self.query_one("#detail-relevance-bar", ProgressBar).update(total=100, progress=int(score * 100))
        
        body_text = f"[italic]{escape(reason)}[/italic]\n\n"
        if doi:
            body_text += f"󰓄 DOI: [link=\"{doi}\"]{escape(doi)}[/link]\n"
        if url:
            body_text += f"󰍉 URL: [link=\"{url}\"]{escape(url)}[/link]\n"
        body_text += f"\n{escape(abstract)}…"
        
        self.query_one("#detail-body", Static).update(body_text)


# ---------------------------------------------------------------------------
# App principal
# ---------------------------------------------------------------------------

class ScholarAgentApp(App):
    TITLE = "Scholar Agent"
    SUB_TITLE = "Busca Científica Inteligente"
    
    # Catppuccin Mocha Palette
    CSS = """
    /* Global TCSS */
    * {
        transition: background 200ms;
    }

    Screen {
        background: #1e1e2e;
        color: #cdd6f4;
    }

    #top-bar {
        height: auto;
        padding: 1 2;
        background: #313244;
        border-bottom: round $primary;
        margin-bottom: 1;
    }
    
    #search-input {
        width: 1fr;
        border: tall #45475a;
        background: #1e1e2e;
    }
    
    #search-input:focus {
        border: tall $primary;
    }

    #run-btn {
        width: 16;
        margin-left: 1;
        height: 3;
    }

    #status-bar {
        height: 3;
        padding: 0 2;
        background: #181825;
        content-align: left middle;
        border-bottom: solid #313244;
        margin-bottom: 1;
    }

    #progress {
        width: 24;
        margin: 0 2;
    }

    #loading-icon {
        width: auto;
        height: 1;
        margin-right: 1;
        color: $primary;
    }

    #main-area {
        height: 1fr;
        padding: 0 1;
    }

    #results-panel {
        width: 65%;
        padding: 1;
        border: round #313244;
        background: #1e1e2e;
        margin-right: 1;
    }

    #side-panel {
        width: 35%;
        padding: 1;
        background: #181825;
        border: round #313244;
    }

    #log-panel {
        height: 12;
        border: round #313244;
        margin-top: 1;
        background: #1e1e2e;
        padding: 0 1;
    }

    #save-btn {
        margin-top: 1;
        width: 100%;
        height: 3;
    }

    #selection-info {
        height: 3;
        content-align: center middle;
        padding: 0 1;
        color: $accent;
        text-style: bold;
        background: #313244 20%;
        border: round #313244;
        margin-top: 1;
    }

    DataTable {
        height: 1fr;
        border: none;
        background: transparent;
    }
    
    DataTable > .datatable--header {
        text-style: bold;
        background: #313244;
        color: $primary;
    }

    DataTable > .datatable--cursor {
        background: $primary 30%;
        color: #ffffff;
    }
    
    DataTable:hover {
        background: transparent;
    }

    .panel-title {
        color: $primary;
        padding: 0 1;
        text-style: bold;
        margin-bottom: 1;
        border-bottom: solid $primary;
        width: 100%;
    }

    Footer {
        background: #11111b;
        color: #a6adc8;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Sair"),
        Binding("s", "save", "Salvar"),
        Binding("enter", "run_search", "Buscar", show=False),
        Binding("space", "toggle_select", "Selecionar"),
    ]

    articles: reactive[list[dict]] = reactive([])
    selected: reactive[set[int]] = reactive(set)
    running: reactive[bool] = reactive(False)
    last_state: AgentState | None = None

    # ------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header()

        with Horizontal(id="top-bar"):
            yield Label("󰍉 ", id="search-icon", variant="primary")
            yield Input(
                placeholder="O que você deseja pesquisar hoje?", 
                id="search-input"
            )
            yield Button("Buscar", id="run-btn", variant="primary")

        with Horizontal(id="status-bar"):
            yield LoadingIndicator(id="loading-icon")
            yield Label("Pronto para iniciar a busca científica.", id="status-label")
            yield ProgressBar(total=100, id="progress", show_eta=False)

        with Horizontal(id="main-area"):
            with Vertical(id="results-panel"):
                yield Label("󰄵  RESULTADOS DA PESQUISA", classes="panel-title")
                yield DataTable(id="results-table", cursor_type="row", zebra_stripes=True)

            with Vertical(id="side-panel"):
                yield Label("󰈙  DETALHES DO ARTIGO", classes="panel-title")
                yield ArticleDetail(id="detail-panel")
                yield Label("0 artigo(s) selecionado(s)", id="selection-info")
                yield Button("󰒚 Exportar (.bib + .md)", id="save-btn", variant="success")
                with Container(id="log-panel"):
                    yield Log(id="agent-log", auto_scroll=True)

        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#results-table", DataTable)
        table.add_columns("󰄵", "#", "󰗚 Título", "󰃭 Ano", "󰈙 Fonte", "󰓥 Score")
        self.query_one("#progress", ProgressBar).update(progress=0)
        self.query_one("#search-input", Input).focus()
        self.query_one("#loading-icon").display = False

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
        if idx is not None and 0 <= idx < len(self.articles):
            try:
                article = self.articles[idx]
                if isinstance(article, dict):
                    self.query_one("#detail-panel", ArticleDetail).show(article)
            except Exception as e:
                self.notify(escape(f"Erro ao exibir detalhes: {e}"), severity="error")

    # ------------------------------------------------------------------
    # Ações

    def action_run_search(self) -> None:
        if self.running:
            return
        query = self.query_one("#search-input", Input).value.strip()
        if not query:
            self.notify("Por favor, insira um termo de busca.", severity="warning")
            return

        self._start_search(query)

    @work(exclusive=True)
    async def _start_search(self, query: str) -> None:
        self.running = True
        self.articles = []
        self.selected = set()
        self.query_one("#results-table", DataTable).clear()
        self.query_one("#loading-icon").display = True
        
        log = self.query_one("#agent-log", Log)
        log.clear()
        log.write_line(f"󰍉 [Busca Iniciada] {escape(query)}")

        self._set_status("Roteando para as melhores fontes...", progress=15)
        
        try:
            state = AgentState(query=query)
            result_dict = await graph.ainvoke(state)
            result = AgentState(**result_dict)
            self.last_state = result
            self._on_agent_done(result)
        except Exception as exc:
            self._on_agent_error(str(exc))
        finally:
            self.running = False
            self.query_one("#loading-icon").display = False

    def _on_agent_done(self, state: AgentState | dict) -> None:
        def get_val(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        area = get_val(state, "area", "unknown")
        sources = get_val(state, "sources", [])
        if not isinstance(sources, list):
            sources = [str(sources)]
        source_str = ", ".join(sources)
        
        articles = get_val(state, "articles", [])
        error = get_val(state, "error")

        log = self.query_one("#agent-log", Log)
        log.write_line(f"✅ Área: {escape(str(area))}")
        log.write_line(f"📡 Fontes: {escape(source_str)}")
        log.write_line(f"📚 Resultados: {len(articles)}")

        if error:
            log.write_line(f"⚠️ [AVISO] {escape(str(error))}")

        self.articles = articles
        self._populate_table(articles)
        self._set_status(
            f"Sucesso! {len(articles)} artigos encontrados.",
            progress=100,
        )
        self.notify(f"Busca concluída: {len(articles)} resultados.", title="Sucesso")
        self.query_one("#results-table").focus()

    def _on_agent_error(self, error: str) -> None:
        with open("tui_error.log", "a") as f:
            f.write(f"ERRO: {error}\n")
        log = self.query_one("#agent-log", Log)
        log.write_line(f"❌ [ERRO] {escape(str(error))}")
        self._set_status("Erro durante a execução.", progress=0)
        self.notify("Ocorreu um erro na busca.", severity="error")

    def _populate_table(self, articles: list[dict]) -> None:
        table = self.query_one("#results-table", DataTable)
        table.clear()
        if not isinstance(articles, list):
            return
            
        for i, a in enumerate(articles):
            if not isinstance(a, dict):
                continue
            is_sel = "󰄵" if i in self.selected else "󰄱"
            title = str(a.get("title") or "")[:80]
            year = str(a.get("year") or "—")
            source = str(a.get("source") or "")[:15]
            
            try:
                score_val = float(a.get("relevance_score", 0))
                score_bar = render_score_bar(score_val)
            except (ValueError, TypeError):
                score_bar = Text("░░░░░░░░░░ 0%")
                
            table.add_row(is_sel, str(i + 1), escape(title), escape(year), escape(source), score_bar)

    def action_toggle_select(self) -> None:
        table = self.query_one("#results-table", DataTable)
        idx = table.cursor_row
        if idx is None or idx < 0 or idx >= len(self.articles):
            return
        
        if idx in self.selected:
            self.selected.remove(idx)
        else:
            self.selected.add(idx)
        
        is_sel = "󰄵" if idx in self.selected else "󰄱"
        try:
            table.update_cell_at(Coordinate(idx, 0), is_sel)
        except Exception:
            pass
        
        info = self.query_one("#selection-info", Label)
        info.update(f"󰄵 {len(self.selected)} artigo(s) selecionado(s)")

    def action_save(self) -> None:
        if not self.last_state or not self.articles:
            self.notify("Nenhum resultado para salvar.", severity="warning")
            return
        
        indices = self.selected if self.selected else set(range(len(self.articles)))
        to_save = [self.articles[i] for i in sorted(indices) if i < len(self.articles)]
        
        if not to_save:
            return

        try:
            def get_val(obj, key, default=None):
                if isinstance(obj, dict):
                    return obj.get(key, default)
                return getattr(obj, key, default)

            query = get_val(self.last_state, "query", "")
            sources = get_val(self.last_state, "sources", [])
            area = get_val(self.last_state, "area", "")

            bib_path = export_bibtex(to_save, query)
            sources_str = ", ".join(sources)
            md_path = export_markdown(
                to_save,
                query,
                area,
                sources_str,
            )

            log = self.query_one("#agent-log", Log)
            log.write_line(f"💾 [Exportado] {bib_path.name}")
            log.write_line(f"💾 [Exportado] {md_path.name}")
            
            msg = f"Arquivos salvos em: {OUTPUT_DIR.resolve()}"
            self._set_status(msg, progress=100)
            self.notify("Artigos exportados com sucesso!", title="Exportação")
        except Exception as e:
            self.notify(f"Erro ao salvar: {e}", severity="error")

    def _set_status(self, msg: str, progress: int = 0) -> None:
        self.query_one("#status-label", Label).update(msg)
        self.query_one("#progress", ProgressBar).update(progress=progress)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ScholarAgentApp().run()
