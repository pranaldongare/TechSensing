from typing import List, Optional

from pydantic import BaseModel, Field


class Page(BaseModel):
    number: int
    text: str
    images: Optional[List[str]] = Field(default_factory=list)


class Document(BaseModel):
    id: str
    type: str
    file_name: str
    content: List[Page] = Field(default_factory=list)
    title: str
    full_text: str
    summary: Optional[str] = None
    has_sql_data: bool = Field(
        default=False,
        description="Whether this document has structured data loaded into SQLite for SQL querying.",
    )
    spreadsheet_schema: Optional[str] = Field(
        default=None,
        description="Optional human-readable SQL schema for spreadsheet data loaded from this document.",
    )


class Documents(BaseModel):
    documents: List[Document] = Field(default_factory=list)
    thread_id: str
    user_id: str
