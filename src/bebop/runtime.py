from __future__ import annotations

import os

from dbos import DBOS, DBOSConfig


TASK_QUEUE = "bebop-tasks"


def init_dbos() -> None:
    config: DBOSConfig = {
        "name": "bebop-code-hub",
        "application_version": "0.1.0",
        "system_database_url": os.getenv("DBOS_SYSTEM_DATABASE_URL"),
    }
    DBOS(config=config)
    DBOS.launch()
    DBOS.register_queue(
        TASK_QUEUE,
        worker_concurrency=max(1, int(os.getenv("BEBOP_TASK_CONCURRENCY", "3"))),
    )
