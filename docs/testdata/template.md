# FastNote Acceptance Template

This document is the canonical input for acceptance test A12. Every port opens this exact
file, appends a marker, saves, and exports it. Do not edit it without updating the harness.

## Formatting

Text may be **bold**, *italic*, or ~~struck through~~. Inline `code` appears here.

## Lists

- First item
- Second item
  - Nested item
- Third item

1. Ordered one
2. Ordered two

## Code

```go
func Greet(name string) string {
    return "Hello, " + name
}
```

## Table

| Feature | Supported |
|---------|-----------|
| Headings | yes |
| Tables | yes |
| Math | yes |

## Tasks

- [x] Completed task
- [ ] Outstanding task

## Math

Inline math $E = mc^2$ appears here.

$$
\sum_{i=1}^{n} i = \frac{n(n+1)}{2}
$$

## Quote

> A capability that cannot be exercised through the interface does not exist.

## Unicode

Chinese, Cyrillic, and emoji must survive the round trip.

---

END OF TEMPLATE
