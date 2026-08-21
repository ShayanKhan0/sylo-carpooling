#!/bin/bash
echo "🧪 Running automated tests..."

# Run backend tests
echo "Testing Backend (FastAPI)..."
cd backend && pytest tests/ --verbose --cov=.

# Run frontend tests
echo "Testing Frontend (Flutter)..."
cd ../frontend && flutter test

echo "✅ All tests completed!"
