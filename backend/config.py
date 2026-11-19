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
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    cohere_api_key: str = os.getenv("COHERE_API_KEY", "")
    cohere_rerank_model: str = os.getenv(
        "COHERE_RERANK_MODEL", "rerank-multilingual-v3.0"
    )
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    embedding_dimension: int = int(os.getenv("EMBEDDING_DIMENSION", "1536"))
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")

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


settings = Settings()

