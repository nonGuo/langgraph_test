"""
测试用例脑图生成节点 - 使用 ReAct Agent 模式.

对应 Dify 节点:
- 1768538766043 (Agent - 规划脑图)
- 1768538931156 (answer - 与用户交互)
- 1768539081186 (assigner - 保存测试用例脑图)

该节点使用 ReAct Agent 模式：
1. 分析 Mapping 文档、表属性、测试要点
2. 检索知识库获取测试用例设计规范
3. 规划并生成符合规范的测试用例脑图
4. 输出 mermaid 格式的脑图供用户确认
"""

import json
import logging
import re
from typing import Any, Optional, Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from state import GraphState
from agents.base_react_agent import run_react_agent

logger = logging.getLogger(__name__)


# ============================================================================
# 系统提示词
# ============================================================================

MIND_MAP_AGENT_PROMPT = """
# Role
你是一名资深的数据仓库测试专家，擅长根据提供的文档规划生成符合用例规范的测试用例列表。

# Task
根据提供的 Mapping 文档、表属性、提取的 RS 测试要点以及常见测试用例，规划生成符合用例规范的测试用例列表（脑图形式）。

# Tools
你可以使用以下工具：
1. `send_msg`: 发送消息工具（用于与用户确认或发送通知）

# Context Data

## 1. Mapping 文档
### 表级 Mapping:
{table_1}

### 字段级 Mapping:
{table_2}

## 2. 表属性及变更内容
{ts_info}

## 3. 测试用例设计规范 (知识库检索结果)
{knowledge_result}

## 4. 必须包含的测试要点 (RS 文档提取)
{rs_points}

## 5. 常见测试用例示例
- IT 用例_表视图检查{{schema.table/view name}}目标表/视图及临时表存在检查
- IT 用例_表视图检查{{schema.table/view name}}验证整表有数
- IT 用例_表视图检查{{schema.table/view name}}验证表倾斜率<0.1
- IT 用例_表视图检查{{schema.table/view name}}业务主键唯一性检查
- IT 用例_表视图检查{{schema.table/view name}}目标表/视图及临时表数据一致性检查
- (更多见知识库...)

# Workflow (必须严格遵守)

## Step 1: 分析输入材料
- 阅读 Mapping 文档，理解源表和目标表的映射关系
- 分析表属性，了解表结构和变更内容
- 查看 RS 测试要点，明确必须覆盖的测试场景
- 参考知识库中的测试用例设计规范

## Step 2: 规划测试用例类别
必须包含以下类别（根据实际情况判断）：
1. **用户指定的测试要点** (必须包含)
2. **基础一致性** (非必选，根据 Mapping 复杂度判断)
3. **字段级逻辑** (非必选，根据字段转换逻辑判断)
4. **数据质量** (非必选，根据业务重要性判断)
5. **性能相关** (非必选，根据数据量判断)
6. **业务相关** (非必选，根据业务复杂度判断)

## Step 3: 生成测试用例脑图
- 使用 mermaid 格式输出脑图
- 确保测试用例不超过 20 个
- L3 级别的测试用例禁止出现模糊表达，应定义具体指标

# Constraints
1. **禁止幻觉**: 严禁产生不存在的事实，如果输入信息中无法获取主键信息，避免生成主键唯一性测试用例
2. **参考但不盲从**: 常用测试用例是以往需求的总结，并不代表当前需求适合，请结合当前需求仔细分析选择
3. **区分需求类型**: 构造测试用例时应分清楚需求是优化类还是新增类需求
4. **格式规范**: 生成的脑图必须符合 mermaid 语法

# Output Format
当你完成规划后，输出最终答案：

Final Answer
```json
{
  "mind_map": "mermaid 格式的脑图",
  "explanation": "脑图设计说明和依据"
}
```

# Mermaid 格式示例
```mermaid
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
    L3_1_2("[IT 用例][数据一致性检查] 源表目标表数据一致")
    L1_1 --> L3_1_2
```
"""


# ============================================================================
# 结果解析函数
# ============================================================================

def parse_mind_map_result(
    content: str
) -> tuple[Optional[str], str, bool, Optional[str]]:
    """
    解析脑图生成 Agent 的输出.
    
    从 Agent 输出中提取 mermaid 脑图和解释说明.
    
    Args:
        content: Agent 输出内容
    
    Returns:
        (mind_map_json, thinking, success, error)
    """
    import re
    
    # 尝试提取 JSON 块
    json_pattern = r"```json\s*(.*?)\s*```"
    matches = re.findall(json_pattern, content, re.DOTALL | re.IGNORECASE)
    
    if matches:
        try:
            result_json = json.loads(matches[-1])
            mind_map = result_json.get("mind_map", "")
            explanation = result_json.get("explanation", "")
            
            # 提取 mermaid 图
            mermaid = _extract_mermaid_from_text(mind_map)
            
            thinking = f"脑图设计说明：{explanation}"
            return mermaid, thinking, True, None
            
        except json.JSONDecodeError:
            logger.warning("无法解析 JSON 响应")
    
    # 尝试直接提取 mermaid 图
    mermaid = _extract_mermaid_from_text(content)
    if mermaid:
        return mermaid, content[:300], True, None
    
    # 返回原始内容
    return content, content[:500], False, "未能解析出结构化脑图"


def _extract_mermaid_from_text(text: str) -> str:
    """
    从文本中提取 mermaid 图表.
    
    Args:
        text: 包含 mermaid 代码的文本
    
    Returns:
        纯 mermaid 图表字符串
    """
    # 尝试提取 ```mermaid ... ``` 块
    pattern = r"```mermaid\s*(.*?)\s*```"
    matches = re.findall(pattern, text, re.DOTALL)
    if matches:
        return matches[0].strip()
    
    # 尝试提取 ``` ... ``` 块中包含 graph 的内容
    pattern = r"```\s*(graph\s*.*?)\s*```"
    matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
    if matches:
        return matches[0].strip()
    
    # 如果没有代码块，检查是否直接包含 graph 内容
    if "graph" in text.lower():
        # 尝试提取 graph 开始到结尾的内容
        graph_start = text.lower().find("graph")
        if graph_start != -1:
            return text[graph_start:].strip()
    
    return ""


# ============================================================================
# 工具创建函数
# ============================================================================

def create_send_msg_tool(messaging_tool: Any) -> Optional[BaseTool]:
    """
    从 MessagingTool 创建 LangChain 工具.
    
    Args:
        messaging_tool: MessagingTool 实例
    
    Returns:
        LangChain 工具函数
    """
    from langchain_core.tools import tool
    
    if not messaging_tool:
        return None
    
    @tool("send_msg")
    def send_msg(content: str, receiver: str) -> str:
        """
        发送消息，支持发送 welink 消息、Outlook 邮件等.
        
        Args:
            content: 要发送的消息内容
            receiver: 消息接收人工号，例如 q00797588
        
        Returns:
            发送结果
        """
        try:
            result = messaging_tool.send(
                receiver=receiver,
                content=content,
            )
            if result.success:
                return f"✅ 消息发送成功：{result.message}"
            else:
                return f"❌ 消息发送失败：{result.error}"
        except Exception as e:
            return f"❌ 异常：{str(e)}"
    
    return send_msg


# ============================================================================
# 主节点函数
# ============================================================================

def mind_map_generator_node(
    state: GraphState,
    llm: BaseChatModel,
    messaging_tool: Any = None,
    max_iterations: int = 3,
) -> GraphState:
    """
    使用 ReAct Agent 生成测试用例脑图.
    
    该节点实现了完整的 ReAct 循环：
    1. 分析输入材料（Mapping、表属性、测试要点）
    2. 可选：使用 send_msg 工具与用户交互
    3. 规划并生成 mermaid 格式的测试用例脑图
    4. 保存到 conversation state
    
    Args:
        state: 当前图状态
        llm: 语言模型
        messaging_tool: 消息发送工具
        max_iterations: 最大 ReAct 迭代次数
    
    Returns:
        更新后的状态，包含 test_case_naotu
    """
    # 收集上下文信息
    table_1 = state.get("mapping_table1", "")
    table_2 = state.get("mapping_table2", "")
    ts_info = state.get("ts_info", {})
    knowledge_result = state.get("result", "")
    rs_points = state.get("RS", "")
    w3_id = state.get("user_w3_id", "")
    
    logger.info("使用 ReAct Agent 生成测试用例脑图...")
    
    # 创建工具列表
    tools: list[BaseTool] = []
    
    if messaging_tool:
        send_msg_tool = create_send_msg_tool(messaging_tool)
        if send_msg_tool:
            tools.append(send_msg_tool)
            logger.info(f"创建了 send_msg 工具")
    
    # 构建系统提示词
    system_prompt = MIND_MAP_AGENT_PROMPT.format(
        table_1=table_1[:2000] if table_1 else "无",
        table_2=table_2[:2000] if table_2 else "无",
        ts_info=str(ts_info)[:500] if ts_info else "无",
        knowledge_result=knowledge_result[:1000] if knowledge_result else "无",
        rs_points=rs_points[:1000] if rs_points else "无",
    )
    
    # 构建输入数据
    input_data = {
        "table_1": table_1,
        "table_2": table_2,
        "ts_info": ts_info,
        "knowledge_result": knowledge_result,
        "rs_points": rs_points,
        "w3_id": w3_id,
    }
    
    # 运行 ReAct Agent
    try:
        agent_result = run_react_agent(
            input_data=input_data,
            llm=llm,
            tools=tools,
            system_prompt=system_prompt,
            max_iterations=max_iterations,
            user_message="请根据提供的 Mapping 文档、表属性和测试要点，生成测试用例脑图。",
            parse_result_fn=parse_mind_map_result,
        )
        
        # 提取结果
        mind_map = agent_result.get("final_result", "")
        agent_thinking = agent_result.get("agent_thinking", "")
        success = agent_result.get("success", False)
        error = agent_result.get("error")
        
        if not mind_map:
            logger.warning("Agent 未生成有效的脑图")
            return {
                **state,
                "llm_response": f"生成测试用例脑图失败：{error or '未知错误'}",
            }
        
        logger.info(f"脑图生成成功：{len(mind_map)} 字符")
        
        # 格式化用户确认消息
        confirmation_message = _format_user_confirmation(mind_map, agent_thinking)
        
        return {
            **state,
            "test_case_naotu": mind_map,  # 保存到 conversation state
            "llm_response": confirmation_message,
        }
        
    except Exception as e:
        logger.exception(f"脑图生成失败：{e}")
        return {
            **state,
            "llm_response": f"生成测试用例脑图失败：{str(e)}",
        }


def _format_user_confirmation(mind_map: str, thinking: str) -> str:
    """
    格式化用户确认消息.
    
    Args:
        mind_map: 生成的脑图
        thinking: Agent 的思考过程
    
    Returns:
        格式化的确认消息
    """
    return f"""
## 测试用例脑图已生成

{mind_map}

---

### 设计说明
{thinking}

---

**请问该测试用例脑图生成是否正确？**
- 如果需要修改，请直接告诉我需要调整的内容
- 如果确认无误，请回复："**确认脑图正确，生成测试用例**"
"""


# ============================================================================
# 路由函数 (用于条件边)
# ============================================================================

def mind_map_confirm_router(state: GraphState) -> str:
    """
    根据用户对脑图的确认进行路由.
    
    条件边，检查用户是确认了脑图还是请求修改.
    
    Args:
        state: 当前图状态
    
    Returns:
        下一个节点名称
    """
    query = state.get("query", "").lower()
    
    # 确认关键词
    confirm_keywords = [
        "确认", "正确", "没问题", "可以", "继续", "生成用例",
        "confirm", "correct", "yes", "continue"
    ]
    
    # 修改关键词
    modify_keywords = [
        "修改", "不对", "错误", "增加", "删除", "调整",
        "modify", "change", "wrong", "add", "remove"
    ]
    
    for keyword in confirm_keywords:
        if keyword in query:
            logger.info("用户确认了脑图，继续生成测试用例")
            return "generate_test_cases"
    
    for keyword in modify_keywords:
        logger.info("用户请求修改脑图")
        return "regenerate_mind_map"
    
    # 默认请求澄清
    logger.info("用户响应不明确，请求澄清")
    return "request_clarification"
