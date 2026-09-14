from __future__ import annotations

import hashlib
import secrets
import time

TOKEN_PREFIX = 'hm_sk_'  # hivemind secret key
DEVICE_TOKEN_PREFIX = 'hm_dt_'  # hivemind device token


def generate_api_key(name: str | None = None) -> tuple[str, str, str]:
    """
    Generate a new API key.
    
    Returns:
        tuple[str, str, str]: (full_key, key_hash, key_prefix)
    """
    raw = secrets.token_urlsafe(32)
    full_key = f'{TOKEN_PREFIX}{raw}'
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    key_prefix = full_key[:16]
    return full_key, key_hash, key_prefix


def generate_device_token() -> tuple[str, str]:
    """
    Generate a new device token.
    
    Returns:
        tuple[str, str]: (full_token, token_hash)
    """
    raw = secrets.token_urlsafe(32)
    full_token = f'{DEVICE_TOKEN_PREFIX}{raw}'
    token_hash = hashlib.sha256(full_token.encode()).hexdigest()
    return full_token, token_hash


def hash_token(token: str) -> str:
    """
    Hash a token for storage/lookup.
    
    Args:
        token: The plain-text token.
        
    Returns:
        str: The SHA-256 hash of the token.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def verify_scope(scopes: list[str], required: str) -> bool:
    """
    Check if the required scope is satisfied. 'admin' implies all scopes.
    
    Args:
        scopes: The list of scopes the token possesses.
        required: The scope required for the operation.
        
    Returns:
        bool: True if authorized, False otherwise.
    """
    if 'admin' in scopes:
        return True
    return required in scopes


SCOPE_HIERARCHY = {
    'admin': {'admin', 'run', 'read'},
    'run': {'run', 'read'},
    'read': {'read'},
}
