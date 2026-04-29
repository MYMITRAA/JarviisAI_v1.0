// Package runner coordinates test runs triggered by the local agent.
// When the watcher detects a file change, the runner:
//   1. Debounces rapid saves (collect changes over 500ms)
//   2. Determines which project(s) are affected
//   3. Calls the JarviisAI cloud API to start a test run
//   4. Streams results back to the terminal

package runner

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"path/filepath"
	"strings"
	"time"

	"github.com/jarviisai/agent/internal/config"
	"github.com/jarviisai/agent/internal/watcher"
)

// RunTrigger is the payload sent to the cloud API.
type RunTrigger struct {
	ProjectID   string   `json:"project_id"`
	OrgID       string   `json:"org_id"`
	TriggerType string   `json:"trigger_type"` // "local_watch"
	GitBranch   string   `json:"git_branch,omitempty"`
	ChangedFiles []string `json:"changed_files"`
}

// Runner handles test run coordination.
type Runner struct {
	cfg    *config.Config
	client *http.Client
}

// New creates a new Runner.
func New(cfg *config.Config) *Runner {
	return &Runner{
		cfg: cfg,
		client: &http.Client{Timeout: 30 * time.Second},
	}
}

// HandleEvent processes a file change event and triggers a test run.
func (r *Runner) HandleEvent(ctx context.Context, event watcher.Event) {
	if r.cfg.APIToken == "" {
		fmt.Println("⚠️  No API token configured. Run: jarviis config set api_token <your-token>")
		return
	}

	// Determine project from changed file path
	projectID := r.inferProjectID(event.Path)
	if projectID == "" {
		return
	}

	ext := strings.ToLower(filepath.Ext(event.Path))
	fmt.Printf("📁 Changed: %s\n", event.Path)
	fmt.Printf("🚀 Triggering JarviisAI test run...\n")

	// Get current git branch
	branch := r.getGitBranch(filepath.Dir(event.Path))

	payload := RunTrigger{
		ProjectID:    projectID,
		OrgID:        r.cfg.OrgSlug,
		TriggerType:  "local_watch",
		GitBranch:    branch,
		ChangedFiles: []string{event.Path},
	}

	body, _ := json.Marshal(payload)
	req, err := http.NewRequestWithContext(
		ctx, "POST",
		r.cfg.APIBaseURL+"/api/v1/local/trigger-run",
		bytes.NewReader(body),
	)
	if err != nil {
		fmt.Printf("❌ Error creating request: %v\n", err)
		return
	}
	req.Header.Set("Authorization", "Bearer "+r.cfg.APIToken)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Agent-Version", "1.0.0")

	resp, err := r.client.Do(req)
	if err != nil {
		fmt.Printf("❌ Cannot reach JarviisAI API: %v\n", err)
		fmt.Printf("   Check your internet connection and API token\n")
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusUnauthorized {
		fmt.Printf("❌ Invalid API token. Run: jarviis config set api_token <new-token>\n")
		return
	}

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusAccepted {
		body, _ := io.ReadAll(resp.Body)
		fmt.Printf("❌ API error (%d): %s\n", resp.StatusCode, string(body))
		return
	}

	var result map[string]any
	json.NewDecoder(resp.Body).Decode(&result)

	runID, _ := result["run_id"].(string)
	if runID != "" {
		fmt.Printf("✅ Test run started: %s\n", runID)
		fmt.Printf("   View at: %s/dashboard/runs/%s\n", r.cfg.APIBaseURL, runID)
	} else {
		fmt.Printf("✅ Test run queued\n")
	}
}

// inferProjectID tries to map a file path to a JarviisAI project ID.
// In the full implementation this reads from ~/.jarviis/projects.yaml
// which maps local dirs to project IDs.
func (r *Runner) inferProjectID(path string) string {
	// Stub: in practice reads project mapping from config
	_ = path
	return ""
}

// getGitBranch returns the current git branch for a directory.
func (r *Runner) getGitBranch(dir string) string {
	// Stub: exec git rev-parse --abbrev-ref HEAD
	return "main"
}

// WatchAndRun starts watching files and triggering runs.
func (r *Runner) WatchAndRun(ctx context.Context) error {
	w, err := watcher.New(watcher.WatchConfig{
		Paths:      r.cfg.WatchPaths,
		IgnoreDirs: r.cfg.IgnoreDirs,
		Debounce:   500 * time.Millisecond,
	})
	if err != nil {
		return fmt.Errorf("creating watcher: %w", err)
	}

	go func() {
		if err := w.Run(ctx); err != nil {
			fmt.Printf("Watcher error: %v\n", err)
		}
	}()

	for {
		select {
		case <-ctx.Done():
			return nil
		case event, ok := <-w.Events():
			if !ok {
				return nil
			}
			go r.HandleEvent(ctx, event)
		}
	}
}
