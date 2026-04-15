# Scholar Agent

Agente de busca de literatura científica com LangGraph + Ollama (qwen3:14b).  
TUI em terminal. Exporta `.bib` e `.md`.

## Fontes suportadas

| Fonte            | Área principal                              |
|------------------|---------------------------------------------|
| arXiv            | Física, CS, matemática, bioinformática      |
| PubMed           | Biomedicina, bioquímica, biotecnologia      |
| Semantic Scholar | Multi-área, busca por citação               |
| CrossRef         | DOI e metadados de qualquer revista         |
| Playwright       | Nature, Wiley, ACS (requer JS)             |

## Instalação

```bash
# 1. Clonar / entrar na pasta
cd scholar_agent

# 2. Ambiente virtual
python -m venv .venv
source .venv/bin/activate      # Linux/Mac
# .venv\Scripts\activate       # Windows

# 3. Dependências
pip install -r requirements.txt

# 4. Browser para o Playwright (só na primeira vez)
playwright install chromium

# 5. Garantir que o Ollama está rodando com o modelo
ollama pull qwen3:14b
ollama serve                   # em outro terminal, se não estiver rodando
```

## Uso

```bash
python tui.py
```

### Atalhos da TUI

| Tecla   | Ação                              |
|---------|-----------------------------------|
| Enter   | Executar busca                    |
| ↑ ↓     | Navegar na lista                  |
| Espaço  | Selecionar / deselecionar artigo  |
| s       | Salvar selecionados (.bib + .md)  |
| q       | Sair                              |

Se nenhum artigo for selecionado ao pressionar `s`, todos são exportados.

## Exemplos de query

```
graph neural networks biological networks
CRISPR base editing off-target effects 2024
molecular dynamics GROMACS membrane proteins
network topology scale-free biochemical pathways
computational docking AutoDock Vina drug discovery
```

## Saída

Arquivos salvos em `outputs/`:
- `<slug>_<timestamp>.bib` — BibTeX pronto para LaTeX / Zotero
- `<slug>_<timestamp>.md`  — Markdown com resumos em português e scores

## Ajuste do modelo

Edite `agent/graph.py` para trocar o modelo:

```python
llm = ChatOllama(
    model="qwen3:14b",   # troque por "llama3.1:8b" para mais velocidade
    temperature=0.1,
    num_ctx=8192,
)
```

Com 16 GB VRAM você pode usar até `qwen3:14b` confortavelmente.  
Para respostas mais rápidas, `llama3.1:8b` roda em ~60 tokens/s na RTX 5060 Ti.
