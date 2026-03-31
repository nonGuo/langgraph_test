"""
Tests for DatabaseTool.

Run with: python -m pytest test_database_tool.py -v
Or: python test_database_tool.py
"""

import os
import unittest
from unittest.mock import patch, MagicMock

from tools.database_tool import DatabaseTool, SQLSecurity, QueryResult


class TestSQLSecurity(unittest.TestCase):
    """Test SQL security validation."""

    def test_valid_select_query(self):
        """Test valid SELECT query passes validation."""
        sql = "SELECT * FROM users WHERE id = 1"
        is_valid, error_msg = SQLSecurity.validate_sql(sql)
        self.assertTrue(is_valid)
        self.assertEqual(error_msg, "")

    def test_valid_select_with_where(self):
        """Test SELECT with complex WHERE clause."""
        sql = "SELECT id, name FROM users WHERE age > 18 AND status = 'active'"
        is_valid, error_msg = SQLSecurity.validate_sql(sql)
        self.assertTrue(is_valid)

    def test_valid_select_with_join(self):
        """Test SELECT with JOIN."""
        sql = """
            SELECT u.name, o.order_id
            FROM users u
            JOIN orders o ON u.id = o.user_id
            WHERE o.status = 'completed'
        """
        is_valid, error_msg = SQLSecurity.validate_sql(sql)
        self.assertTrue(is_valid)

    def test_valid_with_clause(self):
        """Test WITH clause (CTE)."""
        sql = """
            WITH active_users AS (
                SELECT id FROM users WHERE status = 'active'
            )
            SELECT * FROM active_users
        """
        is_valid, error_msg = SQLSecurity.validate_sql(sql)
        self.assertTrue(is_valid)

    def test_insert_rejected(self):
        """Test INSERT is rejected."""
        sql = "INSERT INTO users (name) VALUES ('test')"
        is_valid, error_msg = SQLSecurity.validate_sql(sql)
        self.assertFalse(is_valid)
        self.assertIn("禁止", error_msg)

    def test_update_rejected(self):
        """Test UPDATE is rejected."""
        sql = "UPDATE users SET name = 'test' WHERE id = 1"
        is_valid, error_msg = SQLSecurity.validate_sql(sql)
        self.assertFalse(is_valid)

    def test_delete_rejected(self):
        """Test DELETE is rejected."""
        sql = "DELETE FROM users WHERE id = 1"
        is_valid, error_msg = SQLSecurity.validate_sql(sql)
        self.assertFalse(is_valid)

    def test_drop_rejected(self):
        """Test DROP is rejected."""
        sql = "DROP TABLE users"
        is_valid, error_msg = SQLSecurity.validate_sql(sql)
        self.assertFalse(is_valid)

    def test_empty_sql_rejected(self):
        """Test empty SQL is rejected."""
        is_valid, error_msg = SQLSecurity.validate_sql("")
        self.assertFalse(is_valid)
        self.assertIn("不能为空", error_msg)

    def test_whitespace_only_sql_rejected(self):
        """Test whitespace-only SQL is rejected."""
        is_valid, error_msg = SQLSecurity.validate_sql("   ")
        self.assertFalse(is_valid)

    def test_sql_with_comments(self):
        """Test SQL with comments is validated correctly."""
        sql = """
            -- This is a comment
            SELECT * FROM users
            /* Multi-line comment */
            WHERE id = 1
        """
        is_valid, error_msg = SQLSecurity.validate_sql(sql)
        self.assertTrue(is_valid)

    def test_injection_attempt_rejected(self):
        """Test SQL injection attempt is rejected."""
        sql = "SELECT * FROM users; DROP TABLE users; --"
        is_valid, error_msg = SQLSecurity.validate_sql(sql)
        # Should detect the dangerous pattern after semicolon
        self.assertFalse(is_valid)


class TestDatabaseTool(unittest.TestCase):
    """Test DatabaseTool functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.db_config = {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", "5432")),
            "database": os.getenv("DB_NAME", "gaussdb"),
            "user": os.getenv("DB_USER", "admin"),
            "password": os.getenv("DB_PASSWORD", ""),
        }

    def test_initialization(self):
        """Test DatabaseTool initializes with correct parameters."""
        tool = DatabaseTool(
            host="test_host",
            port=5433,
            database="test_db",
            user="test_user",
            password="test_pass",
            pool_size=10,
            statement_timeout=60,
            max_rows=500,
        )
        self.assertEqual(tool.host, "test_host")
        self.assertEqual(tool.port, 5433)
        self.assertEqual(tool.database, "test_db")
        self.assertEqual(tool.pool_size, 10)
        self.assertEqual(tool.statement_timeout, 60)
        self.assertEqual(tool.max_rows, 500)

    def test_default_values(self):
        """Test default parameter values."""
        tool = DatabaseTool()
        self.assertEqual(tool.host, "localhost")
        self.assertEqual(tool.port, 5432)
        self.assertEqual(tool.database, "gaussdb")
        self.assertEqual(tool.pool_size, 5)
        self.assertEqual(tool.max_rows, 1000)
        self.assertEqual(tool.statement_timeout, 30)

    def test_build_connection_string(self):
        """Test connection string building."""
        tool = DatabaseTool(
            host="localhost",
            port=5432,
            database="testdb",
            user="testuser",
            password="testpass",
        )
        conn_str = tool._build_connection_string()
        self.assertIn("postgresql://testuser:testpass@localhost:5432/testdb", conn_str)

    def test_add_limit_if_needed(self):
        """Test LIMIT clause addition."""
        tool = DatabaseTool()
        
        # Should add LIMIT
        sql = "SELECT * FROM users"
        result = tool._add_limit_if_needed(sql, 100)
        self.assertIn("LIMIT 100", result.upper())
        
        # Should not add LIMIT if already present
        sql_with_limit = "SELECT * FROM users LIMIT 50"
        result = tool._add_limit_if_needed(sql_with_limit, 100)
        self.assertNotIn("LIMIT 100", result.upper())
        self.assertIn("LIMIT 50", result.upper())

    def test_query_result_dataclass(self):
        """Test QueryResult dataclass."""
        # Success case
        result = QueryResult(
            success=True,
            data=[{"id": 1, "name": "test"}],
            row_count=1,
        )
        self.assertTrue(result.success)
        self.assertEqual(result.row_count, 1)
        self.assertIsNone(result.error)
        
        # Error case
        result = QueryResult(
            success=False,
            error="Connection failed",
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error, "Connection failed")
        self.assertIsNone(result.data)

    @unittest.skipUnless(
        os.getenv("DB_HOST") and os.getenv("DB_PASSWORD"),
        "Database credentials not set in environment"
    )
    def test_context_manager(self):
        """Test context manager usage."""
        tool = DatabaseTool(
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("DB_NAME", "gaussdb"),
            user=os.getenv("DB_USER", "admin"),
            password=os.getenv("DB_PASSWORD"),
        )
        
        with tool:
            # Connection should be established
            self.assertIsNotNone(tool._pool)
        
        # After context exit, pool should be closed
        self.assertIsNone(tool._pool)

    @unittest.skipUnless(
        os.getenv("DB_HOST") and os.getenv("DB_PASSWORD"),
        "Database credentials not set in environment"
    )
    def test_execute_query_basic(self):
        """Test basic query execution."""
        tool = DatabaseTool(
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("DB_NAME", "gaussdb"),
            user=os.getenv("DB_USER", "admin"),
            password=os.getenv("DB_PASSWORD"),
        )
        
        try:
            tool.connect()
            
            # Test a simple query
            result = tool.execute_query("SELECT 1 as test")
            self.assertTrue(result.success)
            self.assertEqual(result.row_count, 1)
            self.assertEqual(result.data[0]["test"], 1)
            
        finally:
            tool.disconnect()

    @unittest.skipUnless(
        os.getenv("DB_HOST") and os.getenv("DB_PASSWORD"),
        "Database credentials not set in environment"
    )
    def test_execute_query_invalid_sql(self):
        """Test query execution with invalid SQL."""
        tool = DatabaseTool(
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("DB_NAME", "gaussdb"),
            user=os.getenv("DB_USER", "admin"),
            password=os.getenv("DB_PASSWORD"),
        )
        
        try:
            tool.connect()
            
            # Test INSERT (should be rejected by security check)
            result = tool.execute_query("INSERT INTO test VALUES (1)")
            self.assertFalse(result.success)
            self.assertIn("禁止", result.error)
            
        finally:
            tool.disconnect()


class TestQueryResult(unittest.TestCase):
    """Test QueryResult dataclass."""

    def test_success_result(self):
        """Test successful query result."""
        result = QueryResult(
            success=True,
            data=[{"id": 1}],
            row_count=1,
        )
        self.assertTrue(result.success)
        self.assertEqual(len(result.data), 1)
        self.assertEqual(result.row_count, 1)

    def test_error_result(self):
        """Test error query result."""
        result = QueryResult(
            success=False,
            error="Database error",
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error, "Database error")
        self.assertIsNone(result.data)
        self.assertEqual(result.row_count, 0)


if __name__ == "__main__":
    # Run tests
    unittest.main(verbosity=2)
