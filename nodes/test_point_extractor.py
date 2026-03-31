"""
Test point extraction node.

Extracts test points from RS document using regex or LLM fallback.
"""

import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from state import GraphState

logger = logging.getLogger(__name__)


# LLM fallback prompt for test point extraction
TEST_POINTS_EXTRACTION_PROMPT = """
你是一个文档分析师。请阅读以下文档片段，根据整个 RS 内容来提取合适的测试要点：

1. 考虑本次需求的修改点，针对性地生成本次需求重点需要测试的要点。
2. 提取'测试要点'章节的内容（章节内模板测试要点不要一股脑全提取出来，要根据本次需求的修改内容来提取有用的测试要点。但是对于明显是人工写的测试要点要全量提取出来）。
3. DQ（数据质量检查，一般是质量六性）类的有专门的检查平台，不要提取该部分内容作为测试要点。

文档内容：
{doc_content}

注意，仅输出测试要点内容即可，不要输出任何其他字符。
"""


def extract_test_points_node(
    state: GraphState,
    llm: BaseChatModel,
) -> GraphState:
    """
    Extract test points from RS document.
    
    Corresponds to Dify nodes:
    - 1768479835816 (if-else - check if extraction succeeded)
    - 1768479918871 (LLM - fallback extraction)
    - 1768480079086 (variable-aggregator)
    
    This node:
    1. Checks if regex extraction succeeded
    2. If not, uses LLM to extract test points
    3. Aggregates results
    
    Args:
        state: Current graph state
        llm: Language model for extraction
        
    Returns:
        Updated state with RS test points
    """
    section_content = state.get("section_content", "")
    rs_raw = state.get("rs_raw", "")
    
    logger.info(f"Extracting test points, section_content length: {len(section_content)}")
    
    # Check if regex extraction succeeded
    if section_content and len(section_content.strip()) > 10:
        logger.info("Regex extraction succeeded, using section_content")
        return {
            **state,
            "RS": section_content,  # Save to conversation state
        }
    
    # Fallback to LLM extraction
    logger.info("Regex extraction failed/empty, using LLM fallback")
    
    try:
        prompt_text = TEST_POINTS_EXTRACTION_PROMPT.format(
            doc_content=rs_raw[:4000]  # Limit context size
        )
        
        messages = [
            SystemMessage(
                content="你是一个专业的文档分析师，擅长从 RS 文档中提取测试要点。"
            ),
            HumanMessage(content=prompt_text),
        ]
        
        response = llm.invoke(messages)
        extracted_points = response.content.strip()
        
        logger.info(
            f"LLM extracted test points: {len(extracted_points)} chars"
        )
        
        return {
            **state,
            "RS": extracted_points,  # Save to conversation state
        }
        
    except Exception as e:
        logger.exception(f"Test points extraction failed: {e}")
        # Return empty result on error
        return {
            **state,
            "RS": "不涉及",  # Default value as per Dify DSL
        }
