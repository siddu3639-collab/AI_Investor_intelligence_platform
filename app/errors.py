class NotFoundError(Exception):
    """Something the caller asked for doesn't exist (-> 404)."""


class ConflictError(Exception):
    """The request clashes with existing data, e.g. a duplicate upload (-> 409)."""


class IngestionError(Exception):
    """The document could not be turned into searchable chunks (-> 422)."""
