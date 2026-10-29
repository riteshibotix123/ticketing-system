import uuid
from dataclasses import dataclass

from app.core.enums import Role

STAFF_ROLES = frozenset({Role.ADMIN, Role.SUPER_ADMIN})


@dataclass(frozen=True, slots=True)
class Actor:
    id: uuid.UUID
    global_role: Role
    department_id: str
    spoke_department_ids: frozenset[str]
    name: str
    email: str

    @property
    def is_spoke(self) -> bool:
        return bool(self.spoke_department_ids)

    @property
    def is_admin_or_super_admin(self) -> bool:
        return self.global_role in STAFF_ROLES

    @property
    def is_super_admin(self) -> bool:
        return self.global_role is Role.SUPER_ADMIN

    def has_role(self, role: Role) -> bool:
        if role is Role.EMPLOYEE:
            return True
        if role is Role.SPOKE:
            return self.is_spoke
        return self.global_role is role

    @property
    def roles(self) -> list[Role]:
        roles = [Role.EMPLOYEE]
        if self.is_spoke:
            roles.append(Role.SPOKE)
        if self.global_role in STAFF_ROLES:
            roles.append(self.global_role)
        return roles
