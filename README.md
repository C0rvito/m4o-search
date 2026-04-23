# m4oSearch

Um agente de busca de literatura científica com interface TUI.

## Funcionalidades

- **Busca em múltiplas bases científicas**: arXiv, PubMed, Semantic Scholar, CrossRef e Nature.
- **Roteamento Inteligente**: Direciona a consulta para as fontes mais adequadas com base no tópico.
- **Processamento via LLM Local**: Utiliza Ollama (modelo padrão `qwen3:14b`) para ranqueamento e tradução.
- **Exportação Flexível**: Salva resultados nos formatos BibTeX e Markdown.
- **Interface TUI Interativa**: Navegação, seleção de artigos e visualização de detalhes diretamente no terminal.
- **Tradução Automática**: Traduz resumos (abstracts) para o português para facilitar a leitura.

## Instalação

1. Clone o repositório.
2. Crie e ative um ambiente virtual:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # No Linux/Mac
   ```
3. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```
4. Instale o navegador para o Playwright:
   ```bash
   playwright install chromium
   ```
5. Instale o Ollama e baixe o modelo necessário:
   ```bash
   ollama pull qwen3:14b
   ```

## Configuração

Crie um arquivo `.env` na raiz do projeto seguindo este modelo:
```env
OLLAMA_MODEL=qwen3:14b
ENTREZ_EMAIL=seu_email@exemplo.com  # Necessário para buscas no PubMed
```

## Uso

Execute a aplicação:
```bash
python src/tui.py
```

## Estrutura do Projeto

```
.
├── src/
│   ├── agent/          # Agente LangGraph e integrações de banco de dados
│   │   ├── __init__.py
│   │   ├── graph.py      # Fluxo de trabalho LangGraph com roteamento e busca
│   │   └── exporter.py   # Exportação para formatos BibTeX e Markdown
│   └── tui.py          # Interface TUI (Textual) - Ponto de entrada
├── outputs/            # Resultados exportados (criado automaticamente)
└── README.md
```

## Como Funciona

### Arquitetura do Grafo do Agente
O sistema utiliza um fluxo de trabalho LangGraph que orquestra o processo de busca:

1. **Nó de Roteamento (Router Node)**: Usa o LLM para determinar a melhor fonte de dados com base no tópico da consulta.
2. **Nós de Busca em Bancos de Dados**: 
   - **arXiv**: Física, Computação, Matemática, Biologia Quantitativa.
   - **PubMed**: Biomedicina, Bioquímica, Biologia Molecular.
   - **Semantic Scholar**: Busca multi-área e grafo de citações.
   - **CrossRef**: Busca por DOI e metadados de periódicos.
   - **Playwright**: Captura de dados de sites como Nature, Wiley e ACS que exigem execução de JavaScript.
3. **Nó de Processamento e Ranqueamento (Parser + Ranker Node)**: O LLM processa os resultados brutos, traduz os resumos para o português e atribui notas de relevância.

### Interface TUI
A interface baseada em Textual oferece:
- Campo de busca com sugestões.
- Tabela de resultados com ordenação por relevância.
- Painel de detalhes exibindo título, autores, ano, fonte, score de relevância e resumo.
- Mecanismo de seleção (barra de espaço para selecionar/deselecionar).
- Funcionalidade de salvamento (tecla `s` exporta para `.bib` e `.md`).

## Requisitos

- Python 3.10+
- Ollama com modelo `qwen3:14b` (ou similar configurado no `.env`).
- Dependências listadas em `requirements.txt`.

## Licença

Este projeto está licenciado sob a Licença MIT.
