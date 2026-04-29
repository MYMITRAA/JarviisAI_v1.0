// JarviisAI Local Agent
// Runs on developer machines to enable local Docker testing,
// file watching, and direct test execution without going through the cloud.
//
// Install: brew install jarviisai/tap/jarviis
// Start:   jarviis agent start
// Stop:    jarviis agent stop

package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"syscall"

	"github.com/jarviisai/agent/internal/api"
	"github.com/jarviisai/agent/internal/config"
	"github.com/jarviisai/agent/internal/daemon"
	"github.com/jarviisai/agent/internal/watcher"
	"github.com/spf13/cobra"
)

var version = "1.0.0"

func main() {
	root := &cobra.Command{
		Use:     "jarviis",
		Short:   "JarviisAI Local Agent",
		Long:    "Autonomous testing and deployment agent for your local environment",
		Version: version,
	}

	root.AddCommand(
		agentCmd(),
		testCmd(),
		deployCmd(),
		configCmd(),
		statusCmd(),
	)

	if err := root.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

// ── agent start/stop/status ───────────────────────────────────

func agentCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "agent",
		Short: "Manage the JarviisAI agent daemon",
	}

	start := &cobra.Command{
		Use:   "start",
		Short: "Start the local agent",
		RunE: func(cmd *cobra.Command, args []string) error {
			cfg, err := config.Load()
			if err != nil {
				return fmt.Errorf("config error: %w", err)
			}

			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()

			// Handle SIGTERM/SIGINT
			sigs := make(chan os.Signal, 1)
			signal.Notify(sigs, syscall.SIGINT, syscall.SIGTERM)
			go func() {
				<-sigs
				fmt.Println("\nShutting down JarviisAI agent...")
				cancel()
			}()

			fmt.Printf("🚀 JarviisAI Agent v%s starting...\n", version)
			fmt.Printf("   API server: http://localhost:%d\n", cfg.APIPort)
			fmt.Printf("   Watch paths: %v\n", cfg.WatchPaths)

			d := daemon.New(cfg)
			return d.Run(ctx)
		},
	}

	stop := &cobra.Command{
		Use:   "stop",
		Short: "Stop the local agent",
		RunE: func(cmd *cobra.Command, args []string) error {
			client := api.NewLocalClient()
			return client.Stop()
		},
	}

	status := &cobra.Command{
		Use:   "status",
		Short: "Show agent status",
		RunE: func(cmd *cobra.Command, args []string) error {
			client := api.NewLocalClient()
			status, err := client.Status()
			if err != nil {
				fmt.Println("❌ Agent is not running")
				return nil
			}
			fmt.Printf("✅ Agent running (v%s)\n", status.Version)
			fmt.Printf("   Uptime: %s\n", status.Uptime)
			fmt.Printf("   Active runs: %d\n", status.ActiveRuns)
			fmt.Printf("   Docker: %s\n", status.DockerVersion)
			return nil
		},
	}

	cmd.AddCommand(start, stop, status)
	return cmd
}

// ── jarviis test <url> ────────────────────────────────────────

func testCmd() *cobra.Command {
	var (
		projectID string
		browsers  []string
		watch     bool
	)

	cmd := &cobra.Command{
		Use:   "test [url]",
		Short: "Run AI-powered tests against a URL",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			url := args[0]
			client := api.NewLocalClient()

			fmt.Printf("🤖 Starting autonomous test run for: %s\n", url)
			return client.RunTests(api.TestRequest{
				URL:       url,
				ProjectID: projectID,
				Browsers:  browsers,
				Watch:     watch,
			})
		},
	}

	cmd.Flags().StringVar(&projectID, "project", "", "Project ID from JarviisAI dashboard")
	cmd.Flags().StringSliceVar(&browsers, "browsers", []string{"chromium"}, "Browsers to test (chromium, firefox, webkit)")
	cmd.Flags().BoolVar(&watch, "watch", false, "Watch for file changes and re-run tests")

	return cmd
}

// ── jarviis deploy ────────────────────────────────────────────

func deployCmd() *cobra.Command {
	var (
		env      string
		imageTag string
	)

	cmd := &cobra.Command{
		Use:   "deploy [project-slug]",
		Short: "Deploy a project to an environment",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			projectSlug := args[0]
			client := api.NewLocalClient()

			fmt.Printf("🚀 Deploying %s to %s...\n", projectSlug, env)
			return client.Deploy(api.DeployRequest{
				ProjectSlug: projectSlug,
				Environment: env,
				ImageTag:    imageTag,
			})
		},
	}

	cmd.Flags().StringVar(&env, "env", "staging", "Target environment (staging, production)")
	cmd.Flags().StringVar(&imageTag, "tag", "", "Docker image tag (default: current git commit)")

	return cmd
}

// ── jarviis config ────────────────────────────────────────────

func configCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "config",
		Short: "Configure the local agent",
	}

	set := &cobra.Command{
		Use:   "set <key> <value>",
		Short: "Set a configuration value",
		Args:  cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			return config.Set(args[0], args[1])
		},
	}

	show := &cobra.Command{
		Use:   "show",
		Short: "Show current configuration",
		RunE: func(cmd *cobra.Command, args []string) error {
			cfg, err := config.Load()
			if err != nil {
				return err
			}
			cfg.Print()
			return nil
		},
	}

	cmd.AddCommand(set, show)
	return cmd
}

// ── jarviis status ────────────────────────────────────────────

func statusCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "status",
		Short: "Show agent and project status",
		RunE: func(cmd *cobra.Command, args []string) error {
			client := api.NewLocalClient()
			return client.PrintStatus()
		},
	}
}
