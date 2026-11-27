import os
from pathlib import Path
from pydantic import BaseModel

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseModel):
    # OpenAI & Cohere Configuration
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "").strip()
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "").strip()
    cohere_api_key: str = os.getenv("COHERE_API_KEY", "").strip()
    cohere_rerank_model: str = os.getenv(
        "COHERE_RERANK_MODEL", "rerank-multilingual-v3.0"
    )
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    embedding_dimension: int = int(os.getenv("EMBEDDING_DIMENSION", "1536"))
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini").strip()

    # Qdrant Configuration
    qdrant_url: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_api_key: str | None = os.getenv("QDRANT_API_KEY", None)
    qdrant_collection_name: str = os.getenv(
        "QDRANT_COLLECTION_NAME", "academic_regulations"
    )
    use_in_memory_qdrant: bool = (
        os.getenv("USE_IN_MEMORY_QDRANT", "true").lower() == "true"
    )

    # Paths
    raw_pdfs_dir: Path = BASE_DIR / "data" / "raw_pdfs"
    processed_dir: Path = BASE_DIR / "data" / "processed"
    sqlite_db_path: Path = BASE_DIR / "data" / "tdmu_chat_history.db"
    allowed_email_domain: str = "@student.tdmu.edu.vn"

    # Google OAuth & TDMU Admin Configuration
    google_client_id: str = (
        os.getenv("GOOGLE_CLIENT_ID")
        or os.getenv("NEXT_PUBLIC_GOOGLE_CLIENT_ID")
        or ""
    ).strip()
    admin_emails: list[str] = ["2224801030361@student.tdmu.edu.vn"]

    # Facebook Messenger Bot Webhook Configuration
    messenger_verify_token: str = os.getenv(
        "MESSENGER_VERIFY_TOKEN", "tdmu_rag_verify_token"
    ).strip()
    messenger_page_access_token: str = os.getenv(
        "MESSENGER_PAGE_ACCESS_TOKEN", ""
    ).strip()


settings = Settings()

