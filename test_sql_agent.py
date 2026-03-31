"""
Tests for SQL Agent ReAct strategy.

Run with: python -m pytest test_sql_agent.py -v
Or: python test_sql_agent.py

This test suite covers:
1. Agent subgraph state and flow
2. Agent planner node
3. Tools executor node
4. Final answer extraction
5. Full ReAct loop integration
6. SQL generator node integration
"""

import json
import os
import unittest
from unittest.mock import Mock, MagicMock, patch

from langchain_core.messages import (
    SystemMessage,
    HumanMessage,
    AIMessage,
    ToolMessage,
)

from agents.sql_agent import (
    run_sql_agent_for_test_case,
    SQL_AGENT_SYSTEM_PROMPT,
    parse_sql_from_result,
)

from agents.base_react_agent import (
    ReActAgentState,
    should_continue,
    run_react_agent,
    create_react_agent_subgraph,
    create_agent_planner_node,
    create_tools_executor_node,
    create_final_answer_extractor,
)

from tools.agent_tools import (
    create_database_tool,
    create_knowledge_tool,
    create_agent_tools,
)


class TestAgentSubgraphState(unittest.TestCase):
    """Test agent subgraph state structure."""

    def test_state_initialization(self):
        """Test agent subgraph state can be initialized."""
        state = {
            "test_case": {"case_name": "Test Case 1"},
            "context": {"ddl": "CREATE TABLE test..."},
            "max_iterations": 5,
            "messages": [],
            "iteration_count": 0,
            "final_result": None,
            "agent_thinking": None,
            "success": False,
            "error": None,
        }
        self.assertEqual(state["iteration_count"], 0)
        self.assertEqual(state["max_iterations"], 5)


class TestAgentPlannerNode(unittest.TestCase):
    """Test agent planner node functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_llm = Mock()
        self.mock_tools = [
            Mock(name="database_query_with_sql"),
            Mock(name="query_knowledge_base"),
        ]

    def test_planner_node_basic(self):
        """Test planner node with basic input."""
        # Mock LLM response
        mock_response = AIMessage(
            content="I need to query the database",
            tool_calls=[
                {
                    "name": "database_query_with_sql",
                    "args": {"query_sql": "SELECT 1"},
                    "id": "call_1",
                }
            ],
        )
        self.mock_llm.bind_tools.return_value.invoke.return_value = mock_response

        state = {
            "input_data": {"case_name": "Test"},
            "max_iterations": 5,
            "system_prompt": "You are a SQL expert",
            "messages": [HumanMessage(content="Generate SQL")],
            "iteration_count": 0,
            "final_result": None,
            "agent_thinking": None,
            "success": False,
            "error": None,
        }

        planner_node = create_agent_planner_node(self.mock_llm, self.mock_tools, 5)
        result = planner_node(state)

        # Verify iteration count increased
        self.assertEqual(result["iteration_count"], 1)
        # Verify messages were updated
        self.assertEqual(len(result["messages"]), 1)
        self.assertIsInstance(result["messages"][0], AIMessage)

    def test_planner_node_respects_max_iterations(self):
        """Test planner node respects max iterations limit."""
        state = {
            "input_data": {"case_name": "Test"},
            "max_iterations": 3,
            "system_prompt": "You are a SQL expert",
            "messages": [],
            "iteration_count": 3,  # Already at limit
            "final_result": None,
            "agent_thinking": None,
            "success": False,
            "error": None,
        }

        planner_node = create_agent_planner_node(self.mock_llm, self.mock_tools, 3)
        result = planner_node(state)

        # Should signal max iterations reached
        self.assertFalse(result["success"])
        self.assertIn("达到最大迭代次数", result["messages"][0].content)


class TestToolsExecutorNode(unittest.TestCase):
    """Test tools executor node functionality."""

    def test_executor_with_tool_calls(self):
        """Test executor processes tool calls correctly."""
        # Mock tool
        mock_tool = Mock()
        mock_tool.name = "database_query_with_sql"
        mock_tool.invoke.return_value = "✅ 执行成功\n返回行数：1"

        tools_by_name = {"database_query_with_sql": mock_tool}

        state = {
            "input_data": {},
            "max_iterations": 5,
            "system_prompt": "You are a SQL expert",
            "messages": [
                AIMessage(
                    content="Executing query",
                    tool_calls=[
                        {
                            "name": "database_query_with_sql",
                            "args": {"query_sql": "SELECT 1"},
                            "id": "call_1",
                        }
                    ],
                )
            ],
            "iteration_count": 1,
            "final_result": None,
            "agent_thinking": None,
            "success": False,
            "error": None,
        }

        executor_node = create_tools_executor_node(tools_by_name)
        result = executor_node(state)

        # Verify tool was called
        mock_tool.invoke.assert_called_once_with({"query_sql": "SELECT 1"})
        # Verify ToolMessage was added
        self.assertEqual(len(result["messages"]), 1)
        self.assertIsInstance(result["messages"][0], ToolMessage)
        self.assertEqual(result["messages"][0].content, "✅ 执行成功\n返回行数：1")

    def test_executor_with_unknown_tool(self):
        """Test executor handles unknown tools gracefully."""
        tools_by_name = {"database_query_with_sql": Mock()}

        state = {
            "input_data": {},
            "max_iterations": 5,
            "system_prompt": "You are a SQL expert",
            "messages": [
                AIMessage(
                    content="Calling unknown tool",
                    tool_calls=[
                        {
                            "name": "unknown_tool",
                            "args": {},
                            "id": "call_1",
                        }
                    ],
                )
            ],
            "iteration_count": 1,
            "final_result": None,
            "agent_thinking": None,
            "success": False,
            "error": None,
        }

        executor_node = create_tools_executor_node(tools_by_name)
        result = executor_node(state)

        # Should return error message
        self.assertIn("未知工具", result["messages"][0].content)

    def test_executor_with_empty_messages(self):
        """Test executor handles empty messages."""
        state = {
            "input_data": {},
            "max_iterations": 5,
            "system_prompt": "You are a SQL expert",
            "messages": [],
            "iteration_count": 0,
            "final_result": None,
            "agent_thinking": None,
            "success": False,
            "error": None,
        }

        executor_node = create_tools_executor_node({"tool": Mock()})
        result = executor_node(state)

        # Should return state unchanged
        self.assertEqual(result["messages"], [])


class TestExtractFinalAnswer(unittest.TestCase):
    """Test final answer extraction."""

    def test_extract_json_final_answer(self):
        """Test extraction of JSON formatted final answer."""
        state = {
            "input_data": {},
            "max_iterations": 5,
            "system_prompt": "You are a SQL expert",
            "messages": [
                AIMessage(
                    content="""
Final Answer
```json
{
  "sql": "SELECT COUNT(*) FROM users",
  "passed": true,
  "result_data": "100 rows",
  "thinking": "I analyzed the test case and created this SQL"
}
```
"""
                )
            ],
            "iteration_count": 2,
            "final_result": None,
            "agent_thinking": None,
            "success": False,
            "error": None,
        }

        extractor = create_final_answer_extractor()
        result = extractor(state)

        self.assertTrue(result["success"])
        self.assertIsNotNone(result["final_result"])
        self.assertIn("SELECT COUNT", result["final_result"])

    def test_extract_sql_regex_fallback(self):
        """Test SQL extraction using regex when JSON parsing fails."""
        state = {
            "input_data": {},
            "max_iterations": 5,
            "system_prompt": "You are a SQL expert",
            "messages": [
                AIMessage(
                    content='The SQL is: {"sql": "SELECT * FROM test"} based on my analysis'
                )
            ],
            "iteration_count": 1,
            "final_result": None,
            "agent_thinking": None,
            "success": False,
            "error": None,
        }

        extractor = create_final_answer_extractor()
        result = extractor(state)

        # JSON parsing succeeded (it found the JSON object)
        self.assertTrue(result["success"])
        self.assertIn("SELECT * FROM test", result["final_result"])

    def test_extract_no_answer(self):
        """Test handling of missing AI response."""
        state = {
            "input_data": {},
            "max_iterations": 5,
            "system_prompt": "You are a SQL expert",
            "messages": [],
            "iteration_count": 0,
            "final_result": None,
            "agent_thinking": None,
            "success": False,
            "error": None,
        }

        extractor = create_final_answer_extractor()
        result = extractor(state)

        self.assertFalse(result["success"])
        self.assertIn("无输出", result["agent_thinking"])


class TestShouldContinue(unittest.TestCase):
    """Test conditional edge logic for ReAct loop."""

    def test_continue_with_tool_calls(self):
        """Test loop continues when agent has tool calls."""
        state = {
            "messages": [
                AIMessage(
                    content="I need to query",
                    tool_calls=[
                        {
                            "name": "database_query_with_sql",
                            "args": {"query_sql": "SELECT 1"},
                            "id": "call_1",
                        }
                    ],
                )
            ]
        }

        result = should_continue(state)
        self.assertEqual(result, "continue")

    def test_end_with_final_answer(self):
        """Test loop ends with Final Answer."""
        state = {
            "messages": [
                AIMessage(content="Final Answer: The SQL is SELECT 1")
            ]
        }

        result = should_continue(state)
        self.assertEqual(result, "end")

    def test_end_with_no_tool_calls(self):
        """Test loop ends when agent has no tool calls."""
        state = {
            "messages": [
                AIMessage(content="I'm done analyzing")
            ]
        }

        result = should_continue(state)
        self.assertEqual(result, "end")

    def test_continue_after_tool_execution(self):
        """Test loop continues after tool execution."""
        state = {
            "messages": [
                ToolMessage(
                    content="Query result: 100 rows",
                    tool_call_id="call_1",
                    name="database_query_with_sql",
                )
            ]
        }

        result = should_continue(state)
        # After tool execution, agent needs to reason about results
        self.assertEqual(result, "continue")


class TestCreateReActAgentSubgraph(unittest.TestCase):
    """Test ReAct agent subgraph creation."""

    def test_subgraph_creation(self):
        """Test subgraph is created with correct structure."""
        mock_llm = Mock()
        mock_tools = [Mock(name="tool1"), Mock(name="tool2")]

        graph = create_react_agent_subgraph(
            name="TestAgent",
            llm=mock_llm,
            tools=mock_tools,
            system_prompt="You are a test agent",
            max_iterations=5,
        )

        # Verify graph was created
        self.assertIsNotNone(graph)

    def test_subgraph_with_no_tools(self):
        """Test subgraph creation with empty tools list."""
        mock_llm = Mock()

        graph = create_react_agent_subgraph(
            name="TestAgent",
            llm=mock_llm,
            tools=[],
            system_prompt="You are a test agent",
            max_iterations=3,
        )

        self.assertIsNotNone(graph)


class TestRunSqlAgentForTestCase(unittest.TestCase):
    """Test main entry point for SQL agent."""

    def test_run_with_basic_test_case(self):
        """Test running agent with basic test case."""
        mock_llm = Mock()
        mock_tools = [Mock(name="database_query_with_sql")]

        test_case = {
            "case_name": "Verify user count",
            "eval_step_descri": "Check total users",
            "expected_result": "PASS",
        }

        context = {
            "ddl": "CREATE TABLE users (id INT, name VARCHAR)",
            "table_mapping": "",
            "col_mapping": "",
        }

        # Mock the subgraph execution
        with patch(
            "agents.base_react_agent.create_react_agent_subgraph"
        ) as mock_create:
            mock_graph = Mock()
            mock_graph.invoke.return_value = {
                "final_result": '{"sql": "SELECT 1"}',
                "agent_thinking": "Analyzed test case",
                "success": True,
                "error": None,
                "iteration_count": 2,
            }
            mock_create.return_value = mock_graph

            result = run_sql_agent_for_test_case(
                test_case=test_case,
                context=context,
                llm=mock_llm,
                tools=mock_tools,
                max_iterations=5,
            )

            # Verify result structure
            self.assertIn("sql_result", result)
            self.assertIn("agent_thinking", result)
            self.assertIn("success", result)
            self.assertTrue(result["success"])

    def test_run_with_exception(self):
        """Test error handling when agent fails."""
        mock_llm = Mock()
        mock_tools = []

        with patch(
            "agents.base_react_agent.run_react_agent"
        ) as mock_run:
            mock_run.return_value = {
                "final_result": None,
                "agent_thinking": "Agent 执行失败：Exception",
                "success": False,
                "error": "Agent failed",
                "iteration_count": 0,
            }

            result = run_sql_agent_for_test_case(
                test_case={},
                context={},
                llm=mock_llm,
                tools=mock_tools,
                max_iterations=5,
            )

            # Should return error state
            self.assertFalse(result["success"])
            self.assertIn("Agent 执行失败", result["agent_thinking"])


class TestCreateAgentTools(unittest.TestCase):
    """Test agent tool creation."""

    def test_create_database_tools(self):
        """Test database tool creation."""
        mock_db_tool = Mock()

        tools = create_agent_tools(db_tool=mock_db_tool, knowledge_tool=None)

        # Should create 3 database tools
        self.assertEqual(len(tools), 3)
        tool_names = [tool.name for tool in tools]
        self.assertIn("database_query_with_sql", tool_names)
        self.assertIn("query_tables", tool_names)
        self.assertIn("query_columns", tool_names)

    def test_create_knowledge_tool(self):
        """Test knowledge tool creation."""
        mock_knowledge_tool = Mock()

        tools = create_agent_tools(db_tool=None, knowledge_tool=mock_knowledge_tool)

        # Should create 1 knowledge tool
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0].name, "query_knowledge_base")

    def test_create_all_tools(self):
        """Test creating all tools."""
        mock_db_tool = Mock()
        mock_knowledge_tool = Mock()

        tools = create_agent_tools(
            db_tool=mock_db_tool, knowledge_tool=mock_knowledge_tool
        )

        # Should create 4 tools total
        self.assertEqual(len(tools), 4)


class TestAgentToolsIntegration(unittest.TestCase):
    """Integration tests for agent tools."""

    def test_database_tool_wrapper(self):
        """Test database tool wrapper."""
        mock_db_tool = Mock()
        mock_db_tool.execute_query.return_value = Mock(
            success=True,
            data=[{"id": 1, "name": "test"}],
            row_count=1,
            error=None,
        )

        tool = create_database_tool(mock_db_tool)

        result = tool.invoke({"query_sql": "SELECT * FROM users"})

        # Verify tool was called
        mock_db_tool.execute_query.assert_called_once_with("SELECT * FROM users")
        # Verify result format
        self.assertIn("✅ 执行成功", result)

    def test_database_tool_error_handling(self):
        """Test database tool error handling."""
        mock_db_tool = Mock()
        mock_db_tool.execute_query.return_value = Mock(
            success=False,
            data=None,
            row_count=0,
            error="Connection failed",
        )

        tool = create_database_tool(mock_db_tool)

        result = tool.invoke({"query_sql": "INVALID SQL"})

        self.assertIn("❌ 执行失败", result)
        self.assertIn("Connection failed", result)

    def test_knowledge_tool_wrapper(self):
        """Test knowledge tool wrapper."""
        mock_knowledge_tool = Mock()
        mock_knowledge_tool.search.return_value = Mock(
            success=True,
            content="SELECT example FROM test",
            score=0.95,
            source_documents=[{"id": 1}],
            error=None,
        )

        tool = create_knowledge_tool(mock_knowledge_tool)

        result = tool.invoke(
            {"test_case_name": "User validation", "search_query": "validation SQL"}
        )

        # Verify tool was called
        mock_knowledge_tool.search.assert_called_once()
        # Verify result format
        self.assertIn("✅ 检索成功", result)
        self.assertIn("SELECT example", result)


class TestSQLAgentSystemPrompt(unittest.TestCase):
    """Test SQL agent system prompt."""

    def test_prompt_formatting(self):
        """Test system prompt can be formatted correctly."""
        formatted = SQL_AGENT_SYSTEM_PROMPT.format(
            max_iterations=5,
            ddl="CREATE TABLE test...",
            table_mapping="table1 -> table2",
            col_mapping="col1 -> col2",
            test_case_json='{"case_name": "Test"}',
        )

        # Verify all placeholders were replaced
        self.assertNotIn("{max_iterations}", formatted)
        self.assertNotIn("{ddl}", formatted)
        self.assertIn("CREATE TABLE test", formatted)
        self.assertIn("5", formatted)

    def test_prompt_contains_tools(self):
        """Test system prompt mentions all tools."""
        self.assertIn("database_query_with_sql", SQL_AGENT_SYSTEM_PROMPT)
        self.assertIn("query_knowledge_base", SQL_AGENT_SYSTEM_PROMPT)
        self.assertIn("query_tables", SQL_AGENT_SYSTEM_PROMPT)
        self.assertIn("query_columns", SQL_AGENT_SYSTEM_PROMPT)

    def test_prompt_contains_workflow(self):
        """Test system prompt contains workflow instructions."""
        self.assertIn("Step 1", SQL_AGENT_SYSTEM_PROMPT)
        self.assertIn("Step 2", SQL_AGENT_SYSTEM_PROMPT)
        self.assertIn("Step 3", SQL_AGENT_SYSTEM_PROMPT)
        self.assertIn("Step 4", SQL_AGENT_SYSTEM_PROMPT)
        self.assertIn("Step 5", SQL_AGENT_SYSTEM_PROMPT)


class TestReActLoopIntegration(unittest.TestCase):
    """Integration tests for full ReAct loop."""

    def test_full_react_loop_simulation(self):
        """Simulate a full ReAct loop with mocked LLM."""
        # Create mock LLM that simulates a complete ReAct conversation
        mock_llm = Mock()

        # Simulate: Plan -> Tool call -> Observe -> Final answer
        responses = [
            AIMessage(
                content="I'll query the database",
                tool_calls=[
                    {
                        "name": "database_query_with_sql",
                        "args": {"query_sql": "SELECT COUNT(*) FROM users"},
                        "id": "call_1",
                    }
                ],
            ),
            AIMessage(
                content="""
Final Answer
```json
{
  "sql": "SELECT COUNT(*) FROM users",
  "passed": true,
  "result_data": "100 rows",
  "thinking": "Query executed successfully"
}
```
"""
            ),
        ]

        mock_llm.bind_tools.return_value.invoke.side_effect = responses

        # Create mock tool
        mock_tool = Mock()
        mock_tool.name = "database_query_with_sql"
        mock_tool.invoke.return_value = "✅ 执行成功\n返回行数：100"

        # Create and run subgraph
        graph = create_react_agent_subgraph(
            name="TestSQLAgent",
            llm=mock_llm,
            tools=[mock_tool],
            system_prompt="You are a SQL expert",
            max_iterations=5,
        )

        initial_state = {
            "input_data": {"case_name": "Count users"},
            "max_iterations": 5,
            "system_prompt": "You are a SQL expert",
            "messages": [
                SystemMessage(content="You are a SQL expert"),
                HumanMessage(content="Generate SQL"),
            ],
            "iteration_count": 0,
            "final_result": None,
            "agent_thinking": None,
            "success": False,
            "error": None,
        }

        result = graph.invoke(initial_state)

        # Verify the loop completed
        self.assertIsNotNone(result["final_result"])
        self.assertTrue(result["success"])
        # Should have used 2 iterations (1 tool call + 1 final answer)
        self.assertEqual(result["iteration_count"], 2)


class TestSqlGeneratorNodeIntegration(unittest.TestCase):
    """Integration tests for SQL generator node."""

    def test_sql_generator_with_mock_agent(self):
        """Test SQL generator node with mocked agent."""
        from nodes.sql_generator import sql_generator_node
        from state import GraphState

        mock_llm = Mock()
        mock_config = Mock()
        mock_config.max_sql_iterations = 5
        mock_db_tool = Mock()
        mock_knowledge_tool = Mock()

        # Mock the agent runner (imported inside function from agents.sql_agent)
        with patch("agents.sql_agent.run_sql_agent_for_test_case") as mock_run:
            mock_run.return_value = {
                "sql_result": '{"sql": "SELECT 1", "passed": true}',
                "agent_thinking": "Analyzed and generated SQL",
                "success": True,
                "error": None,
                "iteration_count": 2,
            }

            state = {
                "query": "Generate test cases",
                "files": [],
                "w3_id": "user123",
                "user_w3_id": "user123",
                "DDL": "CREATE TABLE test (id INT)",
                "RS": "Requirements",
                "mapping_table1": "mapping1",
                "mapping_table2": "mapping2",
                "test_case": json.dumps(
                    [
                        {
                            "case_name": "Test 1",
                            "level": "level1",
                            "pre_condition": "None",
                            "need_generate_sql": True,
                            "eval_step_descri": "Check data",
                            "expected_result": "PASS",
                            "tags": "smoke",
                        }
                    ]
                ),
                "test_case_naotu": "",
                "mapping_raw": "",
                "rs_raw": "",
                "ts_raw": "",
                "table_1": "",
                "table_2": "",
                "section_content": "",
                "ts_info": {},
                "class_type": "3",
                "class_reason": "Initial request",
                "result": "",
                "body": "",
                "messages": [],
                "llm_response": "",
                "new_test_case": "",
                "md_output": "",
            }

            result = sql_generator_node(
                state=state,
                llm=mock_llm,
                config=mock_config,
                db_tool=mock_db_tool,
                knowledge_tool=mock_knowledge_tool,
            )

            # Verify agent was called
            mock_run.assert_called_once()
            # Verify result was updated
            self.assertIn("test_case", result)
            self.assertIn("llm_response", result)
            # Verify summary message
            self.assertIn("SQL 生成完成", result["llm_response"])


if __name__ == "__main__":
    # Run tests
    unittest.main(verbosity=2)
