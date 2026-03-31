"""
SQL generator node using ReAct Agent.

This module uses the LangGraph-based ReAct Agent to generate and execute
SQL for test case validation. The agent can:
1. Retrieve knowledge base examples
2. Query table/column metadata
3. Generate and execute SQL
4. Self-correct based on execution results

This matches the behavior of Dify's Agent node with ReAct strategy.
"""

import json
import logging
from typing import Any, Optional

from langchain_core.language_models import BaseChatModel

from state import GraphState, TestCaseItem
from config import Config
from tools.agent_tools import create_agent_tools

logger = logging.getLogger(__name__)


def sql_generator_node(
    state: GraphState,
    llm: BaseChatModel,
    config: Config = None,
    db_tool: Any = None,
    knowledge_tool: Any = None,
) -> GraphState:
    """
    Generate and execute SQL for test cases using ReAct Agent.

    This node processes each test case through the ReAct Agent subgraph,
    which implements the full ReAct loop:
    1. Plan: Analyze test case and decide what tools to use
    2. Act: Call tools (database query, knowledge retrieval, etc.)
    3. Observe: Process tool outputs
    4. Reason: Decide next action based on observations
    5. Repeat: Continue until task is complete or max iterations

    Corresponds to Dify iteration subgraph:
    - 1768484069294 (code - check if SQL needed)
    - 1768484268147 (if-else - route based on need_generate_sql)
    - 1769565941597 (Agent - query knowledge base for few-shot)
    - 1769514001390 (Agent - generate SQL with ReAct loop)
    - 1768658658449 (tool - execute SQL)
    - 1768484458580 (code - update test case item)

    Args:
        state: Current graph state
        llm: Language model for agent
        config: Configuration object
        db_tool: Database execution tool
        knowledge_tool: Knowledge base retrieval tool

    Returns:
        Updated state with processed test cases
    """
    from agents.sql_agent import run_sql_agent_for_test_case, parse_sql_from_result

    # Get test cases
    test_case_json = state.get("test_case", "[]")

    try:
        test_cases = json.loads(test_case_json)
    except json.JSONDecodeError:
        logger.error("Failed to parse test cases JSON")
        return {
            **state,
            "llm_response": "错误：无法解析测试用例 JSON",
        }

    logger.info(f"Processing {len(test_cases)} test cases with ReAct Agent...")

    # Create agent tools
    tools = create_agent_tools(
        db_tool=db_tool,
        knowledge_tool=knowledge_tool,
    )

    if not tools:
        logger.warning("No tools available for agent")
        return {
            **state,
            "llm_response": "错误：没有可用的工具（数据库工具或知识库工具未初始化）",
        }

    # Get max iterations from config
    max_iterations = config.max_sql_iterations if config else 5

    # Process each test case through the ReAct Agent
    processed_cases = []

    for i, case in enumerate(test_cases):
        case_name = case.get("case_name", f"Case {i+1}")
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing test case {i+1}/{len(test_cases)}: {case_name}")
        logger.info(f"{'='*60}")

        # Check if SQL generation is needed
        need_sql = case.get("need_generate_sql", True)

        if not need_sql:
            logger.info(f"SQL generation not needed for: {case_name}")
            case["agent_thinking"] = "无需生成 SQL，需要人工介入测试"
            case["db_excute_result"] = "N/A"
            processed_cases.append(case)
            continue

        # Build context for the agent
        context = _build_context_for_case(case, state)

        # Run the ReAct Agent for this test case
        try:
            agent_result = run_sql_agent_for_test_case(
                test_case=case,
                context=context,
                llm=llm,
                tools=tools,
                max_iterations=max_iterations,
            )

            # Extract results from agent output
            sql_result = agent_result.get("sql_result", "")
            agent_thinking = agent_result.get("agent_thinking", "")
            success = agent_result.get("success", False)
            error = agent_result.get("error")

            # Parse the SQL from agent result using the helper from sql_agent
            sql_dict = parse_sql_from_result(sql_result)
            sql = sql_dict.get("sql", "")
            passed = sql_dict.get("passed", None)
            result_data = sql_dict.get("result_data", "")

            # Update test case with results
            if sql:
                case["eval_step_descri"] = sql
            case["agent_thinking"] = _format_agent_thinking(
                agent_thinking, success, error
            )
            case["db_excute_result"] = _format_execution_result(
                sql_result, passed, result_data, success, error
            )

            logger.info(
                f"Agent completed for {case_name}: "
                f"success={success}, iterations={agent_result.get('iteration_count', 'N/A')}"
            )

        except Exception as e:
            logger.exception(f"Agent execution failed for {case_name}")
            case["agent_thinking"] = f"Agent 执行失败：{str(e)}"
            case["db_excute_result"] = "ERROR"

        processed_cases.append(case)

    # Update state with processed test cases
    new_test_case_json = json.dumps(processed_cases, ensure_ascii=False)

    # Generate summary message
    summary = _generate_summary(processed_cases)

    return {
        **state,
        "test_case": new_test_case_json,
        "new_test_case": new_test_case_json,
        "llm_response": summary,
    }


def _build_context_for_case(
    case: TestCaseItem,
    state: GraphState,
) -> dict[str, str]:
    """
    Build context information for a test case.

    Args:
        case: Test case dictionary
        state: Graph state

    Returns:
        Context dictionary with DDL, mapping, etc.
    """
    return {
        "ddl": state.get("DDL", ""),
        "table_mapping": state.get("mapping_table1", ""),
        "col_mapping": state.get("mapping_table2", ""),
        "rs": state.get("RS", ""),
        "case_name": case.get("case_name", ""),
        "tags": case.get("tags", ""),
    }


def _format_agent_thinking(
    agent_thinking: str,
    success: bool,
    error: Optional[str],
) -> str:
    """
    Format agent thinking for display.

    Args:
        agent_thinking: Raw agent output
        success: Whether agent succeeded
        error: Error message if any

    Returns:
        Formatted thinking string
    """
    lines = []

    if not success:
        lines.append(f"⚠️ 状态：部分成功（{error or '未知错误'}）")
    else:
        lines.append("✅ 状态：成功")

    # Truncate long thinking
    if len(agent_thinking) > 1000:
        lines.append(f"\n📝 思考过程 (摘要):\n{agent_thinking[:500]}...\n...{agent_thinking[-500:]}")
    else:
        lines.append(f"\n📝 思考过程:\n{agent_thinking}")

    return "\n".join(lines)


def _format_execution_result(
    sql_result: str,
    passed: Optional[bool],
    result_data: str,
    success: bool,
    error: Optional[str],
) -> str:
    """
    Format SQL execution result for display.

    Args:
        sql_result: Raw agent output
        passed: Whether test passed
        result_data: Result data string
        success: Whether agent succeeded
        error: Error message if any

    Returns:
        Formatted result string
    """
    lines = []

    # Status indicator
    if passed is True:
        lines.append("✅ 测试通过 (PASS)")
    elif passed is False:
        lines.append("❌ 测试失败 (FAIL)")
    elif not success:
        lines.append(f"⚠️ 执行异常：{error or '未知错误'}")
    else:
        lines.append("❓ 测试结果未知")

    # Add result data (truncated)
    if result_data and len(result_data) > 500:
        lines.append(f"\n📊 执行结果 (摘要):\n{result_data[:500]}...")
    elif result_data:
        lines.append(f"\n📊 执行结果:\n{result_data}")

    return "\n".join(lines)


def _generate_summary(processed_cases: list[dict[str, Any]]) -> str:
    """
    Generate summary of SQL generation results.

    Args:
        processed_cases: List of processed test cases

    Returns:
        Summary string for user
    """
    total = len(processed_cases)
    need_sql_count = sum(
        1 for c in processed_cases if c.get("need_generate_sql", True)
    )
    skip_count = total - need_sql_count

    # Count pass/fail
    pass_count = sum(
        1 for c in processed_cases
        if c.get("db_excute_result", "").startswith("✅ 测试通过")
    )
    fail_count = sum(
        1 for c in processed_cases
        if c.get("db_excute_result", "").startswith("❌ 测试失败")
    )
    error_count = sum(
        1 for c in processed_cases
        if c.get("db_excute_result", "").startswith("⚠️ 执行异常")
        or c.get("db_excute_result", "") == "ERROR"
    )

    summary_lines = [
        "### SQL 生成完成",
        "",
        f"📊 统计信息:",
        f"  - 总测试用例数：{total}",
        f"  - 需要生成 SQL: {need_sql_count}",
        f"  - 人工介入 (跳过): {skip_count}",
        f"  - 测试通过：{pass_count}",
        f"  - 测试失败：{fail_count}",
        f"  - 执行异常：{error_count}",
        "",
        "✅ 所有测试用例的 SQL 已生成并执行完毕。",
    ]

    return "\n".join(summary_lines)
