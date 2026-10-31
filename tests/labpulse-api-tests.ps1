<#
  LabPulse API test script
  ------------------------
  Tests the public routes, CORS preflight, the staff-only routes (with and
  without the key) and the status update flow.

  The staff key is NOT stored in this file. You are prompted for it when the
  script runs, so this file is safe to commit to GitHub.

  Usage:  .\labpulse-api-tests.ps1
#>

$base   = "https://qa8chos6le.execute-api.ap-south-1.amazonaws.com"
$origin = "http://labpulse-frontend-adithyan-2026.s3-website.ap-south-1.amazonaws.com"

# Prompt for the key (input is hidden)
$secure = Read-Host "Enter STAFF_KEY" -AsSecureString
$bstr   = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
$key    = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
$h      = @{ "x-staff-key" = $key }

# Returns the HTTP status code whether the call succeeds or fails
function Get-Code {
    param([scriptblock]$Call)
    try   { (& $Call).StatusCode }
    catch { [int]$_.Exception.Response.StatusCode }
}

Write-Host "`n=== 1. Public status check (expect 200) ==="
Invoke-WebRequest -UseBasicParsing -Uri "$base/status/test-01" |
    Select-Object StatusCode, Content

Write-Host "`n=== 2. CORS preflight for GET /reports (expect 204 + Access-Control-* headers) ==="
$pre = Invoke-WebRequest -UseBasicParsing -Uri "$base/reports" -Method OPTIONS -Headers @{
    "Origin"                         = $origin
    "Access-Control-Request-Method"  = "GET"
    "Access-Control-Request-Headers" = "x-staff-key"
}
$pre.StatusCode
$pre.Headers

Write-Host "`n=== 3. GET /reports WITHOUT key (expect 403) ==="
Get-Code { Invoke-WebRequest -UseBasicParsing -Uri "$base/reports" }

Write-Host "`n=== 4. GET /reports WITH key (expect 200 + report list) ==="
$list = Invoke-WebRequest -UseBasicParsing -Uri "$base/reports" -Headers $h
$list.StatusCode
$list.Content

# Use the first report from the list for the PATCH tests
$first = ($list.Content | ConvertFrom-Json).reports | Select-Object -First 1
if (-not $first) {
    Write-Host "No reports found. Submit one with POST /reports first, then re-run." -ForegroundColor Yellow
    return
}
$patchUri = "$base/reports/$($first.equipment_id)/$($first.report_id)"

Write-Host "`n=== 5. PATCH WITHOUT key (expect 403) ==="
Get-Code {
    Invoke-WebRequest -UseBasicParsing -Method PATCH -Uri $patchUri `
        -ContentType "application/json" -Body '{"status":"RESOLVED"}'
}

Write-Host "`n=== 6. PATCH WITH key -> RESOLVED (expect 200) ==="
$p = Invoke-WebRequest -UseBasicParsing -Method PATCH -Uri $patchUri -Headers $h `
    -ContentType "application/json" -Body '{"status":"RESOLVED"}'
$p.StatusCode
$p.Content

Write-Host "`n=== 7. Public status after update (has_open_report should be false) ==="
(Invoke-WebRequest -UseBasicParsing -Uri "$base/status/$($first.equipment_id)").Content

Write-Host "`n=== 8. Reopen the report (restores test data) ==="
(Invoke-WebRequest -UseBasicParsing -Method PATCH -Uri $patchUri -Headers $h `
    -ContentType "application/json" -Body '{"status":"OPEN"}').Content

Write-Host "`n=== 9. Optional throttle probe: 60 rapid requests, count status codes ==="
$codes = 1..60 | ForEach-Object { Get-Code { Invoke-WebRequest -UseBasicParsing -Uri "$base/status/test-01" } }
$codes | Group-Object | Select-Object Name, Count

# Clear the key from memory
$key = $null
$h   = $null
