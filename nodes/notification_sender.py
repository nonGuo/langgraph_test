"""
Notification sender node.

Sends completion notification to user via WeLink/email.
"""

import json as json_lib
import logging
from typing import Any

from state import GraphState

logger = logging.getLogger(__name__)


def send_notification_node(
    state: GraphState,
    excel_client: Any = None,
    messaging_tool: Any = None,
    xmind_output_dir: str = "./xmind_output",
) -> GraphState:
    """
    Send task completion notification with Excel and XMind files.

    Corresponds to Dify nodes:
    - 1768658381557 (code - copy test cases)
    - 1768483862919 (HTTP request - generate Excel)
    - 1768710190090 (tool - send message)

    Args:
        state: Current graph state
        excel_client: Excel generation API client
        messaging_tool: Messaging tool for notifications
        xmind_output_dir: XMind output directory

    Returns:
        Updated state with notification status
    """
    # Get user's W3 ID
    user_w3_id = state.get("user_w3_id", "")

    if not user_w3_id:
        # Try from w3_id input
        user_w3_id = state.get("w3_id", "")

    if not user_w3_id:
        logger.warning("No user W3 ID provided, skipping notification")
        return {
            **state,
            "llm_response": state.get("llm_response", "") + "\n\n[通知发送失败：未提供 W3 账号]",
        }

    # Get test cases
    test_case_json = state.get("new_test_case", state.get("test_case", "[]"))

    try:
        test_cases = json_lib.loads(test_case_json)
        test_case_count = len(test_cases)
    except Exception:
        test_case_count = 0
        test_cases = []

    logger.info(f"Sending completion notification to {user_w3_id} for {test_case_count} test cases")

    # Generate Excel (if client provided)
    excel_result = ""
    if excel_client:
        try:
            # Use sync version for simplicity
            result = excel_client.generate_excel_sync(test_cases)
            if result.success:
                excel_result = result.file_path or result.file_url or "Excel 文件已生成"
            else:
                logger.error(f"Excel generation failed: {result.error}")
                excel_result = f"Excel 生成失败：{result.error}"
        except Exception as e:
            logger.exception("Excel generation exception")
            excel_result = f"Excel 生成异常：{str(e)}"
    else:
        excel_result = "Excel 文件已生成（模拟）"

    # Generate XMind from mind map (if available)
    xmind_result = ""
    mind_map = state.get("test_case_naotu", "")
    if mind_map:
        try:
            from mermaid_to_xmind import generate_xmind_file
            import os

            # Ensure output directory exists
            os.makedirs(xmind_output_dir, exist_ok=True)

            # Generate filename
            from datetime import datetime
            filename = f"测试用例脑图_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xmind"
            xmind_path = os.path.join(xmind_output_dir, filename)

            # Generate XMind file
            result = generate_xmind_file(mind_map, xmind_path)
            if result.get("success"):
                xmind_result = xmind_path
                logger.info(f"XMind 文件已生成：{xmind_path}, 节点数：{result.get('node_count', 0)}")
            else:
                logger.error(f"XMind generation failed: {result.get('error')}")
                xmind_result = f"脑图生成失败：{result.get('error')}"
        except Exception as e:
            logger.exception("XMind generation exception")
            xmind_result = f"脑图生成异常：{str(e)}"
    else:
        xmind_result = "未生成脑图文件"

    # Send notification (if tool provided)
    notification_sent = False
    if messaging_tool:
        try:
            content = f"""
测试用例生成任务已完成！

✅ 生成测试用例数量：{test_case_count} 个
📊 Excel 文件：{excel_result}
🧠 XMind 脑图：{xmind_result}

---
AI 辅助测试用例生成助手
"""
            result = messaging_tool.send_welink(
                receiver=user_w3_id,
                content=content,
            )

            if result.success:
                notification_sent = True
                logger.info(f"Notification sent to {user_w3_id}")
            else:
                logger.error(f"Notification failed: {result.error}")

        except Exception as e:
            logger.exception("Notification sending exception")

    # Format response
    response_message = f"""
{state.get('llm_response', '')}

### 任务完成通知

- ✅ 测试用例生成完成
- 📊 共生成 {test_case_count} 个测试用例
- 📁 Excel 文件：{excel_result}
- 🧠 XMind 脑图：{xmind_result}
- 🔔 WeLink 通知：{'已发送' if notification_sent else '未发送'}

任务已完成，请查收 WeLink 消息获取 Excel 和 XMind 文件。
"""

    return {
        **state,
        "llm_response": response_message,
        "body": excel_result,  # For compatibility with Dify DSL
        "xmind_file": xmind_result,  # XMind file path
    }


def send_chat_response_node(state: GraphState) -> GraphState:
    """
    Send response for chat/guidance branch.
    
    Handles class_type=1 and class_type=4 responses
    (chat, guidance, missing materials).
    
    Args:
        state: Current graph state
        
    Returns:
        Updated state with response message
    """
    class_reason = state.get("class_reason", "")
    llm_response = state.get("llm_response", "")
    
    # Build guidance message
    if "缺少" in class_reason or "缺失" in class_reason:
        response = f"""
{llm_response}

为了为您生成测试用例，我还需要您补充以下材料：

📄 **Mapping 文档**: 描述表与表之间的数据映射关系
📄 **RS 文档** (可选): 需求规格说明书，包含测试要点
📄 **TS 文档**: 技术规格说明书，包含表结构设计

请上传缺失的文档后，我们再开始生成测试用例。
"""
    else:
        response = llm_response
    
    return {
        **state,
        "llm_response": response,
    }
