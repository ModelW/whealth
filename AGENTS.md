# CSS Architecture

## Rules

1. **Simple class selectors only.** No complex selectors, nesting, or chaining.
   Just `.class-name {}`.
2. **No `!important`.** Ever.
3. Each page gets its own CSS file in `static/<app>/css/` loaded via
   `{% static %}`.
