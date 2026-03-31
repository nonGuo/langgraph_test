"""
Mermaid 到 XMind 转换工具.

XMind 文件 (.xmind) 本质上是一个 zip 包，包含:
- content.json: 思维导图内容
- metadata.json: 元数据
- thumbnail.png: 缩略图 (可选)

该模块实现 mermaid graph LR 格式到 XMind 格式的转换.
"""

import json
import logging
import re
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class MindMapNode:
    """思维导图节点."""
    title: str
    children: list["MindMapNode"] = field(default_factory=list)
    id: str = field(default_factory=lambda: "")

    def to_xmind_topic(self) -> dict[str, Any]:
        """转换为 XMind topic 格式."""
        topic = {
            "id": self.id,
            "title": self.title,
        }
        if self.children:
            topic["children"] = {
                "attached": [child.to_xmind_topic() for child in self.children]
            }
        return topic


def parse_mermaid_graph(mermaid_text: str) -> MindMapNode:
    """
    解析 mermaid graph LR 格式的文本.

    支持格式:
    ```
    graph LR
        root("根节点")
        L1_1("一级节点 1")
        L1_2("一级节点 2")
        root --> L1_1
        root --> L1_2
        L3_1_1("叶子节点")
        L1_1 --> L3_1_1
    ```

    Args:
        mermaid_text: mermaid 格式的文本

    Returns:
        MindMapNode 根节点
    """
    lines = mermaid_text.strip().split("\n")

    # 存储所有节点定义和关系
    node_definitions: dict[str, str] = {}  # node_id -> title
    relationships: list[tuple[str, str]] = []  # (parent_id, child_id)

    # 解析每一行
    for line in lines:
        line = line.strip()

        # 跳过空行和 graph 声明
        if not line or line.startswith("graph"):
            continue

        # 跳过注释
        if line.startswith("%%"):
            continue

        # 匹配节点定义：node_id("title") 或 node_id("title with spaces")
        node_pattern = r'(\w+)\s*\("([^"]+)"\)'
        node_match = re.match(node_pattern, line)
        if node_match:
            node_id = node_match.group(1)
            title = node_match.group(2).replace("<br/>", "\n")  # 处理 HTML 换行
            node_definitions[node_id] = title
            continue

        # 匹配关系：parent --> child
        rel_pattern = r'(\w+)\s*-->\s*(\w+)'
        rel_match = re.match(rel_pattern, line)
        if rel_match:
            parent_id = rel_match.group(1)
            child_id = rel_match.group(2)
            relationships.append((parent_id, child_id))
            continue

    logger.info(f"解析到 {len(node_definitions)} 个节点，{len(relationships)} 个关系")

    # 构建树结构
    return build_tree(node_definitions, relationships)


def build_tree(
    node_definitions: dict[str, str],
    relationships: list[tuple[str, str]],
) -> MindMapNode:
    """
    从节点定义和关系构建树结构.

    Args:
        node_definitions: 节点 ID 到标题的映射
        relationships: (parent_id, child_id) 关系列表

    Returns:
        MindMapNode 根节点
    """
    # 创建所有节点
    nodes: dict[str, MindMapNode] = {}
    for node_id, title in node_definitions.items():
        nodes[node_id] = MindMapNode(title=title, id=node_id)

    # 找出根节点 (没有父节点的节点)
    all_parents = set(rel[0] for rel in relationships)
    all_children = set(rel[1] for rel in relationships)

    # 根节点是被作为父节点引用但从未作为子节点引用的节点
    root_candidates = all_parents - all_children

    # 如果没有找到根节点，使用第一个定义的节点
    if not root_candidates:
        root_id = list(node_definitions.keys())[0] if node_definitions else None
        if root_id:
            root_candidates = {root_id}

    if not root_candidates:
        # 创建一个虚拟根节点
        return MindMapNode(title="根节点", children=[])

    root_id = list(root_candidates)[0]
    root = nodes[root_id]

    # 建立父子关系
    child_to_parent = {}
    for parent_id, child_id in relationships:
        if parent_id in nodes and child_id in nodes:
            nodes[parent_id].children.append(nodes[child_id])
            child_to_parent[child_id] = parent_id

    # 处理孤立的节点 (没有连接到根的节点)
    for node_id, node in nodes.items():
        if node_id != root_id and node_id not in child_to_parent:
            # 将孤立节点作为根节点的子节点
            root.children.append(node)

    return root


def create_xmind_content(root_node: MindMapNode, sheet_title: str = "思维导图") -> dict[str, Any]:
    """
    创建 XMind content.json 结构.

    Args:
        root_node: 根节点
        sheet_title: 工作表标题

    Returns:
        content.json 字典结构
    """
    content = {
        "rootTopic": root_node.to_xmind_topic(),
        "sheetProperties": {
            "id": "sheet-1",
            "title": sheet_title,
            "rootTopicId": root_node.id,
        },
        "styles": {},
        "topicPositioning": "overlapped",
        "topicOverlapping": "hierarchical",
        "theme": {
            "id": "default",
            "title": "默认主题",
        },
    }

    return content


def create_xmind_metadata() -> dict[str, Any]:
    """创建 XMind metadata.json 结构."""
    return {
        "fileVersion": "1.0.0",
        "creator": "AI4Test LangGraph",
        "creatorVersion": "1.0",
        "format": "xmind",
        "id": "ai4test-mindmap",
    }


def generate_xmind_file(
    mermaid_text: str,
    output_path: str,
    sheet_title: str = "测试用例脑图",
) -> dict[str, Any]:
    """
    从 mermaid 文本生成 XMind 文件.

    Args:
        mermaid_text: mermaid 格式的脑图文本
        output_path: 输出文件路径 (.xmind)
        sheet_title: 工作表标题

    Returns:
        生成结果字典
    """
    try:
        # 解析 mermaid
        root_node = parse_mermaid_graph(mermaid_text)

        # 创建 content.json
        content = create_xmind_content(root_node, sheet_title)

        # 创建 metadata.json
        metadata = create_xmind_metadata()

        # 创建 XMind 文件 (zip 格式)
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("content.json", json.dumps(content, ensure_ascii=False, indent=2))
            zf.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))

        # 写入文件
        with open(output_path, "wb") as f:
            f.write(buffer.getvalue())

        logger.info(f"XMind 文件已生成：{output_path}")

        return {
            "success": True,
            "file_path": output_path,
            "node_count": count_nodes(root_node),
        }

    except Exception as e:
        logger.exception("XMind 生成失败")
        return {
            "success": False,
            "error": str(e),
        }


def count_nodes(node: MindMapNode) -> int:
    """统计节点数量."""
    count = 1
    for child in node.children:
        count += count_nodes(child)
    return count


def generate_xmind_to_bytes(
    mermaid_text: str,
    sheet_title: str = "测试用例脑图",
) -> tuple[bool, Optional[bytes], Optional[str]]:
    """
    从 mermaid 文本生成 XMind 文件字节流.

    Args:
        mermaid_text: mermaid 格式的脑图文本
        sheet_title: 工作表标题

    Returns:
        (success, file_bytes, error)
    """
    try:
        # 解析 mermaid
        root_node = parse_mermaid_graph(mermaid_text)

        # 创建 content.json
        content = create_xmind_content(root_node, sheet_title)

        # 创建 metadata.json
        metadata = create_xmind_metadata()

        # 创建 XMind 文件 (zip 格式)
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("content.json", json.dumps(content, ensure_ascii=False, indent=2))
            zf.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))

        return True, buffer.getvalue(), None

    except Exception as e:
        logger.exception("XMind 生成失败")
        return False, None, str(e)


# ============================================================================
# 便捷函数
# ============================================================================

def mermaid_to_xmind(
    mermaid_text: str,
    output_path: str,
    sheet_title: str = "测试用例脑图",
) -> bool:
    """
    便捷函数：将 mermaid 脑图转换为 XMind 文件.

    Args:
        mermaid_text: mermaid 格式的脑图
        output_path: 输出路径
        sheet_title: 工作表标题

    Returns:
        是否成功
    """
    result = generate_xmind_file(mermaid_text, output_path, sheet_title)
    return result["success"]
