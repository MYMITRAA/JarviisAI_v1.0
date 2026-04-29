// Package config handles JarviisAI agent configuration.
// Config is stored in ~/.jarviis/config.yaml

package config

import (
	"fmt"
	"os"
	"path/filepath"

	"gopkg.in/yaml.v3"
)

type Config struct {
	// Cloud connection
	APIBaseURL string `yaml:"api_base_url"`
	APIToken   string `yaml:"api_token"`
	OrgSlug    string `yaml:"org_slug"`

	// Local agent server
	APIPort int `yaml:"api_port"`

	// File watching
	WatchPaths []string `yaml:"watch_paths"`
	IgnoreDirs []string `yaml:"ignore_dirs"`

	// Docker
	DockerHost string `yaml:"docker_host"`

	// Test runner
	DefaultBrowsers []string `yaml:"default_browsers"`
	MaxParallelTests int     `yaml:"max_parallel_tests"`

	// Logging
	LogLevel string `yaml:"log_level"`
	LogFile  string `yaml:"log_file"`
}

func DefaultConfig() *Config {
	return &Config{
		APIBaseURL:       "https://api.jarviis.ai",
		APIPort:          7331,
		WatchPaths:       []string{"."},
		IgnoreDirs:       []string{"node_modules", ".git", ".next", "__pycache__", "dist", "build"},
		DockerHost:       "unix:///var/run/docker.sock",
		DefaultBrowsers:  []string{"chromium"},
		MaxParallelTests: 4,
		LogLevel:         "info",
		LogFile:          "",
	}
}

func configPath() string {
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".jarviis", "config.yaml")
}

func Load() (*Config, error) {
	cfg := DefaultConfig()
	path := configPath()

	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			// First run — create default config
			if err := Save(cfg); err != nil {
				return nil, err
			}
			return cfg, nil
		}
		return nil, fmt.Errorf("reading config: %w", err)
	}

	if err := yaml.Unmarshal(data, cfg); err != nil {
		return nil, fmt.Errorf("parsing config: %w", err)
	}

	return cfg, nil
}

func Save(cfg *Config) error {
	path := configPath()
	if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
		return err
	}
	data, err := yaml.Marshal(cfg)
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0600)
}

func Set(key, value string) error {
	cfg, err := Load()
	if err != nil {
		return err
	}
	switch key {
	case "api_token":
		cfg.APIToken = value
	case "api_base_url":
		cfg.APIBaseURL = value
	case "org_slug":
		cfg.OrgSlug = value
	case "api_port":
		fmt.Sscanf(value, "%d", &cfg.APIPort)
	case "log_level":
		cfg.LogLevel = value
	default:
		return fmt.Errorf("unknown config key: %s", key)
	}
	if err := Save(cfg); err != nil {
		return err
	}
	fmt.Printf("✓ Set %s = %s\n", key, value)
	return nil
}

func (c *Config) Print() {
	fmt.Printf("JarviisAI Agent Configuration\n")
	fmt.Printf("  API URL:    %s\n", c.APIBaseURL)
	fmt.Printf("  Org:        %s\n", c.OrgSlug)
	fmt.Printf("  Agent Port: %d\n", c.APIPort)
	fmt.Printf("  Log Level:  %s\n", c.LogLevel)
	fmt.Printf("  Docker:     %s\n", c.DockerHost)
	if c.APIToken != "" {
		fmt.Printf("  Token:      %s...\n", c.APIToken[:8])
	} else {
		fmt.Printf("  Token:      (not set — run: jarviis config set api_token <your-token>)\n")
	}
}
