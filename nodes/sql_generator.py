"""
SQL generator node for test case validation.

Uses Agent (ReAct) to generate and execute SQL for each test case.
"""

import json
import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from state import GraphState, TestCaseItem

logger = logging.getLogger(__name__)


# SQL generation prompt from Dify DSL (simplified)
SQL_GENERATION_PROMPT = """
# Role
你是一名资深的数据仓库测试的 SQL 专家。你的任务是为给定的测试用例生成准确、可执行的验证 SQL 脚本。

# Input Context
1. 参考范例 (Reference):
   - 包含历史相似用例的 SQL 写法，请仔细模仿其逻辑结构
   - {few_shot}

2. 测试用例详情 (Case Detail):
   {md_table}

3. 映射逻辑 (Mappings):
   - <表级关联> (决定 JOIN/WHERE): {table_mapping}
   - <字段计算> (决定 SELECT): {col_mapping}

4. 目标表结构 (DDL):
   {ddl}

# Workflow (必须严格遵守的执行流程)

## Step 1: 策略分析 (Analyze)
- 阅读 Context 中的参考范例，确定 SQL 风格
- 分析测试用例详情中的 expected_result
- 确定断言逻辑：什么情况算 PASS，什么情况算 FAIL

## Step 2: 编写初版 SQL (Draft)
- 根据 Mapping 和 DDL 编写 SQL
- 关键规则 A (Schema): 必须检查 Context 中的 DDL 以及表级关联，确保表名严格遵循 schema.table_name 格式
- 关键规则 B (PASS/FAIL 输出):
  - 你的 SQL 必须包含断言逻辑，直接输出 'PASS' 或 'FAIL'
  - 使用 CASE WHEN 结构

## Step 3: 执行与诊断 (Execute & Diagnose)
你必须调用 database_query_with_sql 工具执行你编写的 SQL，并根据工具返回的 Observation 进行决策：

### 情况 A：工具返回"执行报错" (Runtime Error)
- 这是 SQL 语法或元数据错误
- 不要直接重试相同的 SQL
- 必须重新阅读 Context 中的 DDL 以及 mapping，或者调用工具查询有哪些表/字段
- 修正 SQL 语法后，再次调用 database_query_with_sql

### 情况 B：工具返回"执行成功" (Execution Success)
- SQL 语法是完全正确的
- 无论结果是 'PASS' 还是 'FAIL'，都代表 SQL 能够正常运行
- 严禁为了让结果变成 'PASS' 而修改 SQL 逻辑
- 立即停止工具调用，直接进入 Step 4

## Step 4: 最终输出 (Final Answer)
仅当 Step 3 处于"情况 B"时，输出最终 JSON：

Final Answer
{{"sql": "最终验证通过的 SQL 语句"}}

# Output Format
按照以下格式回答：
Final Answer
{{"sql": "最终验证通过的 SQL 语句"}}
"""


def sql_generator_node(
    state: GraphState,
    llm: BaseChatModel,
    db_tool: Any = None,
    knowledge_tool: Any = None,
) -> GraphState:
    """
    Generate and execute SQL for test case validation.
    
    Corresponds to Dify iteration subgraph:
    - 1768484069294 (code - check if SQL needed)
    - 1768484268147 (if-else - route based on need_generate_sql)
    - 1768636785422 (LLM - extract mapping info)
    - 1769565941597 (Agent - query knowledge base for few-shot)
    - 1769570150785 (code - extract few-shot)
    - 1769514001390 (Agent - generate SQL)
    - 1768658658449 (tool - execute SQL)
    - 1768484458580 (code - update test case item)
    
    This is a simplified version. Full implementation requires
    iteration subgraph.
    
    Args:
        state: Current graph state
        llm: Language model for generation
        db_tool: Database execution tool
        knowledge_tool: Knowledge base retrieval tool
        
    Returns:
        Updated state with SQL results
    """
    # Get test cases
    test_case_json = state.get("test_case", "[]")
    
    try:
        test_cases = json.loads(test_case_json)
    except json.JSONDecodeError:
        logger.error("Failed to parse test cases JSON")
        return state
    
    logger.info(f"Processing {len(test_cases)} test cases for SQL generation...")
    
    # Process each test case
    processed_cases = []
    
    for i, case in enumerate(test_cases):
        logger.info(f"Processing test case {i+1}/{len(test_cases)}: {case.get('case_name', 'Unknown')}")
        
        # Check if SQL generation is needed
        need_sql = case.get("need_generate_sql", True)
        
        if not need_sql:
            logger.info("SQL generation not needed for this case")
            case["agent_thinking"] = "无需生成 SQL，需要人工测试"
            case["db_excute_result"] = "N/A"
            processed_cases.append(case)
            continue
        
        # Generate SQL for this test case
        try:
            result = _generate_sql_for_case(
                case=case,
                state=state,
                llm=llm,
                db_tool=db_tool,
                knowledge_tool=knowledge_tool,
            )
            
            case["eval_step_descri"] = result.get("sql", case.get("eval_step_descri", ""))
            case["agent_thinking"] = result.get("thinking", "")
            case["db_excute_result"] = result.get("execution_result", "")
            
        except Exception as e:
            logger.exception(f"SQL generation failed for case {case.get('case_name')}")
            case["agent_thinking"] = f"SQL 生成失败：{str(e)}"
            case["db_excute_result"] = "ERROR"
        
        processed_cases.append(case)
    
    # Update state with processed test cases
    new_test_case_json = json.dumps(processed_cases, ensure_ascii=False)
    
    return {
        **state,
        "test_case": new_test_case_json,
        "new_test_case": new_test_case_json,
    }


def _generate_sql_for_case(
    case: TestCaseItem,
    state: GraphState,
    llm: BaseChatModel,
    db_tool: Any = None,
    knowledge_tool: Any = None,
) -> dict[str, str]:
    """
    Generate SQL for a single test case.
    
    Args:
        case: Test case dictionary
        state: Graph state
        llm: Language model
        db_tool: Database tool
        knowledge_tool: Knowledge tool
        
    Returns:
        Dictionary with sql, thinking, and execution_result
    """
    # Gather context
    few_shot = ""
    if knowledge_tool:
        try:
            few_shot = knowledge_tool.retrieve_few_shot(case)
        except Exception as e:
            logger.warning(f"Knowledge retrieval failed: {e}")
            few_shot = "未找到可参考的业务逻辑或 SQL"
    
    table_mapping = state.get("table_mapping_useful_info", "")
    col_mapping = state.get("col_table_mapping_useful_info", "")
    ddl = state.get("DDL", "")
    
    # Format test case as markdown table
    md_table = _format_case_as_markdown(case)
    
    # Build prompt
    prompt_text = SQL_GENERATION_PROMPT.format(
        few_shot=few_shot[:1000] if few_shot else "无",
        md_table=md_table,
        table_mapping=table_mapping[:1000] if table_mapping else "无",
        col_mapping=col_mapping[:1000] if col_mapping else "无",
        ddl=ddl[:1000] if ddl else "无",
    )
    
    # Call LLM (simplified - without full ReAct loop)
    messages = [
        SystemMessage(
            content="你是一名资深的数据仓库测试的 SQL 专家，擅长生成 GAUSS DB 验证 SQL。"
        ),
        HumanMessage(content=prompt_text),
    ]
    
    response = llm.invoke(messages)
    response_text = response.content
    
    # Extract SQL from response
    sql = _extract_sql_from_response(response_text)
    
    # Execute SQL if db_tool available
    execution_result = ""
    if sql and db_tool:
        try:
            result = db_tool.execute_query(sql)
            if result.success:
                execution_result = str(result.data)
            else:
                execution_result = f"执行错误：{result.error}"
        except Exception as e:
            execution_result = f"执行异常：{str(e)}"
    
    return {
        "sql": sql,
        "thinking": response_text[:500],  # Truncate for state
        "execution_result": execution_result,
    }


def _extract_sql_from_response(response: str) -> str:
    """
    Extract SQL from LLM response.
    
    Args:
        response: LLM response text
        
    Returns:
        Extracted SQL string
    """
    import re
    
    # Try to find JSON with sql key
    pattern = r'\{\s*"sql"\s*:\s*"([^"]+)"\s*\}'
    matches = re.findall(pattern, response)
    
    if matches:
        return matches[0]
    
    # Try to find SQL code block
    pattern = r"```sql\s*(.*?)\s*```"
    matches = re.findall(pattern, response, re.DOTALL | re.IGNORECASE)
    
    if matches:
        return matches[0]
    
    # Try to find any SQL-like content (SELECT ... FROM)
    pattern = r"(SELECT\s+.*?;)"
    matches = re.findall(pattern, response, re.DOTALL | re.IGNORECASE)
    
    if matches:
        return matches[0]
    
    # Return empty if nothing found
    logger.warning("No SQL found in response")
    return ""


def _format_case_as_markdown(case: TestCaseItem) -> str:
    """
    Format test case as markdown table.
    
    Args:
        case: Test case dictionary
        
    Returns:
        Markdown table string
    """
    headers = ["Key", "Value"]
    lines = [
        "| Key | Value |",
        "|---|---|",
    ]
    
    for key, value in case.items():
        if value:
            safe_value = str(value).replace("|", "\\|").replace("\n", "<br>")
            lines.append(f"| {key} | {safe_value} |")
    
    return "\n".join(lines)


def should_generate_sql_router(state: GraphState, item: dict) -> str:
    """
    Route based on whether SQL generation is needed.
    
    Conditional edge for iteration subgraph.
    
    Args:
        state: Graph state
        item: Current test case item
        
    Returns:
        Next node name
    """
    need_sql = item.get("need_generate_sql", True)
    
    if need_sql:
        return "generate_sql"
    else:
        return "skip_sql_generation"
