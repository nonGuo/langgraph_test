"""
测试 Excel 生成功能.
"""

import json
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.excel_client import ExcelClient, ExcelGenerationResult


def test_excel_generation():
    """测试 Excel 生成功能."""

    # 模拟测试用例数据
    test_cases = [
        {
            "case_name": "[IT 用例][表视图检查]dwb_ltc_invoice_head_i 目标表存在检查",
            "level": "level1",
            "pre_condition": "调度系统已配置目标表任务",
            "need_generate_sql": True,
            "eval_step_descri": "查询系统表，验证目标表是否存在",
            "expected_result": "表存在，返回记录数>0",
            "tags": "IT 用例_表视图/基础检查",
            "agent_thinking": "这是一个基础检查测试用例，需要验证表是否存在",
            "db_excute_result": "✅ 测试通过 (PASS)",
        },
        {
            "case_name": "[IT 用例][数据一致性] 源表目标表数据条数一致",
            "level": "level2",
            "pre_condition": "源表和目标表数据已同步完成",
            "need_generate_sql": True,
            "eval_step_descri": "分别统计源表和目标表的记录数，对比是否一致",
            "expected_result": "源表记录数 = 目标表记录数",
            "tags": "IT 用例_表视图/数据一致性",
            "agent_thinking": "需要对比源表和目标表的数据量",
            "db_excute_result": "❌ 测试失败 (FAIL)",
        },
        {
            "case_name": "[IT 用例][性能测试] 查询耗时检查",
            "level": "level3",
            "pre_condition": "表数据已加载完成",
            "need_generate_sql": False,
            "eval_step_descri": "执行典型查询，记录查询耗时",
            "expected_result": "查询耗时<5 秒",
            "tags": "IT 用例_表视图/性能测试",
            "agent_thinking": "性能测试需要人工计时",
            "db_excute_result": "N/A",
        },
    ]

    print("=" * 60)
    print("Excel 生成测试")
    print("=" * 60)

    # 创建客户端
    client = ExcelClient(output_dir="./test_excel_output")

    # 生成 Excel
    result = client.generate_excel(
        test_cases=test_cases,
        filename="测试用例生成测试.xlsx",
    )

    # 打印结果
    print(f"\n生成结果:")
    print(f"  成功：{result.success}")
    print(f"  文件路径：{result.file_path}")
    print(f"  行数：{result.row_count}")

    if result.error:
        print(f"  错误：{result.error}")

    if result.success:
        print(f"\n✅ Excel 文件生成成功!")
        print(f"   文件位置：{os.path.abspath(result.file_path)}")
    else:
        print(f"\n❌ Excel 文件生成失败!")

    return result.success


def test_field_mapping():
    """测试字段映射配置."""
    from excel_config import (
        TEST_CASE_FIELD_HEADERS,
        TEST_CASE_FIELD_ORDER,
        TEST_CASE_COLUMN_WIDTHS,
        get_field_header,
        get_ordered_fields,
        get_column_width,
        convert_field_value,
    )

    print("\n" + "=" * 60)
    print("字段映射配置测试")
    print("=" * 60)

    print("\n字段顺序:")
    for i, field in enumerate(get_ordered_fields(), 1):
        print(f"  {i}. {field}")

    print("\n字段到表头映射:")
    for field, header in TEST_CASE_FIELD_HEADERS.items():
        print(f"  {field} -> {header}")

    print("\n列宽配置:")
    for field, width in TEST_CASE_COLUMN_WIDTHS.items():
        print(f"  {field}: {width}")

    print("\n值转换测试:")
    print(f"  need_generate_sql=True -> '{convert_field_value('need_generate_sql', True)}'")
    print(f"  need_generate_sql=False -> '{convert_field_value('need_generate_sql', False)}'")
    print(f"  level='level1' -> '{convert_field_value('level', 'level1')}'")

    return True


if __name__ == "__main__":
    # 测试字段映射
    test_field_mapping()

    # 测试 Excel 生成
    success = test_excel_generation()

    sys.exit(0 if success else 1)
