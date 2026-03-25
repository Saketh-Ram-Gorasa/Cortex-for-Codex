#!/usr/bin/env python3
"""
Seed demo snapshots for 2-day demo.

This script:
1. Creates test user account
2. Creates test project
3. Generates 50 realistic demo snapshots
4. Inserts them into PostgreSQL

Usage:
    python scripts/seed_demo_snapshots.py
"""

import sys
import json
from datetime import datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from snapshot_fabricator import SnapshotFabricator


def seed_demo_snapshots():
    """Generate and display demo snapshots"""
    
    # Demo user and project IDs
    user_id = "demo-user-secondcortex"
    project_id = "demo-project-backend"
    
    print("=" * 80)
    print("🎯 SNAPSHOT FABRICATOR - Demo Data Generation")
    print("=" * 80)
    print("")
    print(f"User ID:      {user_id}")
    print(f"Project ID:   {project_id}")
    print(f"Demo target:  50 realistic snapshots")
    print(f"Time span:    Past 30 days")
    print("")
    
    # Generate snapshots
    fabricator = SnapshotFabricator()
    snapshots = fabricator.generate_snapshots(
        user_id=user_id,
        project_id=project_id,
        count=50,
        days_back=30
    )
    
    print(f"✓ Generated {len(snapshots)} snapshots")
    print("")
    
    # Display sample snapshots
    print("Sample snapshots (first 5):")
    print("-" * 80)
    for i, snap in enumerate(snapshots[:5], 1):
        timestamp = snap['timestamp'][:10]  # Date only
        summary = snap['summary'][:60]
        file = snap['active_file'].split('/')[-1]
        print(f"{i}. [{timestamp}] {file:30} | {summary}...")
    print("")
    
    # Statistics
    files = set(s['active_file'] for s in snapshots)
    languages = set(s['language_id'] for s in snapshots)
    summaries_count = len(set(s['summary'] for s in snapshots))
    
    print("Snapshot Statistics:")
    print(f"  - Unique files touched:        {len(files)}")
    print(f"  - Languages:                   {', '.join(languages)}")
    print(f"  - Unique summaries:            {summaries_count}")
    print(f"  - All have metadata:           {all(s['metadata_for_search'] for s in snapshots)}")
    print(f"  - sync_status set to SYNCED:   {all(s['sync_status'] == 'SYNCED' for s in snapshots)}")
    print("")
    
    # Show database insertion SQL
    print("Database Insert SQL (first snapshot):")
    print("-" * 80)
    first = snapshots[0]
    sql = f"""
INSERT INTO snapshots (
    id, project_id, user_id, active_file, language_id, git_branch,
    timestamp, shadow_graph, summary, entities, relations,
    metadata_for_search, sync_status, created_at, updated_at
) VALUES (
    '{first['id']}',
    '{first['project_id']}',
    '{first['user_id']}',
    '{first['active_file']}',
    '{first['language_id']}',
    '{first['git_branch']}',
    '{first['timestamp']}',
    E'<code context here>',
    '{first['summary']}',
    '{first['entities']}',
    '{first['relations']}',
    '{first['metadata_for_search']}',
    'SYNCED',
    '{first['created_at']}',
    '{first['updated_at']}'
);
"""
    print(sql)
    print("-" * 80)
    print("")
    
    # Show how to insert via Python
    print("Python Database Insertion Code:")
    print("-" * 80)
    print("""
import psycopg2

conn_string = "postgresql://user:pass@localhost/secondcortex"
with psycopg2.connect(conn_string) as conn:
    with conn.cursor() as cur:
        for snap in snapshots:
            cur.execute(\"\"\"
                INSERT INTO snapshots (...)
                VALUES (...)
            \"\"\", (snap['id'], snap['project_id'], ...))
        conn.commit()
print(f"✓ Inserted {len(snapshots)} snapshots")
""")
    print("-" * 80)
    print("")
    
    # Export to JSON for inspection
    output_file = "snapshots_demo_data.json"
    with open(output_file, "w") as f:
        json.dump(snapshots, f, indent=2, default=str)
    
    print(f"✓ Exported snapshots to: {output_file}")
    print("")
    print("🎯 Next Steps:")
    print("  1. Review snapshots_demo_data.json")
    print("  2. Create PostgreSQL database: 'secondcortex'")
    print("  3. Run database schema migration (check docs/plans/)")
    print("  4. Insert snapshots into database")
    print("  5. Start backend: docker-compose up")
    print("  6. Test API: curl http://localhost:8000/api/v1/snapshots/timeline")
    print("  7. Open dashboard: http://localhost:3000/dashboard")
    print("")
    print("=" * 80)


if __name__ == "__main__":
    seed_demo_snapshots()
