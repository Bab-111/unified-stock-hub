name: Keepalive

# Prevents GitHub from disabling Actions on repos with no activity.
# GitHub disables scheduled workflows after 60 days of repo inactivity.
# This workflow commits a tiny timestamp file weekly to keep the repo active.

on:
  schedule:
    - cron: "0 10 * * 1"  # Every Monday 10:00 UTC
  workflow_dispatch:

permissions:
  contents: write

jobs:
  keepalive:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Update keepalive timestamp
        run: |
          echo "$(date -u)" > .keepalive
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add .keepalive
          git diff --staged --quiet || git commit -m "chore: keepalive $(date -u +%Y-%m-%d)"
          git push
