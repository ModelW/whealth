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

## Meta Controls

A control can be declared as **manifest-only** by setting `meta: true` in its
manifest. Meta controls have no Python check of their own — they bundle a set
of dependencies under a single name (e.g. "the website works"):

```
yourapp/
├── controls/
│   └── website_works/
│       ├── __init__.py      # Empty — no Control class allowed
│       ├── README.md        # Documents what the bundle means
│       └── manifest.yaml    # meta: true + depends_on
```

```yaml
meta: true
depends_on:
    - database
    - yourapp.frontend
```

Rules and semantics:

- The `__init__.py` must exist (the package has to be importable) but must
  NOT contain a `BaseControl` subclass — declaring `meta: true` alongside a
  Python check is a validation error.
- `depends_on` must be non-empty: a meta control with no dependencies would
  check nothing at all, so discovery rejects it.
- A `README.md` is still required; it documents what the bundle means.
- The control itself always passes. Its meaningful signal is the **deep**
  status: `GET /control/<app>/<slug>/deep.json` returns 200 when every
  transitive dependency is healthy and 418 otherwise — which makes meta
  controls ideal readiness-probe targets.
- Meta controls default to `is_ignorable: false` (ignoring a pure bundle is
  meaningless); an explicit `is_ignorable: true` still wins.
- Controls depending *on* a meta control only see the meta's own (always
  green) result — upstream failures do not propagate through it to shallow
  dependents.

## Discoverability

**TODO**: Control auto-discovery is not yet implemented.

## Scheduling

**TODO**: Scheduling and periodic execution is not yet implemented.

## Notifications

**TODO**: Alerting and notification channels are not yet implemented.

## Testing

**TODO**: Testing utilities and fixtures are not yet implemented.
