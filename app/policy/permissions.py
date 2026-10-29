import uuid
from datetime import datetime
from types import MappingProxyType
from typing import Final

from app.core.enums import ProtectedActionStatus, Role
from app.policy import Actor
from app.policy.flags import (
    ADMINS_MANAGE,
    CONFIDENTIAL_MANAGE,
    DEPARTMENTS_MANAGE,
    POLICY_MANAGE,
    USERS_MANAGE_ROLES,
    has_permission,
)

SIGNUP_ROLE_RANK: Final = MappingProxyType(
    {
        Role.EMPLOYEE: 0,
        Role.ADMIN: 1,
        Role.SUPER_ADMIN: 2,
    }
)
MIN_ACTIVE_SUPER_ADMINS: Final = 2


def can_decide_signup(
    actor: Actor,
    requested_role: Role,
    approved_role: Role | None,
    applicant_id: uuid.UUID,
) -> bool:
    if actor.id == applicant_id:
        return False
    roles = [requested_role] if approved_role is None else [requested_role, approved_role]
    if any(role not in SIGNUP_ROLE_RANK for role in roles):
        return False
    highest = max(roles, key=SIGNUP_ROLE_RANK.__getitem__)
    if highest is Role.EMPLOYEE:
        return actor.is_admin_or_super_admin
    return actor.is_super_admin


def can_list_users(actor: Actor, admins_can_manage_departments: bool) -> bool:
    return has_permission(
        actor, USERS_MANAGE_ROLES, admins_can_manage_departments
    ) or has_permission(actor, ADMINS_MANAGE, admins_can_manage_departments)


def can_manage_account(
    actor: Actor, target_role: Role, admins_can_manage_departments: bool
) -> bool:
    if not has_permission(actor, USERS_MANAGE_ROLES, admins_can_manage_departments):
        return False
    if actor.is_super_admin:
        return True
    return target_role is Role.EMPLOYEE


def can_change_account_state(
    actor: Actor,
    target_id: uuid.UUID,
    target_role: Role,
    admins_can_manage_departments: bool,
) -> bool:
    if actor.id == target_id:
        return False
    return can_manage_account(actor, target_role, admins_can_manage_departments)


def deactivation_is_protected(target_role: Role) -> bool:
    return target_role is Role.SUPER_ADMIN


def can_manage_admins(actor: Actor, admins_can_manage_departments: bool) -> bool:
    return has_permission(actor, ADMINS_MANAGE, admins_can_manage_departments)


def keeps_minimum_super_admins(active_super_admin_count: int) -> bool:
    return active_super_admin_count - 1 >= MIN_ACTIVE_SUPER_ADMINS


def is_independent_super_admin(
    actor: Actor, requested_by_id: uuid.UUID, target_id: uuid.UUID
) -> bool:
    return actor.is_super_admin and actor.id not in {requested_by_id, target_id}


def can_decide_protected_action(
    actor: Actor,
    requested_by_id: uuid.UUID,
    target_id: uuid.UUID,
    status: ProtectedActionStatus,
    expires_at: datetime,
    now: datetime,
) -> bool:
    if status is not ProtectedActionStatus.PENDING or expires_at <= now:
        return False
    return is_independent_super_admin(actor, requested_by_id, target_id)


def can_manage_departments(actor: Actor, admins_can_manage_departments: bool) -> bool:
    return has_permission(actor, DEPARTMENTS_MANAGE, admins_can_manage_departments)


def can_manage_grants(actor: Actor, admins_can_manage_departments: bool) -> bool:
    return has_permission(actor, CONFIDENTIAL_MANAGE, admins_can_manage_departments)


def can_read_policy(actor: Actor) -> bool:
    return actor.is_admin_or_super_admin


def can_manage_policy(actor: Actor, admins_can_manage_departments: bool) -> bool:
    return has_permission(actor, POLICY_MANAGE, admins_can_manage_departments)
