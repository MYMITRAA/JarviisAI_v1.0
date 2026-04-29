// Package api provides HTTP clients for both the local agent API
// and the JarviisAI cloud API.

package api

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

const localAgentPort = 7331

type LocalClient struct {
	base   string
	client *http.Client
}

type StatusResponse struct {
	Version       string `json:"version"`
	Uptime        string `json:"uptime"`
	ActiveRuns    int    `json:"active_runs"`
	DockerVersion string `json:"docker_version"`
}

type TestRequest struct {
	URL       string   `json:"url"`
	ProjectID string   `json:"project_id,omitempty"`
	Browsers  []string `json:"browsers"`
	Watch     bool     `json:"watch"`
}

type DeployRequest struct {
	ProjectSlug string `json:"project_slug"`
	Environment string `json:"environment"`
	ImageTag    string `json:"image_tag,omitempty"`
}

func NewLocalClient() *LocalClient {
	return &LocalClient{
		base: fmt.Sprintf("http://127.0.0.1:%d", localAgentPort),
		client: &http.Client{Timeout: 10 * time.Second},
	}
}

func (c *LocalClient) Status() (*StatusResponse, error) {
	resp, err := c.client.Get(c.base + "/status")
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var status StatusResponse
	if err := json.NewDecoder(resp.Body).Decode(&status); err != nil {
		return nil, err
	}
	return &status, nil
}

func (c *LocalClient) Stop() error {
	resp, err := c.client.Post(c.base+"/stop", "application/json", nil)
	if err != nil {
		return fmt.Errorf("agent not running: %w", err)
	}
	defer resp.Body.Close()
	fmt.Println("✓ Agent stopped")
	return nil
}

func (c *LocalClient) RunTests(req TestRequest) error {
	body, _ := json.Marshal(req)
	resp, err := c.client.Post(c.base+"/test", "application/json", bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("agent not running — start with: jarviis agent start\nError: %w", err)
	}
	defer resp.Body.Close()
	data, _ := io.ReadAll(resp.Body)
	fmt.Println(string(data))
	return nil
}

func (c *LocalClient) Deploy(req DeployRequest) error {
	body, _ := json.Marshal(req)
	resp, err := c.client.Post(c.base+"/deploy", "application/json", bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("agent not running: %w", err)
	}
	defer resp.Body.Close()
	data, _ := io.ReadAll(resp.Body)
	fmt.Println(string(data))
	return nil
}

func (c *LocalClient) PrintStatus() error {
	status, err := c.Status()
	if err != nil {
		fmt.Println("❌ Agent is not running")
		fmt.Println("   Start with: jarviis agent start")
		return nil
	}
	fmt.Printf("✅ JarviisAI Agent\n")
	fmt.Printf("   Version:     %s\n", status.Version)
	fmt.Printf("   Uptime:      %s\n", status.Uptime)
	fmt.Printf("   Active runs: %d\n", status.ActiveRuns)
	if status.DockerVersion != "" {
		fmt.Printf("   Docker:      %s\n", status.DockerVersion)
	}
	return nil
}
