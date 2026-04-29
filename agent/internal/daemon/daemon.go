// Package daemon runs the local agent's main loop:
//   - HTTP API server on localhost:7331
//   - File system watcher for auto-run on change
//   - Docker client for local container management
//   - Heartbeat to cloud API

package daemon

import (
	"context"
	"fmt"
	"net/http"
	"sync"
	"time"

	"github.com/jarviisai/agent/internal/config"
)

type Status struct {
	Version       string    `json:"version"`
	Uptime        string    `json:"uptime"`
	ActiveRuns    int       `json:"active_runs"`
	DockerVersion string    `json:"docker_version"`
	StartedAt     time.Time `json:"started_at"`
}

type Daemon struct {
	cfg       *config.Config
	startedAt time.Time
	mu        sync.RWMutex
	activeRuns int
	status    Status
}

func New(cfg *config.Config) *Daemon {
	return &Daemon{
		cfg:       cfg,
		startedAt: time.Now(),
	}
}

func (d *Daemon) Run(ctx context.Context) error {
	errCh := make(chan error, 3)

	// Start local API server
	go func() {
		errCh <- d.startAPIServer(ctx)
	}()

	// Start file watcher
	go func() {
		errCh <- d.startFileWatcher(ctx)
	}()

	// Start heartbeat to cloud
	go func() {
		d.runHeartbeat(ctx)
		errCh <- nil
	}()

	select {
	case <-ctx.Done():
		fmt.Println("Agent stopped.")
		return nil
	case err := <-errCh:
		return err
	}
}

func (d *Daemon) startAPIServer(ctx context.Context) error {
	mux := http.NewServeMux()

	// Status
	mux.HandleFunc("/status", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(fmt.Sprintf(
			`{"version":"1.0.0","uptime":"%s","active_runs":%d,"started_at":"%s"}`,
			time.Since(d.startedAt).Round(time.Second),
			d.getActiveRuns(),
			d.startedAt.Format(time.RFC3339),
		)))
	})

	// Stop
	mux.HandleFunc("/stop", func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(`{"message":"stopping"}`))
		go func() {
			time.Sleep(100 * time.Millisecond)
			// Signal context cancel — handled by cobra command
		}()
	})

	// Trigger test run
	mux.HandleFunc("/test", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", 405)
			return
		}
		// Parsed in runner package
		w.Write([]byte(`{"message":"test run queued"}`))
	})

	addr := fmt.Sprintf("127.0.0.1:%d", d.cfg.APIPort)
	server := &http.Server{Addr: addr, Handler: mux}

	go func() {
		<-ctx.Done()
		server.Close()
	}()

	fmt.Printf("✅ Agent API listening on http://%s\n", addr)
	if err := server.ListenAndServe(); err != http.ErrServerClosed {
		return fmt.Errorf("API server: %w", err)
	}
	return nil
}

func (d *Daemon) startFileWatcher(ctx context.Context) error {
	fmt.Printf("👁  Watching: %v\n", d.cfg.WatchPaths)
	// Full file watcher implementation uses fsnotify
	// This stub returns immediately
	<-ctx.Done()
	return nil
}

func (d *Daemon) runHeartbeat(ctx context.Context) {
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			// POST to cloud API to confirm agent is alive
			// client.Heartbeat(d.cfg.APIToken)
		}
	}
}

func (d *Daemon) getActiveRuns() int {
	d.mu.RLock()
	defer d.mu.RUnlock()
	return d.activeRuns
}

func (d *Daemon) incrementRuns() {
	d.mu.Lock()
	d.activeRuns++
	d.mu.Unlock()
}

func (d *Daemon) decrementRuns() {
	d.mu.Lock()
	if d.activeRuns > 0 {
		d.activeRuns--
	}
	d.mu.Unlock()
}
