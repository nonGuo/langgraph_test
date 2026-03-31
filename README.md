# AI4Test LangGraph

基于 LangGraph 的智能测试用例生成系统，用于数据仓库测试。从 Dify chatflow 迁移而来。

## 概述

本项目实现了一个智能测试用例生成助手，具备以下能力：

- 📄 **文档解析**：解析映射文档、RS（需求规格说明书）、TS（技术规格说明书）
- 🧠 **意图分类**：理解用户请求（新任务、修改思维导图、聊天等）
- 🗺️ **生成思维导图**：以 Mermaid 格式创建测试用例结构
- 📝 **创建测试用例**：将思维导图转换为结构化的 JSON 测试用例
- 💾 **生成 SQL**：使用 ReAct Agent 为每个测试用例生成验证 SQL
- 📊 **导出 Excel**：生成格式化的 Excel 文件
- 🔔 **发送通知**：通过 WeLink 通知用户完成状态

## 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        AI4Test Graph                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  START → 意图分类 → 路由                                         │
│                                                                  │
│  分支 1: 聊天/引导 → LLM 响应 → END                              │
│  分支 2: 确认思维导图 → 生成测试用例 → ...                        │
│  分支 3: 文档处理 → 提取 → 生成 → END                            │
│  分支 4: 其他 → LLM 响应 → END                                   │
│                                                                  │
│  文档处理流程：                                                   │
│    解析映射 → 解析 RS → 解析 TS → 提取测试点                     │
│    → 知识检索 → 生成思维导图                                     │
│    → 生成测试用例 → 生成 SQL (迭代)                               │
│    → 生成 Excel → 发送通知 → END                                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## 项目结构

```
langgraph_test/
├── __init__.py
├── state.py              # TypedDict 状态定义
├── config.py             # 配置与环境变量
├── graph.py              # 主图组装
├── main.py               # CLI 入口
├── pyproject.toml        # 项目依赖
├── requirements.txt      # Pip 依赖
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
│   └── routing.py        # 条件边逻辑
├── tools/
│   ├── __init__.py
│   ├── database_tool.py  # ✅ 数据库查询执行工具（已实现）
│   ├── knowledge_tool.py # 知识库检索工具
│   └── messaging_tool.py # 通知消息工具
└── api/
    ├── __init__.py
    └── excel_client.py   # Excel 生成 API 客户端
```

## 安装

### 前置条件

- Python 3.10+
- 可访问 OpenAI 兼容的 LLM API
- （可选）GAUSS DB 访问权限用于 SQL 执行
- （可选）知识库 API 访问权限

### 安装依赖

```bash
pip install -r requirements.txt
```

或使用 poetry：

```bash
poetry install
```

## 配置

复制环境配置示例文件：

```bash
cp .env.example .env
```

编辑 `.env` 配置你的设置：

```bash
# LLM 配置
LLM_PROVIDER=openai_api_compatible
LLM_MODEL=privacy_Qwen3-Coder-480B-A35B-ReAct
LLM_API_KEY=your-api-key
LLM_API_BASE=http://localhost:8000/v1
LLM_TEMPERATURE=0

# 数据库配置
DB_HOST=localhost
DB_PORT=5432
DB_NAME=gaussdb
DB_USER=admin
DB_PASSWORD=

# 知识库
KNOWLEDGE_BASE_ID=your-kb-id
KNOWLEDGE_TOP_K=3

# Excel 生成 API
EXCEL_API_URL=http://10.31.169.36:9002/generate_excel

# 通知
NOTIFICATION_ENABLED=true
```

## 使用

### 命令行

```bash
# 基本用法
python main.py --query "生成测试用例" \
    --mapping mapping.md \
    --rs requirement.md \
    --ts technical.md \
    --w3-id q00797588

# 详细日志模式
python main.py --query "帮我生成测试用例" \
    --mapping ./docs/mapping.md \
    --rs ./docs/rs.md \
    --ts ./docs/ts.md \
    --w3-id q00797588 \
    --verbose
```

### 编程用法

```python
from config import Config
from graph import create_graph
from langchain_openai import ChatOpenAI

# 设置
config = Config.from_env()
llm = ChatOpenAI(
    model=config.llm_model,
    api_key=config.llm_api_key,
    base_url=config.llm_api_base,
)

# 创建图
graph = create_graph(config=config, llm=llm)

# 准备输入
input_state = {
    "query": "生成测试用例",
    "files": [
        {
            "type": "mapping",
            "filename": "mapping.md",
            "content": "...",
        },
        # ... 更多文件
    ],
    "w3_id": "q00797588",
}

# 运行
result = graph.invoke(input_state)
print(result["llm_response"])
```

## 工具实现状态

### 1. DatabaseTool (`tools/database_tool.py`) ✅

**已实现** - 完整的数据库查询执行工具

功能特性：
- ✅ SQL 安全验证（仅允许 SELECT 查询）
- ✅ 自动添加 LIMIT 限制（防止返回过多数据）
- ✅ 语句超时控制（默认 30 秒）
- ✅ 连接池管理（psycopg-pool）
- ✅ 查询表/列信息辅助方法
- ✅ 上下文管理器支持

核心方法：
```python
class DatabaseTool:
    def execute_query(self, query_sql: str) -> QueryResult:
        """执行 SQL 查询，返回 QueryResult"""
        
    def query_tables(self, schema: str = None) -> list[str]:
        """查询表列表"""
        
    def query_columns(self, table_name: str, schema: str = None) -> list[dict]:
        """查询列信息"""
        
    def get_sample_data(self, table_name: str, limit: int = 10) -> list[dict]:
        """获取示例数据"""
```

与 LangGraph 节点交互：
- `sql_generator_node` 调用 `db_tool.execute_query()` 执行验证 SQL
- 返回 `QueryResult(success, data, error, row_count)`
- 执行结果存入 `state["test_case"]` 的 `db_excute_result` 字段

### 2. KnowledgeTool (`tools/knowledge_tool.py`)

**已实现** - 基于 FAISS 的本地知识库检索工具

功能特性：
- ✅ 文档导入和向量化（支持 Markdown, TXT, PDF 等格式）
- ✅ 基于语义的相似度检索
- ✅ 分数阈值过滤
- ✅ 知识库持久化（FAISS 索引 + pickle）
- ✅ Few-shot SQL 示例检索

核心方法：
```python
class KnowledgeTool:
    def add_documents(self, documents: list[str], metadatas: list[dict]) -> int:
        """添加文档到知识库"""

    def search(self, query: str, top_k: int = 3) -> KnowledgeResult:
        """检索知识库"""

    def retrieve_few_shot(self, test_case_item: dict) -> str:
        """为测试用例检索 few-shot SQL 示例"""
```

### 3. MessagingTool (`tools/messaging_tool.py`)

**桩实现** - 消息通知工具（暂不需要真实通知）

当前状态：
- ⚠️ 模拟实现，返回伪造的成功结果
- ⚠️ 不影响程序运行，只是不会真实发送消息
- 如需真实通知，需实现 WeLink API 或 SMTP 集成

### 4. ExcelClient (`api/excel_client.py`)

**已实现** - 本地 Excel 生成客户端

功能特性：
- ✅ 使用 openpyxl 库在本地生成 Excel 文件
- ✅ 支持自定义字段到表头的映射
- ✅ 自动调整列宽
- ✅ 表头样式（蓝色背景、白色粗体字）
- ✅ 交替行背景色
- ✅ 完整的边框样式
- ✅ 支持文件输出和字节流返回

字段映射配置 (`excel_config/__init__.py`):
```python
# 字段名 -> 中文表头
TEST_CASE_FIELD_HEADERS = {
    "case_name": "测试用例名称",
    "level": "测试等级",
    "pre_condition": "前置条件",
    "need_generate_sql": "是否需要 SQL",
    "eval_step_descri": "测试步骤描述",
    "expected_result": "预期结果",
    "tags": "标签",
    "agent_thinking": "Agent 思考过程",
    "db_excute_result": "数据库执行结果",
}

# 字段显示顺序
TEST_CASE_FIELD_ORDER = ["case_name", "level", "pre_condition", ...]

# 列宽配置
TEST_CASE_COLUMN_WIDTHS = {"case_name": 40, "level": 12, ...}

# 值转换规则
TEST_CASE_FIELD_CONVERTERS = {
    "need_generate_sql": lambda x: "是" if x else "否",
    "level": lambda x: x.replace("level", "L"),
}
```

核心方法：
```python
class ExcelClient:
    def generate_excel(self, test_cases: list[dict], filename: str = None) -> ExcelGenerationResult:
        """生成 Excel 文件"""

    def generate_excel_sync(self, test_cases: list[dict]) -> ExcelGenerationResult:
        """同步版本（兼容旧接口）"""
```

与 LangGraph 节点交互：
- `send_notification_node` 调用 `excel_client.generate_excel_sync()` 生成 Excel
- 返回 `ExcelGenerationResult(success, file_path, file_content, row_count)`
- 文件路径存入 `state["body"]` 用于通知消息

## 迁移说明

本项目从 Dify chatflow 导出文件 (`ai4test.yml`) 迁移而来。关键概念对照：

| Dify 概念 | LangGraph 等价物 |
|-----------|-----------------|
| Workflow nodes | Graph nodes |
| Conversation variables | State TypedDict |
| Iteration | Subgraph 或 loop |
| Agent (ReAct) | LangChain Agent + tools |
| Knowledge retrieval | Custom tool |
| HTTP Request | httpx client |
| Code nodes | Python functions |

## 状态管理

图使用统一的 `GraphState`，组合了：

- `InputState`: 用户输入（query, files, w3_id）
- `ConversationState`: 持久化对话变量
- `ProcessingState`: 临时处理结果
- `IntentState`: 分类结果
- 额外的消息和响应状态

## 测试

```bash
# 运行测试
pytest test_database_tool.py -v

# 带覆盖率
pytest --cov=langgraph_test tests/
```

## 开发

### 代码风格

```bash
# 格式化代码
black .

# 代码检查
ruff check .

# 类型检查
mypy .
```

## 许可证

MIT

## 贡献

1. Fork 仓库
2. 创建功能分支
3. 提交更改
4. 运行测试
5. 提交 Pull Request

## 联系方式

如有问题或建议，请在 GitHub 上提交 issue。
