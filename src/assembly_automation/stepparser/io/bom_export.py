"""Keep processing diagnostics out of user-facing BOM measurements."""


def without_status_fields(value):
    """Copy JSON data while removing calculation statuses at every level."""
    if isinstance(value, dict):
        return {key: without_status_fields(item) for key, item in value.items()
                if key != "status" and not key.endswith("_status")}
    if isinstance(value, list):
        return [without_status_fields(item) for item in value]
    return value
