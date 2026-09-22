Customer Service (CS) API — Integration Guide
For CS / chat-widget backend developers integrating with AcroBuild property data.
These are read-only, company-scoped APIs. All data returned belongs to the `companyId` passed in the URL path (`/api/cs/{companyId}/...`).
---
Overview
Item	Detail
Purpose	Expose company contact, projects, amenities, wings, typologies, and inventory to customer-service / website chat integrations
Service	`acro-rest`
Base path	`/api/cs/{companyId}`
Methods	`GET` only
Auth	API key header (`apiKey`) — no CRM login / access token
CORS	Enabled (`CrossOrigin` on controller)
Environment base URLs
Environment	Example REST base URL
Local dev	`http://localhost:8081`
Staging	`https://acro-rest-api.ekodemy.xyz`
Production	`https://rest-api.acrobuild.ai`
Full endpoint example:
```
GET {restUrl}/api/cs/22/company
```
---
Authentication
Every request must include the API key in a header:
Header	Required	Description
`apiKey`	Yes	Company CS API key (issued per environment by AcroBuild ops)
Every request must include `companyId` in the path:
Path param	Required	Description
`companyId`	Yes	Company whose data to return
Do not send CRM headers (`accessToken`, `eko-user`, etc.). These APIs are intentionally outside Barricade user auth.
Security: Store `apiKey` on your server (CS backend / middleware). Never embed it in browser JavaScript or public chat-widget client code.
Example — curl (Windows / Linux)
```bash
curl.exe -H "apiKey: YOUR_CS_API_KEY" http://localhost:8081/api/cs/22/company
```
Example — PowerShell
PowerShell aliases `curl` to `Invoke-WebRequest`. Use `curl.exe` or:
```powershell
Invoke-RestMethod -Uri "http://localhost:8081/api/cs/22/company" -Headers @{ apiKey = "YOUR_CS_API_KEY" }
```
---
Recommended integration flow
Typical chat-widget / CS bot sequence:
Company contact — `GET /api/cs/{companyId}/company` (phone, email, address for “contact us” answers)
Project list — `GET /api/cs/{companyId}/projects` (which projects exist)
Project detail — `GET /api/cs/{companyId}/projects/{projectId}` (single project metadata, including `location`)
Amenities — `GET /api/cs/{companyId}/projects/{projectId}/amenities`
Wings — `GET /api/cs/{companyId}/projects/{projectId}/wings`
Typologies — `GET /api/cs/{companyId}/projects/{projectId}/typologies` or `GET /api/cs/{companyId}/wings/{wingId}/typologies`
Inventory — `GET /api/cs/{companyId}/wings/{wingId}/inventory?availableOnly=true` (available units for a wing)
Project / wing / typology IDs from one response are used in the next request. Cross-company IDs return `404`.
---
Endpoints
1. Get company contact details
```
GET /api/cs/{companyId}/company
```
Path params
Param	Type	Description
`companyId`	Long	Company ID
Response `200`:
```json
{
  "id": 15,
  "companyName": "Acme Builders",
  "businessName": "Acme Builders Pvt Ltd",
  "address": "123 Main Street",
  "city": "Mumbai",
  "zipCode": "400001",
  "phoneNo": 9876543210,
  "contactEmail": "sales@acme.com",
  "websiteUrl": "https://www.acme.com",
  "socialUrls": "{\"facebook\":\"...\"}",
  "companyImageUrl": "https://..."
}
```
---
2. List projects
```
GET /api/cs/{companyId}/projects
```
Returns non-deleted projects for the given company.
Response `200`: array of project objects (same shape as single project below).
```json
[
  {
    "id": 101,
    "projectName": "Sunrise Towers",
    "projectCode": "ST-01",
    "address": "Sector 5",
    "locality": "Andheri",
    "city": "Mumbai",
    "location": "Sector 5, Andheri, Mumbai",
    "zipcode": "400053",
    "reraNo": "P51800001234",
    "contact": 9876543210,
    "countryCode": 91,
    "website": "https://...",
    "propertyDetails": "2 & 3 BHK",
    "estimatedStartDate": 1700000000000,
    "estimatedEndDate": 1800000000000,
    "longitude": "72.8777",
    "latitude": "19.0760",
    "projectImageUrl": "https://...",
    "projectType": "Residential",
    "isPublished": true
  }
]
```
`location` is composed from non-empty `address`, `locality`, and `city` (comma-separated). Use `longitude` / `latitude` for map pins.
---
3. Get project by ID
```
GET /api/cs/{companyId}/projects/{projectId}
```
Path params
Param	Type	Description
`companyId`	Long	Company ID
`projectId`	Long	Project ID
Response `200`: single project object (same fields as list item above).
---
4. List amenities for a project
```
GET /api/cs/{companyId}/projects/{projectId}/amenities
```
Returns resolved amenity/facility library items selected for the project. Empty selection returns `[]`.
Path params
Param	Type	Description
`companyId`	Long	Company ID
`projectId`	Long	Project ID
Response `200`:
```json
[
  {
    "id": 12,
    "iconName": "Swimming Pool",
    "type": "Amenities",
    "url": "https://..."
  },
  {
    "id": 15,
    "iconName": "Gym",
    "type": "Facilities",
    "url": "https://..."
  }
]
```
---
5. List wings for a project
```
GET /api/cs/{companyId}/projects/{projectId}/wings
```
Response `200`:
```json
[
  {
    "id": 501,
    "projectId": 101,
    "name": "Tower A",
    "code": "A",
    "developmentType": "Residential",
    "expectedPossesionDate": 1800000000000,
    "constructionStatus": "Under Construction",
    "totalFloors": 20,
    "saleableUnits": 80,
    "saleableArea": 45000
  }
]
```
---
6. List typologies for a project
All typologies across all wings in the project.
```
GET /api/cs/{companyId}/projects/{projectId}/typologies
```
Response `200`:
```json
[
  {
    "id": 901,
    "wingId": 501,
    "typologyName": "2 BHK Premium",
    "typologyType": "2BHK",
    "saleableArea": 950.0,
    "carpetArea": 720.0,
    "unitAmenities": "Balcony, Parking",
    "imageUrl": "https://...",
    "rateType": "perSqFt",
    "minBasePrice": 8500.0,
    "maxBasePrice": 9200.0
  }
]
```
---
7. List typologies for a wing
```
GET /api/cs/{companyId}/wings/{wingId}/typologies
```
Path params
Param	Type	Description
`companyId`	Long	Company ID
`wingId`	Long	Wing ID
Response `200`: array of typology objects (same shape as above).
---
8. List inventory units for a wing
```
GET /api/cs/{companyId}/wings/{wingId}/inventory?availableOnly=true
```
Path params
Param	Type	Description
`companyId`	Long	Company ID
`wingId`	Long	Wing ID
Query params
Param	Required	Default	Description
`availableOnly`	No	`true`	When `true`, returns only units with status Available. When `false`, returns all units for the wing.
Response `200`:
```json
[
  {
    "id": 12001,
    "wingId": 501,
    "typologyId": 901,
    "typologyName": "2 BHK Premium",
    "typologyType": "2BHK",
    "floorNumber": 5,
    "unitNumber": 502,
    "status": 21,
    "statusLabel": "Available",
    "carpetArea": 720.0,
    "saleableArea": 950.0
  }
]
```
Unit status labels (`statusLabel` / internal `status` code):
statusLabel	status code
Sold	20
Available	21
Parking	22
Reserved	23
Booked	24
Hold	97
---
Errors
Failed requests return JSON:
```json
{
  "errorMessage": "Human-readable message"
}
```
HTTP status	Typical cause
`401`	Missing or invalid `apiKey` header
`404`	Company not found, or project/wing ID not found for this company
`400`	Request blocked before CS handler (e.g. Barricade not skipping `/api/cs` — ops/config issue)
Success list endpoints return `[]` when there is no data (not an error).
---
Response field reference
Company (`CsCompanyDto`)
Field	Type	Description
`id`	Long	Company ID
`companyName`	String	Display name
`businessName`	String	Legal / business name
`address`	String	Office address
`city`	String	City
`zipCode`	String	PIN / zip
`phoneNo`	Long	Primary phone
`contactEmail`	String	Contact email
`websiteUrl`	String	Company website
`socialUrls`	String	Social links (often JSON string)
`companyImageUrl`	String	Logo / image URL
Project (`CsProjectDto`)
Field	Type	Description
`id`	Long	Project ID
`projectName`	String	Project name
`projectCode`	String	Internal code
`address`, `locality`, `city`	String	Location
`reraNo`	String	RERA registration
`contact`	Long	Project contact number
`countryCode`	Integer	Phone country code
`website`	String	Project website
`propertyDetails`	String	Short description
`estimatedStartDate`, `estimatedEndDate`	Long	Epoch ms
`longitude`, `latitude`	String	Geo coordinates
`projectImageUrl`	String	Hero image
`projectType`	String	e.g. Residential
`isPublished`	Boolean	Published flag
Wing (`CsWingDto`)
Field	Type	Description
`id`	Long	Wing ID
`projectId`	Long	Parent project
`name`, `code`	String	Wing name / code
`developmentType`	String	Development type
`expectedPossesionDate`	Long	Epoch ms
`constructionStatus`	String	Construction status
`totalFloors`	Integer	Floor count
`saleableUnits`	Integer	Unit count
`saleableArea`	Integer	Saleable area
Typology (`CsTypologyDto`)
Field	Type	Description
`id`	Long	Typology ID
`wingId`	Long	Parent wing
`typologyName`, `typologyType`	String	Name and type (e.g. 2BHK)
`saleableArea`, `carpetArea`	Double	Areas
`unitAmenities`	String	Amenities text
`imageUrl`	String	Floor plan / image
`rateType`	String	Pricing rate type
`minBasePrice`, `maxBasePrice`	Double	Price range
Inventory unit (`CsInventoryUnitDto`)
Field	Type	Description
`id`	Long	Unit mapping ID
`wingId`, `typologyId`	Long	References
`typologyName`, `typologyType`	String	Denormalized typology info
`floorNumber`, `unitNumber`	Integer	Location in tower
`status`	Integer	Status code (see table above)
`statusLabel`	String	Human-readable status
`carpetArea`, `saleableArea`	Double	Unit areas
---
Quick test checklist
After receiving `apiKey`, `companyId`, and `{restUrl}` from AcroBuild:
```bash
# 1. Company (replace COMPANY_ID)
curl.exe -H "apiKey: YOUR_CS_API_KEY" {restUrl}/api/cs/COMPANY_ID/company

# 2. Projects
curl.exe -H "apiKey: YOUR_CS_API_KEY" {restUrl}/api/cs/COMPANY_ID/projects

# 3. Wings (replace PROJECT_ID)
curl.exe -H "apiKey: YOUR_CS_API_KEY" {restUrl}/api/cs/COMPANY_ID/projects/PROJECT_ID/wings

# 4. Typologies by project
curl.exe -H "apiKey: YOUR_CS_API_KEY" {restUrl}/api/cs/COMPANY_ID/projects/PROJECT_ID/typologies

# 5. Inventory (replace WING_ID)
curl.exe -H "apiKey: YOUR_CS_API_KEY" "{restUrl}/api/cs/COMPANY_ID/wings/WING_ID/inventory?availableOnly=true"
```
---
Server configuration (AcroBuild ops)
Not exposed to CS integrators; documented for internal reference.
Config key	Description
`app.csApiKey`	Shared secret validated from `apiKey` header
Barricade must skip CS paths (prefix match):
```yaml
barricade:
  skipPaths:
    - /api/cs
    - /api/public
```
---