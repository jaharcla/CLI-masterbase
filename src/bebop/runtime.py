from __future__ import annotations

import os

from dbos import DBOS, DBOSConfig


def init_dbos() -> None:
    config: DBOSConfig = {
        "name": "bebop-code-hub",
        "application_version": "0.1.0",
        "system_database_url": os.getenv("DBOS_SYSTEM_DATABASE_URL"),
    }
    DBOS(config=config)
    DBOS.launch()
