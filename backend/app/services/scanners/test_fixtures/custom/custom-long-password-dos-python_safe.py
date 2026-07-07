# Safe Long Password DoS fixture — length check before bcrypt
import bcrypt

def hash_password(password):
    if len(password) > 72:
        raise ValueError("Password exceeds maximum length of 72 bytes")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password, salt)

def register_user(username, password):
    encoded = password.encode()
    if len(encoded) < 8:
        raise ValueError("Password too short")
    if len(encoded) > 72:
        raise ValueError("Password too long")
    hashed = bcrypt.hashpw(encoded, bcrypt.gensalt())
    return {"username": username, "password": hashed}
