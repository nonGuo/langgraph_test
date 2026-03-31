"""
Test case generation node.

Converts confirmed mind map into structured test case JSON.
"""

import json
import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from state import GraphState, TestCaseItem

logger = logging.getLogger(__name__)


# Test case generation prompt from Dify DSL (simplified)
TEST_CASE_GENERATION_PROMPT = """
# Role
你是一名自动化测试脚本编写专家。

# Task
将用户确认的测试计划转换为结构化的 JSON 数据，用于生成最终 Excel。

# 测试计划（脑图）
{mind_map}

# Instructions
1. 遍历确认后的测试计划
2. 填充等级 (level1-4)，核心业务逻辑为 level1
3. 填充标签 (IT 用例_表视图，业务用例等)
4. 如果用户 query 中给出了脑图则优先使用用户给出的脑图，否则使用测试计划中的脑图

# Output Format (JSON List)
[
  {{
    "case_name": "目标表主键不重复校验",
    "level": "level1",
    "pre_condition": "源表任务已完成，目标表任务已完成",
    "need_generate_sql": true/false,
    "eval_step_descri": "测试步骤流程描述",
    "expected_result": "查询结果为空，无重复主键",
    "tags": "IT 用例表视图/业务用例/配置调度配置"
  }
]

# Rules for need_generate_sql
- true: 可以通过 SQL 直接验证的测试用例
- false: 需要人工介入测试的场景，例如:
  - 验证变更前后数据内容一致性
  - 验证查询耗时
  - 其他无法通过 SQL 直接得到验证结果的场景
"""


def test_case_generator_node(
    state: GraphState,
    llm: BaseChatModel,
) -> GraphState:
    """
    Generate structured test cases from confirmed mind map.
    
    Corresponds to Dify nodes:
    - 1768539572937 (Agent - test case generation)
    - 1768539764964 (assigner - save test cases)
    - 1768539771147 (answer - user confirmation)
    - 1768555668465 (code - format as markdown)
    
    Args:
        state: Current graph state
        llm: Language model for generation
        
    Returns:
        Updated state with test_case JSON
    """
    mind_map = state.get("test_case_naotu", "")
    query = state.get("query", "")
    
    logger.info("Generating structured test cases from mind map...")
    
    try:
        # Build prompt
        prompt_text = TEST_CASE_GENERATION_PROMPT.format(
            mind_map=mind_map[:3000] if mind_map else "无"
        )
        
        # Add user query context if provided
        if query and "生成用例" in query:
            prompt_text += f"\n\n用户额外要求：{query}"
        
        messages = [
            SystemMessage(
                content="你是一名自动化测试脚本编写专家，擅长将测试脑图转换为结构化的测试用例 JSON。"
            ),
            HumanMessage(content=prompt_text),
        ]
        
        response = llm.invoke(messages)
        response_text = response.content
        
        # Parse JSON from response
        test_cases = _parse_test_cases_json(response_text)
        
        logger.info(f"Generated {len(test_cases)} test cases")
        
        # Format for display
        md_output = _format_test_cases_markdown(test_cases)
        
        return {
            **state,
            "test_case": json.dumps(test_cases, ensure_ascii=False),
            "md_output": md_output,
            "llm_response": _format_confirmation_message(md_output, len(test_cases)),
        }
        
    except Exception as e:
        logger.exception(f"Test case generation failed: {e}")
        return {
            **state,
            "llm_response": f"生成测试用例失败：{str(e)}",
        }


def _parse_test_cases_json(response: str) -> list[dict[str, Any]]:
    """
    Parse test cases JSON from LLM response.
    
    Args:
        response: LLM response text
        
    Returns:
        List of test case dictionaries
    """
    import re
    
    # Clean response
    text = response.strip()
    
    # Remove markdown code blocks
    if "```json" in text:
        text = text.split("```json", 1)[-1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[-1].split("```", 1)[0].strip()
    
    try:
        # Try direct parsing
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Try to find JSON array pattern
    pattern = r"\[\s*\{.*?\}\s*\]"
    matches = re.findall(pattern, text, re.DOTALL)
    
    if matches:
        try:
            return json.loads(matches[0])
        except json.JSONDecodeError:
            pass
    
    # Return empty list on failure
    logger.warning("Failed to parse test cases JSON, returning empty list")
    return []


def _format_test_cases_markdown(test_cases: list[dict[str, Any]]) -> str:
    """
    Format test cases as markdown table for display.
    
    Python implementation similar to Dify node 1768555668465.
    
    Args:
        test_cases: List of test case dictionaries
        
    Returns:
        Markdown table string
    """
    if not test_cases:
        return "暂无数据"
    
    # Get headers from first item
    headers = list(test_cases[0].keys())
    
    # Build markdown table
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    
    for item in test_cases:
        row_values = []
        for h in headers:
            val = str(item.get(h, "")).replace("|", "\\|").replace("\n", "<br>")
            row_values.append(val)
        lines.append("| " + " | ".join(row_values) + " |")
    
    return "\n".join(lines)


def _format_confirmation_message(md_output: str, count: int) -> str:
    """
    Format user confirmation message.
    
    Args:
        md_output: Markdown formatted test cases
        count: Number of test cases
        
    Returns:
        Confirmation message string
    """
    return f"""
### Agent 生成的测试用例：

{md_output}

当前测试用例生成已完成，共 {count} 个测试用例。

正在为您链接数据库生成每个测试用例对应的 SQL，该过程耗时较长，
您可暂时离开，任务完成后将会通过 welink 发送消息推送给您。
"""
