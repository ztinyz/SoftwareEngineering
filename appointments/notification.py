from .kafka import publish_event


def notify(event: str, email: str, data: dict):
    publish_event(
        "notification",
        {
            "event": event,
            "recipient": {
                "email": email,
            },
            "data": data,
        }
    )
