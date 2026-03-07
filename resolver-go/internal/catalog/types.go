package catalog

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"regexp"
	"strings"
)

// SourceType represents supported data source types
type SourceType string

const (
	SourceTypeSnowflake  SourceType = "snowflake"
	SourceTypeOracle     SourceType = "oracle"
	SourceTypeMSSQL      SourceType = "mssql" // Microsoft SQL Server
	SourceTypeREST       SourceType = "rest"
	SourceTypeStatic     SourceType = "static"
	SourceTypeExcel      SourceType = "excel"
	SourceTypeBloomberg  SourceType = "bloomberg"
	SourceTypeRefinitiv  SourceType = "refinitiv"
	SourceTypeOpenSearch SourceType = "opensearch" // OpenSearch/Elasticsearch
	// Synthetic/computed sources
	SourceTypeComposite SourceType = "composite" // Combines multiple sources
	SourceTypeDerived   SourceType = "derived"   // Computed from other monikers
)

// NodeStatus represents lifecycle status for catalog nodes
type NodeStatus string

const (
	NodeStatusDraft         NodeStatus = "draft"          // Being defined, not visible to clients
	NodeStatusPendingReview NodeStatus = "pending_review" // Submitted for governance review
	NodeStatusApproved      NodeStatus = "approved"       // Governance approved, ready to activate
	NodeStatusActive        NodeStatus = "active"         // Live and resolvable
	NodeStatusDeprecated    NodeStatus = "deprecated"     // Still works but clients warned
	NodeStatusArchived      NodeStatus = "archived"       // No longer resolvable
)

// Ownership represents ownership for a catalog node with data governance roles
type Ownership struct {
	// Simplified ownership fields
	AccountableOwner *string `json:"accountable_owner,omitempty" yaml:"accountable_owner,omitempty"`
	DataSpecialist   *string `json:"data_specialist,omitempty" yaml:"data_specialist,omitempty"`
	SupportChannel   *string `json:"support_channel,omitempty" yaml:"support_channel,omitempty"`

	// Formal data governance roles (BCBS 239 / DAMA style)
	ADOP     *string `json:"adop,omitempty" yaml:"adop,omitempty"`         // Accountable Data Owner/Principal
	ADS      *string `json:"ads,omitempty" yaml:"ads,omitempty"`           // Accountable Data Steward
	ADAL     *string `json:"adal,omitempty" yaml:"adal,omitempty"`         // Accountable Data Access Lead
	ADOPName *string `json:"adop_name,omitempty" yaml:"adop_name,omitempty"` // Human-readable names
	ADSName  *string `json:"ads_name,omitempty" yaml:"ads_name,omitempty"`
	ADALName *string `json:"adal_name,omitempty" yaml:"adal_name,omitempty"`

	// UI link - URL to a custom UI/dashboard for this node
	UI *string `json:"ui,omitempty" yaml:"ui,omitempty"`
}

// MergeWithParent merges this ownership with a parent, using parent values for any fields not set
func (o *Ownership) MergeWithParent(parent *Ownership) *Ownership {
	return &Ownership{
		AccountableOwner: firstNonNil(o.AccountableOwner, parent.AccountableOwner),
		DataSpecialist:   firstNonNil(o.DataSpecialist, parent.DataSpecialist),
		SupportChannel:   firstNonNil(o.SupportChannel, parent.SupportChannel),
		ADOP:             firstNonNil(o.ADOP, parent.ADOP),
		ADS:              firstNonNil(o.ADS, parent.ADS),
		ADAL:             firstNonNil(o.ADAL, parent.ADAL),
		ADOPName:         firstNonNil(o.ADOPName, parent.ADOPName),
		ADSName:          firstNonNil(o.ADSName, parent.ADSName),
		ADALName:         firstNonNil(o.ADALName, parent.ADALName),
		UI:               firstNonNil(o.UI, parent.UI),
	}
}

// IsComplete checks if all ownership fields are defined
func (o *Ownership) IsComplete() bool {
	return o.AccountableOwner != nil && o.DataSpecialist != nil && o.SupportChannel != nil
}

// HasGovernanceRoles checks if any formal governance roles are defined
func (o *Ownership) HasGovernanceRoles() bool {
	return o.ADOP != nil || o.ADS != nil || o.ADAL != nil
}

// IsEmpty checks if no ownership fields are defined
func (o *Ownership) IsEmpty() bool {
	return o.AccountableOwner == nil && o.DataSpecialist == nil && o.SupportChannel == nil &&
		o.ADOP == nil && o.ADS == nil && o.ADAL == nil
}

// Helper function to get first non-nil string pointer
func firstNonNil(ptrs ...*string) *string {
	for _, p := range ptrs {
		if p != nil {
			return p
		}
	}
	return nil
}

// QueryCacheConfig represents cache configuration for expensive queries
type QueryCacheConfig struct {
	Enabled                 bool `json:"enabled" yaml:"enabled"`
	TTLSeconds              int  `json:"ttl_seconds" yaml:"ttl_seconds"`
	RefreshIntervalSeconds  int  `json:"refresh_interval_seconds" yaml:"refresh_interval_seconds"`
	RefreshOnStartup        bool `json:"refresh_on_startup" yaml:"refresh_on_startup"`
}

// SourceBinding represents binding to an actual data source
type SourceBinding struct {
	SourceType        SourceType                 `json:"type" yaml:"type"`
	Config            map[string]interface{}     `json:"config" yaml:"config"`
	AllowedOperations []string                   `json:"allowed_operations,omitempty" yaml:"allowed_operations,omitempty"`
	Schema            map[string]interface{}     `json:"schema,omitempty" yaml:"schema,omitempty"`
	ReadOnly          bool                       `json:"read_only" yaml:"read_only"`
	Cache             *QueryCacheConfig          `json:"cache,omitempty" yaml:"cache,omitempty"`
}

// Fingerprint returns SHA-256 fingerprint of the binding contract
func (sb *SourceBinding) Fingerprint() string {
	data := map[string]interface{}{
		"source_type":         string(sb.SourceType),
		"config":              sb.Config,
		"allowed_operations":  sb.AllowedOperations,
		"schema":              sb.Schema,
		"read_only":           sb.ReadOnly,
	}
	raw, _ := json.Marshal(data)
	hash := sha256.Sum256(raw)
	return fmt.Sprintf("%x", hash[:8]) // First 16 hex chars (8 bytes)
}

// AccessPolicy represents access policy for controlling query patterns
type AccessPolicy struct {
	RequiredSegments         []int    `json:"required_segments,omitempty" yaml:"required_segments,omitempty"`
	MinFilters               int      `json:"min_filters,omitempty" yaml:"min_filters,omitempty"`
	BlockedPatterns          []string `json:"blocked_patterns,omitempty" yaml:"blocked_patterns,omitempty"`
	MaxRowsWarn              *int     `json:"max_rows_warn,omitempty" yaml:"max_rows_warn,omitempty"`
	MaxRowsBlock             *int     `json:"max_rows_block,omitempty" yaml:"max_rows_block,omitempty"`
	CardinalityMultipliers   []int    `json:"cardinality_multipliers,omitempty" yaml:"cardinality_multipliers,omitempty"`
	BaseRowCount             int      `json:"base_row_count" yaml:"base_row_count"`
	RequireConfirmationAbove *int     `json:"require_confirmation_above,omitempty" yaml:"require_confirmation_above,omitempty"`
	DenialMessage            *string  `json:"denial_message,omitempty" yaml:"denial_message,omitempty"`
	AllowedRoles             []string `json:"allowed_roles,omitempty" yaml:"allowed_roles,omitempty"`
	AllowedHours             *[2]int  `json:"allowed_hours,omitempty" yaml:"allowed_hours,omitempty"` // [start_hour, end_hour] in UTC
}

// EstimateRows estimates the number of rows that would be returned based on segment values
func (ap *AccessPolicy) EstimateRows(segments []string) int {
	multiplier := 1
	for i, seg := range segments {
		if strings.ToUpper(seg) == "ALL" {
			if i < len(ap.CardinalityMultipliers) {
				multiplier *= ap.CardinalityMultipliers[i]
			} else {
				multiplier *= 100 // Default multiplier for unknown segments
			}
		}
	}
	baseCount := ap.BaseRowCount
	if baseCount == 0 {
		baseCount = 100
	}
	return baseCount * multiplier
}

// Validate validates if a query pattern is allowed
// Returns (is_allowed, error_message, estimated_rows)
func (ap *AccessPolicy) Validate(segments []string) (bool, *string, int) {
	path := strings.Join(segments, "/")
	estimatedRows := ap.EstimateRows(segments)

	// Check blocked patterns
	for _, pattern := range ap.BlockedPatterns {
		matched, _ := regexp.MatchString("(?i)"+pattern, path)
		if matched {
			msg := fmt.Sprintf("Query pattern '%s' is blocked by access policy", path)
			if ap.DenialMessage != nil {
				msg = *ap.DenialMessage
			}
			return false, &msg, estimatedRows
		}
	}

	// Check required segments
	for _, idx := range ap.RequiredSegments {
		if idx < len(segments) && strings.ToUpper(segments[idx]) == "ALL" {
			msg := fmt.Sprintf("Access policy requires segment %d to be specified (cannot use ALL)", idx)
			return false, &msg, estimatedRows
		}
	}

	// Check minimum filters
	if ap.MinFilters > 0 {
		nonAllCount := 0
		for _, s := range segments {
			if strings.ToUpper(s) != "ALL" {
				nonAllCount++
			}
		}
		if nonAllCount < ap.MinFilters {
			msg := fmt.Sprintf("Access policy requires at least %d specific filters, but only %d provided",
				ap.MinFilters, nonAllCount)
			return false, &msg, estimatedRows
		}
	}

	// Check row limits
	if ap.MaxRowsBlock != nil && estimatedRows > *ap.MaxRowsBlock {
		msg := fmt.Sprintf("Query would return ~%d rows, exceeding limit of %d. Add more specific filters to reduce result size.",
			estimatedRows, *ap.MaxRowsBlock)
		if ap.DenialMessage != nil {
			msg = *ap.DenialMessage
		}
		return false, &msg, estimatedRows
	}

	// Warning for large queries (but allowed)
	var warning *string
	if ap.MaxRowsWarn != nil && estimatedRows > *ap.MaxRowsWarn {
		w := fmt.Sprintf("Large query: estimated %d rows", estimatedRows)
		warning = &w
	}

	return true, warning, estimatedRows
}

// DataQuality represents data quality information for a catalog node
type DataQuality struct {
	DQOwner         *string  `json:"dq_owner,omitempty" yaml:"dq_owner,omitempty"`
	QualityScore    *float64 `json:"quality_score,omitempty" yaml:"quality_score,omitempty"`
	ValidationRules []string `json:"validation_rules,omitempty" yaml:"validation_rules,omitempty"`
	KnownIssues     []string `json:"known_issues,omitempty" yaml:"known_issues,omitempty"`
	LastValidated   *string  `json:"last_validated,omitempty" yaml:"last_validated,omitempty"` // ISO format
}

// SLA represents service level agreement for a data source
type SLA struct {
	Freshness          *string `json:"freshness,omitempty" yaml:"freshness,omitempty"`
	Availability       *string `json:"availability,omitempty" yaml:"availability,omitempty"`
	SupportHours       *string `json:"support_hours,omitempty" yaml:"support_hours,omitempty"`
	EscalationContact  *string `json:"escalation_contact,omitempty" yaml:"escalation_contact,omitempty"`
}

// Freshness represents data freshness information
type Freshness struct {
	LastLoaded           *string  `json:"last_loaded,omitempty" yaml:"last_loaded,omitempty"`
	RefreshSchedule      *string  `json:"refresh_schedule,omitempty" yaml:"refresh_schedule,omitempty"`
	SourceSystem         *string  `json:"source_system,omitempty" yaml:"source_system,omitempty"`
	UpstreamDependencies []string `json:"upstream_dependencies,omitempty" yaml:"upstream_dependencies,omitempty"`
}

// ColumnSchema represents schema definition for a single column
type ColumnSchema struct {
	Name         string  `json:"name" yaml:"name"`
	DataType     string  `json:"data_type" yaml:"data_type"` // "string", "float", "date", "integer", "boolean"
	Description  string  `json:"description,omitempty" yaml:"description,omitempty"`
	SemanticType *string `json:"semantic_type,omitempty" yaml:"semantic_type,omitempty"` // "identifier", "measure", "dimension", "timestamp"
	Example      *string `json:"example,omitempty" yaml:"example,omitempty"`
	Nullable     bool    `json:"nullable" yaml:"nullable"`
	PrimaryKey   bool    `json:"primary_key,omitempty" yaml:"primary_key,omitempty"`
	ForeignKey   *string `json:"foreign_key,omitempty" yaml:"foreign_key,omitempty"` // Reference to another moniker path
}

// DataSchema represents schema metadata for a data source
type DataSchema struct {
	Columns         []ColumnSchema `json:"columns,omitempty" yaml:"columns,omitempty"`
	Description     string         `json:"description,omitempty" yaml:"description,omitempty"`
	SemanticTags    []string       `json:"semantic_tags,omitempty" yaml:"semantic_tags,omitempty"`
	PrimaryKey      []string       `json:"primary_key,omitempty" yaml:"primary_key,omitempty"`
	UseCases        []string       `json:"use_cases,omitempty" yaml:"use_cases,omitempty"`
	Examples        []string       `json:"examples,omitempty" yaml:"examples,omitempty"`
	RelatedMonikers []string       `json:"related_monikers,omitempty" yaml:"related_monikers,omitempty"`
	Granularity     *string        `json:"granularity,omitempty" yaml:"granularity,omitempty"`
	TypicalRowCount *string        `json:"typical_row_count,omitempty" yaml:"typical_row_count,omitempty"` // e.g., "1K-10K", "1M-10M"
	UpdateFrequency *string        `json:"update_frequency,omitempty" yaml:"update_frequency,omitempty"`   // e.g., "daily", "real-time", "monthly"
}

// Documentation represents documentation links for a data source
type Documentation struct {
	GlossaryURL        *string           `json:"glossary_url,omitempty" yaml:"glossary_url,omitempty"`
	RunbookURL         *string           `json:"runbook_url,omitempty" yaml:"runbook_url,omitempty"`
	OnboardingURL      *string           `json:"onboarding_url,omitempty" yaml:"onboarding_url,omitempty"`
	DataDictionaryURL  *string           `json:"data_dictionary_url,omitempty" yaml:"data_dictionary_url,omitempty"`
	APIDocsURL         *string           `json:"api_docs_url,omitempty" yaml:"api_docs_url,omitempty"`
	ArchitectureURL    *string           `json:"architecture_url,omitempty" yaml:"architecture_url,omitempty"`
	ChangelogURL       *string           `json:"changelog_url,omitempty" yaml:"changelog_url,omitempty"`
	ContactURL         *string           `json:"contact_url,omitempty" yaml:"contact_url,omitempty"`
	AdditionalLinks    map[string]string `json:"additional_links,omitempty" yaml:"additional_links,omitempty"`
}

// ToDict converts documentation to dictionary for API responses
func (d *Documentation) ToDict() map[string]interface{} {
	result := make(map[string]interface{})
	if d.GlossaryURL != nil {
		result["glossary"] = *d.GlossaryURL
	}
	if d.RunbookURL != nil {
		result["runbook"] = *d.RunbookURL
	}
	if d.OnboardingURL != nil {
		result["onboarding"] = *d.OnboardingURL
	}
	if d.DataDictionaryURL != nil {
		result["data_dictionary"] = *d.DataDictionaryURL
	}
	if d.APIDocsURL != nil {
		result["api_docs"] = *d.APIDocsURL
	}
	if d.ArchitectureURL != nil {
		result["architecture"] = *d.ArchitectureURL
	}
	if d.ChangelogURL != nil {
		result["changelog"] = *d.ChangelogURL
	}
	if d.ContactURL != nil {
		result["contact"] = *d.ContactURL
	}
	if len(d.AdditionalLinks) > 0 {
		result["additional"] = d.AdditionalLinks
	}
	return result
}

// IsEmpty checks if no documentation links are defined
func (d *Documentation) IsEmpty() bool {
	return d.GlossaryURL == nil && d.RunbookURL == nil && d.OnboardingURL == nil &&
		d.DataDictionaryURL == nil && d.APIDocsURL == nil && d.ArchitectureURL == nil &&
		d.ChangelogURL == nil && d.ContactURL == nil && len(d.AdditionalLinks) == 0
}

// AuditEntry represents a record of a change to a catalog node
type AuditEntry struct {
	Timestamp string  `json:"timestamp" yaml:"timestamp"` // ISO format
	Path      string  `json:"path" yaml:"path"`
	Action    string  `json:"action" yaml:"action"` // created, updated, status_changed, ownership_changed
	Actor     string  `json:"actor" yaml:"actor"`
	OldValue  *string `json:"old_value,omitempty" yaml:"old_value,omitempty"`
	NewValue  *string `json:"new_value,omitempty" yaml:"new_value,omitempty"`
	Details   *string `json:"details,omitempty" yaml:"details,omitempty"`
}

// CatalogNode represents a node in the catalog hierarchy
type CatalogNode struct {
	Path        string     `json:"path" yaml:"-"`
	DisplayName string     `json:"display_name" yaml:"display_name"`
	Description string     `json:"description" yaml:"description"`

	// Domain mapping (for top-level nodes)
	Domain *string `json:"domain,omitempty" yaml:"domain,omitempty"`

	// Ownership (inherits from ancestors if not set)
	Ownership *Ownership `json:"ownership,omitempty" yaml:"ownership,omitempty"`

	// Source binding (only leaf nodes typically have this)
	SourceBinding *SourceBinding `json:"source_binding,omitempty" yaml:"source_binding,omitempty"`

	// Data governance
	DataQuality *DataQuality   `json:"data_quality,omitempty" yaml:"data_quality,omitempty"`
	SLA         *SLA           `json:"sla,omitempty" yaml:"sla,omitempty"`
	Freshness   *Freshness     `json:"freshness,omitempty" yaml:"freshness,omitempty"`

	// Machine-readable schema for AI agent discoverability
	DataSchema *DataSchema `json:"schema,omitempty" yaml:"schema,omitempty"`

	// Access policy for query guardrails
	AccessPolicy *AccessPolicy `json:"access_policy,omitempty" yaml:"access_policy,omitempty"`

	// Documentation links
	Documentation *Documentation `json:"documentation,omitempty" yaml:"documentation,omitempty"`

	// Data classification
	Classification string `json:"classification" yaml:"classification"`

	// Data assurance tier (1=bronze, 2=silver, 3=gold - configurable labels)
	DataAssuranceTier *int `json:"data_assurance_tier,omitempty" yaml:"data_assurance_tier,omitempty"`

	// Tags for searchability
	Tags []string `json:"tags,omitempty" yaml:"tags,omitempty"`

	// Additional metadata
	Metadata map[string]interface{} `json:"metadata,omitempty" yaml:"metadata,omitempty"`

	// Governance lifecycle
	Status              NodeStatus `json:"status" yaml:"status"`
	CreatedAt           *string    `json:"created_at,omitempty" yaml:"created_at,omitempty"`
	UpdatedAt           *string    `json:"updated_at,omitempty" yaml:"updated_at,omitempty"`
	CreatedBy           *string    `json:"created_by,omitempty" yaml:"created_by,omitempty"`
	ApprovedBy          *string    `json:"approved_by,omitempty" yaml:"approved_by,omitempty"`
	DeprecationMessage  *string    `json:"deprecation_message,omitempty" yaml:"deprecation_message,omitempty"`

	// Successor-based migration
	Successor         *string `json:"successor,omitempty" yaml:"successor,omitempty"`
	SunsetDeadline    *string `json:"sunset_deadline,omitempty" yaml:"sunset_deadline,omitempty"`
	MigrationGuideURL *string `json:"migration_guide_url,omitempty" yaml:"migration_guide_url,omitempty"`

	// Is this a leaf node (actual data) or category (contains children)?
	IsLeaf bool `json:"is_leaf" yaml:"is_leaf"`
}

// ResolvedOwnership represents ownership resolved through the hierarchy, with provenance
type ResolvedOwnership struct {
	// Simplified ownership with provenance
	AccountableOwner       *string `json:"accountable_owner,omitempty"`
	AccountableOwnerSource *string `json:"accountable_owner_source,omitempty"`

	DataSpecialist       *string `json:"data_specialist,omitempty"`
	DataSpecialistSource *string `json:"data_specialist_source,omitempty"`

	SupportChannel       *string `json:"support_channel,omitempty"`
	SupportChannelSource *string `json:"support_channel_source,omitempty"`

	// Formal governance roles with provenance
	ADOP       *string `json:"adop,omitempty"`
	ADOPSource *string `json:"adop_source,omitempty"`
	ADOPName   *string `json:"adop_name,omitempty"`
	ADOPNameSource *string `json:"adop_name_source,omitempty"`

	ADS        *string `json:"ads,omitempty"`
	ADSSource  *string `json:"ads_source,omitempty"`
	ADSName    *string `json:"ads_name,omitempty"`
	ADSNameSource *string `json:"ads_name_source,omitempty"`

	ADAL       *string `json:"adal,omitempty"`
	ADALSource *string `json:"adal_source,omitempty"`
	ADALName   *string `json:"adal_name,omitempty"`
	ADALNameSource *string `json:"adal_name_source,omitempty"`

	UI       *string `json:"ui,omitempty"`
	UISource *string `json:"ui_source,omitempty"`
}

// ToOwnership converts ResolvedOwnership to simple Ownership (without provenance)
func (ro *ResolvedOwnership) ToOwnership() *Ownership {
	return &Ownership{
		AccountableOwner: ro.AccountableOwner,
		DataSpecialist:   ro.DataSpecialist,
		SupportChannel:   ro.SupportChannel,
		ADOP:             ro.ADOP,
		ADS:              ro.ADS,
		ADAL:             ro.ADAL,
		ADOPName:         ro.ADOPName,
		ADSName:          ro.ADSName,
		ADALName:         ro.ADALName,
		UI:               ro.UI,
	}
}

// GovernanceRoles returns governance roles with their provenance as a map
func (ro *ResolvedOwnership) GovernanceRoles() map[string]map[string]*string {
	return map[string]map[string]*string{
		"adop": {
			"value":      ro.ADOP,
			"name":       ro.ADOPName,
			"defined_at": ro.ADOPSource,
		},
		"ads": {
			"value":      ro.ADS,
			"name":       ro.ADSName,
			"defined_at": ro.ADSSource,
		},
		"adal": {
			"value":      ro.ADAL,
			"name":       ro.ADALName,
			"defined_at": ro.ADALSource,
		},
	}
}
