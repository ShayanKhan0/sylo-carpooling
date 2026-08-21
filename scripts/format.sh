#!/bin/bash
echo "🎨 Auto-formatting code..."

# Format Python code (backend)
echo "Formatting Python code with black..."
cd backend && black . --line-length 100

# Format Dart/Flutter code (frontend)
echo "Formatting Dart code with dart format..."
cd ../frontend && dart format .

echo "✨ Code formatting completed!"
