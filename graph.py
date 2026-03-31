"""
Main LangGraph assembly for AI4Test.

This module assembles all nodes and edges into the complete graph workflow.
"""

import logging
from typing import Any

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.language_models import BaseChatModel

from state import GraphState
from config import Config

logger = logging.getLogger(__name__)


class AI4TestGraph:
    """
    AI4Test LangGraph workflow.
    
    This class encapsulates the complete graph workflow migrated from Dify.
    
    Main workflow branches:
    1. Intent Classification -> Route to appropriate branch
    2. Document Processing -> Parse Mapping/RS/TS
    3. Test Points Extraction -> Extract or generate test points
    4. Mind Map Generation -> Generate test case structure
    5. Test Case Generation -> Convert mind map to JSON
    6. SQL Generation (Iteration) -> Generate SQL for each test case
    7. Excel Generation -> Create Excel file
    8. Notification -> Send completion message
    
    Attributes:
        config: Configuration object
        llm: Language model instance
        graph: Compiled StateGraph
    """
    
    def __init__(
        self,
        config: Config,
        llm: BaseChatModel,
        db_tool: Any = None,
        knowledge_tool: Any = None,
        messaging_tool: Any = None,
        excel_client: Any = None,
    ):
        """
        Initialize the graph with configuration and tools.
        
        Args:
            config: Configuration object
            llm: Language model for all LLM calls
            db_tool: Database execution tool
            knowledge_tool: Knowledge base retrieval tool
            messaging_tool: Notification messaging tool
            excel_client: Excel generation API client
        """
        self.config = config
        self.llm = llm
        self.db_tool = db_tool
        self.knowledge_tool = knowledge_tool
        self.messaging_tool = messaging_tool
        self.excel_client = excel_client
        
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """
        Build the StateGraph with all nodes and edges.
        
        Returns:
            Compiled StateGraph
        """
        logger.info("Building AI4Test graph...")
        
        # Initialize graph with GraphState
        builder = StateGraph(GraphState)
        
        # Add all nodes
        self._add_nodes(builder)
        
        # Add edges (routing logic)
        self._add_edges(builder)
        
        # Compile the graph
        graph = builder.compile()
        logger.info("Graph built successfully")
        
        return graph
    
    def _add_nodes(self, builder: StateGraph) -> None:
        """
        Add all nodes to the graph builder.
        
        Args:
            builder: StateGraph builder
        """
        from nodes import (
            intent_classifier_node,
            parse_mapping_node,
            parse_rs_node,
            parse_ts_node,
            extract_test_points_node,
            mind_map_generator_node,
            test_case_generator_node,
            sql_generator_node,
            send_notification_node,
        )
        from nodes.notification_sender import send_chat_response_node
        
        # Intent classification
        builder.add_node(
            "intent_classifier",
            lambda state: intent_classifier_node(state, self.llm),
        )
        
        # Document processing branch
        builder.add_node("parse_mapping", parse_mapping_node)
        builder.add_node("parse_rs", parse_rs_node)
        builder.add_node("parse_ts", lambda state: parse_ts_node(state, self.llm))
        
        # Test points extraction
        builder.add_node(
            "extract_test_points",
            lambda state: extract_test_points_node(state, self.llm),
        )
        
        # Knowledge retrieval
        builder.add_node("retrieve_knowledge", self._retrieve_knowledge_node)
        
        # Mind map generation (using ReAct Agent)
        builder.add_node(
            "generate_mind_map",
            lambda state: mind_map_generator_node(
                state,
                self.llm,
                messaging_tool=self.messaging_tool,
                max_iterations=self.config.max_sql_iterations if self.config else 3,
            ),
        )
        
        # Chat/guidance response
        builder.add_node("handle_chat_guidance", send_chat_response_node)
        
        # Test case generation (using ReAct Agent)
        builder.add_node(
            "generate_test_cases",
            lambda state: test_case_generator_node(
                state,
                self.llm,
                max_iterations=self.config.max_sql_iterations if self.config else 3,
            ),
        )
        
        # SQL generation (using ReAct Agent subgraph)
        builder.add_node(
            "generate_sql",
            lambda state: sql_generator_node(
                state=state,
                llm=self.llm,
                config=self.config,
                db_tool=self.db_tool,
                knowledge_tool=self.knowledge_tool,
            ),
        )
        
        # Notification
        builder.add_node(
            "send_notification",
            lambda state: send_notification_node(
                state, self.excel_client, self.messaging_tool
            ),
        )
    
    def _add_edges(self, builder: StateGraph) -> None:
        """
        Add edges and routing logic to the graph builder.
        
        Args:
            builder: StateGraph builder
        """
        from edges.routing import (
            intent_router,
            test_points_extraction_router,
        )
        
        # Entry point
        builder.set_entry_point("intent_classifier")
        
        # Intent classification routing
        builder.add_conditional_edges(
            "intent_classifier",
            intent_router,
            {
                "handle_chat_guidance": "handle_chat_guidance",
                "confirm_mindmap_branch": "generate_mind_map",
                "document_processing_branch": "parse_mapping",
            },
        )
        
        # Document processing flow
        builder.add_edge("parse_mapping", "parse_rs")
        builder.add_edge("parse_rs", "parse_ts")
        builder.add_edge("parse_ts", "extract_test_points")
        
        # Test points extraction routing
        builder.add_conditional_edges(
            "extract_test_points",
            test_points_extraction_router,
            {
                "extraction_success": "retrieve_knowledge",
                "extraction_fallback_llm": "retrieve_knowledge",
            },
        )
        
        # Knowledge retrieval -> Mind map
        builder.add_edge("retrieve_knowledge", "generate_mind_map")
        
        # Mind map -> (user confirmation happens externally)
        # For now, go directly to test case generation
        builder.add_edge("generate_mind_map", "generate_test_cases")
        
        # Test case generation -> SQL generation
        builder.add_edge("generate_test_cases", "generate_sql")
        
        # SQL generation -> Notification
        builder.add_edge("generate_sql", "send_notification")
        
        # Chat/guidance -> END
        builder.add_edge("handle_chat_guidance", END)
        
        # Notification -> END
        builder.add_edge("send_notification", END)
    
    def _retrieve_knowledge_node(self, state: GraphState) -> GraphState:
        """
        Retrieve knowledge base for test case standards.
        
        Internal node for knowledge retrieval.
        
        Args:
            state: Current graph state
            
        Returns:
            Updated state with knowledge results
        """
        if not self.knowledge_tool:
            logger.warning("Knowledge tool not available, skipping retrieval")
            return {**state, "result": ""}
        
        query = state.get("query", "测试用例设计规范")
        
        try:
            result = self.knowledge_tool.search(query=query)
            if result.success:
                logger.info(f"Knowledge retrieved: {len(result.content)} chars")
                return {**state, "result": result.content}
            else:
                logger.warning(f"Knowledge retrieval failed: {result.error}")
                return {**state, "result": ""}
        except Exception as e:
            logger.exception("Knowledge retrieval error")
            return {**state, "result": ""}
    
    def invoke(self, input_state: dict[str, Any]) -> dict[str, Any]:
        """
        Invoke the graph with input state.
        
        Args:
            input_state: Initial state dictionary
            
        Returns:
            Final state dictionary
        """
        logger.info(f"Invoking graph with input: {input_state.keys()}")
        
        try:
            result = self.graph.invoke(input_state)
            logger.info("Graph execution completed")
            return result
        except Exception as e:
            logger.exception("Graph execution failed")
            raise
    
    def stream(self, input_state: dict[str, Any]):
        """
        Stream graph execution results.
        
        Args:
            input_state: Initial state dictionary
            
        Yields:
            Intermediate state updates
        """
        logger.info(f"Streaming graph with input: {input_state.keys()}")
        
        try:
            for chunk in self.graph.stream(input_state):
                yield chunk
        except Exception as e:
            logger.exception("Graph streaming failed")
            raise


def create_graph(
    config: Config = None,
    llm: BaseChatModel = None,
    **kwargs
) -> AI4TestGraph:
    """
    Factory function to create AI4TestGraph instance.
    
    Convenience function that sets up default configuration and tools.
    
    Args:
        config: Configuration object (uses env if None)
        llm: Language model instance
        **kwargs: Additional tool instances
        
    Returns:
        Configured AI4TestGraph instance
    """
    from config import Config
    from tools.database_tool import DatabaseTool
    from tools.knowledge_tool import KnowledgeTool
    from tools.messaging_tool import MessagingTool
    from api.excel_client import ExcelClient
    
    # Use provided config or load from env
    if config is None:
        config = Config.from_env()
    
    # Create default tools if not provided
    db_tool = kwargs.get("db_tool") or DatabaseTool(
        host=config.db_host,
        port=config.db_port,
        database=config.db_name,
        user=config.db_user,
        password=config.db_password,
        pool_size=config.db_pool_size,
        statement_timeout=config.db_statement_timeout,
        max_rows=config.db_max_rows,
    )
    
    knowledge_tool = kwargs.get("knowledge_tool") or KnowledgeTool(
        knowledge_base_id=config.knowledge_base_id,
        top_k=config.top_k,
        score_threshold=config.score_threshold,
    )
    
    messaging_tool = kwargs.get("messaging_tool") or MessagingTool(
        enabled=config.notification_enabled,
    )

    excel_client = kwargs.get("excel_client") or ExcelClient(
        output_dir=config.excel_output_dir,
        filename_prefix=config.excel_filename_prefix,
    )
    
    return AI4TestGraph(
        config=config,
        llm=llm,
        db_tool=db_tool,
        knowledge_tool=knowledge_tool,
        messaging_tool=messaging_tool,
        excel_client=excel_client,
    )
