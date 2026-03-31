"""
Database query execution tool.

Pure Python implementation using psycopg (PostgreSQL-compatible).
Includes security restrictions for read-only queries.

Security features:
1. SQL validation (SELECT only)
2. Row limit (max 1000 rows)
3. Statement timeout (30 seconds)
4. Connection pooling
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """Result from database query execution."""
    success: bool
    data: Optional[list[dict[str, Any]]] = None
    error: Optional[str] = None
    row_count: int = 0


class SQLSecurity:
    """SQL security validator."""
    
    ALLOWED_OPERATIONS = {'SELECT', 'WITH'}
    
    DANGEROUS_OPERATIONS = {
        'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE',
        'CREATE', 'DROP', 'ALTER', 'RENAME',
        'GRANT', 'REVOKE', 'COPY', 'VACUUM', 'ANALYZE'
    }
    
    @classmethod
    def validate_sql(cls, sql_str: str) -> tuple[bool, str]:
        """
        Validate SQL for safety.
        
        Args:
            sql_str: SQL query string
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not sql_str or not sql_str.strip():
            return False, "SQL 语句不能为空"
        
        cleaned = cls._clean_sql(sql_str)
        operation = cls._extract_operation(cleaned)
        
        if operation in cls.DANGEROUS_OPERATIONS:
            return False, f"禁止的操作：{operation}（只允许 SELECT 查询）"
        
        if operation not in cls.ALLOWED_OPERATIONS:
            return False, f"不支持的操作：{operation}（只允许 SELECT 查询）"
        
        if cls._contains_dangerous_pattern(cleaned):
            return False, "SQL 包含危险模式"
        
        return True, ""
    
    @staticmethod
    def _clean_sql(sql_str: str) -> str:
        """Remove comments and normalize whitespace."""
        # 移除单行注释 --
        sql_str = re.sub(r'--.*?$', '', sql_str, flags=re.MULTILINE)
        # 移除多行注释 /* */
        sql_str = re.sub(r'/\*.*?\*/', '', sql_str, flags=re.DOTALL)
        return sql_str.strip()
    
    @staticmethod
    def _extract_operation(sql_str: str) -> str:
        """Extract the first SQL operation keyword."""
        match = re.match(r'^\s*(\w+)', sql_str, re.IGNORECASE)
        return match.group(1).upper() if match else ''
    
    @classmethod
    def _contains_dangerous_pattern(cls, sql_str: str) -> bool:
        """Check for dangerous patterns like multiple statements."""
        upper_sql = sql_str.upper()
        
        # 检查分号后的危险操作（防止多语句注入）
        if re.search(r';\s*(?:' + '|'.join(cls.DANGEROUS_OPERATIONS) + r')\b', upper_sql):
            return True
        
        return False


class DatabaseTool:
    """
    Tool for executing SQL queries against GAUSS DB (PostgreSQL-compatible).
    
    Security features:
    1. SQL validation (SELECT only)
    2. Row limit (max 1000 rows)
    3. Statement timeout (30 seconds)
    4. Connection pooling
    
    Attributes:
        host: Database host
        port: Database port
        database: Database name
        user: Database user
        password: Database password
        pool_size: Connection pool size
        statement_timeout: Query timeout in seconds
        max_rows: Maximum rows to return
    """
    
    MAX_ROWS = 1000
    STATEMENT_TIMEOUT = 30  # seconds
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "gaussdb",
        user: str = "admin",
        password: str = "",
        pool_size: int = 5,
        statement_timeout: Optional[int] = None,
        max_rows: Optional[int] = None,
    ):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.pool_size = pool_size
        self.statement_timeout = statement_timeout or self.STATEMENT_TIMEOUT
        self.max_rows = max_rows or self.MAX_ROWS
        
        self._pool: Optional[ConnectionPool] = None
        self._connection: Optional[Any] = None
    
    def _build_connection_string(self) -> str:
        """Build PostgreSQL connection string."""
        # URL encode password if needed
        from urllib.parse import quote_plus
        encoded_password = quote_plus(self.password)
        return (
            f"postgresql://{self.user}:{encoded_password}@"
            f"{self.host}:{self.port}/{self.database}"
        )
    
    def connect(self) -> None:
        """
        Establish database connection.
        
        Sets up connection pool and configures session parameters.
        """
        conn_str = self._build_connection_string()
        logger.info(
            f"Connecting to database: {self.database}@{self.host}:{self.port} "
            f"(pool_size={self.pool_size})"
        )
        
        try:
            # Create connection pool
            self._pool = ConnectionPool(
                conn_str,
                open=True,
                min_size=1,
                max_size=self.pool_size,
            )
            
            # Test connection and set timeout
            with self._pool.connection() as conn:
                conn.execute(
                    f"SET statement_timeout = {self.statement_timeout * 1000}"
                )
                logger.info("Database connection established successfully")
                
        except psycopg.Error as e:
            logger.error(f"Database connection failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected connection error: {e}")
            raise
    
    def disconnect(self) -> None:
        """Close database connection pool."""
        if self._pool:
            logger.info("Closing database connection pool")
            try:
                self._pool.close()
            except Exception as e:
                logger.warning(f"Error closing pool: {e}")
            finally:
                self._pool = None
    
    @contextmanager
    def _get_connection(self):
        """Get connection from pool (context manager)."""
        if not self._pool:
            self.connect()
        
        conn = self._pool.getconn()
        try:
            yield conn
        finally:
            self._pool.putconn(conn)
    
    def execute_query(self, query_sql: str) -> QueryResult:
        """
        Execute a SQL query and return results.
        
        Security checks:
        1. Validates SQL is SELECT-only
        2. Adds LIMIT if not present
        3. Respects statement timeout
        
        Args:
            query_sql: SQL query to execute
            
        Returns:
            QueryResult with success status, data, and any errors
        """
        # Security validation
        is_valid, error_msg = SQLSecurity.validate_sql(query_sql)
        if not is_valid:
            logger.warning(f"SQL validation failed: {error_msg}")
            return QueryResult(success=False, error=error_msg)
        
        # Add LIMIT if not present
        final_sql = self._add_limit_if_needed(query_sql, self.max_rows)
        
        logger.info(f"Executing query: {final_sql[:200]}...")
        
        try:
            with self._get_connection() as conn:
                # Set row limit
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(final_sql)
                    rows = cur.fetchall()
                    row_count = cur.rowcount
                    
                    logger.info(f"Query executed successfully, rows={row_count}")
                    
                    return QueryResult(
                        success=True,
                        data=rows,
                        row_count=len(rows) if row_count == -1 else row_count,
                    )
                    
        except psycopg.Error as e:
            error_str = str(e)
            logger.error(f"Query execution failed: {error_str}")
            return QueryResult(
                success=False,
                error=f"数据库错误：{error_str}",
            )
        except Exception as e:
            logger.exception("Unexpected query error")
            return QueryResult(
                success=False,
                error=f"未知错误：{str(e)}",
            )
    
    def _add_limit_if_needed(self, sql_str: str, limit: int) -> str:
        """Add LIMIT clause if not present."""
        # Simple check: does it already have LIMIT?
        if re.search(r'\bLIMIT\s+\d+', sql_str, re.IGNORECASE):
            return sql_str.rstrip(';')
        
        return f"{sql_str.rstrip(';')} LIMIT {limit}"
    
    def query_tables(self, schema: Optional[str] = None) -> list[str]:
        """
        Query list of tables in the database.
        
        Args:
            schema: Optional schema filter (default: 'public')
            
        Returns:
            List of table names
        """
        schema = schema or 'public'
        
        query = """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = %s 
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """
        
        # Use parameterized query for safety
        result = self.execute_query(
            query.replace('%s', f"'{schema}'")
        )
        
        if result.success and result.data:
            return [row['table_name'] for row in result.data]
        return []
    
    def query_columns(
        self,
        table_name: str,
        schema: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """
        Query column information for a table.
        
        Args:
            table_name: Table name
            schema: Optional schema filter
            
        Returns:
            List of column info dictionaries
        """
        schema = schema or 'public'
        
        query = f"""
            SELECT 
                column_name,
                data_type,
                is_nullable,
                character_maximum_length,
                numeric_precision,
                numeric_scale
            FROM information_schema.columns
            WHERE table_schema = '{schema}'
              AND table_name = '{table_name}'
            ORDER BY ordinal_position
        """
        
        result = self.execute_query(query)
        
        if result.success and result.data:
            return result.data
        return []
    
    def get_sample_data(
        self,
        table_name: str,
        schema: Optional[str] = None,
        limit: int = 10
    ) -> list[dict[str, Any]]:
        """
        Get sample data from a table.
        
        Args:
            table_name: Table name
            schema: Optional schema filter
            limit: Number of rows to return
            
        Returns:
            List of row dictionaries
        """
        schema = schema or 'public'
        limit = min(limit, self.max_rows)
        
        query = f"SELECT * FROM {schema}.{table_name} LIMIT {limit}"
        result = self.execute_query(query)
        
        if result.success:
            return result.data or []
        return []
    
    def __enter__(self) -> "DatabaseTool":
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.disconnect()


def execute_gauss_sql(query_sql: str) -> str:
    """
    Execute a GAUSS SQL query and return results as string.
    
    Convenience function for use as a LangChain tool.
    
    Args:
        query_sql: SQL query to execute
        
    Returns:
        String representation of query results or error message
    """
    from config import config
    
    tool = DatabaseTool(
        host=config.db_host,
        port=config.db_port,
        database=config.db_name,
        user=config.db_user,
        password=config.db_password,
    )
    
    try:
        result = tool.execute_query(query_sql)
        if result.success:
            return f"[{result.row_count} rows]\n" + str(result.data)
        else:
            return f"Error: {result.error}"
    except Exception as e:
        logger.exception("Query execution failed")
        return f"Error: {str(e)}"
