"""Casbin RBAC authorization service.

Provides role-based access control for multi-tenant call center.
When CASBIN_MODEL_PATH is not set, operates in permissive mode (all access allowed).

Roles: admin > supervisor > agent > viewer
Resources: agents, calls, scripts, billing, analytics, knowledge, tenants
Actions: read, write, delete, transfer
"""

import os
from pathlib import Path

import structlog

logger = structlog.get_logger()

_enforcer = None
_model_path = os.getenv(
    "CASBIN_MODEL_PATH",
    str(Path(__file__).parent.parent / "config" / "casbin_model.conf"),
)
_policy_path = os.getenv(
    "CASBIN_POLICY_PATH",
    str(Path(__file__).parent.parent / "config" / "casbin_policy.csv"),
)


def _get_enforcer():
    """Return the Casbin enforcer singleton."""
    global _enforcer
    if _enforcer is not None:
        return _enforcer

    is_production = os.getenv("APP_ENV", "development") == "production"

    try:
        import casbin

        if os.path.exists(_model_path) and os.path.exists(_policy_path):
            _enforcer = casbin.Enforcer(_model_path, _policy_path)
            logger.info("casbin_initialized", model=_model_path, policy=_policy_path)
        else:
            logger.warning("casbin_files_not_found", model=_model_path, policy=_policy_path)
            if is_production:
                raise RuntimeError(
                    "Casbin model/policy files not found. Set CASBIN_MODEL_PATH "
                    "and CASBIN_POLICY_PATH or ship the config files in production."
                )
            _enforcer = None
    except ImportError:
        logger.debug("casbin_not_installed")
        if is_production:
            raise RuntimeError(
                "casbin package is not installed. RBAC cannot fail closed "
                "safely without it in production."
            )
        _enforcer = None
    except RuntimeError:
        raise
    except Exception as e:
        logger.warning("casbin_init_failed", error=str(e))
        if is_production:
            raise RuntimeError(f"Casbin initialization failed in production: {e}") from e
        _enforcer = None

    return _enforcer


def _permissive_mode_allowed() -> bool:
    """Whether permissive (allow-all) mode is allowed when Casbin is unavailable.

    Only allowed outside production. In production, missing/broken Casbin
    configuration must fail closed (deny by default) rather than silently
    granting access to every request.
    """
    return os.getenv("APP_ENV", "development") != "production"


def check_permission(role: str, resource: str, action: str) -> bool:
    """Check if a role has permission on a resource for a given action.

    Returns True if Casbin is not configured and not running in production
    (permissive dev mode). Fails closed (denies) in production or on error.
    """
    try:
        enforcer = _get_enforcer()
    except RuntimeError as e:
        # Casbin unavailable/misconfigured in production: fail closed.
        logger.error("casbin_unavailable_fail_closed", role=role, resource=resource, action=action, error=str(e))
        return False

    if not enforcer:
        if _permissive_mode_allowed():
            return True  # Permissive mode: allow all (non-production only)
        logger.error(
            "casbin_unavailable_fail_closed",
            role=role,
            resource=resource,
            action=action,
        )
        return False  # Fail closed in production

    try:
        allowed = enforcer.enforce(role, resource, action)
        if not allowed:
            logger.debug("rbac_denied", role=role, resource=resource, action=action)
        return allowed
    except Exception as e:
        logger.error("casbin_check_failed", error=str(e))
        return False  # Fail closed


def add_role_for_user(user_id: str, role: str) -> bool:
    """Assign a role to a user."""
    enforcer = _get_enforcer()
    if not enforcer:
        return True

    try:
        enforcer.add_role_for_user(user_id, role)
        return True
    except Exception as e:
        logger.error("casbin_add_role_failed", error=str(e))
        return False


def remove_role_for_user(user_id: str, role: str) -> bool:
    """Remove a role from a user."""
    enforcer = _get_enforcer()
    if not enforcer:
        return True

    try:
        enforcer.delete_role_for_user(user_id, role)
        return True
    except Exception as e:
        logger.error("casbin_remove_role_failed", error=str(e))
        return False


def get_roles_for_user(user_id: str) -> list[str]:
    """Get all roles for a user."""
    enforcer = _get_enforcer()
    if not enforcer:
        return []

    try:
        return enforcer.get_roles_for_user(user_id)
    except Exception:
        return []


def get_permissions(role: str) -> list[tuple[str, str]]:
    """Get all (resource, action) permissions for a role."""
    enforcer = _get_enforcer()
    if not enforcer:
        return []

    try:
        return enforcer.get_permissions_for_user(role)
    except Exception:
        return []
