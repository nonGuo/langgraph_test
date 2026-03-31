# AI4Test LangGraph

AI-powered test case generation for data warehouse testing, migrated from Dify chatflow to LangGraph implementation.

## Overview

This project implements an intelligent test case generation assistant that:

- 📄 **Parses documents**: Mapping documents, RS (Requirement Specification), TS (Technical Specification)
- 🧠 **Classifies intent**: Understands user requests (new task, modify mind map, chat, etc.)
- 🗺️ **Generates mind maps**: Creates test case structures in Mermaid format
- 📝 **Creates test cases**: Converts mind maps to structured JSON test cases
- 💾 **Generates SQL**: Creates validation SQL for each test case using ReAct agents
- 📊 **Exports to Excel**: Generates formatted Excel files
- 🔔 **Sends notifications**: Notifies users via WeLink when complete

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        AI4Test Graph                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  START → Intent Classification → Router                         │
│                                                                  │
│  Branch 1: Chat/Guidance → LLM Response → END                  │
│  Branch 2: Confirm Mind Map → Generate Test Cases → ...        │
│  Branch 3: Document Processing → Extract → Generate → END      │
│  Branch 4: Other → LLM Response → END                          │
│                                                                  │
│  Document Processing Flow:                                       │
│    Parse Mapping → Parse RS → Parse TS → Extract Test Points   │
│    → Knowledge Retrieval → Generate Mind Map                   │
│    → Generate Test Cases → Generate SQL (Iteration)            │
│    → Generate Excel → Send Notification → END                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Project Structure

```
langgraph_test/
├── __init__.py
├── state.py              # TypedDict state definitions
├── config.py             # Configuration & environment variables
├── graph.py              # Main graph assembly
├── main.py               # CLI entry point
├── pyproject.toml        # Project dependencies
├── requirements.txt      # Pip requirements
├── nodes/
│   ├── __init__.py
│   ├── intent_classifier.py
│   ├── document_parser.py
│   ├── test_point_extractor.py
│   ├── mind_map_generator.py
│   ├── test_case_generator.py
│   ├── sql_generator.py
│   └── notification_sender.py
├── edges/
│   ├── __init__.py
│   └── routing.py        # Conditional edge logic
├── tools/
│   ├── __init__.py
│   ├── database_tool.py  # Stub for DB execution
│   ├── knowledge_tool.py # Stub for few-shot retrieval
│   └── messaging_tool.py # Stub for notifications
└── api/
    ├── __init__.py
    └── excel_client.py   # HTTP client for Excel generation
```

## Installation

### Prerequisites

- Python 3.10+
- Access to an OpenAI-compatible LLM API
- (Optional) GAUSS DB access for SQL execution
- (Optional) Knowledge base API access

### Install Dependencies

```bash
pip install -r requirements.txt
```

Or using poetry:

```bash
poetry install
```

## Configuration

Copy the example environment file and configure:

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```bash
# LLM Configuration
LLM_PROVIDER=openai_api_compatible
LLM_MODEL=privacy_Qwen3-Coder-480B-A35B-ReAct
LLM_API_KEY=your-api-key
LLM_API_BASE=http://localhost:8000/v1
LLM_TEMPERATURE=0

# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=gaussdb
DB_USER=admin
DB_PASSWORD=

# Knowledge Base
KNOWLEDGE_BASE_ID=your-kb-id
KNOWLEDGE_TOP_K=3

# Excel Generation API
EXCEL_API_URL=http://10.31.169.36:9002/generate_excel

# Notifications
NOTIFICATION_ENABLED=true
```

## Usage

### Command Line

```bash
# Basic usage
python main.py --query "生成测试用例" \
    --mapping mapping.md \
    --rs requirement.md \
    --ts technical.md \
    --w3-id q00797588

# With verbose logging
python main.py --query "帮我生成测试用例" \
    --mapping ./docs/mapping.md \
    --rs ./docs/rs.md \
    --ts ./docs/ts.md \
    --w3-id q00797588 \
    --verbose
```

### Programmatic Usage

```python
from config import Config
from graph import create_graph
from langchain_openai import ChatOpenAI

# Setup
config = Config.from_env()
llm = ChatOpenAI(
    model=config.llm_model,
    api_key=config.llm_api_key,
    base_url=config.llm_api_base,
)

# Create graph
graph = create_graph(config=config, llm=llm)

# Prepare input
input_state = {
    "query": "生成测试用例",
    "files": [
        {
            "type": "mapping",
            "filename": "mapping.md",
            "content": "...",
        },
        # ... more files
    ],
    "w3_id": "q00797588",
}

# Run
result = graph.invoke(input_state)
print(result["llm_response"])
```

## External API Stubs

The following Python implementations are provided as **stubs** and need to be implemented:

### 1. Database Tool (`tools/database_tool.py`)

```python
# TODO: Implement actual GAUSS DB connection
class DatabaseTool:
    def execute_query(self, query_sql: str) -> QueryResult:
        # Implement actual database query execution
        pass
```

### 2. Knowledge Tool (`tools/knowledge_tool.py`)

```python
# TODO: Implement actual knowledge base API integration
class KnowledgeTool:
    def search(self, query: str, test_case_name: str) -> KnowledgeResult:
        # Implement actual knowledge base search
        pass
```

### 3. Messaging Tool (`tools/messaging_tool.py`)

```python
# TODO: Implement actual WeLink/SMTP integration
class MessagingTool:
    def send_welink(self, receiver: str, content: str) -> MessageResult:
        # Implement actual WeLink API call
        pass
```

### 4. Excel Client (`api/excel_client.py`)

```python
# TODO: Implement actual Excel generation API or use library
class ExcelClient:
    def generate_excel(self, test_cases: list) -> ExcelGenerationResult:
        # Implement actual Excel file generation
        pass
```

## Migration Notes

This project is migrated from a Dify chatflow export (`ai4test.yml`). Key differences:

| Dify Concept | LangGraph Equivalent |
|--------------|---------------------|
| Workflow nodes | Graph nodes |
| Conversation variables | State TypedDict |
| Iteration | Subgraph or loop |
| Agent (ReAct) | LangChain Agent with tools |
| Knowledge retrieval | Custom tool |
| HTTP Request | httpx client |
| Code nodes | Python functions |

## State Management

The graph uses a unified `GraphState` that combines:

- `InputState`: User input (query, files, w3_id)
- `ConversationState`: Persistent conversation variables
- `ProcessingState`: Temporary processing results
- `IntentState`: Classification results
- Plus additional state for messages and responses

## Testing

```bash
# Run tests
pytest tests/

# With coverage
pytest --cov=ai4test_langgraph tests/
```

## Development

### Code Style

```bash
# Format code
black .

# Lint code
ruff check .

# Type checking
mypy .
```

## License

MIT

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request

## Contact

For questions or issues, please open an issue on GitHub.
