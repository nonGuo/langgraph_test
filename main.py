"""
AI4Test LangGraph - Main Entry Point

AI-powered test case generation for data warehouse testing.
Migrated from Dify chatflow to LangGraph implementation.

Usage:
    python -m ai4test_langgraph.main --query "生成测试用例" --mapping file.md --rs file.md --ts file.md
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)


def load_file_content(file_path: str) -> str:
    """
    Load content from a file.
    
    Args:
        file_path: Path to file
        
    Returns:
        File content as string
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def setup_llm(config):
    """
    Set up language model from configuration.
    
    Args:
        config: Configuration object
        
    Returns:
        LangChain LLM instance
    """
    from langchain_openai import ChatOpenAI
    
    llm = ChatOpenAI(
        model=config.llm_model,
        api_key=config.llm_api_key,
        base_url=config.llm_api_base,
        temperature=config.llm_temperature,
    )
    
    logger.info(f"Initialized LLM: {config.llm_model}")
    return llm


async def run_graph_async(
    query: str,
    mapping_file: str = None,
    rs_file: str = None,
    ts_file: str = None,
    w3_id: str = None,
):
    """
    Run the graph asynchronously.
    
    Args:
        query: User query
        mapping_file: Path to mapping document
        rs_file: Path to RS document
        ts_file: Path to TS document
        w3_id: User's W3 ID for notifications
    """
    from config import Config
    from graph import create_graph
    
    # Load configuration
    config = Config.from_env()
    
    # Set up LLM
    llm = setup_llm(config)
    
    # Create graph
    ai4test_graph = create_graph(config=config, llm=llm)
    
    # Prepare input state
    files = []
    
    if mapping_file:
        files.append({
            "type": "mapping",
            "filename": Path(mapping_file).name,
            "content": load_file_content(mapping_file),
        })
    
    if rs_file:
        files.append({
            "type": "RS",
            "filename": Path(rs_file).name,
            "content": load_file_content(rs_file),
        })
    
    if ts_file:
        files.append({
            "type": "TS",
            "filename": Path(ts_file).name,
            "content": load_file_content(ts_file),
        })
    
    input_state = {
        "query": query,
        "files": files,
        "w3_id": w3_id or "q00000000",  # Default placeholder
        # Initialize conversation state
        "user_w3_id": w3_id or "",
        "DDL": "",
        "RS": "",
        "mapping_table1": "",
        "mapping_table2": "",
        "test_case": "",
        "test_case_naotu": "",
        # Initialize processing state
        "mapping_raw": "",
        "rs_raw": "",
        "ts_raw": "",
        "table_1": "",
        "table_2": "",
        "section_content": "",
        "ts_info": {},
        # Initialize other state
        "class_type": "",
        "class_reason": "",
        "result": "",
        "llm_response": "",
        "new_test_case": "",
        "md_output": "",
        "body": "",
    }
    
    logger.info("Starting graph execution...")
    
    # Run graph
    result = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: ai4test_graph.invoke(input_state),
    )
    
    return result


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="AI4Test LangGraph - AI-powered test case generation"
    )
    
    parser.add_argument(
        "--query",
        type=str,
        required=True,
        help="User query or command",
    )
    
    parser.add_argument(
        "--mapping",
        type=str,
        help="Path to mapping document (Markdown)",
    )
    
    parser.add_argument(
        "--rs",
        type=str,
        help="Path to RS document (Requirement Specification)",
    )
    
    parser.add_argument(
        "--ts",
        type=str,
        help="Path to TS document (Technical Specification)",
    )
    
    parser.add_argument(
        "--w3-id",
        type=str,
        default="q00000000",
        help="User's W3 ID for notifications (e.g., q00797588)",
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Run the graph
    try:
        result = asyncio.run(run_graph_async(
            query=args.query,
            mapping_file=args.mapping,
            rs_file=args.rs,
            ts_file=args.ts,
            w3_id=args.w3_id,
        ))
        
        # Print result
        print("\n" + "="*80)
        print("GRAPH EXECUTION RESULT")
        print("="*80)
        print(result.get("llm_response", "No response"))
        print("="*80)
        
        # Save test cases to file if available
        test_case_json = result.get("test_case", "")
        if test_case_json:
            try:
                test_cases = json.loads(test_case_json)
                output_file = "test_cases_output.json"
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(test_cases, f, ensure_ascii=False, indent=2)
                print(f"\nTest cases saved to: {output_file}")
            except Exception as e:
                print(f"Could not save test cases: {e}")
        
    except Exception as e:
        logger.exception("Graph execution failed")
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
