"""
DOCX to Markdown Converter.

将 Word (.docx) 文件转换为 Markdown 格式，保留文档结构和表格。

支持功能:
1. 保留标题层级 (Heading 1-6 -> # 到 ######)
2. 保留段落结构
3. 保留表格 (转换为 Markdown 表格)
4. 保留列表 (有序和无序)
5. 保留粗体、斜体等基本格式
6. 按文档原始顺序输出内容
"""

import logging
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)


def docx_to_markdown(file_path: str) -> str:
    """
    将 DOCX 文件转换为 Markdown 格式。

    Args:
        file_path: DOCX 文件路径

    Returns:
        Markdown 格式的文档字符串
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"DOCX 文件不存在：{file_path}")

    if path.suffix.lower() != '.docx':
        raise ValueError(f"不支持的文件格式：{path.suffix}，仅支持 .docx")

    try:
        from docx import Document
    except ImportError:
        raise ImportError("读取 .docx 文件需要 python-docx 库：pip install python-docx")

    logger.info(f"读取 DOCX 文件：{file_path}")
    doc = Document(path)

    markdown_parts = []

    # 按顺序处理文档中的所有元素
    # docx 文档的结构是扁平的，需要遍历所有 block-level 元素
    for element in _iter_block_items(doc):
        markdown = _process_block(element)
        if markdown:
            markdown_parts.append(markdown)

    result = "\n\n".join(markdown_parts)
    logger.info(f"DOCX 转换完成，输出长度：{len(result)} 字符")
    return result


def _iter_block_items(doc):
    """
    迭代文档中的所有块级元素（包括表格中的行）。

    这样可以确保我们按顺序处理所有内容，包括表格内部的内容。
    """
    from docx.document import Document as DocumentClass
    from docx.text.paragraph import Paragraph
    from docx.table import Table

    for block in doc.element.body:
        if block.tag.endswith('tbl'):
            # 这是一个表格
            yield Table(block, doc)
        elif block.tag.endswith('p'):
            # 这是一个段落
            yield Paragraph(block, doc)


def _process_block(element) -> Optional[str]:
    """
    处理单个块级元素（段落或表格）。

    Args:
        element: 段落或表格对象

    Returns:
        Markdown 字符串或 None（如果是空内容）
    """
    from docx.text.paragraph import Paragraph
    from docx.table import Table

    if isinstance(element, Paragraph):
        return _process_paragraph(element)
    elif isinstance(element, Table):
        return _process_table(element)
    return None


def _process_paragraph(para) -> Optional[str]:
    """
    处理段落元素。

    根据段落样式确定输出格式：
    - 标题样式 -> Markdown 标题
    - 列表样式 -> Markdown 列表
    - 普通段落 -> 普通文本
    """
    from docx.enum.style import WD_STYLE_TYPE
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    # 获取段落文本
    text = para.text.strip()
    if not text:
        return None

    # 检查段落样式
    style_name = para.style.name if para.style else ""
    style_type = para.style.type if para.style else None

    # 处理标题
    markdown = _handle_heading(text, style_name, style_type, para)
    if markdown:
        return markdown

    # 处理列表
    markdown = _handle_list(text, style_name, para)
    if markdown:
        return markdown

    # 检查是否是居中的短文本（可能是封面标题）
    if len(text) < 50 and '\n' not in text:
        if hasattr(para, 'alignment') and para.alignment is not None:
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            if para.alignment == WD_ALIGN_PARAGRAPH.CENTER:
                # 居中的短文本，添加强调标记
                return f"**{text}**"

    # 默认作为普通段落
    return _process_inline_formatting(text, para)


def _handle_heading(text: str, style_name: str, style_type, para) -> Optional[str]:
    """处理标题样式。"""
    # 检查是否为标题样式
    is_heading = False
    level = 0

    # 方法 1: 通过样式名称判断
    if style_name:
        style_lower = style_name.lower()
        if 'heading' in style_lower or '标题' in style_lower or '标题 ' in style_lower:
            is_heading = True
            # 尝试提取级别
            for i in range(1, 7):
                if str(i) in style_lower or f'Heading {i}' in style_name or f'标题 {i}' in style_lower:
                    level = i
                    break
            if level == 0:
                level = 1

    # 方法 2: 通过样式 ID 判断
    if not is_heading and para.style is not None:
        style_id = para.style.style_id
        if style_id and 'heading' in style_id.lower():
            is_heading = True
            # 从 style_id 提取级别
            for i in range(1, 7):
                if str(i) in style_id.lower():
                    level = i
                    break
            if level == 0:
                level = 1

    # 方法 3: 通过字体大小和粗体判断（启发式）
    if not is_heading:
        if para.runs:
            first_run = para.runs[0]
            font_size = first_run.font.size
            is_bold = first_run.bold

            # 大字体且粗体可能是标题
            if is_bold and font_size:
                if font_size.pt >= 16:
                    is_heading = True
                    level = 1
                elif font_size.pt >= 14:
                    is_heading = True
                    level = 2
                elif font_size.pt >= 12:
                    is_heading = True
                    level = 3

    if is_heading and level > 0:
        prefix = "#" * level
        return f"{prefix} {text}"

    return None


def _handle_list(text: str, style_name: str, para) -> Optional[str]:
    """处理列表样式。"""
    if style_name:
        style_lower = style_name.lower()
        # 检查是否为列表样式
        if 'list' in style_lower or '列表' in style_lower:
            # 有序列表
            if 'number' in style_lower or '编号' in style_lower:
                return f"1. {text}"
            # 无序列表
            else:
                return f"- {text}"

    # 检查段落是否有编号属性（自动列表）
    if hasattr(para.style, 'style_id') and para.style.style_id:
        style_id = para.style.style_id.lower()
        if 'list' in style_id:
            if 'number' in style_id or 'listenum' in style_id:
                return f"1. {text}"
            else:
                return f"- {text}"

    return None


def _process_inline_formatting(text: str, para) -> str:
    """
    处理段落内的内联格式（粗体、斜体等）。

    遍历段落中的所有 run，根据格式生成 Markdown。
    """
    if not para.runs:
        return text

    result_parts = []
    current_format = ""
    current_text = ""

    for run in para.runs:
        run_text = run.text
        if not run_text:
            continue

        # 确定当前 run 的格式
        is_bold = run.bold
        is_italic = run.italic
        is_underline = run.underline is not None and run.underline

        # 构建格式标记
        format_markers = []
        if is_bold:
            format_markers.append('**')
        if is_italic:
            format_markers.append('*')

        # 如果格式变化，添加标记
        if format_markers:
            formatted_text = "".join(format_markers) + run_text + "".join(reversed(format_markers))
            result_parts.append(formatted_text)
        else:
            result_parts.append(run_text)

    return "".join(result_parts)


def _process_table(table) -> str:
    """
    处理表格元素，转换为 Markdown 表格。

    Args:
        table: docx 表格对象

    Returns:
        Markdown 表格字符串
    """
    rows = []

    for row in table.rows:
        cells = []
        for cell in row.cells:
            # 获取单元格文本，处理换行
            cell_text = cell.text.replace("\n", " ").strip()
            # 转义管道符
            cell_text = cell_text.replace("|", "\\|")
            cells.append(cell_text)
        rows.append(cells)

    if not rows:
        return ""

    # 确定列数
    max_cols = max(len(row) for row in rows)

    # 补齐短行
    for row in rows:
        while len(row) < max_cols:
            row.append("")

    # 构建 Markdown 表格
    lines = []

    # 表头（第一行）
    header = rows[0]
    lines.append("| " + " | ".join(header) + " |")

    # 分隔线
    lines.append("|" + "|".join(["---"] * max_cols) + "|")

    # 数据行
    for row in rows[1:]:
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def convert_docx_to_markdown(file_path: Union[str, Path]) -> str:
    """
    便捷函数：将 DOCX 文件转换为 Markdown 格式。

    Args:
        file_path: DOCX 文件路径

    Returns:
        Markdown 格式的文档字符串
    """
    return docx_to_markdown(str(file_path))
