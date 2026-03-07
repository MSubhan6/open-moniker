package catalog

import (
	"fmt"
	"os"

	"gopkg.in/yaml.v3"
)

// CatalogYAML represents the structure of a catalog YAML file
// The catalog YAML is a flat map of path -> node (no "nodes" wrapper)
type CatalogYAML map[string]*CatalogNodeYAML

// CatalogNodeYAML represents a node in the YAML file
type CatalogNodeYAML struct {
	DisplayName       string             `yaml:"display_name"`
	Description       string             `yaml:"description"`
	Domain            *string            `yaml:"domain"`
	Ownership         *OwnershipYAML     `yaml:"ownership"`
	SourceBinding     *SourceBindingYAML `yaml:"source_binding"`
	AccessPolicy      *AccessPolicyYAML  `yaml:"access_policy"`
	Classification    string             `yaml:"classification"`
	DataAssuranceTier *int               `yaml:"data_assurance_tier"`
	Tags              []string           `yaml:"tags"`
	Status            string             `yaml:"status"`
	IsLeaf            bool               `yaml:"is_leaf"`
	Successor         *string            `yaml:"successor"`
}

// OwnershipYAML represents ownership in YAML
type OwnershipYAML struct {
	AccountableOwner *string `yaml:"accountable_owner"`
	DataSpecialist   *string `yaml:"data_specialist"`
	SupportChannel   *string `yaml:"support_channel"`
	ADOP             *string `yaml:"adop"`
	ADS              *string `yaml:"ads"`
	ADAL             *string `yaml:"adal"`
	ADOPName         *string `yaml:"adop_name"`
	ADSName          *string `yaml:"ads_name"`
	ADALName         *string `yaml:"adal_name"`
	UI               *string `yaml:"ui"`
}

// SourceBindingYAML represents a source binding in YAML
type SourceBindingYAML struct {
	Type              string                 `yaml:"type"`
	Config            map[string]interface{} `yaml:"config"`
	AllowedOperations []string               `yaml:"allowed_operations"`
	Schema            map[string]interface{} `yaml:"schema"`
	ReadOnly          *bool                  `yaml:"read_only"`
}

// AccessPolicyYAML represents access policy in YAML
type AccessPolicyYAML struct {
	RequiredSegments       []int    `yaml:"required_segments"`
	MinFilters             *int     `yaml:"min_filters"`
	BlockedPatterns        []string `yaml:"blocked_patterns"`
	MaxRowsWarn            *int     `yaml:"max_rows_warn"`
	MaxRowsBlock           *int     `yaml:"max_rows_block"`
	CardinalityMultipliers []int    `yaml:"cardinality_multipliers"`
	BaseRowCount           *int     `yaml:"base_row_count"`
	DenialMessage          *string  `yaml:"denial_message"`
}

// LoadCatalog loads a catalog from a YAML file
func LoadCatalog(path string) ([]*CatalogNode, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read catalog file: %w", err)
	}

	var catalogYAML CatalogYAML
	if err := yaml.Unmarshal(data, &catalogYAML); err != nil {
		return nil, fmt.Errorf("parse catalog YAML: %w", err)
	}

	nodes := make([]*CatalogNode, 0, len(catalogYAML))
	for path, nodeYAML := range catalogYAML {
		if nodeYAML != nil {
			node := convertYAMLToNode(path, nodeYAML)
			nodes = append(nodes, node)
		}
	}

	return nodes, nil
}

func convertYAMLToNode(path string, yaml *CatalogNodeYAML) *CatalogNode {
	node := &CatalogNode{
		Path:              path,
		DisplayName:       yaml.DisplayName,
		Description:       yaml.Description,
		Domain:            yaml.Domain,
		Classification:    yaml.Classification,
		DataAssuranceTier: yaml.DataAssuranceTier,
		Tags:              yaml.Tags,
		IsLeaf:            yaml.IsLeaf,
		Successor:         yaml.Successor,
	}

	// Set default classification
	if node.Classification == "" {
		node.Classification = "internal"
	}

	// Validate data assurance tier
	if node.DataAssuranceTier != nil {
		tier := *node.DataAssuranceTier
		if tier < 1 || tier > 3 {
			// Log warning but don't fail - be lenient in Go implementation
			fmt.Printf("Warning: data_assurance_tier must be 1, 2, or 3 for node '%s', got: %d\n", path, tier)
			node.DataAssuranceTier = nil // Ignore invalid tier
		}
	}

	// Parse status
	if yaml.Status != "" {
		node.Status = NodeStatus(yaml.Status)
	} else {
		node.Status = NodeStatusActive
	}

	// Convert ownership
	if yaml.Ownership != nil {
		node.Ownership = &Ownership{
			AccountableOwner: yaml.Ownership.AccountableOwner,
			DataSpecialist:   yaml.Ownership.DataSpecialist,
			SupportChannel:   yaml.Ownership.SupportChannel,
			ADOP:             yaml.Ownership.ADOP,
			ADS:              yaml.Ownership.ADS,
			ADAL:             yaml.Ownership.ADAL,
			ADOPName:         yaml.Ownership.ADOPName,
			ADSName:          yaml.Ownership.ADSName,
			ADALName:         yaml.Ownership.ADALName,
			UI:               yaml.Ownership.UI,
		}
	}

	// Convert source binding
	if yaml.SourceBinding != nil {
		readOnly := true
		if yaml.SourceBinding.ReadOnly != nil {
			readOnly = *yaml.SourceBinding.ReadOnly
		}

		node.SourceBinding = &SourceBinding{
			SourceType:        SourceType(yaml.SourceBinding.Type),
			Config:            yaml.SourceBinding.Config,
			AllowedOperations: yaml.SourceBinding.AllowedOperations,
			Schema:            yaml.SourceBinding.Schema,
			ReadOnly:          readOnly,
		}
	}

	// Convert access policy
	if yaml.AccessPolicy != nil {
		baseRowCount := 100
		if yaml.AccessPolicy.BaseRowCount != nil {
			baseRowCount = *yaml.AccessPolicy.BaseRowCount
		}

		node.AccessPolicy = &AccessPolicy{
			RequiredSegments:       yaml.AccessPolicy.RequiredSegments,
			MinFilters:             0,
			BlockedPatterns:        yaml.AccessPolicy.BlockedPatterns,
			MaxRowsWarn:            yaml.AccessPolicy.MaxRowsWarn,
			MaxRowsBlock:           yaml.AccessPolicy.MaxRowsBlock,
			CardinalityMultipliers: yaml.AccessPolicy.CardinalityMultipliers,
			BaseRowCount:           baseRowCount,
			DenialMessage:          yaml.AccessPolicy.DenialMessage,
		}

		if yaml.AccessPolicy.MinFilters != nil {
			node.AccessPolicy.MinFilters = *yaml.AccessPolicy.MinFilters
		}
	}

	return node
}
