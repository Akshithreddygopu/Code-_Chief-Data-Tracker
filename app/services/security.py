"""Security service for password hashing and validation."""

import hashlib
import hmac


def hash_password(password: str) -> str:
    """Hash a password using SHA-256 with a salt.

    Args:
        password: Plaintext password

    Returns:
        Hashed password string with salt embedded
    """
    # Generate a simple salt (in production, use secrets.token_hex(16))
    salt = "codechef_tracker_salt_2026"
    # Combine password with salt and hash
    hashed = hashlib.sha256((password + salt).encode('utf-8')).hexdigest()
    # Return salt:hash format for easy storage
    return f"{salt}:{hashed}"


def check_password_hash(stored_hash: str, password: str) -> bool:
    """Check if a password matches the stored hash.

    Args:
        stored_hash: Hash string from hash_password (format: salt:hash)
        password: Plaintext password to check

    Returns:
        True if password matches, False otherwise
    """
    try:
        salt, stored_hash_value = stored_hash.split(':', 1)
        newly_hashed = hashlib.sha256((password + salt).encode('utf-8')).hexdigest()
        return hmac.compare_digest(newly_hashed, stored_hash_value)
    except (ValueError, TypeError):
        return False