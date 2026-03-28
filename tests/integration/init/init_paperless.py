#!/usr/bin/env python3
"""
Initialize Paperless-ngx test environment.
Creates user1, user2, and the TestFamily group with proper permissions.
Runs inside the Docker test network, reaching Paperless by service name.
"""
import os
import sys
import time

import requests

PAPERLESS_URL = os.environ["PAPERLESS_URL"].rstrip("/")
ADMIN_USER = os.environ["PAPERLESS_ADMIN_USER"]
ADMIN_PASSWORD = os.environ["PAPERLESS_ADMIN_PASSWORD"]

GROUP_NAME = "TestFamily"
GROUP_PERMISSIONS = [
    "add_document", "view_document",
    "add_tag", "view_tag",
    "view_uisettings",
    "add_note", "change_note", "delete_note", "view_note",
]

TEST_USERS = [
    {"username": "user1", "password": "Nxt-Cl0ud-Test!U1", "email": "user1@test.local"},
    {"username": "user2", "password": "Nxt-Cl0ud-Test!U2", "email": "user2@test.local"},
]


def get_token() -> str:
    """Obtain API token for the admin user."""
    r = requests.post(
        f"{PAPERLESS_URL}/api/token/",
        json={"username": ADMIN_USER, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["token"]


def auth_headers(token: str) -> dict:
    return {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json",
        "Accept": "application/json; version=6",
    }


def create_users(token: str) -> None:
    for user in TEST_USERS:
        r = requests.post(
            f"{PAPERLESS_URL}/api/users/",
            headers=auth_headers(token),
            json=user,
            timeout=30,
        )
        if r.status_code in (200, 201):
            print(f"  Created user '{user['username']}'")
        elif r.status_code == 400 and "already exists" in r.text.lower():
            print(f"  User '{user['username']}' already exists")
        else:
            print(f"  Warning: unexpected response creating '{user['username']}': {r.status_code} {r.text[:200]}")


def get_user_ids(token: str) -> dict:
    r = requests.get(
        f"{PAPERLESS_URL}/api/users/",
        headers=auth_headers(token),
        timeout=30,
    )
    r.raise_for_status()
    # API may paginate; collect all pages
    users = r.json().get("results", [])
    while r.json().get("next"):
        r = requests.get(r.json()["next"], headers=auth_headers(token), timeout=30)
        r.raise_for_status()
        users.extend(r.json().get("results", []))
    return {u["username"]: u["id"] for u in users}


def create_group_and_assign(token: str, user_ids: dict) -> None:
    # Create group
    r = requests.post(
        f"{PAPERLESS_URL}/api/groups/",
        headers=auth_headers(token),
        json={"name": GROUP_NAME, "permissions": GROUP_PERMISSIONS},
        timeout=30,
    )
    if r.status_code in (200, 201):
        group_id = r.json()["id"]
        print(f"  Created group '{GROUP_NAME}' (id={group_id})")
    elif r.status_code == 400:
        # Group may already exist
        r2 = requests.get(
            f"{PAPERLESS_URL}/api/groups/",
            headers=auth_headers(token),
            params={"name__iexact": GROUP_NAME},
            timeout=30,
        )
        r2.raise_for_status()
        results = r2.json().get("results", [])
        if not results:
            raise RuntimeError(f"Could not create or find group '{GROUP_NAME}'")
        group_id = results[0]["id"]
        print(f"  Found existing group '{GROUP_NAME}' (id={group_id})")
    else:
        r.raise_for_status()

    # Add users to group
    for username in ["user1", "user2"]:
        uid = user_ids.get(username)
        if uid is None:
            print(f"  Warning: user '{username}' not found, skipping group assignment")
            continue
        r = requests.patch(
            f"{PAPERLESS_URL}/api/users/{uid}/",
            headers=auth_headers(token),
            json={"groups": [group_id]},
            timeout=30,
        )
        if r.status_code in (200, 201):
            print(f"  Added '{username}' to '{GROUP_NAME}'")
        else:
            print(f"  Warning: could not add '{username}' to group: {r.status_code} {r.text[:200]}")


def main() -> None:
    print("Initializing Paperless-ngx...")
    token = get_token()
    print("  Obtained admin token")
    create_users(token)
    user_ids = get_user_ids(token)
    create_group_and_assign(token, user_ids)
    print("Paperless-ngx initialization complete.")


if __name__ == "__main__":
    main()
