# m4oSearch Documentation

## Project Overview and Purpose

m4oSearch is a scientific literature search agent with a Textual-based TUI (Terminal User Interface). The system enables researchers and scientists to search across multiple scientific databases simultaneously, with intelligent routing to appropriate sources based on query topic, local LLM processing for ranking and translation, and export functionality to academic formats.

The project addresses the challenge of efficiently searching scientific literature by:
- Integrating multiple scientific databases (arXiv, PubMed, Semantic Scholar, CrossRef, Nature)
- Using a LangGraph workflow to orchestrate the search process
- Leveraging local LLMs (qwen3:14b via Ollama) for intelligent routing and article ranking
- Providing Portuguese abstract translation for better readability
- Offering export functionality to BibTeX and Markdown formats

## Installation Instructions

### Prerequisites

1. Python 3.10 or higher
2. Ollama installed on your system
3. At least 16GB of RAM (recommended for optimal performance)

### Installation Steps

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd m4oSearch
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Install the required LLM model:
   ```bash
   ollama pull qwen3:14b
   ```

## Usage Guide with Examples

### Running the Application

To start the application, run:
```bash
python src/tui.py
```

### Interface Navigation

The TUI interface provides the following functionality:
- **Search Input**: Enter your scientific query in the input field
- **Search Execution**: Press Enter to execute the search
- **Results Navigation**: Use arrow keys (↑↓) to navigate through results
- **Selection**: Press Spacebar to select/deselect articles
- **Export**: Press 's' to save selected articles to .bib and .md files
- **Exit**: Press 'q' to quit the application

### Example Usage

1. Launch the application:
   ```bash
   python src/tui.py
   ```

2. Enter a search query like "machine learning in biology" in the input field

3. Review the results in the table view, sorted by relevance

4. Select articles by pressing Spacebar on desired entries

5. Save selected articles using the 's' key

## Architecture Explanation with Diagrams

### System Architecture Overview

The m4oSearch system is built on a LangGraph workflow that orchestrates the search process through multiple stages:

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Query Input   │───▶│   Router Node   │───▶│  Database Nodes │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ Parser + Ranker │
                    └─────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   Export Node   │
                    └─────────────────┘
```

### Core Components

1. **Router Node**: Uses LLM to determine the best database source based on query topic
2. **Database Search Nodes**: 
   - arXiv (physics, CS, math, quantitative biology)
   - PubMed (biomedicine, biochemistry, molecular biology)
   - Semantic Scholar (multi-area, citation graph)
   - CrossRef (DOI lookup, journal metadata)
   - Playwright (Nature, Wiley, ACS - JS-heavy sites)
3. **Parser + Ranker Node**: Uses LLM to process raw results, translate abstracts to Portuguese, and rank articles by relevance

### Routing Logic

The system routes queries to appropriate sources based on topic classification:
- arXiv: network theory, computational biology, computational chemistry
- PubMed: biotechnology, molecular biology, biochemistry
- Semantic Scholar: multi-area reviews, highly cited papers
- CrossRef: DOI or exact title searches
- Playwright: Nature, Science, Cell, Wiley, ACS requiring JavaScript rendering

## Database Integration Details

### Supported Databases

1. **arXiv**: 
   - Covers physics, CS, math, quantitative biology
   - Provides full-text articles with abstracts and metadata

2. **PubMed**: 
   - Focuses on biomedicine, biochemistry, molecular biology
   - Offers extensive biomedical literature database

3. **Semantic Scholar**: 
   - Multi-area coverage with citation graph
   - Provides academic paper metadata and citations

4. **CrossRef**: 
   - DOI lookup and journal metadata
   - Provides reliable citation information

5. **Playwright (Nature, Wiley, ACS)**: 
   - JS-heavy sites requiring browser automation
   - Enables access to paywalled and JS-dependent scientific journals

### Integration Approach

Each database integration is implemented as a separate node in the LangGraph workflow, allowing for:
- Parallel search across multiple databases
- Consistent result formatting
- Error handling for each database source
- Efficient resource utilization

## LLM Integration Details

### Model Used

The system uses the qwen3:14b model via Ollama, which runs locally on the user's machine. This model is chosen for its ability to:
- Classify query topics accurately
- Rank search results by relevance
- Translate abstracts to Portuguese
- Process and format scientific literature

### Integration Points

1. **Routing Logic**: The LLM determines which database to search based on query topic
2. **Result Processing**: LLM processes raw results to extract key information
3. **Abstract Translation**: Translates English abstracts to Portuguese
4. **Ranking**: Ranks articles by relevance to the query

### Configuration

The LLM is configured through the `ChatOllama` class in `graph.py`:
```python
llm = ChatOllama(
    model="qwen3:14b",
    temperature=0.1,
    num_ctx=8192,
    num_predict=2048
)
```

## Export Functionality

### Supported Formats

The system supports exporting search results to two academic formats:

1. **BibTeX (.bib)**: Standard academic format with proper escaping
2. **Markdown (.md)**: Formatted documents with query metadata and article details

### Export Process

When exporting selected articles:
1. The system creates two files in the `outputs/` directory
2. BibTeX format includes proper escaping for special characters
3. Markdown format includes query metadata, article details, and formatted content

### Export Features

- Automatic creation of the `outputs/` directory
- Unique filenames based on article metadata
- Proper formatting for academic use
- Support for multiple selected articles

## Troubleshooting Guide

### Common Issues and Solutions

1. **LLM Model Not Found**
   - **Problem**: Ollama cannot find the qwen3:14b model
   - **Solution**: Run `ollama pull qwen3:14b` to download the model

2. **Database Connection Issues**
   - **Problem**: Failed to connect to scientific databases
   - **Solution**: Check internet connectivity and database availability

3. **Memory Issues**
   - **Problem**: Application crashes due to memory constraints
   - **Solution**: Ensure at least 16GB RAM available; consider reducing parallel searches

4. **TUI Interface Problems**
   - **Problem**: Terminal interface not rendering correctly
   - **Solution**: Try running with different terminal emulators or update Textual library

### Logging and Debugging

The application includes a logging panel in the TUI that displays:
- Search progress information
- Database connection status
- Error messages
- LLM processing details

## Contributing Guidelines

### How to Contribute

1. **Fork the Repository**: Create a personal copy of the repository
2. **Create a Branch**: Make changes in a dedicated branch
3. **Make Changes**: Implement your feature or fix
4. **Test**: Ensure all functionality works correctly
5. **Submit Pull Request**: Propose your changes for review

### Code Style

- Follow PEP 8 coding standards
- Use type hints for all functions and variables
- Include docstrings for all public functions
- Write clear, concise comments

### Adding New Database Sources

To add a new database source:
1. Create a new search function in the graph.py file
2. Add the database to the routing logic
3. Implement proper error handling
4. Test integration thoroughly

### Reporting Issues

When reporting issues:
1. Include the exact error message
2. Provide steps to reproduce the problem
3. Include your system specifications
4. Mention the version of the software

### Development Setup

For development, ensure you have:
- Python 3.10+
- Ollama installed
- All dependencies from requirements.txt
- The qwen3:14b model pulled

### Testing

The project includes a test suite in the `tests/` directory. Run tests with:
```bash
python -m pytest tests/
```
