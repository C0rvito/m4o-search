# Scholar Agent (m4oSearch)

Agente de busca de literatura científica utilizando LangGraph + Ollama.  
Interface TUI no terminal com exportação para `.bib` e `.md`.

## Fontes Suportadas

| Fonte            | Área Principal                              |
|------------------|---------------------------------------------|
| arXiv            | Física, CS, Matemática, Bioinformática      |
| PubMed           | Biomedicina, Bioquímica, Biotecnologia      |
| Semantic Scholar | Multi-área, busca por citação               |
| CrossRef         | DOI e metadados de periódicos               |
| Playwright       | Nature, Wiley, ACS (requer execução de JS)  |

## Instalação

```bash
# 1. Clonar o repositório e entrar na pasta
git clone https://github.com/C0rvito/m4o-search.git
cd m4oSearch

# 2. Criar e ativar ambiente virtual
python -m venv .venv
source .venv/bin/activate      # Linux/Mac
# .venv\Scripts\activate       # Windows

# 3. Instalar dependências
pip install -r requirements.txt

# 4. Instalar navegadores para o Playwright (necessário para Nature/ACS/Wiley)
playwright install chromium

# 5. Configurar o Ollama
ollama pull qwen3:14b
```

## Configuração

Crie um arquivo `.env` na raiz do projeto:
```env
OLLAMA_MODEL=qwen3:14b
ENTREZ_EMAIL=seu_email@exemplo.com
```

## Uso

Para iniciar a interface interativa:
```bash
python src/tui.py
```

### Atalhos da Interface (TUI)

| Tecla   | Ação                              |
|---------|-----------------------------------|
| Enter   | Executar busca                    |
| ↑ / ↓   | Navegar na lista de resultados    |
| Espaço  | Selecionar / deselecionar artigo  |
| s       | Salvar selecionados (.bib + .md)  |
| q       | Sair da aplicação                 |

*Nota: Se nenhum artigo for selecionado ao pressionar `s`, todos os resultados visíveis serão exportados.*

## Exemplos de Consultas

```text
graph neural networks biological networks
CRISPR base editing off-target effects 2024
molecular dynamics GROMACS membrane proteins
network topology scale-free biochemical pathways
```

## Saída (Outputs)

Os arquivos são salvos automaticamente no diretório `outputs/` na raiz do projeto:
- `<query>_<timestamp>.bib` — Formato BibTeX para LaTeX/Zotero.
- `<query>_<timestamp>.md`  — Resumo formatado com traduções para o português e scores de relevância.

## Ajuste do Modelo

O modelo pode ser alterado no arquivo `.env` ou diretamente no código em `src/agent/graph.py`:

```python
llm = ChatOllama(
    model="qwen3:14b",   # Use "llama3.1:8b" para maior velocidade em hardware modesto
    temperature=0.1,
    num_ctx=8192,
)
```

- **qwen3:14b**: Recomendado para melhor qualidade de tradução e ranqueamento (requer ~12GB+ VRAM).
- **llama3.1:8b**: Recomendado para maior velocidade (~60 tokens/s em GPUs modernas).
