"""
Excel 配置和字段映射定义.

该模块集中管理 Excel 生成相关的所有配置，包括：
- 测试用例字段到 Excel 表头的映射
- Excel 样式配置
- 列宽配置
"""

from typing import Any


# ============================================================================
# 测试用例字段到 Excel 表头的映射
# ============================================================================

# 字段名 -> 中文表头 映射
TEST_CASE_FIELD_HEADERS: dict[str, str] = {
    "case_name": "测试用例名称",
    "level": "测试等级",
    "pre_condition": "前置条件",
    "need_generate_sql": "是否需要 SQL",
    "eval_step_descri": "测试步骤描述",
    "expected_result": "预期结果",
    "tags": "标签",
    "agent_thinking": "Agent 思考过程",
    "db_excute_result": "数据库执行结果",
}

# 字段显示顺序（按此顺序生成 Excel 列）
TEST_CASE_FIELD_ORDER: list[str] = [
    "case_name",
    "level",
    "pre_condition",
    "need_generate_sql",
    "eval_step_descri",
    "expected_result",
    "tags",
    "agent_thinking",
    "db_excute_result",
]

# 字段到列宽的映射（字符数）
TEST_CASE_COLUMN_WIDTHS: dict[str, int] = {
    "case_name": 40,
    "level": 12,
    "pre_condition": 30,
    "need_generate_sql": 15,
    "eval_step_descri": 50,
    "expected_result": 40,
    "tags": 25,
    "agent_thinking": 40,
    "db_excute_result": 40,
}

# 必填字段（不允许为空）
TEST_CASE_REQUIRED_FIELDS: list[str] = [
    "case_name",
    "level",
    "eval_step_descri",
    "expected_result",
]

# 字段值转换规则
TEST_CASE_FIELD_CONVERTERS: dict[str, Any] = {
    "need_generate_sql": lambda x: "是" if x is True else ("否" if x is False else str(x)),
    "level": lambda x: x.replace("level", "L") if isinstance(x, str) else x,
}


# ============================================================================
# Excel 样式配置
# ============================================================================

class ExcelStyleConfig:
    """Excel 样式配置类."""

    # 字体配置
    FONT_NAME: str = "微软雅黑"
    FONT_SIZE: int = 10

    # 表头样式
    HEADER_BG_COLOR: str = "4472C4"  # 蓝色背景
    HEADER_FONT_COLOR: str = "FFFFFF"  # 白色字体
    HEADER_FONT_BOLD: bool = True

    # 数据行样式
    ROW_BG_COLOR_ALT: str = "D6DCE4"  # 交替行背景色
    ROW_FONT_COLOR: str = "000000"  # 黑色字体

    # 边框配置
    BORDER_COLOR: str = "000000"
    BORDER_STYLE: str = "thin"

    # 列宽配置
    DEFAULT_COLUMN_WIDTH: int = 20
    AUTO_WIDTH_PADDING: int = 2

    # 行高配置
    DEFAULT_ROW_HEIGHT: int = 20
    HEADER_ROW_HEIGHT: int = 25


# ============================================================================
# Excel 文件命名配置
# ============================================================================

# 默认文件名前缀
DEFAULT_EXCEL_FILENAME_PREFIX: str = "测试用例_"

# 文件名日期格式
FILENAME_DATE_FORMAT: str = "%Y%m%d_%H%M%S"


# ============================================================================
# 辅助函数
# ============================================================================

def get_field_header(field_name: str) -> str:
    """
    获取字段对应的表头名称.

    Args:
        field_name: 字段名

    Returns:
        中文表头名称，如果没有映射则返回原字段名
    """
    return TEST_CASE_FIELD_HEADERS.get(field_name, field_name)


def get_ordered_fields() -> list[str]:
    """
    获取按显示顺序排列的字段列表.

    Returns:
        字段名列表
    """
    return TEST_CASE_FIELD_ORDER.copy()


def get_column_width(field_name: str) -> int:
    """
    获取指定字段的列宽.

    Args:
        field_name: 字段名

    Returns:
        列宽（字符数）
    """
    return TEST_CASE_COLUMN_WIDTHS.get(field_name, ExcelStyleConfig.DEFAULT_COLUMN_WIDTH)


def convert_field_value(field_name: str, value: Any) -> Any:
    """
    转换字段值（根据转换器配置）.

    Args:
        field_name: 字段名
        value: 原始值

    Returns:
        转换后的值
    """
    converter = TEST_CASE_FIELD_CONVERTERS.get(field_name)
    if converter:
        return converter(value)
    return value
