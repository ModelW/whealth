# How to Create a Control

A control is a modular health check that verifies a specific aspect of the
application.

## Structure

Each control lives in its own folder under `controls/` inside a Django app. The
folder name is the control's slug.

```
yourapp/
├── controls/
│   └── your_control_slug/
│       ├── __init__.py      # class Control(BaseControl)
│       ├── README.md        # Documentation
│       └── manifest.yaml    # Metadata (depends_on)
```

## Manifest (`manifest.yaml`)

A YAML file with preamble metadata. Currently supports:

```yaml
depends_on:
    - other_control_slug # Same app
    - yourapp.other_slug # Cross-app reference
```

## Python (`__init__.py`)

Contains exactly one class named `Control` that subclasses `BaseControl`:

```python
from whealth import BaseControl


class Control(BaseControl):
    """Description of what this control checks."""

    def check(self) -> None:
        """Run the check. Raise on failure, return on success."""
```

## Discoverability

**TODO**: Control auto-discovery is not yet implemented.

## Scheduling

**TODO**: Scheduling and periodic execution is not yet implemented.

## Notifications

**TODO**: Alerting and notification channels are not yet implemented.

## Testing

**TODO**: Testing utilities and fixtures are not yet implemented.
