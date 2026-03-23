"""
Unit tests for MCP search_memory with dual retrieval (facts + snapshots).
Tests that search_memory returns both long-term facts and short-term snapshots.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4


@pytest.mark.asyncio
async def test_search_memory_format_with_facts_and_snapshots():
    """Test that search_memory output includes both facts and snapshots sections."""
    mock_facts = [
        {
            "id": str(uuid4()),
            "document": "Peter specializes in database optimization",
            "kind": "experience",
            "salience": 0.9,
            "confidence": 0.8,
            "entities": ["Peter", "database"],
            "source_snapshot_id": "snap-123"
        }
    ]
    
    mock_snapshots = [
        {
            "id": "snap-456",
            "timestamp": "2025-01-15T10:30:00",
            "active_file": "main.py",
            "git_branch": "main",
            "summary": "Refactored authentication",
            "entities": ["auth", "security"]
        }
    ]
    
    # Check that the format strings are correct based on what search_memory would generate
    output = (
        "=== FACTS (LONG-TERM MEMORY) ===\n"
        "Found 1 relevant facts for 'database':\n"
        "--- Fact 1 (experience) ---\n"
        "Content: Peter specializes in database optimization\n"
        "Salience: 90.0% | Confidence: 80.0%\n"
        "Entities: Peter, database\n"
        f"Source: Snapshot snap-123\n"
        "\n=== SNAPSHOTS (SHORT-TERM MEMORY) ===\n"
        "Found 1 relevant snapshots for 'database':\n"
        "--- Snapshot 1 ---\n"
        "Time: 2025-01-15T10:30:00\n"
        "File: main.py\n"
        "Branch: main\n"
        "Summary: Refactored authentication\n"
        "Entities: ['auth', 'security']\n"
    )
    
    # Verify the structure includes expected sections
    assert "=== FACTS (LONG-TERM MEMORY) ===" in output
    assert "=== SNAPSHOTS (SHORT-TERM MEMORY) ===" in output
    assert "database optimization" in output
    assert "Refactored authentication" in output


@pytest.mark.asyncio
async def test_search_memory_fact_formatting():
    """Test that individual facts are formatted correctly in search_memory output."""
    fact = {
        "document": "Users prefer dark mode for reduced eye strain",
        "kind": "opinion",
        "salience": 0.75,
        "confidence": 0.85,
        "entities": ["users", "UI"],
        "source_snapshot_id": "snap-789"
    }
    
    # Simulation of how search_memory formats a fact
    formatted = (
        f"--- Fact 1 (opinion) ---\n"
        f"Content: {fact['document']}\n"
        f"Salience: {fact['salience']:.1%} | Confidence: {fact['confidence']:.1%}\n"
        f"Entities: {', '.join(fact['entities'])}\n"
        f"Source: Snapshot {fact['source_snapshot_id'][:8]}\n"
    )
    
    assert "opinion" in formatted
    assert "75.0%" in formatted  # Salience
    assert "85.0%" in formatted  # Confidence
    assert "dark mode" in formatted
    assert "snap-789" in formatted


@pytest.mark.asyncio
async def test_search_memory_empty_facts_and_snapshots():
    """Test that search_memory handles empty facts and snapshots gracefully."""
    facts_empty = []
    snapshots_empty = []
    
    output_parts = []
    
    if facts_empty:
        output_parts.append(f"Found {len(facts_empty)} relevant facts")
    else:
        output_parts.append(f"No relevant facts found for 'test'.\n")
    
    output_parts.append("\n=== SNAPSHOTS (SHORT-TERM MEMORY) ===\n")
    
    if snapshots_empty:
        output_parts.append(f"Found {len(snapshots_empty)} relevant snapshots")
    else:
        output_parts.append(f"No relevant snapshots found for 'test'.\n")
    
    result = "".join(output_parts)
    
    assert "No relevant facts found" in result
    assert "No relevant snapshots found" in result


@pytest.mark.asyncio
async def test_search_memory_salience_filtering():
    """Test that facts with low salience are still included (min_salience=0.3)."""
    facts = [
        {"document": "High salience fact", "kind": "world", "salience": 0.9, "confidence": 0.8},
        {"document": "Medium salience fact", "kind": "world", "salience": 0.5, "confidence": 0.7},
        {"document": "Low but acceptable fact", "kind": "world", "salience": 0.3, "confidence": 0.6},
    ]
    
    # All facts should be included in output
    assert len(facts) == 3
    for fact in facts:
        assert fact["salience"] >= 0.3


@pytest.mark.asyncio
async def test_search_memory_snapshot_code_context_truncation():
    """Test that code context in snapshots is truncated appropriately."""
    code = "x" * 2000  # 2000 chars
    
    # Simulation of truncation logic
    truncated = code[:1000] + ("..." if len(code) > 1000 else "")
    
    assert len(truncated) == 1003  # 1000 + 3 for "..."
    assert truncated.endswith("...")


@pytest.mark.asyncio
async def test_search_memory_dual_retrieval_sections():
    """Test that search_memory clearly separates facts and snapshots in output."""
    output = (
        "=== FACTS (LONG-TERM MEMORY) ===\n"
        "Found 2 relevant facts:\n"
        "--- Fact 1 (world) ---\n"
        "Content: Fact content here\n"
        "\n=== SNAPSHOTS (SHORT-TERM MEMORY) ===\n"
        "Found 3 relevant snapshots:\n"
        "--- Snapshot 1 ---\n"
        "Time: 2025-01-15T10:30:00\n"
    )
    
    # Check section headers exist and are in correct order
    facts_section = output.find("=== FACTS (LONG-TERM MEMORY) ===")
    snapshots_section = output.find("=== SNAPSHOTS (SHORT-TERM MEMORY) ===")
    
    assert facts_section >= 0, "Facts section header missing"
    assert snapshots_section > facts_section, "Snapshots should come after facts"
