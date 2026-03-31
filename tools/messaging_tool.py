"""
Messaging and notification tool.

This is a stub for the Python implementation that will be merged later.
The actual implementation should send WeLink messages and/or Outlook emails.

TODO: Implement actual messaging service integration.
"""

import logging
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MessageResult:
    """Result from message sending operation."""
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None


class MessagingTool:
    """
    Tool for sending notifications via WeLink/Outlook.
    
    This is a stub implementation. The actual implementation should:
    1. Connect to WeLink API or SMTP server
    2. Format and send messages
    3. Handle delivery failures gracefully
    4. Support both WeLink instant messages and email
    
    Attributes:
        enabled: Whether notifications are enabled
        default_sender: Default sender address/account
    """
    
    def __init__(
        self,
        enabled: bool = True,
        default_sender: str = "ai4test@example.com",
    ):
        self.enabled = enabled
        self.default_sender = default_sender
    
    def send_welink(
        self,
        receiver: str,
        content: str,
        sender: Optional[str] = None
    ) -> MessageResult:
        """
        Send a WeLink instant message.
        
        This is a stub implementation. The actual implementation should:
        1. Validate receiver format (e.g., q00797588)
        2. Call WeLink API to send message
        3. Handle authentication and rate limiting
        
        Args:
            receiver: Receiver's W3 ID (e.g., q00797588)
            content: Message content
            sender: Optional sender override
            
        Returns:
            MessageResult with success status
            
        TODO: Implement actual WeLink integration.
        """
        if not self.enabled:
            logger.info("Notifications disabled, skipping WeLink send")
            return MessageResult(success=True, message_id="disabled")
        
        logger.info(f"Sending WeLink to {receiver}: {content[:50]}...")
        
        # TODO: Implement actual WeLink API call
        # Example:
        # response = requests.post(
        #     "https://api.welink.huawei.com/v1/messages",
        #     headers={"Authorization": f"Bearer {token}"},
        #     json={
        #         "receiver": receiver,
        #         "content": content,
        #         "msg_type": "text"
        #     }
        # )
        
        # Placeholder - simulate success
        return MessageResult(
            success=True,
            message_id="stub_msg_123",
        )
    
    def send_email(
        self,
        receiver: str,
        subject: str,
        content: str,
        sender: Optional[str] = None,
        html: bool = False
    ) -> MessageResult:
        """
        Send an email via Outlook/SMTP.
        
        This is a stub implementation. The actual implementation should:
        1. Connect to SMTP server
        2. Format email (plain text or HTML)
        3. Handle attachments if needed
        4. Support CC/BCC
        
        Args:
            receiver: Receiver email address
            subject: Email subject
            content: Email body content
            sender: Optional sender override
            html: Whether content is HTML
            
        Returns:
            MessageResult with success status
            
        TODO: Implement actual email integration.
        """
        if not self.enabled:
            logger.info("Notifications disabled, skipping email send")
            return MessageResult(success=True, message_id="disabled")
        
        logger.info(f"Sending email to {receiver}: {subject}")
        
        # TODO: Implement actual SMTP/email API call
        # Example:
        # import smtplib
        # from email.mime.text import MIMEText
        #
        # msg = MIMEText(content, 'html' if html else 'plain')
        # msg['Subject'] = subject
        # msg['From'] = sender or self.default_sender
        # msg['To'] = receiver
        #
        # with smtplib.SMTP(smtp_host, smtp_port) as server:
        #     server.login(smtp_user, smtp_password)
        #     server.send_message(msg)
        
        # Placeholder - simulate success
        return MessageResult(
            success=True,
            message_id="stub_email_456",
        )
    
    def send_notification(
        self,
        receiver: str,
        content: str,
        subject: Optional[str] = None,
        channel: str = "welink"
    ) -> MessageResult:
        """
        Send notification via specified channel.
        
        Convenience method that routes to appropriate channel.
        
        Args:
            receiver: Receiver ID (W3 ID or email)
            content: Message content
            subject: Optional subject (for email)
            channel: Channel type ('welink' or 'email')
            
        Returns:
            MessageResult with success status
        """
        if channel == "email":
            return self.send_email(
                receiver=receiver,
                subject=subject or "AI4Test Notification",
                content=content,
            )
        else:  # default to welink
            return self.send_welink(
                receiver=receiver,
                content=content,
            )
    
    def send_completion_notification(
        self,
        receiver: str,
        excel_content: str,
        test_case_count: int
    ) -> MessageResult:
        """
        Send task completion notification with Excel attachment info.
        
        Specialized method for notifying users when test case
        generation is complete.
        
        Args:
            receiver: Receiver's W3 ID
            excel_content: Excel file content or URL
            test_case_count: Number of test cases generated
            
        Returns:
            MessageResult with success status
        """
        subject = "测试用例生成完成"
        content = f"""
测试用例生成任务已完成！

生成测试用例数量：{test_case_count} 个

Excel 文件已生成，请联系管理员获取或访问下载链接。

---
AI 辅助测试用例生成助手
"""
        
        # For now, send via WeLink
        # TODO: Include Excel file as attachment or link
        return self.send_welink(
            receiver=receiver,
            content=content,
        )


# Convenience function for use as a LangChain tool
def send_message(
    receiver: str,
    content: str,
    channel: str = "welink"
) -> str:
    """
    Send a message to a receiver.
    
    This function can be wrapped as a LangChain tool for agent use.
    
    Args:
        receiver: Receiver's W3 ID or email
        content: Message content
        channel: Channel type ('welink' or 'email')
        
    Returns:
        Success or error message string
    """
    from config import config
    
    tool = MessagingTool(enabled=config.notification_enabled)
    
    result = tool.send_notification(
        receiver=receiver,
        content=content,
        channel=channel,
    )
    
    if result.success:
        return f"Message sent successfully to {receiver}"
    else:
        return f"Failed to send message: {result.error}"
