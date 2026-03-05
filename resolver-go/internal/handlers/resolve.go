package handlers

import (
	"encoding/json"
	"net/http"
	"strings"

	"github.com/ganizanisitara/open-moniker-svc/resolver-go/internal/service"
)

// ResolveHandler handles /resolve/{path} requests
type ResolveHandler struct {
	service *service.MonikerService
}

// NewResolveHandler creates a new resolve handler
func NewResolveHandler(svc *service.MonikerService) *ResolveHandler {
	return &ResolveHandler{service: svc}
}

// ServeHTTP implements http.Handler
func (h *ResolveHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	// Extract path from URL
	path := strings.TrimPrefix(r.URL.Path, "/resolve/")
	if path == "" {
		writeError(w, http.StatusBadRequest, "Missing moniker path", nil)
		return
	}

	// Get caller identity (simplified for now)
	caller := &service.CallerIdentity{
		UserID: r.Header.Get("X-User-ID"),
		Source: "api",
	}
	if caller.UserID == "" {
		caller.UserID = "anonymous"
	}

	// Resolve the moniker
	result, err := h.service.Resolve(r.Context(), path, caller)
	if err != nil {
		handleServiceError(w, err)
		return
	}

	// Return result as JSON
	writeJSON(w, http.StatusOK, result)
}

// DescribeHandler handles /describe/{path} requests
type DescribeHandler struct {
	service *service.MonikerService
}

// NewDescribeHandler creates a new describe handler
func NewDescribeHandler(svc *service.MonikerService) *DescribeHandler {
	return &DescribeHandler{service: svc}
}

// ServeHTTP implements http.Handler
func (h *DescribeHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	path := strings.TrimPrefix(r.URL.Path, "/describe/")
	if path == "" {
		writeError(w, http.StatusBadRequest, "Missing path", nil)
		return
	}

	// Get caller identity
	caller := &service.CallerIdentity{
		UserID: r.Header.Get("X-User-ID"),
		Source: "api",
	}
	if caller.UserID == "" {
		caller.UserID = "anonymous"
	}

	result, err := h.service.Describe(r.Context(), path, caller)
	if err != nil {
		handleServiceError(w, err)
		return
	}

	writeJSON(w, http.StatusOK, result)
}

// ListHandler handles /list/{path} requests
type ListHandler struct {
	service *service.MonikerService
}

// NewListHandler creates a new list handler
func NewListHandler(svc *service.MonikerService) *ListHandler {
	return &ListHandler{service: svc}
}

// ServeHTTP implements http.Handler
func (h *ListHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	path := strings.TrimPrefix(r.URL.Path, "/list/")
	// Empty path means list root

	// Get caller identity
	caller := &service.CallerIdentity{
		UserID: r.Header.Get("X-User-ID"),
		Source: "api",
	}
	if caller.UserID == "" {
		caller.UserID = "anonymous"
	}

	result, err := h.service.List(r.Context(), path, caller)
	if err != nil {
		handleServiceError(w, err)
		return
	}

	writeJSON(w, http.StatusOK, result)
}

// Helper functions

func writeJSON(w http.ResponseWriter, status int, data interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(data)
}

func writeError(w http.ResponseWriter, status int, message string, details map[string]interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)

	response := map[string]interface{}{
		"error": message,
	}
	if details != nil {
		for k, v := range details {
			response[k] = v
		}
	}

	json.NewEncoder(w).Encode(response)
}

func handleServiceError(w http.ResponseWriter, err error) {
	switch e := err.(type) {
	case *service.NotFoundError:
		writeError(w, http.StatusNotFound, "Not found", map[string]interface{}{
			"detail": e.Error(),
			"path":   e.Path,
		})
	case *service.AccessDeniedError:
		details := map[string]interface{}{
			"detail": e.Message,
		}
		if e.EstimatedRows != nil {
			details["estimated_rows"] = *e.EstimatedRows
		}
		writeError(w, http.StatusForbidden, "Access denied", details)
	case *service.ResolutionError:
		writeError(w, http.StatusBadRequest, "Resolution error", map[string]interface{}{
			"detail": e.Error(),
		})
	default:
		writeError(w, http.StatusInternalServerError, "Internal server error", map[string]interface{}{
			"detail": err.Error(),
		})
	}
}
