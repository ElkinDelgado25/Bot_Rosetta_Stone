class Email:
    def __init__(self, email: str):
        if "@" not in email or "." not in email.split("@")[-1]:
            raise ValueError("Invalid email address")
        self._email = email

    def __str__(self):
        return self._email

    def __repr__(self):
        return f"Email({self._email})"
