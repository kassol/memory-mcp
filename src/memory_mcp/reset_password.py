"""Reset the console admin password: `python -m memory_mcp.reset_password`.

Removes the password and signs out every console session. The initial access token takes the
current configuration-file value and is live again (also for clients), so it can sign in once to
set a new password. Prints nothing secret.
"""
from .config import settings
from .console_auth import reset_password_offline


def main() -> None:
    removed = reset_password_offline(settings.sqlite_path, settings.auth_token)
    print(f"Admin password removed; {removed} console session(s) signed out.")
    print("The initial access token now has the configuration-file value and is active again.")
    print("Sign in to the console with it to set a new password.")


if __name__ == "__main__":
    main()
