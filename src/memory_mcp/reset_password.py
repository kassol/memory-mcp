"""Reset the console admin password: `python -m memory_mcp.reset_password`.

Removes the password and signs out every console session. The console then accepts the
configuration-file access token once, to set a new password. Prints nothing secret.
"""
from .config import settings
from .console_auth import reset_password_offline


def main() -> None:
    removed = reset_password_offline(settings.sqlite_path)
    print(f"Admin password removed; {removed} console session(s) signed out.")
    print("Sign in to the console with the configuration-file access token to set a new password.")


if __name__ == "__main__":
    main()
