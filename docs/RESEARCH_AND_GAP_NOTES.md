# M2 Research / Gap Notes

## Engineering gap addressed by M2

General LLM troubleshooting can generate plausible instructions, but the
final Settings navigation needs a deterministic, catalog-grounded authority.

M2 addresses this implementation gap by separating:

```text
LLM proposes an action
        ↓
M2 grounds the action in a trusted catalog
        ↓
M2 validates the catalog-backed deeplink
```

This is an engineering/system-design statement, not a claim that no prior
research exists.

## Evidence to collect for the final PPT

Measure, from actual runs:

- exact-match rate
- keyword-match rate
- semantic-match rate
- unresolved rate
- deeplink accuracy
- manual-action deeplink violations
- critical-order violations
- catalog integrity failures

Never insert benchmark numbers until they are measured.
