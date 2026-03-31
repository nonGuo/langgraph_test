""""
通用 ReAct Agent 框架.

该模块提供了一个可复用的 ReAct Agent 框架，适用于各种需要多轮推理和工具调用的场景。

核心特性:
1. 通用的 ReAct 循环：Plan -> Act -> Observe -> Reason
2. 可配置的系统提示词和工具集
3. 迭代次数控制和消息历史管理
4. 支持作为子图嵌入更大的 LangGraph 工作流

使用方式:
1. 定义特定任务的系统提示词
2. 创建工具列表
3. 调用 create_react_agent_subgraph 创建子图
4. 在主图中通过 run_react_agent 调用

示例::

    # 1. 定义提示词
    MIND_MAP_AGENT_PROMPT = "# Role: You are a test case planning expert..."

    # 2. 创建工具
    tools = [send_msg_tool]

    # 3. 创建子图
    agent_graph = create_react_agent_subgraph(
        name="mind_map_agent",
        llm=llm,
        tools=tools,
        system_prompt=MIND_MAP_AGENT_PROMPT,
        max_iterations=3,
    )

    # 4. 运行
    result = run_react_agent(
        input_data={"context": {...}},
        llm=llm,
        tools=tools,
        system_prompt=MIND_MAP_AGENT_PROMPT,
    )
"""

import json
import logging
from typing import Annotated, Any, Callable, Literal, Optional
from typing_extensions import TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    BaseMessage,
    SystemMessage,
    HumanMessage,
    AIMessage,
    ToolMessage,
    trim_messages,
)
from langchain_core.tools import BaseTool

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

logger = logging.getLogger(__name__)


# ============================================================================
# 通用状态定义
# ============================================================================

class ReActAgentState(TypedDict):
    """
    ReAct Agent 的通用状态.
    
    该状态设计用于支持各种 ReAct Agent 场景，包含：
    - 输入数据和上下文
    - 消息历史（由 LangGraph 管理）
    - 迭代控制
    - 最终输出
    """
    # 输入数据（由具体任务定义）
    input_data: dict[str, Any]
    
    # 配置参数
    max_iterations: int
    system_prompt: str
    
    # 消息历史
    messages: Annotated[list[BaseMessage], add_messages]
    
    # 迭代跟踪
    iteration_count: int
    
    # 最终输出
    final_result: Optional[str]
    agent_thinking: Optional[str]
    success: bool
    error: Optional[str]


# ============================================================================
# 通用节点函数
# ============================================================================

def create_agent_planner_node(
    llm: BaseChatModel,
    tools: list[BaseTool],
    max_iterations: int = 5,
) -> Callable[[ReActAgentState], ReActAgentState]:
    """
    创建 Agent 规划节点.
    
    规划节点是 ReAct 循环的"大脑"，负责：
    1. 审查消息历史
    2. 决定是否调用工具或输出最终答案
    3. 返回包含可选 tool_calls 的消息
    
    Args:
        llm: 语言模型
        tools: 可用工具列表
        max_iterations: 最大迭代次数（用于日志）
    
    Returns:
        规划节点函数
    """
    # 绑定工具到 LLM
    llm_with_tools = llm.bind_tools(tools)
    
    def agent_planner_node(state: ReActAgentState) -> ReActAgentState:
        """Agent 规划下一步行动."""
        messages = state["messages"]
        
        # 检查迭代限制
        current_iter = state.get("iteration_count", 0)
        
        if current_iter >= max_iterations:
            logger.warning(f"Agent 达到最大迭代次数 ({max_iterations})")
            return {
                **state,
                "messages": [
                    AIMessage(
                        content=f"已达到最大迭代次数 ({max_iterations})，输出当前最佳结果。"
                    )
                ],
                "success": False,
                "error": f"达到最大迭代次数限制 ({max_iterations})",
            }
        
        # 修剪消息历史（保留最近的消息，避免 token 过多）
        trimmed_messages = trim_messages(
            messages,
            max_tokens=4000,
            strategy="last",
            token_counter=len,
            include_system=False,
        )
        
        # 调用 LLM
        response = llm_with_tools.invoke(trimmed_messages)
        
        logger.info(
            f"Agent 规划：有工具调用={bool(response.tool_calls)}, "
            f"迭代={current_iter + 1}/{max_iterations}"
        )
        
        return {
            **state,
            "messages": [response],
            "iteration_count": current_iter + 1,
        }
    
    return agent_planner_node


def create_tools_executor_node(
    tools_by_name: dict[str, BaseTool],
) -> Callable[[ReActAgentState], ReActAgentState]:
    """
    创建工具执行节点.
    
    该节点：
    1. 从最后一条 AI 消息中提取 tool_calls
    2. 执行每个工具
    3. 返回包含结果的 ToolMessages
    
    Args:
        tools_by_name: 工具名称到工具实例的映射
    
    Returns:
        工具执行节点函数
    """
    def tools_executor_node(state: ReActAgentState) -> ReActAgentState:
        """执行 Agent 请求的工具."""
        messages = state["messages"]
        if not messages:
            logger.warning("没有消息可处理")
            return state
        
        last_message = messages[-1]
        
        # 检查是否有 tool_calls
        if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
            logger.debug("最后的消息没有工具调用")
            return state
        
        tool_outputs = []
        
        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call.get("args", {})
            tool_id = tool_call.get("id", "")
            
            logger.info(f"执行工具：{tool_name}, 参数={tool_args}")
            
            try:
                if tool_name not in tools_by_name:
                    output = f"错误：未知工具 '{tool_name}'"
                else:
                    tool = tools_by_name[tool_name]
                    output = tool.invoke(tool_args)
                
                tool_outputs.append(
                    ToolMessage(
                        content=str(output),
                        tool_call_id=tool_id,
                        name=tool_name,
                    )
                )
                
                logger.info(f"工具 {tool_name} 执行成功")
                
            except Exception as e:
                logger.exception(f"工具 {tool_name} 执行失败")
                tool_outputs.append(
                    ToolMessage(
                        content=f"错误：{str(e)}",
                        tool_call_id=tool_id,
                        name=tool_name,
                    )
                )
        
        return {
            **state,
            "messages": tool_outputs,
        }
    
    return tools_executor_node


def should_continue(state: ReActAgentState) -> Literal["continue", "end"]:
    """
    条件判断：是否继续 ReAct 循环.
    
    继续循环的条件：
    1. 最后的消息包含 tool_calls（Agent 想调用工具）
    2. 或者最后的消息是 ToolMessage（刚执行完工具，需要 Agent 分析结果）
    
    结束循环的条件：
    1. Agent 输出 "Final Answer" 或类似标记
    2. 达到最大迭代次数
    3. 错误状态
    
    Args:
        state: 当前 Agent 状态
    
    Returns:
        下一个节点："continue" 或 "end"
    """
    messages = state["messages"]
    
    if not messages:
        return "end"
    
    last_message = messages[-1]
    
    # 检查是否有明确的最终答案标记
    if isinstance(last_message, AIMessage):
        content = last_message.content or ""
        
        # 检查 Final Answer 模式
        if "Final Answer" in content or "最终答案" in content:
            logger.info("Agent 发出最终答案信号")
            return "end"
        
        # 检查是否有工具调用（有则继续）
        if not last_message.tool_calls:
            logger.info("Agent 没有更多工具调用，结束")
            return "end"
    
    # 继续循环
    return "continue"


def create_final_answer_extractor(
    parse_result_fn: Optional[Callable[[str], tuple[Optional[str], str, bool, Optional[str]]]] = None,
) -> Callable[[ReActAgentState], ReActAgentState]:
    """
    创建最终答案提取器.
    
    该节点从 Agent 的最后输出中提取：
    - 最终结果
    - Agent 的思考过程
    - 成功/失败状态
    
    Args:
        parse_result_fn: 可选的自定义解析函数
            接收：content (str)
            返回：(result, thinking, success, error)
    
    Returns:
        答案提取节点函数
    """
    def extract_final_answer(state: ReActAgentState) -> ReActAgentState:
        """从 Agent 输出中提取最终答案."""
        messages = state["messages"]
        
        if not messages:
            return {
                **state,
                "final_result": None,
                "agent_thinking": "无输出",
                "success": False,
                "error": "Agent 未输出任何内容",
            }
        
        # 找到最后一条 AIMessage
        last_ai_message = None
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                last_ai_message = msg
                break
        
        if not last_ai_message:
            return {
                **state,
                "final_result": None,
                "agent_thinking": "无 AI 输出",
                "success": False,
                "error": "未找到 AI 响应",
            }
        
        content = last_ai_message.content or ""
        logger.info(f"提取最终答案：{content[:200]}...")
        
        # 使用自定义解析函数或默认解析
        if parse_result_fn:
            result, thinking, success, error = parse_result_fn(content)
        else:
            result, thinking, success, error = _default_parse_result(content)
        
        return {
            **state,
            "final_result": result,
            "agent_thinking": thinking,
            "success": success,
            "error": error,
        }
    
    return extract_final_answer


def _default_parse_result(
    content: str
) -> tuple[Optional[str], str, bool, Optional[str]]:
    """
    默认的结果解析函数.
    
    尝试从内容中提取 JSON 格式的结果.
    
    Args:
        content: Agent 输出内容
    
    Returns:
        (result, thinking, success, error)
    """
    import re
    
    # 尝试提取 JSON 块
    json_pattern = r"```json\s*(.*?)\s*```"
    matches = re.findall(json_pattern, content, re.DOTALL | re.IGNORECASE)
    
    if matches:
        try:
            result_json = json.loads(matches[-1])
            thinking = result_json.get("thinking", content[:300])
            return json.dumps(result_json, ensure_ascii=False), thinking, True, None
        except json.JSONDecodeError:
            logger.warning("无法解析 JSON 响应")
    
    # 尝试提取 {"key": "value"} 模式
    json_like_pattern = r'\{[^{}]*\}'
    matches = re.findall(json_like_pattern, content)
    if matches:
        try:
            result_json = json.loads(matches[-1])
            return json.dumps(result_json, ensure_ascii=False), content[:300], True, None
        except json.JSONDecodeError:
            pass
    
    # 返回原始内容
    return content, content[:500], False, "未能解析出结构化结果"


# ============================================================================
# 图构建器
# ============================================================================

def create_react_agent_subgraph(
    name: str,
    llm: BaseChatModel,
    tools: list[BaseTool],
    system_prompt: str,
    max_iterations: int = 5,
    parse_result_fn: Optional[Callable[[str], tuple[Optional[str], str, bool, Optional[str]]]] = None,
) -> StateGraph:
    """
    创建通用的 ReAct Agent 子图.
    
    该子图实现标准的 ReAct 循环：
    1. Agent 规划下一步（LLM + 工具绑定）
    2. 执行工具
    3. Agent 观察结果并再次规划
    4. 重复直到最终答案或达到最大迭代次数
    
    图结构:
    ```
    agent_planner -> should_continue?
                     /           \
              continue           end
                |                 |
           tools_executor        |
                |                 v
                +-------> extract_final_answer -> END
    ```
    
    Args:
        name: Agent 名称（用于日志）
        llm: 语言模型
        tools: 可用工具列表
        system_prompt: 系统提示词
        max_iterations: 最大 ReAct 迭代次数
        parse_result_fn: 可选的自定义结果解析函数
    
    Returns:
        编译好的 StateGraph
    """
    logger.info(f"构建 {name} Agent 子图，工具数={len(tools)}")
    
    # 创建工具查找字典
    tools_by_name = {tool.name: tool for tool in tools}
    
    # 构建图
    builder = StateGraph(ReActAgentState)
    
    # 添加节点
    builder.add_node(
        "agent_planner",
        create_agent_planner_node(llm, tools, max_iterations),
    )
    builder.add_node(
        "tools_executor",
        create_tools_executor_node(tools_by_name),
    )
    builder.add_node(
        "extract_final_answer",
        create_final_answer_extractor(parse_result_fn),
    )
    
    # 设置入口点
    builder.set_entry_point("agent_planner")
    
    # 添加条件边
    builder.add_conditional_edges(
        "agent_planner",
        should_continue,
        {
            "continue": "tools_executor",
            "end": "extract_final_answer",
        },
    )
    
    # 工具执行后回到 Agent 进行推理
    builder.add_edge("tools_executor", "agent_planner")
    
    # 最终答案节点结束子图
    builder.add_edge("extract_final_answer", END)
    
    # 编译
    graph = builder.compile()
    logger.info(f"{name} Agent 子图构建成功")
    
    return graph


# ============================================================================
# 主运行函数
# ============================================================================

def run_react_agent(
    input_data: dict[str, Any],
    llm: BaseChatModel,
    tools: list[BaseTool],
    system_prompt: str,
    max_iterations: int = 5,
    user_message: Optional[str] = None,
    parse_result_fn: Optional[Callable[[str], tuple[Optional[str], str, bool, Optional[str]]]] = None,
) -> dict[str, Any]:
    """
    运行 ReAct Agent 子图.
    
    这是从父图调用的主要入口点.
    
    Args:
        input_data: 输入数据字典（包含任务所需的上下文）
        llm: 语言模型
        tools: 可用工具列表
        system_prompt: 系统提示词
        max_iterations: 最大 ReAct 迭代次数
        user_message: 可选的用户消息（ HumanMessage 内容）
        parse_result_fn: 可选的自定义结果解析函数
    
    Returns:
        包含 final_result, agent_thinking, success, error 的字典
    """
    # 构建初始消息
    initial_messages = [
        SystemMessage(content=system_prompt),
    ]
    
    # 添加用户消息
    if user_message:
        initial_messages.append(HumanMessage(content=user_message))
    else:
        initial_messages.append(
            HumanMessage(content=f"请处理以下任务:\n{json.dumps(input_data, ensure_ascii=False)}")
        )
    
    # 创建子图
    agent_graph = create_react_agent_subgraph(
        name="Generic",
        llm=llm,
        tools=tools,
        system_prompt=system_prompt,
        max_iterations=max_iterations,
        parse_result_fn=parse_result_fn,
    )
    
    # 初始状态
    initial_state = {
        "input_data": input_data,
        "max_iterations": max_iterations,
        "system_prompt": system_prompt,
        "messages": initial_messages,
        "iteration_count": 0,
        "final_result": None,
        "agent_thinking": None,
        "success": False,
        "error": None,
    }
    
    logger.info(f"运行 ReAct Agent...")
    
    try:
        result = agent_graph.invoke(initial_state)
        
        logger.info(
            f"Agent 完成：success={result.get('success')}, "
            f"iterations={result.get('iteration_count')}"
        )
        
        return result
        
    except Exception as e:
        logger.exception("Agent 执行失败")
        return {
            "final_result": None,
            "agent_thinking": f"Agent 执行失败：{str(e)}",
            "success": False,
            "error": str(e),
        }
