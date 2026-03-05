package service

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/ganizanisitara/open-moniker-svc/resolver-go/internal/cache"
	"github.com/ganizanisitara/open-moniker-svc/resolver-go/internal/catalog"
	"github.com/ganizanisitara/open-moniker-svc/resolver-go/internal/config"
	"github.com/ganizanisitara/open-moniker-svc/resolver-go/internal/moniker"
	"github.com/ganizanisitara/open-moniker-svc/resolver-go/internal/telemetry"
)

const maxSuccessorDepth = 5

// MonikerService provides moniker resolution
type MonikerService struct {
	catalog *catalog.Registry
	cache   *cache.InMemory
	config  *config.Config
	emitter *telemetry.Emitter
}

// NewMonikerService creates a new moniker service
func NewMonikerService(reg *catalog.Registry, cacheInst *cache.InMemory, cfg *config.Config, emitter *telemetry.Emitter) *MonikerService {
	return &MonikerService{
		catalog: reg,
		cache:   cacheInst,
		config:  cfg,
		emitter: emitter,
	}
}

// Resolve resolves a moniker to its source binding
func (s *MonikerService) Resolve(ctx context.Context, monikerStr string, caller *CallerIdentity) (*ResolveResult, error) {
	start := time.Now()
	outcome := telemetry.OutcomeSuccess
	var result *ResolveResult
	var err error

	// Defer telemetry emission
	defer func() {
		latency := float64(time.Since(start).Microseconds()) / 1000.0 // Convert to milliseconds
		s.emitResolveTelemetry(monikerStr, caller, outcome, latency, result, err)
	}()

	// Parse moniker
	m, parseErr := moniker.ParseMoniker(monikerStr)
	if parseErr != nil {
		outcome = telemetry.OutcomeError
		err = &ResolutionError{Message: fmt.Sprintf("Invalid moniker: %v", parseErr)}
		return nil, err
	}

	// Get the path
	path := m.CanonicalPath()

	// Find source binding (walk hierarchy if needed)
	binding, bindingPath := s.catalog.FindSourceBinding(path)
	if binding == nil {
		// Check if this is a parent node with children
		children := s.catalog.ChildrenPaths(path)
		if len(children) > 0 {
			// This is a parent node - return children list
			ownership := s.catalog.ResolveOwnership(path)
			result = &ResolveResult{
				Moniker:   monikerStr,
				Path:      path,
				Type:      "parent",
				Source:    nil,
				Ownership: ownership,
				Children:  children,
			}
			return result, nil
		}

		// No source binding and no children - not found
		outcome = telemetry.OutcomeNotFound
		err = &NotFoundError{Path: path}
		return nil, err
	}

	// Check for successor redirect
	node := s.catalog.Get(bindingPath)
	if node != nil && node.Status == catalog.NodeStatusDeprecated && node.Successor != nil {
		// Follow successor chain (with depth limit)
		successorPath := *node.Successor
		for depth := 0; depth < maxSuccessorDepth; depth++ {
			successorNode := s.catalog.Get(successorPath)
			if successorNode == nil {
				break
			}
			if successorNode.Status != catalog.NodeStatusDeprecated || successorNode.Successor == nil {
				// Found non-deprecated successor
				binding, bindingPath = s.catalog.FindSourceBinding(successorPath)
				if binding != nil {
					// Redirect successful
					redirectFrom := path
					path = successorPath
					node = successorNode

					result = s.buildResolveResult(m, path, binding, bindingPath, node)
					result.RedirectedFrom = &redirectFrom
					return result, nil
				}
				break
			}
			successorPath = *successorNode.Successor
		}
	}

	// Validate access policy if present
	if node != nil && node.AccessPolicy != nil {
		segments := m.Path.Segments
		allowed, message, estimatedRows := node.AccessPolicy.Validate(segments)
		if !allowed {
			outcome = telemetry.OutcomeUnauthorized
			err = &AccessDeniedError{
				Message:       *message,
				EstimatedRows: &estimatedRows,
			}
			return nil, err
		}
	}

	// Build result
	result = s.buildResolveResult(m, path, binding, bindingPath, node)
	return result, nil
}

func (s *MonikerService) buildResolveResult(m *moniker.Moniker, path string, binding *catalog.SourceBinding, bindingPath string, node *catalog.CatalogNode) *ResolveResult {
	// Resolve ownership
	ownership := s.catalog.ResolveOwnership(path)

	// Build resolved source
	source := &ResolvedSource{
		SourceType: string(binding.SourceType),
		Connection: make(map[string]interface{}),
		Params:     make(map[string]interface{}),
		ReadOnly:   binding.ReadOnly,
	}

	// Copy config to connection (excluding query)
	for k, v := range binding.Config {
		if k != "query" {
			source.Connection[k] = v
		}
	}

	// Get query from config
	if queryVal, ok := binding.Config["query"]; ok {
		if queryStr, ok := queryVal.(string); ok {
			// Simple placeholder substitution
			formattedQuery := s.formatQuery(queryStr, m)
			source.Query = &formattedQuery
		}
	}

	// Set schema if present
	if binding.Schema != nil {
		source.Schema = binding.Schema
	}

	// Calculate sub-path if binding is at ancestor
	var subPath *string
	if bindingPath != path {
		// Path is longer than binding path
		if strings.HasPrefix(path, bindingPath+"/") {
			sp := strings.TrimPrefix(path, bindingPath+"/")
			subPath = &sp
		}
	}

	return &ResolveResult{
		Moniker:     m.String(),
		Path:        path,
		Type:        "leaf", // This is a leaf node with source binding
		Source:      source,
		Ownership:   ownership,
		Node:        node,
		BindingPath: bindingPath,
		SubPath:     subPath,
	}
}

// formatQuery performs basic placeholder substitution
func (s *MonikerService) formatQuery(query string, m *moniker.Moniker) string {
	result := query

	// Replace {segments[N]} placeholders
	for i, seg := range m.Path.Segments {
		placeholder := fmt.Sprintf("{segments[%d]}", i)
		result = strings.ReplaceAll(result, placeholder, seg)
	}

	// Replace {version_date} if present
	if m.VersionDate() != nil {
		result = strings.ReplaceAll(result, "{version_date}", *m.VersionDate())
	}

	// Replace {is_latest} if present
	isLatest := "false"
	if m.IsLatest() {
		isLatest = "true"
	}
	result = strings.ReplaceAll(result, "{is_latest}", isLatest)

	return result
}

// Describe returns metadata about a path
func (s *MonikerService) Describe(ctx context.Context, path string, caller *CallerIdentity) (*DescribeResult, error) {
	start := time.Now()
	outcome := telemetry.OutcomeSuccess
	var result *DescribeResult
	var err error

	// Defer telemetry emission
	defer func() {
		latency := float64(time.Since(start).Microseconds()) / 1000.0
		s.emitDescribeTelemetry(path, caller, outcome, latency, result, err)
	}()

	node := s.catalog.Get(path)
	if node == nil {
		outcome = telemetry.OutcomeNotFound
	}

	ownership := s.catalog.ResolveOwnership(path)

	// Check if has source binding
	binding, _ := s.catalog.FindSourceBinding(path)
	hasBinding := binding != nil

	var sourceType *string
	if binding != nil {
		st := string(binding.SourceType)
		sourceType = &st
	}

	result = &DescribeResult{
		Node:             node,
		Ownership:        ownership,
		Moniker:          fmt.Sprintf("moniker://%s", path),
		Path:             path,
		HasSourceBinding: hasBinding,
		SourceType:       sourceType,
	}

	return result, nil
}

// List returns children of a path
func (s *MonikerService) List(ctx context.Context, path string, caller *CallerIdentity) (*ListResult, error) {
	start := time.Now()
	outcome := telemetry.OutcomeSuccess
	var result *ListResult
	var err error

	// Defer telemetry emission
	defer func() {
		latency := float64(time.Since(start).Microseconds()) / 1000.0
		s.emitListTelemetry(path, caller, outcome, latency, result, err)
	}()

	childrenPaths := s.catalog.ChildrenPaths(path)
	ownership := s.catalog.ResolveOwnership(path)

	result = &ListResult{
		Children:  childrenPaths,
		Moniker:   fmt.Sprintf("moniker://%s", path),
		Path:      path,
		Ownership: ownership,
	}

	return result, nil
}

// emitResolveTelemetry emits telemetry for resolve operations
func (s *MonikerService) emitResolveTelemetry(monikerStr string, caller *CallerIdentity, outcome telemetry.EventOutcome, latencyMS float64, result *ResolveResult, err error) {
	if s.emitter == nil {
		return
	}

	// Build caller identity for telemetry
	telCaller := s.buildTelemetryCaller(caller)

	// Determine path
	path := monikerStr
	if result != nil {
		path = result.Path
	}

	// Create event
	event := telemetry.NewUsageEvent(monikerStr, path, telCaller, telemetry.OperationRead)
	event.Outcome = outcome
	event.LatencyMS = latencyMS

	// Add result details if available
	if result != nil {
		if result.Source != nil {
			sourceType := result.Source.SourceType
			event.ResolvedSourceType = &sourceType
		}

		if result.Ownership != nil && result.Ownership.Owner != nil {
			event.OwnerAtAccess = result.Ownership.Owner
		}

		if result.Node != nil {
			event.Deprecated = result.Node.Status == catalog.NodeStatusDeprecated
			if result.Node.Successor != nil {
				event.Successor = result.Node.Successor
			}
		}

		if result.RedirectedFrom != nil {
			event.RedirectedFrom = result.RedirectedFrom
		}
	}

	// Add error message if error occurred
	if err != nil {
		errMsg := err.Error()
		event.ErrorMessage = &errMsg
	}

	// Emit event (non-blocking)
	s.emitter.Emit(*event)
}

// emitDescribeTelemetry emits telemetry for describe operations
func (s *MonikerService) emitDescribeTelemetry(path string, caller *CallerIdentity, outcome telemetry.EventOutcome, latencyMS float64, result *DescribeResult, err error) {
	if s.emitter == nil {
		return
	}

	telCaller := s.buildTelemetryCaller(caller)
	moniker := fmt.Sprintf("moniker://%s", path)

	event := telemetry.NewUsageEvent(moniker, path, telCaller, telemetry.OperationDescribe)
	event.Outcome = outcome
	event.LatencyMS = latencyMS

	if result != nil {
		if result.SourceType != nil {
			event.ResolvedSourceType = result.SourceType
		}

		if result.Ownership != nil && result.Ownership.Owner != nil {
			event.OwnerAtAccess = result.Ownership.Owner
		}

		if result.Node != nil {
			event.Deprecated = result.Node.Status == catalog.NodeStatusDeprecated
			if result.Node.Successor != nil {
				event.Successor = result.Node.Successor
			}
		}
	}

	if err != nil {
		errMsg := err.Error()
		event.ErrorMessage = &errMsg
	}

	s.emitter.Emit(*event)
}

// emitListTelemetry emits telemetry for list operations
func (s *MonikerService) emitListTelemetry(path string, caller *CallerIdentity, outcome telemetry.EventOutcome, latencyMS float64, result *ListResult, err error) {
	if s.emitter == nil {
		return
	}

	telCaller := s.buildTelemetryCaller(caller)
	moniker := fmt.Sprintf("moniker://%s", path)

	event := telemetry.NewUsageEvent(moniker, path, telCaller, telemetry.OperationList)
	event.Outcome = outcome
	event.LatencyMS = latencyMS

	if result != nil {
		if result.Ownership != nil && result.Ownership.Owner != nil {
			event.OwnerAtAccess = result.Ownership.Owner
		}

		// Add metadata about number of children
		event.Metadata["children_count"] = len(result.Children)
	}

	if err != nil {
		errMsg := err.Error()
		event.ErrorMessage = &errMsg
	}

	s.emitter.Emit(*event)
}

// buildTelemetryCaller converts CallerIdentity to telemetry.CallerIdentity
func (s *MonikerService) buildTelemetryCaller(caller *CallerIdentity) telemetry.CallerIdentity {
	if caller == nil {
		return telemetry.CallerIdentity{}
	}

	return telemetry.CallerIdentity{
		UserID: &caller.UserID,
	}
}
