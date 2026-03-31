"""
Document parsing nodes.

Handles parsing of uploaded documents:
- Mapping documents (markdown tables)
- RS documents (Requirement Specification)
- TS documents (Technical Specification)
"""

import json
import logging
import re
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from state import GraphState

logger = logging.getLogger(__name__)


def parse_markdown_tables(text: str) -> dict[str, str]:
    """
    Split markdown text into separate tables.
    
    Python implementation of the Dify code node 1768449749100.
    
    Args:
        text: Markdown text containing tables
        
    Returns:
        Dictionary with table_1 and table_2 keys
    """
    # Match markdown tables (lines starting with |)
    pattern = re.compile(r'(?:\|.*\n)+')
    tables = pattern.findall(text)
    
    # Strip whitespace
    tables = [table.strip() for table in tables]
    
    # Filter tables with enough content (more than 4 pipe characters)
    tables = [table for table in tables if table.count('|') > 4]
    
    if len(tables) >= 2:
        return {
            "table_1": tables[0],
            "table_2": tables[1],
        }
    elif len(tables) == 1:
        return {
            "table_1": tables[0],
            "table_2": "",
        }
    else:
        return {
            "table_1": "",
            "table_2": "",
        }


def parse_mapping_node(state: GraphState) -> GraphState:
    """
    Parse mapping document and extract tables.
    
    Corresponds to Dify nodes:
    - 1768449734777 (document-extractor)
    - 1768449749100 (code - format mapping)
    
    Args:
        state: Current graph state
        
    Returns:
        Updated state with table_1 and table_2
    """
    # Get mapping file content from state
    # In real implementation, this would come from file upload
    mapping_raw = state.get("mapping_raw", "")
    
    if not mapping_raw:
        # Try to get from files
        files = state.get("files", [])
        for file in files:
            if file.get("type") == "mapping" or "mapping" in file.get("filename", "").lower():
                mapping_raw = file.get("content", "")
                break
    
    logger.info(f"Parsing mapping document, length: {len(mapping_raw)}")
    
    # Parse tables
    tables = parse_markdown_tables(mapping_raw)
    
    logger.info(
        f"Extracted {len(tables['table_1'])} chars for table_1, "
        f"{len(tables['table_2'])} chars for table_2"
    )
    
    return {
        **state,
        "table_1": tables["table_1"],
        "table_2": tables["table_2"],
        "mapping_table1": tables["table_1"],  # Save to conversation state
        "mapping_table2": tables["table_2"],
    }


def extract_rs_section(doc_string: str, section_name: str = "测试要点") -> str:
    """
    Extract a specific section from RS document.
    
    Python implementation of the Dify code node 1768465208003.
    
    Args:
        doc_string: RS document text
        section_name: Section name to extract
        
    Returns:
        Extracted section content
    """
    # Pattern to match section until next numbered section
    pattern = rf"{section_name}.*?(?=\n\s*\d+\.\d+|\n\s*[A-Z]|$)"
    match = re.search(pattern, doc_string, re.DOTALL)
    
    if match:
        return match.group(0).strip()
    return ""


def parse_rs_node(state: GraphState) -> GraphState:
    """
    Parse RS document and extract test points section.
    
    Corresponds to Dify nodes:
    - 1768463945748 (document-extractor)
    - 1768465208003 (code - extract test points)
    
    Args:
        state: Current graph state
        
    Returns:
        Updated state with section_content
    """
    # Get RS file content
    rs_raw = state.get("rs_raw", "")
    
    if not rs_raw:
        files = state.get("files", [])
        for file in files:
            if file.get("type") == "RS" or "RS" in file.get("filename", "").upper():
                rs_raw = file.get("content", "")
                break
    
    logger.info(f"Parsing RS document, length: {len(rs_raw)}")
    
    # Extract test points section
    section_content = extract_rs_section(rs_raw, "测试要点")
    
    logger.info(f"Extracted test points section: {len(section_content)} chars")
    
    return {
        **state,
        "rs_raw": rs_raw,
        "section_content": section_content,
    }


# TS document extraction prompt
TS_EXTRACTION_PROMPT = """
你是一个文档分析师。请阅读以下文档片段，根据 TS 文档内容提取表的基本信息：

需要提取的基本信息有：
- 目标表的 schema、表名
- 分布方式、分区键、索引
- 主键
- 本次变更内容

提取规则：
1. 仅关注"功能简要说明"和"物理模型设计"部分
2. 一个 TS 文档的目标表都在同一个 schema 下
3. 一个 TS 文档的目标表可能有多个：
   - 以_tmp[0-9]* 结尾的是临时表
   - 以_f 结尾的是事实表
   - 以_i 结尾的是对外提供消费的资产
4. 一个 TS 文档的多个目标表主键相同
5. 表的主键等价于对象的粒度，可以从对象的粒度获取
6. 如 TS 中无分布方式设计，则对象类型为视图
7. _i 结尾的对象可以是视图也可以是物理表
8. 本次变更内容可以从变更记录章节获取，取最新的一行

文档内容：
{doc_content}

注意，必须按如下 JSON 格式输出，不要增加解释：
{{
    "schema": "fin_dwb_cs",
    "目标表": ["dwb_cs_order_base_i", "dwb_cs_order_base_f", "dwb_cs_order_base_tmp"],
    "主键": "order_base_id",
    "分布方式": {{
        "dwb_cs_order_base_i": "无",
        "dwb_cs_order_base_f": "哈希分布 order_base_id",
        "dwb_cs_order_base_tmp": "哈希分布 order_base_id"
    }},
    "索引": {{
        "dwb_cs_order_base_i": "无",
        "dwb_cs_order_base_f": "无",
        "dwb_cs_order_base_tmp": "无"
    }},
    "本次优化点": {{
        "IR 单号": "IR001",
        "变更类型": "新增",
        "详情": "新建表"
    }}
}}
"""


def parse_ts_node(state: GraphState, llm: BaseChatModel) -> GraphState:
    """
    Parse TS document and extract table information using LLM.
    
    Corresponds to Dify nodes:
    - 1774230090685 (document-extractor)
    - 1774230120418 (LLM - TS document extraction)
    
    Args:
        state: Current graph state
        llm: Language model for extraction
        
    Returns:
        Updated state with ts_info
    """
    # Get TS file content
    ts_raw = state.get("ts_raw", "")
    
    if not ts_raw:
        files = state.get("files", [])
        for file in files:
            if file.get("type") == "TS" or "TS" in file.get("filename", "").upper():
                ts_raw = file.get("content", "")
                break
    
    logger.info(f"Parsing TS document, length: {len(ts_raw)}")
    
    try:
        # Build prompt
        prompt_text = TS_EXTRACTION_PROMPT.format(doc_content=ts_raw[:4000])
        
        messages = [
            SystemMessage(content="你是一个专业的文档分析师，擅长从 TS 文档中提取表结构信息。"),
            HumanMessage(content=prompt_text),
        ]
        
        response = llm.invoke(messages)
        response_text = response.content.strip()
        
        # Clean response
        if response_text.startswith("```"):
            response_text = response_text.split("```", 1)[-1].split("```", 1)[0].strip()
        if response_text.startswith("json"):
            response_text = response_text[4:].strip()
        
        # Parse JSON
        ts_info = json.loads(response_text)
        
        # Extract DDL from TS info
        ddl_content = _generate_ddl_from_ts_info(ts_info)
        
        logger.info(f"Successfully extracted TS info: {ts_info.get('目标表', [])}")
        
        return {
            **state,
            "ts_raw": ts_raw,
            "ts_info": ts_info,
            "DDL": ddl_content,  # Save to conversation state
        }
        
    except Exception as e:
        logger.exception(f"TS extraction failed: {e}")
        # Return empty result on error
        return {
            **state,
            "ts_raw": ts_raw,
            "ts_info": {},
            "DDL": "",
        }


def _generate_ddl_from_ts_info(ts_info: dict[str, Any]) -> str:
    """
    Generate DDL statements from TS info.
    
    Helper function to create DDL from extracted TS information.
    
    Args:
        ts_info: Extracted TS information dictionary
        
    Returns:
        DDL statements as string
    """
    # TODO: Implement proper DDL generation
    # For now, return a stub
    schema = ts_info.get("schema", "unknown_schema")
    tables = ts_info.get("目标表", [])
    primary_key = ts_info.get("主键", "id")
    
    ddl_lines = [f"-- DDL for schema: {schema}", ""]
    
    for table in tables:
        ddl_lines.append(f"-- Table: {table}")
        ddl_lines.append(f"-- Primary Key: {primary_key}")
        
        distribution = ts_info.get("分布方式", {}).get(table, "未知")
        ddl_lines.append(f"-- Distribution: {distribution}")
        
        index = ts_info.get("索引", {}).get(table, "无")
        ddl_lines.append(f"-- Index: {index}")
        ddl_lines.append("")
    
    return "\n".join(ddl_lines)
