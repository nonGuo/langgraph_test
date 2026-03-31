"""
LangChain tool wrappers for ReAct Agent.

This module provides LangChain @tool decorators for DatabaseTool and KnowledgeTool,
making them compatible with LangChain's agent framework.
"""

import json
import logging
from typing import Any, Optional

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def create_database_tool(db_tool_instance: Any):
    """
    Create a LangChain tool from DatabaseTool instance.

    Args:
        db_tool_instance: DatabaseTool instance

    Returns:
        LangChain tool function
    """

    @tool("database_query_with_sql")
    def database_query_with_sql(query_sql: str) -> str:
        """
        访问数据库执行 GAUSS SQL。

        根据提供的 SQL，到数据库执行并返回查询结果。
        只允许执行 SELECT 查询，会自动添加 LIMIT 限制。

        Args:
            query_sql: 要执行的 SQL 查询语句

        Returns:
            查询结果字符串，包含执行状态和数据
        """
        if not db_tool_instance:
            return "Error: 数据库工具未初始化"

        try:
            result = db_tool_instance.execute_query(query_sql)

            if result.success:
                # 格式化输出
                output_lines = [
                    f"✅ 执行成功",
                    f"返回行数：{result.row_count}",
                ]

                if result.data:
                    # 限制输出行数，避免 token 过多
                    display_data = result.data[:50]
                    output_lines.append("\n数据预览 (最多 50 行):")
                    output_lines.append(json.dumps(display_data, ensure_ascii=False, indent=2))

                    if result.row_count > 50:
                        output_lines.append(f"\n... 还有 {result.row_count - 50} 行未显示")

                return "\n".join(output_lines)
            else:
                return f"❌ 执行失败：{result.error}"

        except Exception as e:
            logger.exception("Query execution failed")
            return f"❌ 异常：{str(e)}"

    return database_query_with_sql


def create_knowledge_tool(knowledge_tool_instance: Any):
    """
    Create a LangChain tool from KnowledgeTool instance.

    Args:
        knowledge_tool_instance: KnowledgeTool instance

    Returns:
        LangChain tool function
    """

    @tool("query_knowledge_base")
    def query_knowledge_base(
        test_case_name: str,
        search_query: Optional[str] = None
    ) -> str:
        """
        从知识库检索测试用例 SQL 范例。

        根据测试用例名称或自定义查询词，从知识库检索相似的历史测试用例和 SQL 范例。
        用于指导当前测试用例的 SQL 编写。

        Args:
            test_case_name: 测试用例名称（主要检索关键词）
            search_query: 可选的自定义查询词，如果提供则优先使用

        Returns:
            检索到的 SQL 范例和业务逻辑说明
        """
        if not knowledge_tool_instance:
            return "Error: 知识库工具未初始化"

        try:
            # 优先使用自定义查询词
            query = search_query or test_case_name

            logger.info(f"检索知识库：test_case={test_case_name[:50]}...")

            result = knowledge_tool_instance.search(
                query=query,
                test_case_name=test_case_name
            )

            if result.success:
                output_lines = [
                    f"✅ 检索成功",
                    f"相关文档：{len(result.source_documents) if result.source_documents else 1} 篇",
                    f"相关度分数：{result.score:.2f}",
                    "\n检索到的 SQL 范例:",
                    result.content
                ]
                return "\n".join(output_lines)
            else:
                return f"❌ 检索失败：{result.error}"

        except Exception as e:
            logger.exception("Knowledge retrieval failed")
            return f"❌ 异常：{str(e)}"

    return query_knowledge_base


def create_query_tables_tool(db_tool_instance: Any):
    """
    Create a tool for querying available tables.

    Args:
        db_tool_instance: DatabaseTool instance

    Returns:
        LangChain tool function
    """

    @tool("query_tables")
    def query_tables(schema: str = "public") -> str:
        """
        查询数据库中的表列表。

        当不确定有哪些表可用时使用此工具。

        Args:
            schema: Schema 名称，默认为 public

        Returns:
            表名列表
        """
        if not db_tool_instance:
            return "Error: 数据库工具未初始化"

        try:
            tables = db_tool_instance.query_tables(schema=schema)

            if tables:
                return f"✅ Schema '{schema}' 中的表 ({len(tables)} 个):\n" + "\n".join(tables)
            else:
                return f"⚠️ Schema '{schema}' 中没有找到表"

        except Exception as e:
            logger.exception("Query tables failed")
            return f"❌ 异常：{str(e)}"

    return query_tables


def create_query_columns_tool(db_tool_instance: Any):
    """
    Create a tool for querying column information.

    Args:
        db_tool_instance: DatabaseTool instance

    Returns:
        LangChain tool function
    """

    @tool("query_columns")
    def query_columns(table_name: str, schema: str = "public") -> str:
        """
        查询指定表的列信息。

        当需要确认表的列名、数据类型等信息时使用此工具。

        Args:
            table_name: 表名
            schema: Schema 名称，默认为 public

        Returns:
            列信息（列名、数据类型、是否可为空等）
        """
        if not db_tool_instance:
            return "Error: 数据库工具未初始化"

        try:
            columns = db_tool_instance.query_columns(
                table_name=table_name,
                schema=schema
            )

            if columns:
                output_lines = [f"✅ 表 '{schema}.{table_name}' 的列信息 ({len(columns)} 列):"]

                for col in columns:
                    nullable = "NULL" if col.get("is_nullable") == "YES" else "NOT NULL"
                    output_lines.append(
                        f"  - {col['column_name']}: {col['data_type']} ({nullable})"
                    )

                return "\n".join(output_lines)
            else:
                return f"⚠️ 表 '{schema}.{table_name}' 没有找到列信息（表可能不存在）"

        except Exception as e:
            logger.exception("Query columns failed")
            return f"❌ 异常：{str(e)}"

    return query_columns


def create_agent_tools(
    db_tool: Any = None,
    knowledge_tool: Any = None
) -> list:
    """
    Create all available tools for the ReAct Agent.

    Args:
        db_tool: DatabaseTool instance
        knowledge_tool: KnowledgeTool instance

    Returns:
        List of LangChain tools
    """
    tools = []

    # Database query tool (核心工具)
    if db_tool:
        tools.append(create_database_tool(db_tool))
        tools.append(create_query_tables_tool(db_tool))
        tools.append(create_query_columns_tool(db_tool))
        logger.info(f"Created {3} database tools")

    # Knowledge retrieval tool
    if knowledge_tool:
        tools.append(create_knowledge_tool(knowledge_tool))
        logger.info("Created knowledge tool")

    logger.info(f"Total tools created: {len(tools)}")

    return tools
