package config

import (
	"fmt"
	"os"
	"path/filepath"

	"gopkg.in/yaml.v3"
)

// Config represents the service configuration
type Config struct {
	ProjectName string          `yaml:"project_name"`
	Server      ServerConfig    `yaml:"server"`
	Telemetry   TelemetryConfig `yaml:"telemetry"`
	Cache       CacheConfig     `yaml:"cache"`
	Catalog     CatalogConfig   `yaml:"catalog"`
	Auth        AuthConfig      `yaml:"auth"`
	ConfigUI    ConfigUIConfig  `yaml:"config_ui"`
}

// ServerConfig represents server configuration
type ServerConfig struct {
	Host string `yaml:"host"`
	Port int    `yaml:"port"`
}

// TelemetryConfig represents telemetry configuration
type TelemetryConfig struct {
	Enabled             bool                   `yaml:"enabled"`
	SinkType            string                 `yaml:"sink_type"`
	SinkConfig          map[string]interface{} `yaml:"sink_config"`
	BatchSize           int                    `yaml:"batch_size"`
	FlushIntervalSeconds float64               `yaml:"flush_interval_seconds"`
	MaxQueueSize        int                    `yaml:"max_queue_size"`
}

// CacheConfig represents cache configuration
type CacheConfig struct {
	Enabled          bool `yaml:"enabled"`
	MaxSize          int  `yaml:"max_size"`
	DefaultTTLSeconds int `yaml:"default_ttl_seconds"`
}

// CatalogConfig represents catalog configuration
type CatalogConfig struct {
	DefinitionFile        string `yaml:"definition_file"`
	ReloadIntervalSeconds int    `yaml:"reload_interval_seconds"`
}

// AuthConfig represents authentication configuration
type AuthConfig struct {
	Enabled     bool     `yaml:"enabled"`
	Enforce     bool     `yaml:"enforce"`
	MethodOrder []string `yaml:"method_order"`
}

// ConfigUIConfig represents config UI settings
type ConfigUIConfig struct {
	Enabled        bool   `yaml:"enabled"`
	YAMLOutputPath string `yaml:"yaml_output_path"`
	ShowFilePaths  bool   `yaml:"show_file_paths"`
}

// Load loads configuration from a YAML file
func Load(configPath string) (*Config, error) {
	// Default: ../config.yaml (relative to resolver-go/)
	if configPath == "" {
		configPath = filepath.Join("..", "config.yaml")
	}

	data, err := os.ReadFile(configPath)
	if err != nil {
		return nil, fmt.Errorf("read config: %w", err)
	}

	var cfg Config
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		return nil, fmt.Errorf("parse config: %w", err)
	}

	return &cfg, nil
}
