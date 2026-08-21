# Endpoint Testing Script
$baseUrl = "http://localhost:8000"
$results = @()

# Test endpoints without auth
$publicEndpoints = @(
    @{Method="GET"; Path="/"},
    @{Method="GET"; Path="/healthz"},
    @{Method="GET"; Path="/api/v1/health/"},
    @{Method="GET"; Path="/api/v1/health/ready"},
    @{Method="GET"; Path="/api/v1/health/live"},
    @{Method="GET"; Path="/api/v1/health/detailed"},
    @{Method="GET"; Path="/api/v1/health/db"},
    @{Method="POST"; Path="/api/v1/auth/register"},
    @{Method="POST"; Path="/api/v1/auth/login"},
    @{Method="GET"; Path="/docs"},
    @{Method="GET"; Path="/redoc"},
    @{Method="GET"; Path="/openapi.json"}
)

Write-Host "Testing Public Endpoints..." -ForegroundColor Cyan

foreach ($endpoint in $publicEndpoints) {
    try {
        $response = Invoke-WebRequest -Uri "$baseUrl$($endpoint.Path)" -Method $endpoint.Method -ErrorAction Stop -TimeoutSec 5
        $status = "✅ WORKING"
        $statusCode = $response.StatusCode
        $error = $null
    } catch {
        $status = "❌ FAILED"
        $statusCode = $_.Exception.Response.StatusCode.value__
        $error = $_.Exception.Message
    }
    
    $results += [PSCustomObject]@{
        Endpoint = "$($endpoint.Method) $($endpoint.Path)"
        Status = $status
        StatusCode = $statusCode
        Error = $error
    }
    
    Write-Host "  $status - $($endpoint.Method) $($endpoint.Path)" -ForegroundColor $(if ($status -eq "✅ WORKING") { "Green" } else { "Red" })
}

Write-Host "`nTesting Auth-Required Endpoints..." -ForegroundColor Cyan

# Test auth-required endpoints (should return 401 or 403)
$authEndpoints = @(
    @{Method="GET"; Path="/api/v1/auth/me"},
    @{Method="POST"; Path="/api/v1/auth/logout"},
    @{Method="GET"; Path="/api/v1/users/me"},
    @{Method="GET"; Path="/api/v1/drivers/me"},
    @{Method="GET"; Path="/api/v1/rides/available"},
    @{Method="POST"; Path="/api/v1/match/find"},
    @{Method="GET"; Path="/api/v1/ratings/user"},
    @{Method="GET"; Path="/api/v1/history/rides"},
    @{Method="GET"; Path="/api/v1/analytics/overview"}
)

foreach ($endpoint in $authEndpoints) {
    try {
        $response = Invoke-WebRequest -Uri "$baseUrl$($endpoint.Path)" -Method $endpoint.Method -ErrorAction Stop -TimeoutSec 5
        $status = "⚠️ NO AUTH CHECK"
        $statusCode = $response.StatusCode
        $error = "Expected 401/403 but got $statusCode"
    } catch {
        $statusCode = $_.Exception.Response.StatusCode.value__
        if ($statusCode -eq 401 -or $statusCode -eq 403 -or $statusCode -eq 422) {
            $status = "✅ WORKING"
            $error = $null
        } else {
            $status = "❌ FAILED"
            $error = $_.Exception.Message
        }
    }
    
    $results += [PSCustomObject]@{
        Endpoint = "$($endpoint.Method) $($endpoint.Path)"
        Status = $status
        StatusCode = $statusCode
        Error = $error
    }
    
    Write-Host "  $status - $($endpoint.Method) $($endpoint.Path) (Status: $statusCode)" -ForegroundColor $(if ($status -eq "✅ WORKING") { "Green" } elseif ($status -eq "⚠️ NO AUTH CHECK") { "Yellow" } else { "Red" })
}

# Summary
Write-Host "`n" + "="*80 -ForegroundColor Cyan
Write-Host "SUMMARY" -ForegroundColor Cyan
Write-Host "="*80 -ForegroundColor Cyan

$working = ($results | Where-Object { $_.Status -eq "✅ WORKING" }).Count
$failed = ($results | Where-Object { $_.Status -eq "❌ FAILED" }).Count
$warning = ($results | Where-Object { $_.Status -eq "⚠️ NO AUTH CHECK" }).Count

Write-Host "Total Tested: $($results.Count)" -ForegroundColor White
Write-Host "Working: $working" -ForegroundColor Green
Write-Host "Failed: $failed" -ForegroundColor Red
Write-Host "Warnings: $warning" -ForegroundColor Yellow

# Show failed endpoints
if ($failed -gt 0) {
    Write-Host "`nFAILED ENDPOINTS:" -ForegroundColor Red
    $results | Where-Object { $_.Status -eq "❌ FAILED" } | Format-Table -AutoSize
}

# Export results
$results | Export-Csv -Path "endpoint_test_results.csv" -NoTypeInformation
Write-Host "`nResults exported to endpoint_test_results.csv" -ForegroundColor Green
