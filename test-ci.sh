#!/bin/bash
# Script to test CI pipeline locally using Docker

set -e

echo "🐳 Building Docker image to simulate GitHub Actions runner..."
docker build -f Dockerfile.ci-test -t touchterrain-ci-test .

echo ""
echo "🧪 Running CI test in Docker container..."
docker run --rm -v "$(pwd):/workspace" touchterrain-ci-test

echo ""
echo "✅ CI test completed successfully!"
