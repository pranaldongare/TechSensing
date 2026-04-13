"""
SQLite Manager for Excel/CSV Data
Manages per-user, per-thread in-memory SQLite databases that store
spreadsheet data as queryable SQL tables.
"""

import os
from pathlib import Path
import re
import sqlite3
import traceback
from typing import Dict, List, Optional, Tuple

import pandas as pd

from core.parsers.excel_utils import (
    deduplicate_columns,
    detect_merged_header_rows,
    find_header_row,
    flatten_multiindex_columns,
)


def _clean_dataframe_unicode(df: pd.DataFrame) -> pd.DataFrame:
    """Strip \u00a0, zero-width chars, and other unicode whitespace from all string cells."""
    for col in df.columns:
        if df[col].dtype == object or str(df[col].dtype) == "string":
            df[col] = df[col].apply(
                lambda x: (
                    re.sub(r"[\u00a0\u200b\u200c\u200d\ufeff\xa0]+", " ", str(x))
                    .replace("\n", " ")
                    .strip()
                    if isinstance(x, str) and str(x) != "nan"
                    else x
                )
            )
    return df


class SQLiteManager:
    """
    Manages SQLite databases for spreadsheet data.
    Each (user_id, thread_id) pair gets its own persistent file-based SQLite
    database stored at data/{user_id}/threads/{thread_id}/sqlite/thread.db.
    The doc_id → table_name mapping is persisted in a __doc_table_registry table
    so it survives process restarts without re-parsing the original files.
    """

    # Class-level storage: { (user_id, thread_id): sqlite3.Connection }
    _connections: Dict[Tuple[str, str], sqlite3.Connection] = {}

    # Track which tables belong to which document:
    # { (user_id, thread_id): { doc_id: [table_name, ...] } }
    _table_registry: Dict[Tuple[str, str], Dict[str, List[str]]] = {}

    @classmethod
    def _get_db_path(cls, user_id: str, thread_id: str) -> str:
        """Return the file path for a thread's persistent SQLite database."""
        db_dir = os.path.join("data", user_id, "threads", thread_id, "sqlite")
        os.makedirs(db_dir, exist_ok=True)
        return os.path.join(db_dir, "thread.db")

    @classmethod
    def _ensure_registry_table(cls, conn: sqlite3.Connection) -> None:
        """Create the internal registry table if it does not exist."""
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS __doc_table_registry (
                doc_id TEXT NOT NULL,
                table_name TEXT NOT NULL,
                PRIMARY KEY (doc_id, table_name)
            )
            """
        )
        conn.commit()

    @classmethod
    def _reload_registry(cls, user_id: str, thread_id: str) -> None:
        """Populate the in-memory registry dict from the persisted DB table.

        Also migrates any legacy table names that contain hyphens
        (from UUIDs) to use underscores so SQL queries work without quoting.
        """
        key = (user_id, thread_id)
        conn = cls._connections[key]
        cls._ensure_registry_table(conn)
        cursor = conn.execute(
            "SELECT doc_id, table_name FROM __doc_table_registry"
        )
        registry: Dict[str, List[str]] = {}
        for doc_id, table_name in cursor.fetchall():
            # Migrate legacy hyphenated table names → underscores
            if "-" in table_name:
                new_name = table_name.replace("-", "_")
                try:
                    conn.execute(
                        f'ALTER TABLE "{table_name}" RENAME TO "{new_name}";'
                    )
                    conn.execute(
                        "UPDATE __doc_table_registry "
                        "SET table_name = ? WHERE doc_id = ? AND table_name = ?",
                        (new_name, doc_id, table_name),
                    )
                    conn.commit()
                    print(
                        f"[SQLiteManager] Migrated table: {table_name} → {new_name}"
                    )
                    table_name = new_name
                except Exception as e:
                    print(f"[SQLiteManager] Table rename failed ({table_name}): {e}")
            registry.setdefault(doc_id, []).append(table_name)
        cls._table_registry[key] = registry

    @classmethod
    def get_connection(cls, user_id: str, thread_id: str) -> sqlite3.Connection:
        """Get or create a persistent file-based SQLite connection for a user/thread pair."""
        key = (user_id, thread_id)
        if key not in cls._connections:
            db_path = cls._get_db_path(user_id, thread_id)
            conn = sqlite3.connect(db_path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL;")
            cls._connections[key] = conn
            cls._table_registry[key] = {}
            # Rebuild in-memory registry from the persisted DB on first open
            cls._reload_registry(user_id, thread_id)
        return cls._connections[key]

    @classmethod
    def close_connection(cls, user_id: str, thread_id: str):
        """Close and remove the SQLite connection for a user/thread pair."""
        key = (user_id, thread_id)
        if key in cls._connections:
            try:
                cls._connections[key].close()
            except Exception:
                pass
            del cls._connections[key]
        if key in cls._table_registry:
            del cls._table_registry[key]

    @classmethod
    def _sanitize_table_name(cls, name: str) -> str:
        """Create a safe SQL table name from a sheet/file name."""
        # Remove non-alphanumeric chars (except underscores)
        sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", str(name).strip())
        # Ensure it doesn't start with a digit
        if sanitized and sanitized[0].isdigit():
            sanitized = f"t_{sanitized}"
        # Collapse multiple underscores
        sanitized = re.sub(r"_+", "_", sanitized).strip("_")
        return sanitized.lower() or "unnamed_table"

    @classmethod
    def _sanitize_column_name(cls, name: str) -> str:
        """Create a safe SQL column name."""
        sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", str(name).strip())
        if sanitized and sanitized[0].isdigit():
            sanitized = f"col_{sanitized}"
        sanitized = re.sub(r"_+", "_", sanitized).strip("_")
        return sanitized.lower() or "unnamed_col"

    @classmethod
    def load_spreadsheet(
        cls,
        user_id: str,
        thread_id: str,
        doc_id: str,
        file_path: str,
        file_name: str,
    ) -> Dict[str, List[dict]]:
        """
        Load an Excel/CSV file into the SQLite database.
        Each sheet becomes a separate table.

        Returns:
            Dict mapping table_name -> list of column info dicts
        """
        conn = cls.get_connection(user_id, thread_id)
        key = (user_id, thread_id)
        ext = Path(file_path).suffix.lower()
        base_name = Path(file_name).stem

        tables_created = {}
        table_names = []

        try:
            if ext == ".csv":
                df = pd.read_csv(file_path)
                # Clean unicode whitespace from all cells
                df = _clean_dataframe_unicode(df)
                # Clean and deduplicate column names
                df.columns = deduplicate_columns(
                    [cls._sanitize_column_name(c) for c in df.columns]
                )
                df = df.convert_dtypes()

                table_name = cls._sanitize_table_name(base_name)
                # Make table name unique by suffixing with doc_id
                # Replace hyphens in UUID to keep the name SQL-safe
                table_name = f"{table_name}_{doc_id.replace('-', '_')}"

                df.to_sql(table_name, conn, index=False, if_exists="replace")
                tables_created[table_name] = cls._get_column_info(conn, table_name)
                table_names.append(table_name)

            elif ext in {".xls", ".xlsx"}:
                if ext == ".xlsx":
                    xls = pd.ExcelFile(file_path, engine="openpyxl")
                else:
                    xls = pd.ExcelFile(file_path, engine="xlrd")

                for sheet_name in xls.sheet_names:
                    # Detect Header to ensure correct columns
                    header_idx, _ = find_header_row(file_path, sheet_name)

                    # Detect multi-level headers from merged cells (.xlsx only)
                    if ext == ".xlsx":
                        header_param = detect_merged_header_rows(
                            file_path, sheet_name, header_idx
                        )
                    else:
                        header_param = header_idx

                    df = pd.read_excel(xls, sheet_name=sheet_name, header=header_param)

                    # Flatten MultiIndex columns if multi-level headers were detected
                    if isinstance(header_param, list):
                        df = flatten_multiindex_columns(df)

                    # Clean unicode whitespace from all cells
                    df = _clean_dataframe_unicode(df)

                    # Clean and deduplicate column names
                    df.columns = deduplicate_columns(
                        [cls._sanitize_column_name(c) for c in df.columns]
                    )

                    # Drop fully empty rows
                    df = df.dropna(how="all")

                    # Convert dtypes for better type inference
                    df = df.convert_dtypes()

                    # Build table name: filename_sheetname_docid
                    if len(xls.sheet_names) == 1:
                        table_name = cls._sanitize_table_name(base_name)
                    else:
                        table_name = cls._sanitize_table_name(
                            f"{base_name}_{sheet_name}"
                        )
                    # Replace hyphens in UUID to keep the name SQL-safe
                    table_name = f"{table_name}_{doc_id.replace('-', '_')}"

                    df.to_sql(table_name, conn, index=False, if_exists="replace")
                    tables_created[table_name] = cls._get_column_info(conn, table_name)
                    table_names.append(table_name)

            # Register tables for this document (in-memory + persisted)
            if key not in cls._table_registry:
                cls._table_registry[key] = {}
            cls._table_registry[key][doc_id] = table_names

            # Persist doc_id → table_name mapping so it survives restarts
            cls._ensure_registry_table(conn)
            for tname in table_names:
                conn.execute(
                    "INSERT OR IGNORE INTO __doc_table_registry (doc_id, table_name) "
                    "VALUES (?, ?)",
                    (doc_id, tname),
                )
            conn.commit()

        except Exception as e:
            print(f"[SQLiteManager] Error loading {file_name}: {e}")
            traceback.print_exc()

        return tables_created

    @classmethod
    def _get_column_info(cls, conn: sqlite3.Connection, table_name: str) -> List[dict]:
        """Get column information for a table."""
        cursor = conn.cursor()
        cursor.execute(f'PRAGMA table_info("{table_name}");')
        columns = cursor.fetchall()
        return [
            {
                "name": col[1],
                "type": col[2],
                "nullable": not col[3],  # notnull flag
            }
            for col in columns
        ]

    @classmethod
    def get_schema(cls, user_id: str, thread_id: str) -> Optional[str]:
        """
        Get a human-readable schema description for all tables in this user/thread's DB.
        Returns None if no tables exist.
        """
        key = (user_id, thread_id)
        if key not in cls._connections:
            return None

        conn = cls._connections[key]
        cursor = conn.cursor()
        # Exclude __doc_table_registry — it is an internal bookkeeping table
        # and must not be exposed as user data in schema descriptions.
        cursor.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name != '__doc_table_registry';"
        )
        tables = cursor.fetchall()

        if not tables:
            return None

        schema_parts = []
        for (table_name,) in tables:
            cursor.execute(f'PRAGMA table_info("{table_name}");')
            columns = cursor.fetchall()

            col_lines = []
            for col in columns:
                col_name = col[1]
                col_type = col[2]
                col_lines.append(f"  - {col_name} ({col_type})")

            # Get row count
            try:
                cursor.execute(f'SELECT COUNT(*) FROM "{table_name}";')
                row_count = cursor.fetchone()[0]
            except Exception:
                row_count = "unknown"

            # Get a sample of first 3 rows for context
            try:
                cursor.execute(f'SELECT * FROM "{table_name}" LIMIT 3;')
                sample_rows = cursor.fetchall()
                col_names = [col[1] for col in columns]
                sample_text = ""
                if sample_rows:
                    sample_lines = []
                    for row in sample_rows:
                        row_dict = dict(zip(col_names, row))
                        sample_lines.append(f"    {row_dict}")
                    sample_text = f"\n  Sample rows:\n" + "\n".join(sample_lines)
            except Exception:
                sample_text = ""

            schema_parts.append(
                f'Table: "{table_name}"\n'
                f"  Rows: {row_count}\n"
                f"  Columns:\n" + "\n".join(col_lines) + sample_text
            )

        return "\n\n".join(schema_parts)

    @classmethod
    def execute_query(cls, user_id: str, thread_id: str, query: str, max_rows: int = 500) -> Dict:
        """
        Execute a SQL query against the user/thread's SQLite database.
        Only SELECT queries are allowed for safety.

        Returns:
            Dict with 'success', 'data' or 'error', and 'row_count' keys
        """
        key = (user_id, thread_id)
        if key not in cls._connections:
            return {
                "success": False,
                "error": "No spreadsheet data loaded for this session.",
                "data": None,
                "row_count": 0,
            }

        conn = cls._connections[key]

        # Security: only allow SELECT statements
        normalized = query.strip().upper()
        if not normalized.startswith("SELECT"):
            return {
                "success": False,
                "error": "Only SELECT queries are allowed. Do not use INSERT, UPDATE, DELETE, DROP, or ALTER.",
                "data": None,
                "row_count": 0,
            }

        # Block dangerous keywords even in SELECT
        dangerous = ["DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE", "ATTACH"]
        for keyword in dangerous:
            # Match the keyword as a standalone word (not part of column names)
            if re.search(rf"\b{keyword}\b", normalized):
                return {
                    "success": False,
                    "error": f"Query contains disallowed keyword: {keyword}",
                    "data": None,
                    "row_count": 0,
                }

        try:
            df = pd.read_sql_query(query, conn)
            # Limit output to avoid overwhelming the LLM
            truncated = max_rows is not None and len(df) > max_rows
            if truncated:
                result_df = df.head(max_rows)
            else:
                result_df = df

            result_text = result_df.to_markdown(index=False)

            return {
                "success": True,
                "data": result_text,
                "row_count": len(df),
                "truncated": truncated,
                "columns": list(df.columns),
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"SQL Error: {str(e)}",
                "data": None,
                "row_count": 0,
            }

    @classmethod
    def has_spreadsheet_data(cls, user_id: str, thread_id: str) -> bool:
        """Check if there's any spreadsheet data loaded for this user/thread.

        Excludes __doc_table_registry, which is always created by get_connection()
        and is an internal bookkeeping table, not user spreadsheet data.
        """
        key = (user_id, thread_id)
        if key not in cls._connections:
            return False
        conn = cls._connections[key]
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name != '__doc_table_registry';"
            )
            tables = cursor.fetchall()
            return len(tables) > 0
        except Exception:
            return False

    @classmethod
    def get_tables_for_document(
        cls, user_id: str, thread_id: str, doc_id: str
    ) -> List[str]:
        """Get the table names associated with a specific document."""
        key = (user_id, thread_id)
        if key not in cls._table_registry:
            return []
        return cls._table_registry[key].get(doc_id, [])

    @classmethod
    def drop_tables_for_document(
        cls, user_id: str, thread_id: str, doc_id: str
    ) -> None:
        """Drop all SQLite tables associated with a specific document."""
        key = (user_id, thread_id)
        table_names = cls.get_tables_for_document(user_id, thread_id, doc_id)
        if not table_names:
            return
        if key not in cls._connections:
            return
        conn = cls._connections[key]
        for table_name in table_names:
            try:
                conn.execute(f'DROP TABLE IF EXISTS "{table_name}";')
                print(f"[SQLiteManager] Dropped table {table_name} for doc {doc_id}")
            except Exception as e:
                print(f"[SQLiteManager] Error dropping table {table_name}: {e}")
        # Remove from persisted registry table
        try:
            conn.execute(
                "DELETE FROM __doc_table_registry WHERE doc_id = ?", (doc_id,)
            )
        except Exception:
            pass
        conn.commit()
        # Remove from in-memory registry
        if key in cls._table_registry and doc_id in cls._table_registry[key]:
            del cls._table_registry[key][doc_id]

    @classmethod
    def reload_from_files(
        cls, user_id: str, thread_id: str, files_info: List[dict]
    ) -> None:
        """
        Ensure spreadsheet data is available in SQLite for the given documents.

        With persistent SQLite, data survives process restarts so this method
        only re-parses files whose doc_id is NOT already in the persisted
        __doc_table_registry (i.e., genuinely missing, not just evicted from
        the in-memory connection dict).

        Args:
            user_id: The user ID.
            thread_id: The thread ID.
            files_info: List of dicts with {'path': str, 'file_name': str, 'doc_id': str}
        """
        # Opening the connection also calls _reload_registry(), populating the
        # in-memory registry from the persisted DB.
        cls.get_connection(user_id, thread_id)
        key = (user_id, thread_id)

        # Check and load each file if needed
        for file_info in files_info:
            doc_id = file_info.get("doc_id")

            # If tables for this doc are already registered (from DB or prior load), skip it
            if key in cls._table_registry and doc_id in cls._table_registry[key]:
                continue

            file_path = file_info.get("path")
            file_name = file_info.get("file_name")

            if not file_path or not os.path.exists(file_path):
                print(f"[SQLiteManager] File not found for reload: {file_path}")
                continue

            try:
                # Load the file
                print(
                    f"[SQLiteManager] Reloading {file_name} for thread {thread_id}..."
                )
                cls.load_spreadsheet(
                    user_id=user_id,
                    thread_id=thread_id,
                    doc_id=doc_id,
                    file_path=file_path,
                    file_name=file_name,
                )
            except Exception as e:
                print(f"[SQLiteManager] Error reloading {file_name}: {e}")
                traceback.print_exc()
