# Vulnerable Long Password DoS fixture — no length check before bcrypt
import bcrypt

def hash_password(password):
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password, salt)

def register_user(username, password):
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    return {"username": username, "password": hashed}
