#!/bin/bash
echo "🚀 Starting SmartCarpoolingApp locally..."
cd backend && uvicorn main:app --reload &
cd ../frontend && flutter run
