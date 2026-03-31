"""
SQL Agent using the generic ReAct Agent framework.

This module provides SQL-specific functionality that leverages the
generic ReAct Agent framework from base_react_agent.py.

The SQL Agent can:
1. Retrieve knowledge base examples for few-shot SQL patterns
2. Query table/column metadata from the database
3. Generate and execute SQL for test case validation
4. Self-correct based on execution results

Usage:
    ```python
    from agents.sql_agent import run_sql_agent_for_test_case, SQL_AGENT_SYSTEM_PROMPT
    from tools.agent_tools import create_agent_tools

    # Create tools
    tools = create_agent_tools(db_tool, knowledge_tool)

    # Run the agent
    result = run_sql_agent_for_test_case(
        test_case=test_case,
        context=context,
        llm=llm,
        tools=tools,
        max_iterations=5,
    )
    ```
"""

import json
import logging
from typing import Any, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from agents.base_react_agent import run_react_agent

logger = logging.getLogger(__name__)


# ============================================================================
# System Prompt for SQL Agent
# ============================================================================

SQL_AGENT_SYSTEM_PROMPT = """
# Role
你是一位资深的数据仓库测试专家，擅长从测试用例中提炼业务逻辑，并构建精准的校验 SQL。

# Tools
你可以使用以下工具：
1. `database_query_with_sql`: 执行 SQL 查询，验证测试用例
2. `query_knowledge_base`: 从知识库检索历史测试用例的 SQL 范例
3. `query_tables`: 查询数据库中有哪些表
4. `query_columns`: 查询表的列结构信息

# Workflow (必须严格遵守)

## Step 1: 分析测试用例
- 阅读测试用例的 case_name, eval_step_descri, expected_result
- 理解需要验证的业务逻辑
- 查看 context 中的 DDL、mapping 信息

## Step 2: 检索知识库 (可选但推荐)
- 调用 `query_knowledge_base` 工具，使用 case_name 作为检索词
- 学习历史相似用例的 SQL 写法
- 提取可复用的 SQL 模式和逻辑

## Step 3: 探索表结构 (如需要)
- 如果不确定表名或列名，调用 `query_tables` 或 `query_columns`
- 确保你使用的表和字段都存在

## Step 4: 编写并执行 SQL
- 根据分析编写 SQL
- **关键**: SQL 必须包含断言逻辑，输出 'PASS' 或 'FAIL'
- 使用 CASE WHEN 结构实现断言
- 调用 `database_query_with_sql` 执行你的 SQL

## Step 5: 诊断与修正
根据工具返回的 Observation 进行决策：

### 情况 A: 执行报错 (语法/元数据错误)
- 仔细阅读错误信息
- 检查表名、列名是否正确（可调用 query_columns 确认）
- 检查 SQL 语法
- 修正后重新执行

### 情况 B: 执行成功，返回 PASS/FAIL
- ✅ 这是预期结果！SQL 已成功验证测试用例
- 停止工具调用，输出最终答案

### 情况 C: 执行成功，但返回格式不对
- 修改 SQL，确保输出包含 'PASS' 或 'FAIL'
- 重新执行

# Constraints
1. **严禁虚构字段**: SQL 中使用的表和字段必须来自 DDL 或 query_columns 的返回
2. **只允许 SELECT**: 不能执行 INSERT/UPDATE/DELETE 等操作
3. **输出格式**: 最终答案必须是 JSON 格式，包含 sql 和 passed 字段
4. **迭代限制**: 最多 {max_iterations} 次工具调用，超时必须输出当前最佳结果

# Context Information
- DDL (表结构): {ddl}
- 表级 Mapping: {table_mapping}
- 字段级 Mapping: {col_mapping}

# Test Case to Process
{test_case_json}

# Output Format
当你完成所有工具调用并得到最终结果后，输出：

Final Answer
```json
{{
  "sql": "最终验证 SQL",
  "passed": true/false,
  "result_data": "执行结果摘要",
  "thinking": "你的思考过程"
}}
```
"""


# ============================================================================
# Result Parsing Function
# ============================================================================

def parse_sql_agent_result(
    content: str
) -> tuple[Optional[str], str, bool, Optional[str]]:
    """
    Parse the SQL Agent's output.

    Extracts the SQL result JSON from the agent's final answer.

    Args:
        content: Agent output content

    Returns:
        (sql_result_json, thinking, success, error)
    """
    import re

    sql_result = None
    thinking = content[:500]  # Default to truncated content
    success = True
    error = None

    # Pattern 1: Look for JSON block after "Final Answer"
    json_pattern = r"```json\s*(.*?)\s*```"
    matches = re.findall(json_pattern, content, re.DOTALL | re.IGNORECASE)

    if matches:
        try:
            result_json = json.loads(matches[-1])
            sql_result = json.dumps(result_json, ensure_ascii=False)
            thinking = result_json.get("thinking", content[:300])
            logger.info(f"Extracted JSON result: {result_json.keys()}")
            return sql_result, thinking, True, None
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON from response")

    # Pattern 2: Look for {"sql": ...} pattern
    sql_pattern = r'\{\s*"sql"\s*:\s*"([^"]+)"'
    sql_matches = re.findall(sql_pattern, content)
    if sql_matches:
        sql_result = sql_matches[-1]
        logger.info(f"Extracted SQL using regex: {sql_result[:100]}...")
        thinking = content[:300]
        success = False
        error = "仅提取到 SQL，未找到完整 JSON 结构"
        return sql_result, thinking, success, error

    # Pattern 3: Return raw content as fallback
    sql_result = content
    success = False
    error = "未能解析出结构化结果，返回原始输出"

    return sql_result, thinking, success, error


# ============================================================================
# Main Entry Point
# ============================================================================

def run_sql_agent_for_test_case(
    test_case: dict[str, Any],
    context: dict[str, str],
    llm: BaseChatModel,
    tools: list[BaseTool],
    max_iterations: int = 5,
) -> dict[str, Any]:
    """
    Run the ReAct Agent for SQL generation using the generic framework.

    This function wraps the generic run_react_agent with SQL-specific
    prompt formatting and result parsing.

    Args:
        test_case: Test case dictionary to process
            Expected keys: case_name, eval_step_descri, expected_result, etc.
        context: Context information dictionary
            Expected keys: ddl, table_mapping, col_mapping, rs, tags
        llm: Language model instance
        tools: List of available LangChain tools
        max_iterations: Maximum ReAct iterations (default: 5)

    Returns:
        Dictionary containing:
            - sql_result: Raw agent output (JSON string if successful)
            - agent_thinking: Agent's reasoning process
            - success: Whether the agent completed successfully
            - error: Error message if any
            - iteration_count: Number of iterations performed
    """
    # Extract context information
    ddl = context.get("ddl", "")
    table_mapping = context.get("table_mapping", "")
    col_mapping = context.get("col_mapping", "")

    # Build system prompt with context
    system_prompt = SQL_AGENT_SYSTEM_PROMPT.format(
        max_iterations=max_iterations,
        ddl=ddl[:2000] if ddl else "无",
        table_mapping=table_mapping[:1000] if table_mapping else "无",
        col_mapping=col_mapping[:1000] if col_mapping else "无",
        test_case_json=json.dumps(test_case, ensure_ascii=False),
    )

    # Build input data for the agent
    input_data = {
        "test_case": test_case,
        "context": context,
    }

    # Build user message
    case_name = test_case.get("case_name", "Unknown")
    user_message = (
        f"请为测试用例 '{case_name}' 生成验证 SQL。\n\n"
        f"测试步骤：{test_case.get('eval_step_descri', 'N/A')}\n"
        f"预期结果：{test_case.get('expected_result', 'N/A')}"
    )

    logger.info(f"Running SQL Agent for test case: {case_name}")

    # Run the generic ReAct Agent
    result = run_react_agent(
        input_data=input_data,
        llm=llm,
        tools=tools,
        system_prompt=system_prompt,
        max_iterations=max_iterations,
        user_message=user_message,
        parse_result_fn=parse_sql_agent_result,
    )

    # Map generic result fields to SQL-specific fields
    sql_result = {
        "sql_result": result.get("final_result"),
        "agent_thinking": result.get("agent_thinking"),
        "success": result.get("success"),
        "error": result.get("error"),
        "iteration_count": result.get("iteration_count", 0),
    }

    logger.info(
        f"SQL Agent completed: "
        f"success={sql_result['success']}, "
        f"iterations={sql_result['iteration_count']}"
    )

    return sql_result


# ============================================================================
# Helper Functions
# ============================================================================

def parse_sql_from_result(sql_result: str) -> dict[str, Any]:
    """
    Parse SQL and metadata from agent result.

    Args:
        sql_result: Raw agent output (JSON string)

    Returns:
        Dictionary with sql, passed, result_data keys
    """
    result = {
        "sql": "",
        "passed": None,
        "result_data": "",
    }

    if not sql_result:
        return result

    try:
        # Try to parse as JSON
        result_json = json.loads(sql_result)
        result["sql"] = result_json.get("sql", "")
        result["passed"] = result_json.get("passed")
        result["result_data"] = result_json.get("result_data", "")
    except (json.JSONDecodeError, TypeError):
        # Fallback: try regex extraction
        import re

        sql_pattern = r'"sql"\s*:\s*"([^"]+)"'
        matches = re.findall(sql_pattern, sql_result)
        if matches:
            result["sql"] = matches[-1]

        # Check for PASS/FAIL
        if "PASS" in sql_result.upper():
            result["passed"] = True
        elif "FAIL" in sql_result.upper():
            result["passed"] = False

        result["result_data"] = sql_result[:500]

    return result
