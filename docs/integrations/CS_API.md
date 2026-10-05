# AcroBuild Customer Service API

The application uses a read-only, company-scoped property API. This page
documents the contract the repository consumes; source in
`services/acrobuild_company_service.py` is authoritative for request behavior.

## Configuration and security

```env
ACROBUILD_CS_API_BASE_URL=http://your-cs-api-host:port
ACROBUILD_CS_API_KEY=
ACROBUILD_CS_API_COMPANY_ID=
ACROBUILD_CS_API_TIMEOUT_SECONDS=2.5
ACROBUILD_CS_API_CACHE_TTL_SECONDS=300
ACROBUILD_CS_API_LIVE_ONLY=true
```

Every upstream request sends `apiKey` as a server-side header and inserts the
configured company ID into `/api/cs/{companyId}/...`. Never expose the key in
browser code, documentation, logs, or evidence. Administrators can persist an
override through the protected CS API settings page; the stored key is never
returned to the browser and a blank update preserves it.

## Endpoints consumed

| Purpose | Upstream request |
| --- | --- |
| Company contact | `GET /api/cs/{companyId}/company` |
| Projects | `GET /api/cs/{companyId}/projects` |
| Project amenities | `GET /api/cs/{companyId}/projects/{projectId}/amenities` |
| Project wings | `GET /api/cs/{companyId}/projects/{projectId}/wings` |
| Project typologies | `GET /api/cs/{companyId}/projects/{projectId}/typologies` |
| Wing typologies | `GET /api/cs/{companyId}/wings/{wingId}/typologies` |
| Wing inventory | `GET /api/cs/{companyId}/wings/{wingId}/inventory?availableOnly=true|false` |

IDs returned by one request scope the next. The service filters customer-facing
projects and resolves names without inventing records. Full suffixed names take
precedence over a contained base name.

## Fields used by the application

- Company: display/business name, address, city, phone, email, website, social
  links, and image URL.
- Project: ID, name/code, address/locality/city/location, coordinates, RERA
  number, contact, website, property details, dates, image, type, and publication
  status.
- Amenity: `iconName`, type, and URL.
- Wing: ID, name/code, development type, possession date, construction status,
  floor/unit totals, and saleable area.
- Typology: ID, wing, name/type, carpet/saleable area, unit amenities, image URL,
  rate type, and minimum/maximum base rate.
- Inventory: wing/typology IDs, home type, floor/unit number, status label/code,
  and areas.

Field availability varies by record. `imageUrl` is treated as unverified image
content, not automatically as a brochure or floor plan. `expectedPossesionDate`
uses the upstream API's spelling.

## Source, caching, and fallback

All requests for one assist turn use a trace and per-turn memoization. The trace
feeds `data_api_calls` and the final live-data enforcement gate.

With `ACROBUILD_CS_API_LIVE_ONLY=true`, a live failure is reported honestly and
no local snapshot is used. With live-only mode disabled, a compatible local
snapshot may cover a failed endpoint. Snapshots are isolated by connection
configuration; a snapshot for the environment default is not reused after an
administrator points the app at a different server.

`source_status` distinguishes `live_api`, `snapshot`, `failed`, and unavailable
results. Within one turn, the latest call for the same endpoint and parameters is
authoritative, allowing a successful retry to supersede an earlier failure.

## Error behavior

- Missing or invalid configuration raises a controlled availability error.
- HTTP/network/timeout failures are logged internally; public responses receive
  sanitized errors.
- Empty lists are valid data, not transport failures.
- A cross-company or missing project/wing is not replaced with a plausible
  record.
- Property answers with unsupported numeric claims are replaced by the live-data
  failure response rather than being sent to the customer.

## Safe probe

Use service functions instead of constructing URLs with credentials in shell
history:

```powershell
.venv/Scripts/python.exe -c "from services.acrobuild_company_service import get_company_projects; print(len(get_company_projects()))"
```

This proves the configured project-list call succeeded at that moment. It does
not validate every downstream endpoint or Sarvam.

For end-to-end checks, use the scripts in the
[development guide](../DEVELOPMENT.md). Their results belong under
`docs/evidence/live/`.
