import os
import sys
import uuid
import importlib
from pathlib import Path

try:
    psycopg2 = importlib.import_module("psycopg2")
except Exception:
    psycopg2 = None

sys.path.insert(0, str(Path(__file__).parent.parent))

from snapshot_fabricator import SnapshotFabricator


def main() -> int:
    if psycopg2 is None:
        print("✗ psycopg2 is required. Install with: pip install psycopg2-binary")
        return 1

    conn_string = os.getenv("POSTGRES_CONNECTION_STRING", "postgresql://localhost/secondcortex")

    user_id = uuid.UUID("11111111-1111-4111-8111-111111111111")
    project_id = uuid.UUID("22222222-2222-4222-8222-222222222222")

    fabricator = SnapshotFabricator()
    snapshots = fabricator.generate_snapshots(str(user_id), str(project_id), count=50, days_back=30)

    with psycopg2.connect(conn_string) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (id, email)
                VALUES (%s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (user_id, "demo@secondcortex.labs"),
            )

            cur.execute(
                """
                INSERT INTO projects (id, user_id, name, workspace_folder)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (project_id, user_id, "SecondCortex Backend", "/opt/secondcortex-backend"),
            )

            for snap in snapshots:
                cur.execute(
                    """
                    INSERT INTO snapshots (
                        id, project_id, user_id, active_file, language_id, git_branch,
                        timestamp, shadow_graph, summary, entities, relations,
                        metadata_for_search, sync_status, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        active_file = EXCLUDED.active_file,
                        language_id = EXCLUDED.language_id,
                        git_branch = EXCLUDED.git_branch,
                        timestamp = EXCLUDED.timestamp,
                        shadow_graph = EXCLUDED.shadow_graph,
                        summary = EXCLUDED.summary,
                        entities = EXCLUDED.entities,
                        relations = EXCLUDED.relations,
                        metadata_for_search = EXCLUDED.metadata_for_search,
                        sync_status = EXCLUDED.sync_status,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        uuid.UUID(snap["id"]),
                        project_id,
                        user_id,
                        snap["active_file"],
                        snap["language_id"],
                        snap["git_branch"],
                        snap["timestamp"],
                        snap["shadow_graph"],
                        snap["summary"],
                        snap["entities"],
                        snap["relations"],
                        snap["metadata_for_search"],
                        "SYNCED",
                        snap["created_at"],
                        snap["updated_at"],
                    ),
                )

        conn.commit()

    print(f"✓ Seeded {len(snapshots)} demo snapshots")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
