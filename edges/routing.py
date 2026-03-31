"""
Routing functions for conditional edges.
"""

import logging

from state import GraphState

logger = logging.getLogger(__name__)


def intent_router(state: GraphState) -> str:
    """
    Route to appropriate branch based on intent classification.
    
    Maps class_type to next node:
    - 1: handle_chat_guidance (chat/guidance/missing materials)
    - 2: confirm_mindmap_branch (confirm and generate test cases)
    - 3: document_processing_branch (initial request)
    - 4: handle_chat_guidance (other/chit-chat)
    
    Args:
        state: Current graph state
        
    Returns:
        Next node name
    """
    class_type = state.get("class_type", "4")
    
    routing_map = {
        "1": "handle_chat_guidance",
        "2": "confirm_mindmap_branch",
        "3": "document_processing_branch",
        "4": "handle_chat_guidance",
    }
    
    next_node = routing_map.get(class_type, "handle_chat_guidance")
    logger.info(f"Intent router: class_type={class_type} -> {next_node}")
    
    return next_node


def test_points_extraction_router(state: GraphState) -> str:
    """
    Route based on whether test points extraction succeeded.
    
    Corresponds to Dify node 1768479835816.
    
    Args:
        state: Current graph state
        
    Returns:
        Next node name
    """
    section_content = state.get("section_content", "")
    
    # Check if extraction succeeded (non-empty content)
    if section_content and len(section_content.strip()) > 10:
        logger.info("Test points extraction succeeded")
        return "extraction_success"
    else:
        logger.info("Test points extraction failed/empty, using LLM fallback")
        return "extraction_fallback_llm"


def mind_map_confirm_router(state: GraphState) -> str:
    """
    Route based on user confirmation of mind map.
    
    Checks user query for confirmation or modification keywords.
    
    Args:
        state: Current graph state
        
    Returns:
        Next node name
    """
    query = state.get("query", "").lower()
    test_case_naotu = state.get("test_case_naotu", "")
    
    # If no mind map exists, can't confirm
    if not test_case_naotu:
        logger.info("No mind map to confirm")
        return "generate_mind_map"
    
    # Keywords indicating confirmation
    confirm_keywords = [
        "确认", "正确", "没问题", "可以", "继续", "生成用例",
        "confirm", "correct", "yes", "continue", "ok"
    ]
    
    # Keywords indicating modification request
    modify_keywords = [
        "修改", "不对", "错误", "增加", "删除", "调整", "改变",
        "modify", "change", "wrong", "add", "remove", "update"
    ]
    
    for keyword in confirm_keywords:
        if keyword in query:
            logger.info("User confirmed mind map")
            return "confirm_mindmap"
    
    for keyword in modify_keywords:
        logger.info("User requested mind map modification")
        return "modify_mindmap"
    
    # Default to waiting for confirmation
    logger.info("User response unclear, waiting for confirmation")
    return "await_confirmation"


def should_generate_sql_router(state: GraphState, item: dict) -> str:
    """
    Route based on whether SQL generation is needed for test case.
    
    Corresponds to Dify node 1768484268147.
    
    Args:
        state: Current graph state
        item: Current test case item
        
    Returns:
        Next node name
    """
    need_sql = item.get("need_generate_sql", True)
    
    if need_sql:
        logger.info("SQL generation needed")
        return "generate_sql"
    else:
        logger.info("SQL generation not needed, skipping")
        return "skip_sql"


def has_rs_document_router(state: GraphState) -> str:
    """
    Route based on whether RS document was provided.
    
    Corresponds to Dify node 1774228896483.
    
    Args:
        state: Current graph state
        
    Returns:
        Next node name
    """
    files = state.get("files", [])
    rs_raw = state.get("rs_raw", "")
    
    # Check if RS file exists
    has_rs = False
    for file in files:
        if file.get("type") == "RS" or "RS" in file.get("filename", "").upper():
            has_rs = True
            break
    
    if has_rs or rs_raw:
        logger.info("RS document provided")
        return "has_rs"
    else:
        logger.info("No RS document provided")
        return "no_rs"
