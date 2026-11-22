import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
    # FE origins allowed by CORS (comma-separated). Default covers local dev.
    FE_ORIGINS = [
        o.strip()
        for o in os.environ.get(
            "FE_ORIGINS",
            "http://localhost:8080,http://127.0.0.1:8080,http://localhost:5500",
        ).split(",")
        if o.strip()
    ]
    WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
    WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
    JWT_TTL_SECONDS = int(os.environ.get("JWT_TTL_SECONDS", "900"))  # 15 min
    CACHE_PRODUCTS_TTL = int(os.environ.get("CACHE_PRODUCTS_TTL", "60"))
    CACHE_DASHBOARD_TTL = int(os.environ.get("CACHE_DASHBOARD_TTL", "30"))
