"""
测试用例生成节点 - 使用 ReAct Agent 模式.

对应 Dify 节点:
- 1768539572937 (Agent - 生成测试用例)
- 1768539764964 (assigner - 保存测试用例)
- 1768539771147 (answer - 与用户确认)
- 1768555668465 (code - 格式化为 Markdown)

该节点使用 ReAct Agent 模式将确认后的测试用例脑图
转换为结构化的 JSON 数据，用于生成最终 Excel。

ReAct 循环：
1. 分析测试用例脑图（mermaid 格式）
2. 提取每个测试用例的详细信息
3. 判断是否需要生成 SQL
4. 输出结构化 JSON 列表
"""

import json
import logging
import re
from typing import Any, Optional

from langchain_core.language_models import BaseChatModel

from state import GraphState, TestCaseItem
from agents.base_react_agent import run_react_agent

logger = logging.getLogger(__name__)


# ============================================================================
# 系统提示词
# ============================================================================

TEST_CASE_AGENT_PROMPT = """
# Role
你是一名自动化测试脚本编写专家，擅长将测试脑图转换为结构化的测试用例 JSON。

# Task
将用户确认的测试计划（脑图）转换为结构化的 JSON 数据，用于生成最终 Excel。

# Input Data

## 测试用例脑图 (用户已确认)
{mind_map}

## 用户额外要求 (如果有)
{user_query}

# Instructions

## Step 1: 解析脑图
- 分析 mermaid 格式的脑图结构
- 提取每个 L3 级别的测试用例
- 理解每个测试用例的类别和预期结果

## Step 2: 填充测试用例字段
对每个测试用例，填充以下字段：

1. **case_name**: 测试用例名称（从脑图节点提取）
2. **level**: 测试等级 (level1-level4)
   - level1: 核心业务逻辑，关键路径测试
   - level2: 重要业务逻辑，边界条件测试
   - level3: 一般功能测试
   - level4: 辅助功能测试
3. **pre_condition**: 测试前置条件
   - 例如："源表任务已完成，目标表任务已完成"
4. **need_generate_sql**: 是否需要生成 SQL 进行数据库自动化验证
   - **true**: 可以通过 SQL 直接验证的测试用例
   - **false**: 需要人工介入测试的场景，例如：
     - 验证变更前后数据内容一致性（数据库只有一种状态，无法直接对比）
     - 验证查询耗时（需要人工计时）
     - 其他无法通过 SQL 直接得到验证结果的场景
5. **eval_step_descri**: 测试步骤流程描述（对下一步生成 SQL 有指导作用）
6. **expected_result**: 预期测试结果
7. **tags**: 测试用例标签/分类
   - 例如："IT 用例_表视图/业务用例/配置调度配置"

## Step 3: 判断 need_generate_sql
请根据以下规则判断：

### 应该设置为 false 的场景：
- "验证变更前后数据内容一致性" - 需要人工对比
- "验证查询耗时" - 需要人工计时
- "验证数据完整性" - 需要人工检查多个系统
- "验证业务流程正确性" - 需要人工执行完整流程
- 其他需要人工判断、对比、计时的场景

### 应该设置为 true 的场景：
- "目标表存在检查" - 可以 SELECT COUNT(*) 验证
- "主键唯一性检查" - 可以 GROUP BY + HAVING 验证
- "数据一致性检查" - 可以 JOIN 对比源表和目标表
- "字段值范围检查" - 可以 WHERE + CASE WHEN 验证
- 其他可以通过 SQL 直接得到 PASS/FAIL 结果的场景

# Constraints
1. **禁止幻觉**: 不要虚构脑图中不存在的测试用例
2. **等级合理**: 核心业务逻辑测试应为 level1
3. **SQL 判断准确**: 仔细分析每个测试用例是否真的可以通过 SQL 验证
4. **数量限制**: 测试用例总数不超过 20 个

# Output Format
当你完成转换后，输出最终答案：

Final Answer
```json
[
  {{
    "case_name": "目标表主键不重复校验",
    "level": "level1",
    "pre_condition": "源表任务已完成，目标表任务已完成",
    "need_generate_sql": true,
    "eval_step_descri": "查询目标表，按主键分组，统计每组数量",
    "expected_result": "查询结果为空，无重复主键",
    "tags": "IT 用例_表视图/业务用例/配置调度配置"
  }},
  ...
]
```

# Example Output
```json
[
  {{
    "case_name": "[IT 用例][表视图检查]dwb_ltc_invoice_head_i 目标表存在检查",
    "level": "level1",
    "pre_condition": "调度系统已配置目标表任务",
    "need_generate_sql": true,
    "eval_step_descri": "查询系统表，验证目标表是否存在",
    "expected_result": "表存在，返回记录数>0",
    "tags": "IT 用例_表视图/基础检查"
  }},
  {{
    "case_name": "[IT 用例][数据一致性] 源表目标表数据条数一致",
    "level": "level2",
    "pre_condition": "源表和目标表数据已同步完成",
    "need_generate_sql": true,
    "eval_step_descri": "分别统计源表和目标表的记录数，对比是否一致",
    "expected_result": "源表记录数 = 目标表记录数",
    "tags": "IT 用例_表视图/数据一致性"
  }},
  {{
    "case_name": "[IT 用例][性能测试] 查询耗时检查",
    "level": "level3",
    "pre_condition": "表数据已加载完成",
    "need_generate_sql": false,
    "eval_step_descri": "执行典型查询，记录查询耗时",
    "expected_result": "查询耗时<5 秒",
    "tags": "IT 用例_表视图/性能测试"
  }}
]
```
"""


# ============================================================================
# 结果解析函数
# ============================================================================

def parse_test_cases_result(
    content: str
) -> tuple[Optional[str], str, bool, Optional[str]]:
    """
    解析测试用例生成 Agent 的输出.
    
    从 Agent 输出中提取测试用例 JSON 列表.
    
    Args:
        content: Agent 输出内容
    
    Returns:
        (test_cases_json, thinking, success, error)
    """
    # 尝试提取 JSON 块
    import re
    
    json_pattern = r"```json\s*(.*?)\s*```"
    matches = re.findall(json_pattern, content, re.DOTALL | re.IGNORECASE)
    
    if matches:
        try:
            test_cases = json.loads(matches[-1])
            
            # 验证是否为列表
            if isinstance(test_cases, list):
                thinking = f"成功解析 {len(test_cases)} 个测试用例"
                return json.dumps(test_cases, ensure_ascii=False), thinking, True, None
            else:
                logger.warning("解析结果不是列表格式")
        except json.JSONDecodeError:
            logger.warning("无法解析 JSON 响应")
    
    # 尝试提取数组模式
    array_pattern = r'\[\s*\{.*?\}\s*\]'
    array_matches = re.findall(array_pattern, content, re.DOTALL)
    if array_matches:
        try:
            test_cases = json.loads(array_matches[-1])
            thinking = f"成功解析 {len(test_cases)} 个测试用例"
            return json.dumps(test_cases, ensure_ascii=False), thinking, True, None
        except json.JSONDecodeError:
            pass
    
    # 返回错误
    return None, content[:300], False, "未能解析出测试用例 JSON 列表"


# ============================================================================
# 主节点函数
# ============================================================================

def test_case_generator_node(
    state: GraphState,
    llm: BaseChatModel,
    max_iterations: int = 3,
) -> GraphState:
    """
    使用 ReAct Agent 生成结构化测试用例.
    
    该节点实现了完整的 ReAct 循环：
    1. 分析用户确认的测试用例脑图
    2. 提取每个测试用例的详细信息
    3. 判断是否需要生成 SQL
    4. 输出结构化 JSON 列表
    
    Args:
        state: 当前图状态
        llm: 语言模型
        max_iterations: 最大 ReAct 迭代次数
    
    Returns:
        更新后的状态，包含 test_case JSON 和 md_output
    """
    # 收集上下文信息
    mind_map = state.get("test_case_naotu", "")
    query = state.get("query", "")
    
    logger.info("使用 ReAct Agent 生成结构化测试用例...")
    
    # 构建系统提示词
    system_prompt = TEST_CASE_AGENT_PROMPT.format(
        mind_map=mind_map[:3000] if mind_map else "无",
        user_query=query if query and "生成用例" in query else "无",
    )
    
    # 构建输入数据
    input_data = {
        "mind_map": mind_map,
        "user_query": query,
    }
    
    # 运行 ReAct Agent（无外部工具，纯推理）
    try:
        agent_result = run_react_agent(
            input_data=input_data,
            llm=llm,
            tools=[],  # 不需要外部工具
            system_prompt=system_prompt,
            max_iterations=max_iterations,
            user_message="请将确认的测试用例脑图转换为结构化的 JSON 测试用例列表。",
            parse_result_fn=parse_test_cases_result,
        )
        
        # 提取结果
        test_cases_json = agent_result.get("final_result", "")
        agent_thinking = agent_result.get("agent_thinking", "")
        success = agent_result.get("success", False)
        error = agent_result.get("error")
        
        if not test_cases_json:
            logger.warning("Agent 未生成有效的测试用例")
            return {
                **state,
                "llm_response": f"生成测试用例失败：{error or '未知错误'}",
            }
        
        # 解析 JSON 用于格式化
        try:
            test_cases = json.loads(test_cases_json)
        except json.JSONDecodeError:
            logger.error("无法解析生成的测试用例 JSON")
            return {
                **state,
                "llm_response": f"测试用例格式错误：无法解析 JSON",
            }
        
        logger.info(f"测试用例生成成功：{len(test_cases)} 个用例")
        
        # 格式化为 Markdown 表格
        md_output = _format_test_cases_markdown(test_cases)
        
        # 生成确认消息
        confirmation_message = _format_confirmation_message(md_output, len(test_cases), agent_thinking)
        
        return {
            **state,
            "test_case": test_cases_json,  # 保存到 conversation state
            "md_output": md_output,  # 用于显示
            "llm_response": confirmation_message,
        }
        
    except Exception as e:
        logger.exception(f"测试用例生成失败：{e}")
        return {
            **state,
            "llm_response": f"生成测试用例失败：{str(e)}",
        }


def _format_test_cases_markdown(test_cases: list[dict[str, Any]]) -> str:
    """
    将测试用例格式化为 Markdown 表格.
    
    对应 Dify 节点 1768555668465 的功能.
    
    Args:
        test_cases: 测试用例列表
    
    Returns:
        Markdown 表格字符串
    """
    if not test_cases:
        return "暂无数据"
    
    # 获取表头
    headers = list(test_cases[0].keys())
    
    # 构建 Markdown 表格
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


def _format_confirmation_message(
    md_output: str,
    count: int,
    thinking: str,
) -> str:
    """
    格式化用户确认消息.
    
    Args:
        md_output: Markdown 格式的测试用例
        count: 测试用例数量
        thinking: Agent 的思考过程
    
    Returns:
        格式化的确认消息
    """
    return f"""
### 测试用例已生成

共生成 **{count}** 个测试用例：

{md_output}

---

### 生成说明
{thinking}

---

**当前测试用例生成已完成**，正在为您链接数据库生成每个测试用例对应的 SQL。

> ⏱️ 该过程耗时较长，您可暂时离开，任务完成后将会通过 welink 发送消息推送给您。
> 
> 📬 请确认输入参数中的 `w3_id` 已正确填写您的 w3 账号。
"""


# ============================================================================
# 辅助函数
# ============================================================================

def extract_test_case_fields(test_case: dict[str, Any]) -> TestCaseItem:
    """
    从字典提取测试用例字段.
    
    Args:
        test_case: 测试用例字典
    
    Returns:
        TestCaseItem 对象
    """
    return {
        "case_name": test_case.get("case_name", ""),
        "level": test_case.get("level", "level3"),
        "pre_condition": test_case.get("pre_condition", ""),
        "need_generate_sql": test_case.get("need_generate_sql", True),
        "eval_step_descri": test_case.get("eval_step_descri", ""),
        "expected_result": test_case.get("expected_result", ""),
        "tags": test_case.get("tags", ""),
        "agent_thinking": None,
        "db_excute_result": None,
    }
