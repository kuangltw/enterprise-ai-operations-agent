"""角色政策的允許與拒絕矩陣。"""

import pytest

from src.role_policy import allows


@pytest.mark.parametrize("role,expected", [
    ("admin", {"tenant.read", "member.manage", "knowledge.ask", "inventory.read",
               "purchase.draft.create", "purchase.approve"}),
    ("manager", {"tenant.read", "knowledge.ask", "inventory.read",
                 "purchase.draft.create", "purchase.approve"}),
    ("staff", {"tenant.read", "knowledge.ask", "inventory.read",
               "purchase.draft.create"}),
    ("viewer", {"tenant.read", "knowledge.ask", "inventory.read"}),
    ("unknown", set()),
])
def test_role_matrix(role, expected):
    permissions = {"tenant.read", "member.manage", "knowledge.ask", "inventory.read",
                   "purchase.draft.create", "purchase.approve"}
    assert {permission for permission in permissions if allows(role, permission)} == expected


def test_unknown_permission_fails_closed():
    assert not allows("admin", "unknown")
