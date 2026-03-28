#!/usr/bin/env python3
"""
Initialize Nextcloud test environment.
Creates user1, user2, TestFamily group, and shares /Documents/Scans with the group.
Runs inside the Docker test network, reaching Nextcloud by service name.
"""
import os
import sys
import time

import requests
from requests.auth import HTTPBasicAuth

NEXTCLOUD_URL = os.environ["NEXTCLOUD_URL"].rstrip("/")
ADMIN_USER = os.environ["NEXTCLOUD_ADMIN_USER"]
ADMIN_PASSWORD = os.environ["NEXTCLOUD_ADMIN_PASSWORD"]

GROUP_NAME = "TestFamily"
SCAN_DIR = "/Documents/Scans"

TEST_USERS = [
    {"userid": "user1", "password": "user1password", "email": "user1@test.local"},
    {"userid": "user2", "password": "user2password", "email": "user2@test.local"},
]

auth = HTTPBasicAuth(ADMIN_USER, ADMIN_PASSWORD)
OCS_HEADERS = {"OCS-APIRequest": "true"}


def _ocs_post(path: str, data: dict) -> requests.Response:
    return requests.post(
        f"{NEXTCLOUD_URL}{path}",
        auth=auth,
        headers={**OCS_HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
        data=data,
        timeout=30,
    )


def _ocs_ok(r: requests.Response) -> bool:
    """Return True if the OCS response indicates success (100) or already exists (102)."""
    return r.status_code in (200, 201) and (
        "<statuscode>100</statuscode>" in r.text
        or "<statuscode>102</statuscode>" in r.text
    )


def create_users() -> None:
    for user in TEST_USERS:
        r = _ocs_post(
            "/ocs/v1.php/cloud/users",
            {"userid": user["userid"], "password": user["password"], "email": user["email"]},
        )
        if _ocs_ok(r):
            print(f"  Created/exists user '{user['userid']}'")
        else:
            print(f"  Warning: user '{user['userid']}' result: {r.text[:200]}")


def create_group() -> None:
    r = _ocs_post("/ocs/v1.php/cloud/groups", {"groupid": GROUP_NAME})
    if _ocs_ok(r):
        print(f"  Created/exists group '{GROUP_NAME}'")
    else:
        print(f"  Warning: group result: {r.text[:200]}")


def add_users_to_group() -> None:
    for user in TEST_USERS:
        r = _ocs_post(
            f"/ocs/v1.php/cloud/users/{user['userid']}/groups",
            {"groupid": GROUP_NAME},
        )
        if _ocs_ok(r):
            print(f"  Added '{user['userid']}' to '{GROUP_NAME}'")
        else:
            print(f"  Warning: add-to-group result for '{user['userid']}': {r.text[:200]}")


def create_scan_directory() -> None:
    webdav_base = f"{NEXTCLOUD_URL}/remote.php/dav/files/{ADMIN_USER}"
    for path in ["/Documents", SCAN_DIR]:
        r = requests.request("MKCOL", f"{webdav_base}{path}", auth=auth, timeout=30)
        if r.status_code in (201, 405):  # 201 Created, 405 Already exists
            print(f"  Directory ready: {path}")
        else:
            print(f"  Warning: MKCOL {path} returned {r.status_code}")


def share_scan_dir_with_group() -> None:
    r = requests.post(
        f"{NEXTCLOUD_URL}/ocs/v2.php/apps/files_sharing/api/v1/shares",
        auth=auth,
        headers={**OCS_HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
        data={
            "path": SCAN_DIR,
            "shareType": 1,       # 1 = group share
            "shareWith": GROUP_NAME,
            "permissions": 31,    # read + write + create + delete + share
        },
        timeout=30,
    )
    if r.status_code in (200, 201):
        print(f"  Shared '{SCAN_DIR}' with group '{GROUP_NAME}'")
    else:
        print(f"  Warning: share result: {r.status_code} {r.text[:200]}")


def main() -> None:
    print("Initializing Nextcloud...")
    create_users()
    create_group()
    add_users_to_group()
    create_scan_directory()
    share_scan_dir_with_group()
    print("Nextcloud initialization complete.")


if __name__ == "__main__":
    main()
