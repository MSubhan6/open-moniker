package service

import (
	"github.com/ganizanisitara/open-moniker-svc/resolver-go/internal/catalog"
)

// ResolvedSource represents the result of resolving a moniker
type ResolvedSource struct {
	SourceType string                 `json:"source_type"`
	Connection map[string]interface{} `json:"connection"`
	Query      *string                `json:"query,omitempty"`
	Params     map[string]interface{} `json:"params,omitempty"`
	Schema     map[string]interface{} `json:"schema,omitempty"`
	ReadOnly   bool                   `json:"read_only"`
}

// ResolveResult represents the full resolution result
type ResolveResult struct {
	Moniker        string                       `json:"moniker"`
	Path           string                       `json:"path"`
	Type           string                       `json:"type"` // "leaf" or "parent"
	Source         *ResolvedSource              `json:"source,omitempty"` // nil for parent nodes
	Ownership      *catalog.ResolvedOwnership   `json:"ownership"`
	Node           *catalog.CatalogNode         `json:"node,omitempty"`
	BindingPath    string                       `json:"binding_path,omitempty"`
	SubPath        *string                      `json:"sub_path,omitempty"`
	RedirectedFrom *string                      `json:"redirected_from,omitempty"`
	Children       []string                     `json:"children,omitempty"` // populated for parent nodes
}

// DescribeResult represents metadata about a path
type DescribeResult struct {
	Node             *catalog.CatalogNode       `json:"node,omitempty"`
	Ownership        *catalog.ResolvedOwnership `json:"ownership"`
	Moniker          string                     `json:"moniker"`
	Path             string                     `json:"path"`
	HasSourceBinding bool                       `json:"has_source_binding"`
	SourceType       *string                    `json:"source_type,omitempty"`
}

// ListResult represents children of a path
type ListResult struct {
	Children  []string                   `json:"children"`
	Moniker   string                     `json:"moniker"`
	Path      string                     `json:"path"`
	Ownership *catalog.ResolvedOwnership `json:"ownership,omitempty"`
}

// CallerIdentity represents the identity of the API caller
type CallerIdentity struct {
	UserID   string  `json:"user_id"`
	Username *string `json:"username,omitempty"`
	Source   string  `json:"source"` // "api_key", "jwt", "kerberos", etc.
}

// ResolutionError represents an error during resolution
type ResolutionError struct {
	Message string
}

func (e *ResolutionError) Error() string {
	return e.Message
}

// NotFoundError represents a path not found error
type NotFoundError struct {
	Path string
}

func (e *NotFoundError) Error() string {
	return "Path not found: " + e.Path
}

// AccessDeniedError represents an access policy violation
type AccessDeniedError struct {
	Message       string
	EstimatedRows *int
}

func (e *AccessDeniedError) Error() string {
	return e.Message
}
