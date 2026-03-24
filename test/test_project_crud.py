"""
Full CRUD test suite for Project management.
Tests: create, list, rename, archive/unarchive, delete, 403 for non-owners.
"""

from __future__ import annotations

from conftest import signup, create_project


def test_create_project(client):
    """Create a project and verify response shape."""
    user = signup(client, "proj-create")
    project = create_project(client, user["headers"], "AlphaProject")

    assert project["name"] == "AlphaProject"
    assert project["visibility"] == "private"
    assert project["is_archived"] is False
    assert "id" in project


def test_list_projects(client):
    """List projects returns all owned projects."""
    user = signup(client, "proj-list")
    create_project(client, user["headers"], "ProjA")
    create_project(client, user["headers"], "ProjB")

    resp = client.get("/api/v1/projects", headers=user["headers"])
    assert resp.status_code == 200
    projects = resp.json()["projects"]
    names = {p["name"] for p in projects}
    assert "ProjA" in names
    assert "ProjB" in names


def test_rename_project(client):
    """Owner can rename a project via PATCH."""
    user = signup(client, "proj-rename")
    project = create_project(client, user["headers"], "OldName")

    resp = client.patch(
        f"/api/v1/projects/{project['id']}",
        headers=user["headers"],
        json={"name": "NewName"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "NewName"


def test_rename_project_403_for_non_owner(client):
    """Non-owner cannot rename a project."""
    owner = signup(client, "proj-owner")
    other = signup(client, "proj-other")
    project = create_project(client, owner["headers"], "OwnerProj")

    resp = client.patch(
        f"/api/v1/projects/{project['id']}",
        headers=other["headers"],
        json={"name": "Hacked"},
    )
    assert resp.status_code == 403


def test_archive_and_unarchive_project(client):
    """Archive then unarchive a project."""
    user = signup(client, "proj-archive")
    project = create_project(client, user["headers"], "ArchTest")

    # Archive
    resp = client.post(
        f"/api/v1/projects/{project['id']}/archive",
        headers=user["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["is_archived"] is True

    # Unarchive
    resp = client.post(
        f"/api/v1/projects/{project['id']}/unarchive",
        headers=user["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["is_archived"] is False


def test_delete_project(client):
    """Owner can delete a project permanently."""
    user = signup(client, "proj-delete")
    project = create_project(client, user["headers"], "Doomed")

    resp = client.delete(
        f"/api/v1/projects/{project['id']}",
        headers=user["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"

    # Verify it's gone from listing
    listing = client.get("/api/v1/projects", headers=user["headers"])
    assert resp.status_code == 200
    remaining = [p["id"] for p in listing.json()["projects"]]
    assert project["id"] not in remaining


def test_delete_project_403_for_non_owner(client):
    """Non-owner cannot delete a project."""
    owner = signup(client, "proj-del-owner")
    other = signup(client, "proj-del-other")
    project = create_project(client, owner["headers"], "Protected")

    resp = client.delete(
        f"/api/v1/projects/{project['id']}",
        headers=other["headers"],
    )
    assert resp.status_code == 403


def test_delete_nonexistent_project_404(client):
    """Deleting a project that doesn't exist returns 404."""
    user = signup(client, "proj-del-404")
    resp = client.delete(
        "/api/v1/projects/nonexistent-id",
        headers=user["headers"],
    )
    assert resp.status_code == 404
