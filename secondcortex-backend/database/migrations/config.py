"""PostgreSQL Migration Manager"""
import psycopg2
from pathlib import Path
import logging

logger = logging.getLogger("PostgresMigrationManager")


class PostgresMigrationManager:
    def __init__(self, connection_string):
        self.conn_string = connection_string

    def run_migrations(self):
        """Run all migration files in order"""
        schema_file = Path(__file__).parent / "001_create_schema.sql"

        with open(schema_file) as f:
            sql = f.read()

        try:
            with psycopg2.connect(self.conn_string) as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    conn.commit()
            print("✓ Schema created successfully")
            return True
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            print(f"✗ Migration failed: {e}")
            return False


if __name__ == "__main__":
    import sys
    
    connection_string = sys.argv[1] if len(sys.argv) > 1 else "postgresql://localhost/secondcortex"
    mgr = PostgresMigrationManager(connection_string)
    success = mgr.run_migrations()
    sys.exit(0 if success else 1)
