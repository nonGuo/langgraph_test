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

    Supports:
    - Text files (.md, .txt, .sql, etc.): read directly
    - Excel files (.xlsx, .xls): convert to Markdown tables
    - Word files (.docx): convert to Markdown with structure

    Args:
        file_path: Path to file

    Returns:
        File content as string (Markdown format for Excel/DOCX)
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Check if it's an Excel file
    if path.suffix.lower() in ['.xlsx', '.xls']:
        logger.info(f"Detected Excel file: {file_path}, converting to Markdown...")
        from tools.excel_converter import convert_excel_to_markdown
        return convert_excel_to_markdown(file_path)

    # Check if it's a Word document
    if path.suffix.lower() == '.docx':
        logger.info(f"Detected DOCX file: {file_path}, converting to Markdown...")
        from tools.docx_converter import convert_docx_to_markdown
        return convert_docx_to_markdown(file_path)

    # Read text file directly
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
    thread_id: str = None,
):
    """
    Run the graph asynchronously.

    Args:
        query: User query
        mapping_file: Path to mapping document
        rs_file: Path to RS document
        ts_file: Path to TS document
        w3_id: User's W3 ID for notifications
        thread_id: Conversation thread ID for multi-turn dialogue
    """
    from config import Config
    from graph import create_graph

    # Load configuration
    config = Config.from_env()

    # Set up LLM
    llm = setup_llm(config)

    # Create graph with memory support
    ai4test_graph = create_graph(config=config, llm=llm, use_memory=True)

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

    # Generate thread_id if not provided
    if thread_id is None:
        import uuid
        thread_id = f"thread_{uuid.uuid4().hex[:8]}"
        logger.info(f"Generated new thread_id: {thread_id}")

    # Run graph
    result = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: ai4test_graph.invoke(input_state, thread_id=thread_id),
    )

    return result, thread_id


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="AI4Test LangGraph - AI-powered test case generation"
    )

    parser.add_argument(
        "--query",
        type=str,
        help="User query or command (optional for interactive mode)",
    )

    parser.add_argument(
        "--mapping",
        type=str,
        help="Path to mapping document (Markdown/Excel)",
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
        "--thread-id",
        type=str,
        default=None,
        help="Conversation thread ID for multi-turn dialogue",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Enable interactive multi-turn conversation mode",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Interactive mode
    if args.interactive:
        run_interactive_mode(args)
        return

    # Single query mode - query is required
    if not args.query:
        print("Error: --query is required (or use --interactive for multi-turn mode)")
        sys.exit(1)

    try:
        result, thread_id = asyncio.run(run_graph_async(
            query=args.query,
            mapping_file=args.mapping,
            rs_file=args.rs,
            ts_file=args.ts,
            w3_id=args.w3_id,
            thread_id=args.thread_id,
        ))

        # Print result
        print("\n" + "="*80)
        print("GRAPH EXECUTION RESULT")
        print("="*80)
        print(result.get("llm_response", "No response"))
        print("="*80)
        print(f"Thread ID: {thread_id} (use --thread-id {thread_id} to continue conversation)")
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


def run_interactive_mode(args):
    """
    Run interactive multi-turn conversation mode.

    Args:
        args: Parsed argument object
    """
    print("\n" + "="*80)
    print("AI4Test LangGraph - Interactive Multi-turn Conversation Mode")
    print("="*80)
    print()
    print("Commands:")
    print("  /quit     - Exit the conversation")
    print("  /clear    - Clear conversation history and start fresh")
    print("  /thread   - Show current thread ID")
    print()

    # Initialize or use provided thread_id
    thread_id = args.thread_id
    if not thread_id:
        import uuid
        thread_id = f"thread_{uuid.uuid4().hex[:8]}"
        print(f"Generated new thread ID: {thread_id}")
        print()

    # Store files from initial input
    initial_files = []

    if args.mapping:
        try:
            content = load_file_content(args.mapping)
            initial_files.append({
                "type": "mapping",
                "filename": Path(args.mapping).name,
                "content": content,
            })
            print(f"Loaded mapping file: {args.mapping}")
        except Exception as e:
            print(f"Warning: Could not load mapping file: {e}")

    if args.rs:
        try:
            content = load_file_content(args.rs)
            initial_files.append({
                "type": "RS",
                "filename": Path(args.rs).name,
                "content": content,
            })
            print(f"Loaded RS file: {args.rs}")
        except Exception as e:
            print(f"Warning: Could not load RS file: {e}")

    if args.ts:
        try:
            content = load_file_content(args.ts)
            initial_files.append({
                "type": "TS",
                "filename": Path(args.ts).name,
                "content": content,
            })
            print(f"Loaded TS file: {args.ts}")
        except Exception as e:
            print(f"Warning: Could not load TS file: {e}")

    print()
    print("Enter your message (or command):")
    print("-"*40)

    from config import Config
    from graph import create_graph

    # Load configuration and create graph (once)
    config = Config.from_env()
    llm = setup_llm(config)
    ai4test_graph = create_graph(config=config, llm=llm, use_memory=True)

    # Conversation state
    conversation_state = {
        "user_w3_id": args.w3_id,
        "DDL": "",
        "RS": "",
        "mapping_table1": "",
        "mapping_table2": "",
        "test_case": "",
        "test_case_naotu": "",
        "mapping_raw": "",
        "rs_raw": "",
        "ts_raw": "",
        "table_1": "",
        "table_2": "",
        "section_content": "",
        "ts_info": {},
        "class_type": "",
        "class_reason": "",
        "result": "",
        "llm_response": "",
        "new_test_case": "",
        "md_output": "",
        "body": "",
    }

    # Store initial files in state if provided
    if initial_files:
        conversation_state["files"] = initial_files
        # Also populate raw content for processing
        for file in initial_files:
            file_type = file.get("type")
            content = file.get("content", "")
            if file_type == "mapping":
                conversation_state["mapping_raw"] = content
            elif file_type == "RS":
                conversation_state["rs_raw"] = content
            elif file_type == "TS":
                conversation_state["ts_raw"] = content

    config = {"configurable": {"thread_id": thread_id}}

    while True:
        try:
            # Get user input
            user_input = input("\n> ").strip()

            if not user_input:
                continue

            # Handle commands
            if user_input.lower() in ['/quit', '/exit', 'quit', 'exit']:
                print("\nGoodbye!")
                break

            if user_input.lower() == '/clear':
                print("\n[Conversation history cleared]")
                import uuid
                thread_id = f"thread_{uuid.uuid4().hex[:8]}"
                print(f"New thread ID: {thread_id}")
                config = {"configurable": {"thread_id": thread_id}}
                # Reset state
                conversation_state = {k: "" if isinstance(v, str) else {} for k, v in conversation_state.items()}
                conversation_state["user_w3_id"] = args.w3_id
                continue

            if user_input.lower() == '/thread':
                print(f"Current thread ID: {thread_id}")
                continue

            # Prepare input state (merge conversation state with new query)
            input_state = {
                **conversation_state,
                "query": user_input,
                "files": initial_files if not conversation_state.get("files") else conversation_state.get("files", []),
                "w3_id": args.w3_id,
            }

            # Run graph
            result = ai4test_graph.invoke(input_state, thread_id=thread_id)

            # Update conversation state
            for key, value in result.items():
                conversation_state[key] = value

            # Print response
            print("\n" + "-"*40)
            print(result.get("llm_response", "No response"))
            print("-"*40)

            # Save test cases if generated
            test_case_json = result.get("test_case", "")
            if test_case_json and test_case_json != conversation_state.get("test_case", ""):
                try:
                    test_cases = json.loads(test_case_json)
                    output_file = "test_cases_output.json"
                    with open(output_file, "w", encoding="utf-8") as f:
                        json.dump(test_cases, f, ensure_ascii=False, indent=2)
                    print(f"\n[Test cases saved to: {output_file}]")
                except Exception as e:
                    print(f"[Could not save test cases: {e}]")

        except KeyboardInterrupt:
            print("\n\nInterrupted. Type /quit to exit.")
            continue
        except Exception as e:
            logger.exception("Error in interactive mode")
            print(f"\nError: {e}")


if __name__ == "__main__":
    main()
