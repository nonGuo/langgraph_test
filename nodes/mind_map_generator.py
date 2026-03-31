"""
Mind map generation node.

Uses Agent (ReAct) to generate test case mind map in mermaid format.
"""

import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from state import GraphState

logger = logging.getLogger(__name__)


# Mind map generation prompt from Dify DSL (simplified)
MIND_MAP_GENERATION_PROMPT = """
# Role
你是一名资深的数据仓库测试专家。

# Task
根据提供的 Mapping 文档、表属性、提取的 RS 测试要点以及常见测试用例，规划生成符合用例规范的测试用例列表。

# Context
1. Mapping 逻辑: 
   1.1. <表级 mapping>：{table_1}
   1.2. <字段级 mapping>：{table_2}
   
2. 表属性及本次变更内容：{ts_info}

3. 测试用例设计规范：{knowledge_result}

4. 必须包含的测试用例：{rs_points}

5. 常见测试用例示例: 
   - IT 用例表视图检查{{schema.table/view name}}目标表/视图及临时表存在检查
   - IT 用例表视图检查{{schema.table/view name}}验证整表有数
   - IT 用例表视图检查{{schema.table/view name}}验证表倾斜率<0.1
   - IT 用例表视图检查{{schema.table/view name}}业务主键唯一性检查
   - (更多见完整文档...)

# Requirements
1. 禁止幻觉产生不存在的事实（比如绝对禁止想构造主键唯一性测试用例时，当你能获取到的输入信息中无法获取主键信息时，尽量避免生成主键唯一性的测试用例）
2. 常用测试用例是以往需求的总结，并不代表当前需求适合，请结合当前需求仔细分析选择
3. 构造测试用例时应分清楚需求是优化类还是新增类需求
4. 生成的测试用例脑图必须遵从"测试用例设计规范"中定义的规范
5. 请输出一个 mermaid 格式的脑图，包含以下类别的测试（类别 1 必须包含，其他类别结合实际需求判断）：
   5.1. 用户指定的测试要点：必须包含
   5.2. 基础一致性（非必选）
   5.3. 字段级逻辑（非必选）
   5.4. 数据质量（非必选）
   5.5. 性能相关（非必选）
   5.6. 业务相关（非必选）
   
   确保最终生成的测试用例不超过 20 个

6. L3 的测试用例禁止出现模糊的表达，应该定义具体的指标

# Output Format
## 以下是生成的测试要点的脑图

graph LR
    root("目标表/视图测试用例脑图")
    L1_1("用户指定的测试要点")
    L1_2("基础一致性")
    L1_3("字段级逻辑")
    root --> L1_1
    root --> L1_2
    root --> L1_3
    L3_1_1("[IT 用例][表视图检查][对象名]_预期结果")
    L1_1 --> L3_1_1
    
## 解释
xxx
"""


def mind_map_generator_node(
    state: GraphState,
    llm: BaseChatModel,
    agent_tools: list[Any] = None,
) -> GraphState:
    """
    Generate test case mind map using Agent (ReAct pattern).
    
    Corresponds to Dify nodes:
    - 1768480181455 (knowledge-retrieval)
    - 1768538766043 (Agent - mind map generation)
    - 1768538931156 (answer - user interaction)
    - 1768539081186 (assigner - save mind map)
    
    This node uses ReAct agent pattern to:
    1. Retrieve knowledge base for test case standards
    2. Generate mind map in mermaid format
    3. Save to conversation state
    
    Args:
        state: Current graph state
        llm: Language model for generation
        agent_tools: Optional list of tools for agent
        
    Returns:
        Updated state with test_case_naotu
    """
    # Gather context
    table_1 = state.get("mapping_table1", "")
    table_2 = state.get("mapping_table2", "")
    ts_info = state.get("ts_info", {})
    knowledge_result = state.get("result", "")
    rs_points = state.get("RS", "")
    
    logger.info("Generating test case mind map...")
    
    try:
        # Build prompt
        prompt_text = MIND_MAP_GENERATION_PROMPT.format(
            table_1=table_1[:2000] if table_1 else "无",
            table_2=table_2[:2000] if table_2 else "无",
            ts_info=str(ts_info)[:500] if ts_info else "无",
            knowledge_result=knowledge_result[:1000] if knowledge_result else "无",
            rs_points=rs_points[:1000] if rs_points else "无",
        )
        
        # If tools are provided, use agent pattern
        if agent_tools:
            # TODO: Implement full ReAct agent with tools
            logger.info("Using agent pattern with tools")
            # For now, fall through to simple LLM call
        
        # Simple LLM call for now
        messages = [
            SystemMessage(
                content="你是一名资深的数据仓库测试专家，擅长生成符合规范的测试用例脑图。"
            ),
            HumanMessage(content=prompt_text),
        ]
        
        response = llm.invoke(messages)
        mind_map_content = response.content
        
        logger.info(f"Generated mind map: {len(mind_map_content)} chars")
        
        # Extract mermaid diagram from response
        mind_map = _extract_mermaid_from_response(mind_map_content)
        
        return {
            **state,
            "test_case_naotu": mind_map,  # Save to conversation state
            "llm_response": _format_user_confirmation(mind_map),
        }
        
    except Exception as e:
        logger.exception(f"Mind map generation failed: {e}")
        return {
            **state,
            "llm_response": f"生成测试用例脑图失败：{str(e)}",
        }


def _extract_mermaid_from_response(response: str) -> str:
    """
    Extract mermaid diagram from LLM response.
    
    Args:
        response: LLM response text
        
    Returns:
        Mermaid diagram string
    """
    # Look for mermaid code blocks
    import re
    
    # Try to find ```mermaid ... ``` blocks
    pattern = r"```mermaid\s*(.*?)\s*```"
    matches = re.findall(pattern, response, re.DOTALL)
    
    if matches:
        return matches[0].strip()
    
    # Try to find ``` ... ``` blocks with graph content
    pattern = r"```\s*(graph\s*.*?)\s*```"
    matches = re.findall(pattern, response, re.DOTALL | re.IGNORECASE)
    
    if matches:
        return matches[0].strip()
    
    # If no code blocks, return the whole response
    # (might contain inline mermaid)
    return response


def _format_user_confirmation(mind_map: str) -> str:
    """
    Format user confirmation message.
    
    Args:
        mind_map: Generated mind map
        
    Returns:
        Formatted confirmation message
    """
    return f"""
{mind_map}

请问该测试用例脑图生成是否正确？
如果需要修改请直接告诉我，无需修改请回复"确认脑图正确，生成测试用例"。
"""


def mind_map_confirm_router(state: GraphState) -> str:
    """
    Route based on user confirmation of mind map.
    
    Conditional edge that checks if user confirmed the mind map
    or requested modifications.
    
    Args:
        state: Current graph state
        
    Returns:
        Next node name
    """
    query = state.get("query", "").lower()
    
    # Keywords indicating confirmation
    confirm_keywords = [
        "确认", "正确", "没问题", "可以", "继续", "生成用例",
        "confirm", "correct", "yes", "continue"
    ]
    
    # Keywords indicating modification request
    modify_keywords = [
        "修改", "不对", "错误", "增加", "删除", "调整",
        "modify", "change", "wrong", "add", "remove"
    ]
    
    for keyword in confirm_keywords:
        if keyword in query:
            logger.info("User confirmed mind map, proceeding to test case generation")
            return "generate_test_cases"
    
    for keyword in modify_keywords:
        logger.info("User requested mind map modification")
        return "regenerate_mind_map"
    
    # Default to regeneration if unclear
    logger.info("User response unclear, requesting clarification")
    return "request_clarification"
