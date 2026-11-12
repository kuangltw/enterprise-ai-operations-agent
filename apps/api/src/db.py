"""共用 Agent 應用資料庫連線池。"""

from sqlalchemy import create_engine

from .settings import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
