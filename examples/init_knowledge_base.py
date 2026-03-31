"""
知识库初始化和使用示例.

运行此脚本以:
1. 安装知识库所需依赖
2. 导入示例文档到知识库
3. 测试知识库检索功能

使用方法:
    python examples/init_knowledge_base.py
"""

import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.knowledge_tool import KnowledgeTool, init_knowledge_base


def create_sample_documents():
    """创建示例测试用例文档."""

    documents = [
        # 文档 1: 测试用例设计规范
        """
# 测试用例设计规范

## 1. 测试用例命名规范

测试用例名称应该清晰表达测试目的，格式为：
`[IT 用例/UT 用例][测试类别] 测试对象_预期结果`

示例:
- [IT 用例][表视图检查] dwb_invoice_i 目标表存在检查
- [IT 用例][主键检查] dwb_invoice_i 业务主键唯一性检查
- [IT 用例][数据一致性] 源表目标表数据条数一致

## 2. 测试用例等级定义

- **level1**: 核心业务逻辑，关键路径测试，必须自动化
- **level2**: 重要业务逻辑，边界条件测试，推荐自动化
- **level3**: 一般功能测试，可选自动化
- **level4**: 辅助功能测试，人工测试

## 3. SQL 验证规范

所有可自动化的测试用例都应该有对应的验证 SQL。

SQL 编写要求:
1. 必须返回 PASS/FAIL 结果
2. 使用 CASE WHEN 结构进行断言
3. 考虑边界条件和异常数据
4. 添加必要的注释说明业务逻辑

## 4. 常见测试类型及 SQL 模板

### 4.1 表存在性检查

```sql
SELECT CASE
    WHEN COUNT(*) > 0 THEN 'PASS'
    ELSE 'FAIL'
END as test_result
FROM information_schema.tables
WHERE table_schema = '目标 schema'
  AND table_name = '目标表名'
```

### 4.2 主键唯一性检查

```sql
SELECT CASE
    WHEN COUNT(*) = COUNT(DISTINCT 主键字段) THEN 'PASS'
    ELSE 'FAIL'
END as test_result
FROM 目标表
WHERE 主键字段 IS NOT NULL
```

### 4.3 数据一致性检查

```sql
SELECT CASE
    WHEN source_cnt = target_cnt THEN 'PASS'
    ELSE 'FAIL'
END as test_result
FROM (
    SELECT
        (SELECT COUNT(*) FROM 源表) as source_cnt,
        (SELECT COUNT(*) FROM 目标表) as target_cnt
) t
```

### 4.4 数据倾斜率检查

```sql
SELECT CASE
    WHEN MAX(node_ratio) < 0.1 THEN 'PASS'
    ELSE 'FAIL'
END as test_result
FROM (
    SELECT
        ABS(cnt - avg_cnt) * 1.0 / avg_cnt as node_ratio
    FROM (
        SELECT
            node_id,
            COUNT(*) as cnt,
            AVG(COUNT(*)) OVER () as avg_cnt
        FROM 目标表
        GROUP BY node_id
    ) t
) t2
```
""",

        # 文档 2: 数据质量检查规范
        """
# 数据质量检查规范 (DQ)

## 1. 完整性检查

### 1.1 空值检查
检查关键字段是否允许为空。

```sql
SELECT CASE
    WHEN COUNT(*) = 0 THEN 'PASS'
    ELSE 'FAIL'
END as test_result
FROM 目标表
WHERE 关键字段 IS NULL
```

### 1.2 记录数波动检查
检查数据量是否有异常波动。

```sql
SELECT CASE
    WHEN ABS(today_cnt - yesterday_cnt) * 1.0 / yesterday_cnt < 0.3 THEN 'PASS'
    ELSE 'FAIL'
END as test_result
FROM (
    SELECT
        (SELECT COUNT(*) FROM 目标表 WHERE dt = '2024-01-01') as today_cnt,
        (SELECT COUNT(*) FROM 目标表 WHERE dt = '2024-01-02') as yesterday_cnt
) t
```

## 2. 准确性检查

### 2.1 枚举值检查
检查字段值是否在允许范围内。

```sql
SELECT CASE
    WHEN COUNT(*) = 0 THEN 'PASS'
    ELSE 'FAIL'
END as test_result
FROM 目标表
WHERE 字段名 NOT IN ('允许值 1', '允许值 2', '允许值 3')
```

### 2.2 数值范围检查
检查数值是否在合理范围内。

```sql
SELECT CASE
    WHEN COUNT(*) = 0 THEN 'PASS'
    ELSE 'FAIL'
END as test_result
FROM 目标表
WHERE 数值字段 < 0 OR 数值字段 > 1000000
```

## 3. 及时性检查

### 3.1 数据产出时间检查
检查数据是否按时产出。

```sql
SELECT CASE
    WHEN DATEDIFF(mi, 预期时间，实际时间) < 30 THEN 'PASS'
    ELSE 'FAIL'
END as test_result
FROM (
    SELECT
        '2024-01-01 06:00:00' as 预期时间，
        MAX(create_time) as 实际时间
    FROM 目标表
    WHERE dt = '2024-01-01'
) t
```
""",

        # 文档 3: 常见业务场景 SQL 示例
        """
# 常见业务场景 SQL 示例

## 场景 1: 环比增长检查

检查今日数据相比昨日是否有合理增长。

```sql
WITH daily_stats AS (
    SELECT
        dt,
        COUNT(*) as order_cnt,
        SUM(amount) as total_amount
    FROM dwb_order_i
    WHERE dt >= '2024-01-01' AND dt <= '2024-01-31'
    GROUP BY dt
)
SELECT CASE
    WHEN AVG(daily_growth_rate) BETWEEN -0.1 AND 0.5 THEN 'PASS'
    ELSE 'FAIL'
END as test_result
FROM (
    SELECT
        (order_cnt - LAG(order_cnt) OVER (ORDER BY dt)) * 1.0 /
        LAG(order_cnt) OVER (ORDER BY dt) as daily_growth_rate
    FROM daily_stats
) t
WHERE daily_growth_rate IS NOT NULL
```

## 场景 2: 关联完整性检查

检查关联表之间的数据完整性。

```sql
SELECT CASE
    WHEN orphan_count = 0 THEN 'PASS'
    ELSE 'FAIL'
END as test_result
FROM (
    SELECT COUNT(*) as orphan_count
    FROM 订单表 o
    LEFT JOIN 用户表 u ON o.user_id = u.id
    WHERE u.id IS NULL
) t
```

## 场景 3: 状态流转检查

检查订单状态是否符合预期的流转规则。

```sql
SELECT CASE
    WHEN invalid_transition_count = 0 THEN 'PASS'
    ELSE 'FAIL'
END as test_result
FROM (
    SELECT COUNT(*) as invalid_transition_count
    FROM (
        SELECT order_id, old_status, new_status
        FROM (
            SELECT
                order_id,
                LAG(status) OVER (PARTITION BY order_id ORDER BY update_time) as old_status,
                status as new_status
            FROM 订单状态变更表
        ) t
        WHERE old_status IS NOT NULL
    ) t2
    WHERE
        -- 无效状态流转规则
        (old_status = 'CANCELLED' AND new_status != 'CANCELLED')
        OR (old_status = 'COMPLETED' AND new_status NOT IN ('COMPLETED', 'REFUNDED'))
) t
```

## 场景 4: 金额一致性检查

检查明细金额与汇总金额是否一致。

```sql
SELECT CASE
    WHEN ABS(diff) < 0.01 THEN 'PASS'
    ELSE 'FAIL'
END as test_result
FROM (
    SELECT
        (SELECT SUM(amount) FROM 订单明细表 WHERE dt = '2024-01-01') as detail_sum,
        (SELECT total_amount FROM 订单汇总表 WHERE dt = '2024-01-01') as summary_sum,
        ABS(
            (SELECT SUM(amount) FROM 订单明细表 WHERE dt = '2024-01-01') -
            (SELECT total_amount FROM 订单汇总表 WHERE dt = '2024-01-01')
        ) as diff
) t
```
""",

        # 文档 4: 测试用例模板
        """
# 测试用例模板

## 模板 1: 表视图检查类

```json
{
  "case_name": "[IT 用例][表视图检查]{schema}.{table_name}_目标表存在检查",
  "level": "level1",
  "pre_condition": "调度系统已配置目标表任务",
  "need_generate_sql": true,
  "eval_step_descri": "查询系统表，验证目标表是否存在",
  "expected_result": "表存在，返回记录数>0",
  "tags": "IT 用例_表视图/基础检查"
}
```

## 模板 2: 主键唯一性检查

```json
{
  "case_name": "[IT 用例][主键检查]{schema}.{table_name}_业务主键唯一性检查",
  "level": "level1",
  "pre_condition": "源表和目标表数据已加载完成",
  "need_generate_sql": true,
  "eval_step_descri": "查询目标表，按主键分组，统计每组数量，验证是否存在重复",
  "expected_result": "无重复主键，每组数量为 1",
  "tags": "IT 用例_表视图/数据质量"
}
```

## 模板 3: 数据一致性检查

```json
{
  "case_name": "[IT 用例][数据一致性]{schema}.{table_name}_源表目标表数据条数一致",
  "level": "level2",
  "pre_condition": "数据同步任务已完成",
  "need_generate_sql": true,
  "eval_step_descri": "分别统计源表和目标表的记录数，对比是否一致",
  "expected_result": "源表记录数 = 目标表记录数",
  "tags": "IT 用例_表视图/数据一致性"
}
```

## 模板 4: 数据倾斜检查

```json
{
  "case_name": "[IT 用例][性能检查]{schema}.{table_name}_数据倾斜率检查",
  "level": "level2",
  "pre_condition": "表数据已加载完成",
  "need_generate_sql": true,
  "eval_step_descri": "计算各节点数据量与平均值的偏差率",
  "expected_result": "最大倾斜率<0.1",
  "tags": "IT 用例_表视图/性能检查"
}
```

## 模板 5: 空值检查

```json
{
  "case_name": "[IT 用例][数据质量]{schema}.{table_name}_关键字段非空检查",
  "level": "level1",
  "pre_condition": "表数据已加载完成",
  "need_generate_sql": true,
  "eval_step_descri": "检查业务主键和关键字段是否为空",
  "expected_result": "关键字段无空值",
  "tags": "IT 用例_表视图/数据质量"
}
```
"""
    ]

    return documents


def main():
    """主函数：初始化知识库并导入示例文档."""

    print("=" * 60)
    print("知识库初始化脚本")
    print("=" * 60)

    # 创建知识库工具实例
    print("\n1. 创建知识库工具...")
    tool = KnowledgeTool(
        collection_name="test_case_knowledge",
        persist_directory="./knowledge_base",
        top_k=3,
        score_threshold=0.3,
    )

    # 创建示例文档
    print("\n2. 准备示例文档...")
    documents = create_sample_documents()
    print(f"   共 {len(documents)} 个示例文档")

    # 导入文档
    print("\n3. 导入文档到知识库...")

    metadatas = [
        {"source": "测试用例设计规范.md", "type": "spec"},
        {"source": "数据质量检查规范.md", "type": "spec"},
        {"source": "常见业务场景 SQL 示例.md", "type": "example"},
        {"source": "测试用例模板.md", "type": "template"},
    ]

    chunk_count = tool.add_documents(documents, metadatas)
    print(f"   成功导入 {chunk_count} 个文档片段")

    # 显示统计信息
    print("\n4. 知识库统计信息:")
    stats = tool.get_collection_stats()
    for key, value in stats.items():
        print(f"   - {key}: {value}")

    # 测试检索
    print("\n5. 测试检索功能...")

    test_queries = [
        "主键唯一性检查 SQL",
        "数据一致性检查",
        "测试用例等级定义",
    ]

    for query in test_queries:
        print(f"\n   检索：'{query}'")
        result = tool.search(query)
        if result.success:
            print(f"   ✅ 检索成功 (score: {result.score:.2f}, docs: {len(result.source_documents)})")
        else:
            print(f"   ❌ 检索失败：{result.error}")

    print("\n" + "=" * 60)
    print("知识库初始化完成!")
    print("=" * 60)

    return tool


if __name__ == "__main__":
    main()
