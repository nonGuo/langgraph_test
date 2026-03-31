"""
Intent classification node.

Classifies user input into categories:
1. Chat/Guidance/Missing materials
2. Confirm mind map and proceed
3. Initial test case generation request
4. Other/Chit-chat
"""

import json
import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from state import GraphState

logger = logging.getLogger(__name__)


# Intent classification prompt from Dify DSL
INTENT_CLASSIFICATION_PROMPT = """
# Role
你是一个专业的数仓测试用例生成助手的意图识别专家。你的任务是根据用户的最新输入（User Query）以及当前的对话上下文（Context），精准判断用户的意图，并将其归类到唯一的类别中。

# Context Data
用户最新输入：{query}
结合用户与 assistant 的聊天历史来辅助判断。例如：若上一轮系统回复的是"脑图/思维导图"，用户提出修改通常属于类别 1；若回复的是"详细用例/SQL/Excel"，用户提出修改通常属于类别 3)*

# Classification Categories & Criteria

请根据以下定义，严格按顺序匹配（优先级从高到低）：

Priority 1: [修正脑图] (class_type: 1)
触发场景：用户对生成的测试点、测试结构、思维导图（XMind/Tree）提出修改意见。
典型特征：包含"增加分支"、"删除节点"、"层级不对"、"测试点遗漏"、"业务逻辑不仅包含 X"、"脑图"等关键词。
状态约束：通常发生在"脑图生成后"且"详细用例生成前"。

Priority 2: [确认脑图无误，生成测试用例] (class_type: 2)
触发场景：脑图不为空且用户认可当前的测试结构或思维导图，希望进入下一步（生成详细用例）。脑图：{test_case_naotu}
典型特征：包含"脑图没问题"、"结构可以"、"生成用例吧"、"继续"、"下一步"等表达。

Priority 3: [初次生成请求] (class_type: 3)
触发场景：用户开启一个新的话题，提供需求文档、表结构（DDL）或业务描述，请求开始生成测试。
典型特征：包含"帮我生成测试用例"、"这是需求文档"、"针对这张表写测试"、"开始测试任务"等，或者是直接粘贴了大段的需求/代码。

Priority 4: [其他/闲聊] (class_type: 4)
触发场景：与测试用例生成任务无关的输入，或无法识别具体指令的模糊输入。
典型特征：打招呼、询问天气、无意义字符、询问你是谁等。

# Decision Logic (Step-by-Step)
分析当前状态：首先看 上一轮系统回复类型 是处于"脑图阶段"还是"详细用例阶段"。
语义匹配：分析 用户最新输入 的关键词和语义重心。
冲突解决：如果用户输入模糊（如"帮我改一下"），若当前是脑图阶段则归为 1，若当前是详细用例阶段则归为 3。

# Output Format

请仅输出一个标准的 JSON 字符串，严禁包含 Markdown 标记（如```json ... ```）：

{{"class_reason": "简短分析：当前处于 [状态]，用户意图是 [关键词/语义]，符合类别 [X] 的定义", "class_type": 1/2/3/4}}
"""


def intent_classifier_node(
    state: GraphState,
    llm: BaseChatModel,
) -> GraphState:
    """
    Classify user intent to route to appropriate workflow branch.
    
    This node analyzes the user's query and conversation context
    to determine which workflow path to follow.
    
    Args:
        state: Current graph state
        llm: Language model for classification
        
    Returns:
        Updated state with class_type and class_reason
        
    Classification Results:
        class_type=1: Modify mind map (chat/guidance)
        class_type=2: Confirm mind map, generate test cases
        class_type=3: Initial generation request
        class_type=4: Other/chit-chat
    """
    query = state.get("query", "")
    test_case_naotu = state.get("test_case_naotu", "")
    
    # Build prompt with context
    prompt_text = INTENT_CLASSIFICATION_PROMPT.format(
        query=query,
        test_case_naotu=test_case_naotu[:500] if test_case_naotu else "空",
    )
    
    logger.info(f"Classifying intent for query: {query[:100]}...")
    
    try:
        # Call LLM for classification
        messages = [
            SystemMessage(content="你是一个专业的意图识别专家。请严格按照要求输出 JSON 格式结果。"),
            HumanMessage(content=prompt_text),
        ]
        
        response = llm.invoke(messages)
        response_text = response.content.strip()
        
        # Remove markdown code blocks if present
        if response_text.startswith("```"):
            response_text = response_text.split("```", 1)[-1].split("```", 1)[0].strip()
        if response_text.startswith("json"):
            response_text = response_text[4:].strip()
        
        # Parse JSON response
        result = json.loads(response_text)
        
        class_type = str(result.get("class_type", "4"))
        class_reason = result.get("class_reason", "Unknown reason")
        
        logger.info(
            f"Intent classification result: class_type={class_type}, "
            f"reason={class_reason[:100]}..."
        )
        
        return {
            **state,
            "class_type": class_type,
            "class_reason": class_reason,
        }
        
    except json.JSONDecodeError as e:
        logger.exception(f"Failed to parse classification response: {e}")
        # Default to class 4 (other) on parse error
        return {
            **state,
            "class_type": "4",
            "class_reason": f"Failed to parse LLM response: {str(e)}",
        }
    except Exception as e:
        logger.exception(f"Intent classification failed: {e}")
        # Default to class 3 (initial request) on error
        return {
            **state,
            "class_type": "3",
            "class_reason": f"Classification error, defaulting to initial request: {str(e)}",
        }


def intent_router(state: GraphState) -> str:
    """
    Route to appropriate branch based on intent classification.
    
    This is a conditional edge function that returns the next node name
    based on the class_type.
    
    Args:
        state: Current graph state
        
    Returns:
        Next node name based on classification
    """
    class_type = state.get("class_type", "4")
    
    routing_map = {
        "1": "handle_chat_guidance",
        "2": "confirm_mindmap_branch",
        "3": "document_processing_branch",
        "4": "handle_chat_guidance",
    }
    
    next_node = routing_map.get(class_type, "handle_chat_guidance")
    logger.info(f"Routing intent class {class_type} to: {next_node}")
    
    return next_node
