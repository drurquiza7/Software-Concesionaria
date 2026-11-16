import uuid


def nuevo_id() -> uuid.UUID:
    # Único punto de generación de PKs: permite pasar a UUID v7 sin tocar los modelos.
    return uuid.uuid4()
