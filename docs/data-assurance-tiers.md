# Data Assurance Tiers

## Overview

The Data Assurance Tiers feature provides a three-tier system for tracking data quality and governance progression across your catalog. Each catalog node can be assigned a numeric tier (1, 2, or 3) that maps to configurable labels, allowing different installations to use their own terminology.

**Key Benefits:**
- **Data Governance**: Track data quality progression from raw to production-ready
- **Installation Flexibility**: Use your organization's terminology (e.g., "cataloged/governed/certified" vs "bronze/silver/gold")
- **API Transparency**: Both numeric tier and human-readable label returned in all API responses
- **Consistency**: Same numeric system across all implementations (Python, Java, Go)

## Architecture

### Numeric Tiers → Configurable Labels

```
Tier 1 → "bronze"  (default)  →  "cataloged", "identified", "raw" (custom)
Tier 2 → "silver"  (default)  →  "governed", "validated", "refined" (custom)
Tier 3 → "gold"    (default)  →  "certified", "attested", "production" (custom)
```

### Storage & Configuration

- **Catalog YAML**: Stores numeric tier (1, 2, or 3) in `data_assurance_tier` field
- **Config YAML**: Maps numeric tiers to human-readable labels in `assurance_tiers` section
- **API Responses**: Returns both `data_assurance_tier` (int) and `data_assurance_label` (string)

## Configuration

### Default Configuration (sample_config.yaml)

```yaml
assurance_tiers:
  enabled: true
  default_tier: 1
  labels:
    1: bronze    # Raw/unvalidated data
    2: silver    # Validated and governed
    3: gold      # Certified and production-ready
```

### Custom Labels Example

For organizations that prefer different terminology:

```yaml
assurance_tiers:
  enabled: true
  default_tier: 1
  labels:
    1: cataloged   # Data is cataloged but not yet validated
    2: governed    # Data governance policies applied
    3: certified   # Full data quality certification
```

Or internal nomenclature:

```yaml
assurance_tiers:
  enabled: true
  default_tier: 1
  labels:
    1: identified  # Data source identified
    2: controlled  # Under data control framework
    3: attested    # Formally attested by data steward
```

## Catalog Definition

### Adding Tiers to Nodes

In `catalog.yaml` or `sample_catalog.yaml`:

```yaml
benchmarks:
  display_name: Benchmarks
  description: Benchmark indices and constituents
  data_assurance_tier: 2  # silver - validated and governed
  ownership:
    accountable_owner: indices-governance@firm.com

benchmarks.constituents:
  display_name: Benchmark Constituents
  data_assurance_tier: 3  # gold - certified and production-ready
  source_binding:
    type: snowflake
    config:
      account: firm-prod.us-east-1
      database: BENCHMARKS

commodities:
  display_name: Commodities
  data_assurance_tier: 1  # bronze - raw data, minimal validation
  ownership:
    accountable_owner: commodities-desk@firm.com

# Node without tier (defaults to null/none)
experimental.new-data:
  display_name: Experimental Data
  # No data_assurance_tier specified - will be null in responses
```

### Validation Rules

- **Valid Values**: Only `1`, `2`, or `3` are accepted
- **Optional Field**: Nodes without `data_assurance_tier` will have `null` in API responses
- **Type Checking**: Must be an integer, not a string

**Invalid Examples:**

```yaml
# ❌ Invalid tier value
bad_node:
  data_assurance_tier: 5  # ERROR: must be 1, 2, or 3

# ❌ String instead of integer
bad_node2:
  data_assurance_tier: "2"  # ERROR: must be integer

# ❌ Zero or negative
bad_node3:
  data_assurance_tier: 0  # ERROR: must be 1, 2, or 3
```

## API Responses

### Resolve Endpoint

**Request:**
```bash
curl http://localhost:8050/resolve/benchmarks.constituents
```

**Response:**
```json
{
  "moniker": "benchmarks.constituents",
  "path": "benchmarks.constituents",
  "type": "leaf",
  "source_type": "snowflake",
  "connection": { ... },
  "ownership": { ... },
  "data_assurance_tier": 3,
  "data_assurance_label": "gold",
  ...
}
```

### Describe Endpoint

**Request:**
```bash
curl http://localhost:8050/describe/benchmarks
```

**Response:**
```json
{
  "path": "benchmarks",
  "display_name": "Benchmarks",
  "ownership": { ... },
  "classification": "internal",
  "data_assurance_tier": 2,
  "data_assurance_label": "silver",
  ...
}
```

### Parent Nodes

Parent nodes (catalog nodes without source bindings) can also have data assurance tiers:

**Request:**
```bash
curl http://localhost:8050/resolve/commodities
```

**Response:**
```json
{
  "moniker": "commodities",
  "path": "commodities",
  "type": "parent",
  "children": ["commodities.crypto", "commodities.energy", "commodities.metals"],
  "data_assurance_tier": 1,
  "data_assurance_label": "bronze",
  ...
}
```

### Nodes Without Tiers

If a node doesn't have `data_assurance_tier` specified:

**Response:**
```json
{
  "moniker": "experimental.new-data",
  "data_assurance_tier": null,
  "data_assurance_label": null,
  ...
}
```

## Implementation Details

### Python Implementation

**Config Class** (`src/moniker_svc/config.py`):
```python
@dataclass
class AssuranceTiersConfig:
    enabled: bool = True
    labels: dict[int, str] = field(default_factory=lambda: {
        1: "bronze", 2: "silver", 3: "gold"
    })
    default_tier: int = 1
```

**CatalogNode** (`src/moniker_svc/catalog/types.py`):
```python
@dataclass(slots=True)
class CatalogNode:
    # ... other fields ...
    data_assurance_tier: int | None = None
```

**Response Mapping** (`src/moniker_svc/main.py`):
```python
# In resolve endpoint
if node and node.data_assurance_tier is not None:
    data_assurance_tier = node.data_assurance_tier
    data_assurance_label = config.assurance_tiers.labels.get(data_assurance_tier)
```

### Java Implementation

**Config Class** (`resolver-java/.../config/AssuranceTiersConfig.java`):
```java
@Data
public class AssuranceTiersConfig {
    private boolean enabled = true;
    private Map<Integer, String> labels = new HashMap<>() {{
        put(1, "bronze");
        put(2, "silver");
        put(3, "gold");
    }};

    public String getLabel(int tier) {
        return labels.get(tier);
    }
}
```

**CatalogNode** (`resolver-java/.../catalog/CatalogNode.java`):
```java
@Data
public class CatalogNode {
    // ... other fields ...
    private Integer dataAssuranceTier;
}
```

### Go Implementation

**Config Struct** (`resolver-go/internal/config/config.go`):
```go
type AssuranceTiersConfig struct {
    Enabled     bool           `yaml:"enabled"`
    DefaultTier int            `yaml:"default_tier"`
    Labels      map[int]string `yaml:"labels"`
}

func (a *AssuranceTiersConfig) GetLabel(tier int) string {
    if !a.Enabled {
        return ""
    }
    return a.Labels[tier]
}
```

**CatalogNode** (`resolver-go/internal/catalog/types.go`):
```go
type CatalogNode struct {
    // ... other fields ...
    DataAssuranceTier *int `json:"data_assurance_tier,omitempty" yaml:"data_assurance_tier,omitempty"`
}
```

## Use Cases

### 1. Data Quality Progression

Track data as it moves through quality gates:

```yaml
# Tier 1: Initial data ingestion
raw.vendor-feeds:
  data_assurance_tier: 1

# Tier 2: After validation and cleansing
validated.vendor-feeds:
  data_assurance_tier: 2

# Tier 3: Production-certified
certified.vendor-feeds:
  data_assurance_tier: 3
```

### 2. Governance Compliance

Map to regulatory compliance levels:

```yaml
assurance_tiers:
  labels:
    1: basic_controls      # Basic data controls
    2: regulatory_ready    # Meets regulatory standards
    3: audit_certified     # Passed external audit
```

### 3. Data Lineage Visualization

Use tiers to color-code nodes in lineage graphs:
- Tier 1 (bronze) → Yellow/Amber
- Tier 2 (silver) → Blue
- Tier 3 (gold) → Green

### 4. SLA Differentiation

Different SLAs based on tier:
- Tier 1: Best effort support
- Tier 2: Business hours support
- Tier 3: 24/7 support with strict SLAs

## Migration Guide

### Existing Catalogs

The feature is fully backwards compatible:

1. **No Changes Required**: Existing catalogs without `data_assurance_tier` continue to work
2. **Gradual Adoption**: Add tiers incrementally, node by node
3. **No Breaking Changes**: API responses include tier fields only when present

### Recommended Migration Steps

1. **Add Configuration**:
   ```bash
   # Add assurance_tiers section to your config.yaml
   vim config.yaml
   ```

2. **Prioritize Critical Data**:
   ```yaml
   # Start with tier 3 (gold) for mission-critical data
   prices.equity:
     data_assurance_tier: 3
   ```

3. **Classify Existing Nodes**:
   ```yaml
   # Tier 1: Raw/unvalidated
   # Tier 2: Validated/governed
   # Tier 3: Certified/production
   ```

4. **Update Documentation**: Document your tier definitions in Confluence/wiki

## Testing

### Validation Test

```bash
# Test invalid tier
cat > test_catalog.yaml <<EOF
invalid_node:
  data_assurance_tier: 5
EOF

python3 -c "from src.moniker_svc.catalog.loader import CatalogLoader; CatalogLoader().load_file('test_catalog.yaml')"
# Expected: ValueError: data_assurance_tier must be 1, 2, or 3
```

### API Test

```bash
# Test resolve with tier
curl http://localhost:8050/resolve/benchmarks.constituents | jq '.data_assurance_tier, .data_assurance_label'
# Expected:
# 3
# "gold"

# Test custom labels
# Update config.yaml with custom labels
curl http://localhost:8050/resolve/benchmarks.constituents | jq '.data_assurance_label'
# Expected: Your custom label for tier 3
```

### Load Test

```bash
# Verify no performance impact
hey -z 30s -c 50 http://localhost:8050/resolve/benchmarks.constituents
```

## Troubleshooting

### Tier Not Appearing in Response

**Symptom**: API response has `null` for tier fields

**Causes:**
1. No `data_assurance_tier` specified in catalog YAML
2. Feature disabled in config (`enabled: false`)
3. Invalid tier value (logged as warning, ignored)

**Solution:**
```yaml
# Ensure tier is set in catalog
benchmarks:
  data_assurance_tier: 2

# Ensure feature is enabled in config
assurance_tiers:
  enabled: true
```

### Label Shows as null but Tier is Set

**Symptom**: `data_assurance_tier: 2` but `data_assurance_label: null`

**Cause**: Label not defined in config for that tier

**Solution:**
```yaml
assurance_tiers:
  labels:
    1: bronze
    2: silver  # Make sure this exists
    3: gold
```

### Validation Error on Load

**Symptom**: `ValueError: data_assurance_tier must be 1, 2, or 3`

**Cause**: Invalid tier value in catalog

**Solution**: Use only 1, 2, or 3
```yaml
# ❌ Wrong
node:
  data_assurance_tier: 4

# ✅ Correct
node:
  data_assurance_tier: 2
```

## Best Practices

1. **Consistent Tier Definitions**: Document what each tier means for your organization
2. **Regular Reviews**: Periodically review and update node tiers as data quality improves
3. **Automation**: Consider automated tier assignment based on data quality metrics
4. **Inheritance**: Parent node tiers can indicate default tier for children (future enhancement)
5. **Audit Trail**: Track tier changes in version control (catalog YAML commits)

## Future Enhancements

Potential future improvements (not yet implemented):

- **Tier Inheritance**: Children inherit tier from parent if not specified
- **Tier History**: Track tier changes over time in audit log
- **Tier-Based Access Control**: Restrict access based on data assurance level
- **Automated Tier Calculation**: Calculate tier from data quality metrics
- **Tier Alerts**: Notify when tier changes (promotion/demotion)
- **Tier Dashboard**: Visual dashboard showing tier distribution across catalog

## References

- Configuration Schema: `src/moniker_svc/config.py`
- Catalog Types: `src/moniker_svc/catalog/types.py`
- Catalog Loader: `src/moniker_svc/catalog/loader.py`
- Sample Config: `sample_config.yaml`
- Sample Catalog: `sample_catalog.yaml`
