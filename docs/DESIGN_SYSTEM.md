# Frontend design-system foundation

Phase 2A adds the approved AcroBuild foundations and primitives without
migrating any existing screen. The source is the Figma file
`w0mkemvbh4WCCfSkP1VBsV`, inspected on 2026-10-06.

## Source mapping

- `src/design-system/tokens.css` mirrors the Figma Primitives, Color, Spacing,
  and Radius variable collections plus its typography and elevation styles.
- `src/components/ui/` provides Button, IconButton, Input, Badge, and Card.
- `src/main.tsx` loads the self-hosted Plus Jakarta Sans variable font and the
  foundation styles before the legacy stylesheets.

Fontsource exposes the variable face as `Plus Jakarta Sans Variable`; the
product-family token keeps `Plus Jakarta Sans` as its next fallback so the code
still maps cleanly to the Figma family name.

The public token names follow the Figma WEB syntax where it exists, including
`--color-bg-canvas`, `--color-action-primary`, `--spacing-md`, and
`--radius-lg`. The primitive classes use the `ab-` prefix so they cannot
accidentally match legacy page selectors.

## Approval boundary

Yellow remains proposed. Its code tokens contain `proposed` and the warning
badge references those explicitly:

- `--color-proposed-yellow-500`
- `--color-accent-yellow-proposed`
- `--color-feedback-warning-proposed`

Their presence supports the Figma warning-badge state; it does not record
yellow as client-approved.

## Migration boundary

No existing page uses these primitives yet, and the legacy `--font-body` /
`--font-heading` variables remain unchanged. Plus Jakarta Sans is bundled and
used by the new primitives, but applying it to existing screens belongs to a
later page-migration phase.
