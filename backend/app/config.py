import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://mql5:mql5@db:5432/mql5")
STALE_SEC = int(os.getenv("STALE_SEC", "120"))
