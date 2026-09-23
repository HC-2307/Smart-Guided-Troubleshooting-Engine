# Member 2 Work Record

## Scope

Member 2 owns the Knowledge / Deeplink Engine:

1. inspect supplied starter assets
2. build searchable catalog representation
3. exact/keyword/semantic action matching
4. catalog ID resolution
5. catalog-backed deeplink resolution
6. sequence validation
7. standard/critical/manual handling
8. URL/catalog integrity checks
9. ground-truth mappings and deeplink evaluation

## Source assets used

- `data/deeplinks.json` — 578 supplied catalog entries
- `data/siis_responses.json` — 20 source-grounded troubleshooting responses
- `data/input.txt` — supplied benchmark queries
- `data/sample_output.json` — supplied example response
- `data/schema.py` — supplied schema reference

## Design decisions

### 1. Catalog is the authority

The resolver copies the deeplink from the matched catalog entry. It never
constructs a URI from the action text.

### 2. Matching is staged

Exact matching is attempted first. If that fails, token/keyword matching
uses the action plus contextual description/steps. A TF-IDF cosine fallback
handles less literal phrasing.

### 3. Ambiguous catalog messages need context

The catalog contains repeated `message` values, so exact message matching
alone is insufficient. Context from the action description and step group
is used to select among duplicate messages.

### 4. Manual actions

Manual actions do not receive an actionable deeplink.

### 5. Critical actions

Critical actions are moved to the end of the action sequence and are checked
for ordering violations.

### 6. Unresolved actions

If the resolver cannot reach a confidence threshold, it returns an explicit
unresolved result. It does not invent a URL.

## Current evidence

The catalog integrity tests verify:

- 578 entries
- unique catalog IDs
- unique deeplink values

The sample response integration test verifies:

- the backup action can resolve to a trusted catalog entry
- the manual repair action receives no deeplink
- no critical ordering violation is introduced

## Ground-truth work still required

The 20 SIIS scenarios are included as source-grounded evaluation inventory.
Their expected catalog IDs are intentionally not filled automatically because
that would turn a model-generated candidate into claimed ground truth.

For each scenario:

1. read the SIIS response
2. identify each actionable Settings screen
3. locate the exact catalog entry
4. record the catalog ID
5. verify the URI is copied from the catalog
6. record unresolved/manual actions explicitly
7. then run deeplink accuracy

## M2 → M3 contract

M2 produces each resolved actionable step with:

- original action fields
- `catalogId` internally for traceability
- `actionableDeeplink` copied from the catalog

The final public response should preserve the team's agreed schema.
M2-specific evidence should remain in internal reports rather than being
silently added to the public contract.
