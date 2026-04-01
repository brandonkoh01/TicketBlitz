import os
import threading
from typing import Optional

from supabase import Client, create_client

_client: Optional[Client] = None
_client_lock = threading.Lock()


def db_configured() -> bool:
    return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_KEY"))


def get_db() -> Client:
    global _client

    if _client is None:
        with _client_lock:
            if _client is None:
                url = os.getenv("SUPABASE_URL")
                key = os.getenv("SUPABASE_SERVICE_KEY")

                if not url or not key:
                    raise RuntimeError(
                        "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set before using the database client"
                    )

                _client = create_client(url, key)

    return _client
