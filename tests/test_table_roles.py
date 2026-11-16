"""Çeviri tablosunun özel veri rolleri: değerler farklı ve dördü de tek katalogdan geliyor."""

from __future__ import annotations

from nxceviri.gui import find_replace, group_proxy, marked_delegate, status_cell, table_roles


def test_roles_have_distinct_values() -> None:
    roles = [
        table_roles.ROW_ROLE,
        table_roles.STATUS_ROLE,
        table_roles.FIND_SPANS_ROLE,
        table_roles.HEADER_ROLE,
    ]
    assert len(set(roles)) == len(roles)


def test_old_modules_expose_catalog_roles() -> None:
    assert marked_delegate.ROW_ROLE is table_roles.ROW_ROLE
    assert status_cell.STATUS_ROLE is table_roles.STATUS_ROLE
    assert find_replace.FIND_SPANS_ROLE is table_roles.FIND_SPANS_ROLE
    assert group_proxy.HEADER_ROLE is table_roles.HEADER_ROLE
