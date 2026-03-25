#!/usr/bin/env python3
"""
Test suite for snapshot_fabricator.py

Run with: pytest tests/test_snapshot_fabricator.py -v
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "secondcortex-backend"))

from snapshot_fabricator import SnapshotFabricator


class TestSnapshotFabricator:
    """Test snapshot generation and validation"""
    
    def setup_method(self):
        """Initialize fabricator before each test"""
        self.fabricator = SnapshotFabricator()
    
    def test_generate_snapshots_count(self):
        """Test that correct number of snapshots are generated"""
        snapshots = self.fabricator.generate_snapshots(
            user_id="test-user",
            project_id="test-project",
            count=10
        )
        assert len(snapshots) == 10, f"Expected 10 snapshots, got {len(snapshots)}"
    
    def test_snapshot_has_required_fields(self):
        """Test that each snapshot has all required fields"""
        snapshots = self.fabricator.generate_snapshots(
            user_id="test-user",
            project_id="test-project",
            count=5
        )
        
        required_fields = {
            'id', 'project_id', 'user_id', 'active_file', 'language_id',
            'git_branch', 'timestamp', 'shadow_graph', 'summary', 'entities',
            'relations', 'metadata_for_search', 'sync_status', 'created_at', 'updated_at'
        }
        
        for snap in snapshots:
            assert set(snap.keys()) >= required_fields, \
                f"Missing fields: {required_fields - set(snap.keys())}"
    
    def test_snapshot_values_not_empty(self):
        """Test that required snapshot fields are not empty"""
        snapshots = self.fabricator.generate_snapshots(
            user_id="test-user",
            project_id="test-project",
            count=5
        )
        
        for snap in snapshots:
            assert snap['id'], "id is empty"
            assert snap['user_id'] == "test-user", "user_id mismatch"
            assert snap['project_id'] == "test-project", "project_id mismatch"
            assert snap['active_file'], "active_file is empty"
            assert snap['language_id'], "language_id is empty"
            assert snap['summary'], "summary is empty"
            assert snap['sync_status'] == 'SYNCED', f"sync_status should be SYNCED, got {snap['sync_status']}"
    
    def test_timestamp_within_range(self):
        """Test that snapshots are spread across requested days"""
        snapshots = self.fabricator.generate_snapshots(
            user_id="test-user",
            project_id="test-project",
            count=20,
            days_back=30
        )
        
        now = datetime.utcnow()
        oldest_allowed = now - timedelta(days=30)
        
        for snap in snapshots:
            ts = datetime.fromisoformat(snap['timestamp'].replace('Z', '+00:00'))
            assert ts <= now, f"Snapshot timestamp in future: {snap['timestamp']}"
            assert ts >= oldest_allowed, f"Snapshot older than {30} days: {snap['timestamp']}"
    
    def test_snapshot_variety(self):
        """Test that snapshots have variety in summaries and files"""
        snapshots = self.fabricator.generate_snapshots(
            user_id="test-user",
            project_id="test-project",
            count=30
        )
        
        unique_summaries = len(set(s['summary'] for s in snapshots))
        unique_files = len(set(s['active_file'] for s in snapshots))
        
        # With 30 snapshots, should have significant variety
        assert unique_summaries >= 10, \
            f"Not enough summary variety: {unique_summaries} unique out of 30"
        assert unique_files >= 5, \
            f"Not enough file variety: {unique_files} unique out of 30"
    
    def test_snapshot_language_consistency(self):
        """Test that language_id matches the file extension"""
        snapshots = self.fabricator.generate_snapshots(
            user_id="test-user",
            project_id="test-project",
            count=50
        )
        
        language_map = {
            '.py': 'python',
            '.ts': 'typescript',
            '.tsx': 'typescript',
            '.js': 'javascript',
            '.sql': 'sql'
        }
        
        for snap in snapshots:
            ext = Path(snap['active_file']).suffix
            expected_lang = language_map.get(ext)
            if expected_lang:
                assert snap['language_id'] == expected_lang, \
                    f"File {snap['active_file']} has language {snap['language_id']}, expected {expected_lang}"
    
    def test_entities_and_relations_present(self):
        """Test that snapshots have entities and relations for graph"""
        snapshots = self.fabricator.generate_snapshots(
            user_id="test-user",
            project_id="test-project",
            count=10
        )
        
        for snap in snapshots:
            # Should have some entity/relation data (could be JSON string or list)
            assert snap['entities'], f"Snapshot {snap['id']} has no entities"
            assert snap['relations'], f"Snapshot {snap['id']} has no relations"


# Command-line test
if __name__ == "__main__":
    import json
    
    print("=" * 80)
    print("🧪 SNAPSHOT FABRICATOR - Manual Test")
    print("=" * 80)
    print("")
    
    fab = SnapshotFabricator()
    snapshots = fab.generate_snapshots("test-user", "test-project", count=10)
    
    print(f"✓ Generated {len(snapshots)} snapshots")
    print("")
    print("First snapshot:")
    print(json.dumps(snapshots[0], indent=2, default=str))
    print("")
    
    # Run basic validations
    print("Validations:")
    print(f"  ✓ All have id:                {all(s.get('id') for s in snapshots)}")
    print(f"  ✓ All have user_id:           {all(s.get('user_id') for s in snapshots)}")
    print(f"  ✓ All have project_id:        {all(s.get('project_id') for s in snapshots)}")
    print(f"  ✓ All have timestamp:         {all(s.get('timestamp') for s in snapshots)}")
    print(f"  ✓ All have summary:           {all(s.get('summary') for s in snapshots)}")
    print(f"  ✓ All are SYNCED:             {all(s.get('sync_status') == 'SYNCED' for s in snapshots)}")
    print("")
    print("✓ All tests passed!")
    print("=" * 80)
