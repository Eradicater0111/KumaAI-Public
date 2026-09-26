from __future__ import annotations

import sqlite3

from app.agent.mission_state import MissionState
from app.memory.memory import DB_PATH


class MissionPersistence:
    """
    Persistent storage for KUMA MissionState objects.

    Persistence records mission state.
    It does not execute missions or decide what happens next.
    """

    def __init__(
        self,
        db_path=DB_PATH,
    ):
        self.db_path = db_path

        self.initialize()

    def get_connection(self):
        return sqlite3.connect(
            self.db_path
        )

    def initialize(self):
        with self.get_connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS missions (
                    mission_id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    state_json TEXT NOT NULL
                )
                """
            )

            connection.commit()

    def create(
        self,
        mission: MissionState,
    ) -> None:
        """
        Persist a new mission.

        Existing mission IDs are rejected.
        """

        if not isinstance(
            mission,
            MissionState,
        ):
            raise TypeError(
                "mission must be a MissionState."
            )

        with self.get_connection() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO missions (
                        mission_id,
                        goal,
                        status,
                        created_at,
                        updated_at,
                        state_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        mission.mission_id,
                        mission.goal,
                        mission.status.value,
                        mission.created_at,
                        mission.updated_at,
                        mission.to_json(),
                    ),
                )

            except sqlite3.IntegrityError as error:
                raise ValueError(
                    f"Mission already exists: "
                    f"{mission.mission_id}"
                ) from error

            connection.commit()

    def save(
        self,
        mission: MissionState,
    ) -> None:
        """
        Update an existing mission.
        """

        if not isinstance(
            mission,
            MissionState,
        ):
            raise TypeError(
                "mission must be a MissionState."
            )

        mission.touch()

        with self.get_connection() as connection:
            cursor = connection.execute(
                """
                UPDATE missions
                SET goal = ?,
                    status = ?,
                    created_at = ?,
                    updated_at = ?,
                    state_json = ?
                WHERE mission_id = ?
                """,
                (
                    mission.goal,
                    mission.status.value,
                    mission.created_at,
                    mission.updated_at,
                    mission.to_json(),
                    mission.mission_id,
                ),
            )

            if cursor.rowcount == 0:
                raise ValueError(
                    f"Mission does not exist: "
                    f"{mission.mission_id}"
                )

            connection.commit()

    def load(
        self,
        mission_id: str,
    ) -> MissionState | None:
        """
        Load a mission by ID.
        """

        mission_id = str(
            mission_id or ""
        ).strip()

        if not mission_id:
            return None

        with self.get_connection() as connection:
            row = connection.execute(
                """
                SELECT state_json
                FROM missions
                WHERE mission_id = ?
                """,
                (mission_id,),
            ).fetchone()

        if row is None:
            return None

        return MissionState.from_json(
            row[0]
        )

    def list_missions(
        self,
    ) -> list[MissionState]:
        """
        Return all persisted missions ordered by most recently updated.
        """

        with self.get_connection() as connection:
            rows = connection.execute(
                """
                SELECT state_json
                FROM missions
                ORDER BY updated_at DESC
                """
            ).fetchall()

        return [
            MissionState.from_json(
                row[0]
            )
            for row in rows
        ]

    def delete(
        self,
        mission_id: str,
    ) -> bool:
        """
        Delete a mission.

        Returns True when a record was removed.
        """

        mission_id = str(
            mission_id or ""
        ).strip()

        if not mission_id:
            return False

        with self.get_connection() as connection:
            cursor = connection.execute(
                """
                DELETE FROM missions
                WHERE mission_id = ?
                """,
                (mission_id,),
            )

            connection.commit()

            return cursor.rowcount > 0