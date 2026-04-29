// Package watcher watches for file system changes and triggers
// JarviisAI test runs automatically when code is saved.
//
// Uses fsnotify for cross-platform file watching (macOS FSEvents,
// Linux inotify, Windows ReadDirectoryChanges).

package watcher

import (
	"context"
	"fmt"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/fsnotify/fsnotify"
)

// Event represents a file change that should trigger a test run.
type Event struct {
	Path      string
	Operation string // "write" | "create" | "rename"
	Timestamp time.Time
}

// WatchConfig defines what to watch and what to ignore.
type WatchConfig struct {
	Paths      []string
	IgnoreDirs []string
	Extensions []string   // Only trigger on these extensions (nil = all)
	Debounce   time.Duration
}

// Watcher monitors directories and emits Events.
type Watcher struct {
	cfg     WatchConfig
	fw      *fsnotify.Watcher
	eventCh chan Event
	mu      sync.Mutex
	pending map[string]time.Time // debounce map
}

// New creates a new file watcher.
func New(cfg WatchConfig) (*Watcher, error) {
	if cfg.Debounce == 0 {
		cfg.Debounce = 500 * time.Millisecond
	}
	if len(cfg.IgnoreDirs) == 0 {
		cfg.IgnoreDirs = []string{
			"node_modules", ".git", ".next", "__pycache__",
			"dist", "build", ".pytest_cache", "vendor",
			".idea", ".vscode", "target",
		}
	}

	fw, err := fsnotify.NewWatcher()
	if err != nil {
		return nil, fmt.Errorf("creating fsnotify watcher: %w", err)
	}

	w := &Watcher{
		cfg:     cfg,
		fw:      fw,
		eventCh: make(chan Event, 100),
		pending: make(map[string]time.Time),
	}

	// Add paths recursively
	for _, path := range cfg.Paths {
		if err := w.addRecursive(path); err != nil {
			fw.Close()
			return nil, err
		}
	}

	return w, nil
}

// Events returns the channel of debounced file change events.
func (w *Watcher) Events() <-chan Event {
	return w.eventCh
}

// Run starts the watcher. Blocks until ctx is cancelled.
func (w *Watcher) Run(ctx context.Context) error {
	defer w.fw.Close()
	defer close(w.eventCh)

	// Debounce timer
	ticker := time.NewTicker(100 * time.Millisecond)
	defer ticker.Stop()

	fmt.Printf("👁  Watching %d paths for changes...\n", len(w.cfg.Paths))

	for {
		select {
		case <-ctx.Done():
			return nil

		case fwEvent, ok := <-w.fw.Events:
			if !ok {
				return nil
			}
			if w.shouldProcess(fwEvent.Name, fwEvent.Op) {
				w.mu.Lock()
				w.pending[fwEvent.Name] = time.Now()
				w.mu.Unlock()
			}

		case err, ok := <-w.fw.Errors:
			if !ok {
				return nil
			}
			fmt.Printf("⚠️  Watcher error: %v\n", err)

		case <-ticker.C:
			w.flushDebounced()
		}
	}
}

// flushDebounced emits events for files that haven't changed in Debounce duration.
func (w *Watcher) flushDebounced() {
	w.mu.Lock()
	defer w.mu.Unlock()

	now := time.Now()
	for path, ts := range w.pending {
		if now.Sub(ts) >= w.cfg.Debounce {
			select {
			case w.eventCh <- Event{
				Path:      path,
				Operation: "write",
				Timestamp: ts,
			}:
			default:
				// Channel full — drop event
			}
			delete(w.pending, path)
		}
	}
}

// shouldProcess returns true if this fsnotify event should trigger a test run.
func (w *Watcher) shouldProcess(path string, op fsnotify.Op) bool {
	if op&(fsnotify.Write|fsnotify.Create|fsnotify.Rename) == 0 {
		return false
	}

	// Check ignored dirs
	for _, ignored := range w.cfg.IgnoreDirs {
		if strings.Contains(filepath.ToSlash(path), "/"+ignored+"/") ||
			strings.HasSuffix(filepath.ToSlash(path), "/"+ignored) {
			return false
		}
	}

	// Check extensions filter
	if len(w.cfg.Extensions) > 0 {
		ext := strings.ToLower(filepath.Ext(path))
		for _, allowed := range w.cfg.Extensions {
			if ext == allowed {
				return true
			}
		}
		return false
	}

	// Ignore hidden files
	base := filepath.Base(path)
	if strings.HasPrefix(base, ".") {
		return false
	}

	// Ignore common generated/compiled files
	ignoreExts := []string{".pyc", ".pyo", ".class", ".o", ".a", ".so", ".dll"}
	ext := strings.ToLower(filepath.Ext(path))
	for _, ie := range ignoreExts {
		if ext == ie {
			return false
		}
	}

	return true
}

// addRecursive adds a directory and all subdirectories to the watcher.
func (w *Watcher) addRecursive(root string) error {
	return filepath.Walk(root, func(path string, info interface{}, err error) error {
		if err != nil {
			return nil // Skip inaccessible paths
		}
		// Cast to os.FileInfo
		// We just try to add — fsnotify will ignore non-dirs
		w.fw.Add(path)
		return nil
	})
}
