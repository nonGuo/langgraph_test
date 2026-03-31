"""
State definitions for the AI Test Case Generation LangGraph.

This module defines the TypedDict structures used for state management
throughout the graph execution.
"""

from typing import Annotated, Any, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class InputState(TypedDict):
    """
    Initial input state from user request.
    
    Attributes:
        query: User's current input message/query
        files: List of uploaded files (mapping, RS, TS)
        w3_id: User's W3 account ID for notifications
    """
    query: str
    files: list[dict[str, Any]]
    w3_id: str


class ConversationState(TypedDict):
    """
    Persistent conversation variables stored across sessions.
    
    These correspond to Dify's conversation_variables:
    - user_w3_id: User's W3 account
    - DDL: Database DDL statements
    - RS: Test points extracted from RS document
    - mapping_table1: Entity-level mapping (table-level)
    - mapping_table2: Attribute-level mapping (field-level)
    - test_case: LLM-generated test case description (JSON list)
    - test_case_naotu: LLM-generated test case mind map (mermaid format)
    """
    user_w3_id: str
    DDL: str
    RS: str
    mapping_table1: str
    mapping_table2: str
    test_case: str
    test_case_naotu: str


class ProcessingState(TypedDict):
    """
    Temporary state for document processing results.
    
    Attributes:
        mapping_raw: Raw parsed mapping document text
        rs_raw: Raw parsed RS document text
        ts_raw: Raw parsed TS document text
        table_1: First extracted mapping table (entity-level)
        table_2: Second extracted mapping table (attribute-level)
        section_content: Extracted test points section from RS
        ts_info: Extracted TS document info (schema, tables, primary keys, etc.)
    """
    mapping_raw: str
    rs_raw: str
    ts_raw: str
    table_1: str
    table_2: str
    section_content: str
    ts_info: dict[str, Any]


class IntentState(TypedDict):
    """
    State for intent classification results.
    
    Attributes:
        class_type: Classification result (1=chat/guidance, 2=confirm mindmap, 
                    3=initial request, 4=other)
        class_reason: Reason for classification
    """
    class_type: str
    class_reason: str


class TestCaseItem(TypedDict):
    """
    Single test case item structure within iteration.
    
    Attributes:
        case_name: Test case name
        level: Test level (level1-level4)
        pre_condition: Pre-conditions for test
        need_generate_sql: Whether SQL generation is needed
        eval_step_descri: Evaluation step description
        expected_result: Expected test result
        tags: Test case tags/categories
        agent_thinking: Agent's reasoning process
        db_excute_result: Database execution result
    """
    case_name: str
    level: str
    pre_condition: str
    need_generate_sql: bool
    eval_step_descri: str
    expected_result: str
    tags: str
    agent_thinking: Optional[str]
    db_excute_result: Optional[str]


class IterationItem(TypedDict):
    """
    State for a single iteration item (test case processing).
    
    Attributes:
        item: Current test case item being processed
        index: Current iteration index
        case_name: Extracted case name for display
        table_mapping_useful_info: Extracted table-level mapping info
        col_table_mapping_useful_info: Extracted field-level mapping info
        md_table: Formatted markdown table of test case
        knowledge_list: Retrieved few-shot examples from knowledge base
        few_shot: Few-shot SQL examples
        sql: Generated SQL for test validation
        query_result: Database query execution result
    """
    item: TestCaseItem
    index: int
    case_name: str
    table_mapping_useful_info: str
    col_table_mapping_useful_info: str
    md_table: str
    knowledge_list: list[str]
    few_shot: str
    sql: str
    query_result: str


class IterationOutput(TypedDict):
    """
    Output from iteration subgraph.
    
    Attributes:
        output: List of processed test case items
    """
    output: list[TestCaseItem]


class KnowledgeRetrievalState(TypedDict):
    """
    State for knowledge retrieval results.
    
    Attributes:
        result: Retrieved knowledge base content
    """
    result: str


class ExcelGenerationState(TypedDict):
    """
    State for Excel generation API response.
    
    Attributes:
        body: Excel file content or URL
    """
    body: str


# Combined state for the main graph
class GraphState(
    InputState,
    ConversationState,
    ProcessingState,
    IntentState,
    KnowledgeRetrievalState,
    ExcelGenerationState,
):
    """
    Combined state for the main graph.
    
    Inherits from all component states to provide a unified state object.
    Also includes messages for chat history.
    
    Attributes:
        messages: Chat message history (managed by LangGraph)
        llm_response: General LLM response text
        new_test_case: Updated test case list after iteration
        md_output: Formatted markdown output for display
    """
    messages: Annotated[list[Any], add_messages]
    llm_response: str
    new_test_case: str
    md_output: str


# State for iteration subgraph
class IterationSubgraphState(TypedDict):
    """
    State for the iteration subgraph (processing individual test cases).
    
    This subgraph handles the complex loop for processing each test case:
    1. Check if SQL generation needed
    2. Extract mapping info
    3. Retrieve few-shot examples
    4. Generate SQL using Agent
    5. Execute SQL and capture result
    6. Update test case item
    """
    # Input from parent
    test_case_list: list[TestCaseItem]
    
    # Shared state from parent graph
    mapping_table1: str
    mapping_table2: str
    DDL: str
    RS: str
    
    # Current iteration state
    item: TestCaseItem
    index: int
    case_name: str
    need_generate_sql: bool
    
    # Processing results
    table_mapping_useful_info: str
    col_table_mapping_useful_info: str
    md_table: str
    few_shot: str
    sql: str
    query_result: str
    agent_thinking: str
    
    # Output accumulation
    output: Annotated[list[TestCaseItem], "accumulated_results"]
