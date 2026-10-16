import os
import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    # Enable auto-reload in local dev unless explicitly running in production
    is_prod = os.getenv("ENVIRONMENT", "").lower() == "production" or os.getenv("RENDER", "").lower() == "true"
    reload = os.getenv("RELOAD", "true" if not is_prod else "false").lower() in ("true", "1")
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=reload)

