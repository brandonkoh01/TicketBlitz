$ErrorActionPreference = "Stop"

$envMap=@{}
Get-Content .env.local | ForEach-Object {
  if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
  $parts=$_.Split('=',2)
  if ($parts.Count -eq 2) { $envMap[$parts[0].Trim()]=$parts[1].Trim() }
}
$token=($envMap['INTERNAL_SERVICE_TOKEN']).Trim()

$results=@()

function Invoke-Case {
  param(
    [string]$Id,
    [int]$Expected,
    [string]$Method,
    [string]$Url,
    [string]$Body = '',
    [hashtable]$Headers = @{}
  )
  $status=-1
  $resp=''
  try {
    if ($Method -eq 'GET') {
      $r=Invoke-WebRequest -UseBasicParsing -Method Get -Uri $Url -Headers $Headers -TimeoutSec 45 -ErrorAction Stop
    } else {
      $r=Invoke-WebRequest -UseBasicParsing -Method $Method -Uri $Url -Headers $Headers -ContentType 'application/json' -Body $Body -TimeoutSec 45 -ErrorAction Stop
    }
    $status=[int]$r.StatusCode
    $resp=$r.Content
  } catch {
    if ($_.Exception.Response) {
      $status=[int]$_.Exception.Response.StatusCode
      $stream=$_.Exception.Response.GetResponseStream()
      $reader=New-Object System.IO.StreamReader($stream)
      $resp=$reader.ReadToEnd()
      $reader.Close()
    } else {
      $resp=$_.Exception.Message
    }
  }
  $result = if ($status -eq $Expected) { 'PASS' } else { 'FAIL' }
  if ($resp.Length -gt 220) { $resp = $resp.Substring(0,220) }
  $script:results += [pscustomobject]@{ id=$Id; expected=$Expected; actual=$status; result=$result; body=$resp }
}

function Offer-Waitlist {
  param([string]$WaitlistId,[string]$HoldId)
  $body = '{"holdID":"' + $HoldId + '"}'
  try {
    Invoke-WebRequest -UseBasicParsing -Method Put -Uri ("http://localhost:5005/waitlist/" + $WaitlistId + "/offer") -Headers @{ 'X-Internal-Token'=$token } -ContentType 'application/json' -Body $body -TimeoutSec 45 -ErrorAction Stop | Out-Null
    return $true
  } catch {
    return $false
  }
}

$wl='6d3a5c49-7600-49d1-9632-a852475cd694'

# Group A
Invoke-Case 'CO-001' 200 'GET' 'http://localhost:6003/health'
Invoke-Case 'CO-002' 200 'GET' 'http://localhost:6003/openapi.json'
Invoke-Case 'CO-003' 200 'GET' 'http://localhost:6003/docs'
Invoke-Case 'CO-004' 400 'POST' 'http://localhost:6003/orchestrator/cancellation' '[]'
Invoke-Case 'CO-005' 400 'POST' 'http://localhost:6003/orchestrator/cancellation' '{"userID":"00000000-0000-0000-0000-000000000001"}'
Invoke-Case 'CO-006' 400 'POST' 'http://localhost:6003/orchestrator/cancellation' '{"bookingID":"70000000-0000-0000-0000-000000000001"}'
Invoke-Case 'CO-007' 400 'POST' 'http://localhost:6003/orchestrator/cancellation' '{"bookingID":"not-a-uuid","userID":"00000000-0000-0000-0000-000000000001"}'
Invoke-Case 'CO-008' 400 'POST' 'http://localhost:6003/bookings/cancel/not-a-uuid' '{"userID":"00000000-0000-0000-0000-000000000001"}'
Invoke-Case 'CO-009' 400 'POST' 'http://localhost:6003/bookings/cancel/70000000-0000-0000-0000-000000000001' '{}'
Invoke-Case 'CO-010' 404 'POST' 'http://localhost:6003/orchestrator/cancellation' '{"bookingID":"00000000-0000-0000-0000-000000009999","userID":"00000000-0000-0000-0000-000000000001"}'

# Group B
Invoke-Case 'CO-020' 409 'POST' 'http://localhost:6003/orchestrator/cancellation' '{"bookingID":"70000000-0000-0000-0000-000000000001","userID":"00000000-0000-0000-0000-000000000002"}'
Invoke-Case 'CO-021' 409 'POST' 'http://localhost:6003/orchestrator/cancellation' '{"bookingID":"7b100000-0000-0000-0000-000000000006","userID":"00000000-0000-0000-0000-000000000001"}'
Invoke-Case 'CO-022' 200 'POST' 'http://localhost:6003/orchestrator/cancellation' '{"bookingID":"70000000-0000-0000-0000-000000000003","userID":"00000000-0000-0000-0000-000000000005"}'
Invoke-Case 'CO-023' 409 'POST' 'http://localhost:6003/orchestrator/cancellation' '{"bookingID":"7b100000-0000-0000-0000-000000000003","userID":"00000000-0000-0000-0000-000000000003"}'
Invoke-Case 'CO-024' 409 'POST' 'http://localhost:6003/orchestrator/cancellation' '{"bookingID":"7b100000-0000-0000-0000-000000000004","userID":"00000000-0000-0000-0000-000000000005"}'
Invoke-Case 'CO-025' 502 'POST' 'http://localhost:6003/orchestrator/cancellation' '{"bookingID":"70000000-0000-0000-0000-000000000001","userID":"00000000-0000-0000-0000-000000000001","reason":"Manual swagger failure-path validation"}'
Invoke-Case 'CO-026' 409 'POST' 'http://localhost:6003/orchestrator/cancellation' '{"bookingID":"70000000-0000-0000-0000-000000000001","userID":"00000000-0000-0000-0000-000000000001","reason":"Manual swagger failure-path validation"}'

# Group C baseline auth/validation
Invoke-Case 'CO-030' 401 'POST' 'http://localhost:6003/orchestrator/cancellation/reallocation/confirm' '{"bookingID":"70000000-0000-0000-0000-000000000001","newHoldID":"40000000-0000-0000-0000-000000000004","waitlistID":"bcefea06-1048-45c9-bde2-04f4d80f3510"}'
Invoke-Case 'CO-031' 400 'POST' 'http://localhost:6003/orchestrator/cancellation/reallocation/confirm' '{"bookingID":"70000000-0000-0000-0000-000000000001","newHoldID":"not-a-uuid","waitlistID":"bcefea06-1048-45c9-bde2-04f4d80f3510"}' @{ 'X-Internal-Token' = $token }
Invoke-Case 'CO-032' 409 'POST' 'http://localhost:6003/orchestrator/cancellation/reallocation/confirm' '{"bookingID":"70000000-0000-0000-0000-000000000001","newHoldID":"40000000-0000-0000-0000-000000000005","waitlistID":"bcefea06-1048-45c9-bde2-04f4d80f3510"}' @{ 'X-Internal-Token' = $token }
Invoke-Case 'CO-033' 409 'POST' 'http://localhost:6003/orchestrator/cancellation/reallocation/confirm' '{"bookingID":"70000000-0000-0000-0000-000000000001","newHoldID":"40000000-0000-0000-0000-000000000004","waitlistID":"bcefea06-1048-45c9-bde2-04f4d80f3510"}' @{ 'X-Internal-Token' = $token }
Invoke-Case 'CO-034' 409 'POST' 'http://localhost:6003/orchestrator/cancellation/reallocation/confirm' '{"bookingID":"70000000-0000-0000-0000-000000000001","newHoldID":"40000000-0000-0000-0000-000000000004","waitlistID":"1aa98295-4279-40b7-b29a-4c7dc7ad1dce"}' @{ 'X-Internal-Token' = $token }

# Group C fixture-dependent
if (Offer-Waitlist $wl '020bccd4-e822-43b8-932c-5d646cb8a4dd') {
  Invoke-Case 'CO-035' 409 'POST' 'http://localhost:6003/orchestrator/cancellation/reallocation/confirm' '{"bookingID":"70000000-0000-0000-0000-000000000001","newHoldID":"020bccd4-e822-43b8-932c-5d646cb8a4dd","waitlistID":"6d3a5c49-7600-49d1-9632-a852475cd694","newUserID":"00000000-0000-0000-0000-000000000002"}' @{ 'X-Internal-Token' = $token }
} else {
  $results += [pscustomobject]@{ id='CO-035'; expected=409; actual=-1; result='FAIL'; body='waitlist offer setup failed' }
}

if (Offer-Waitlist $wl 'c6743671-e1c3-4a5e-9db8-df1be6f58ba5') {
  Invoke-Case 'CO-036' 409 'POST' 'http://localhost:6003/orchestrator/cancellation/reallocation/confirm' '{"bookingID":"70000000-0000-0000-0000-000000000001","newHoldID":"c6743671-e1c3-4a5e-9db8-df1be6f58ba5","waitlistID":"6d3a5c49-7600-49d1-9632-a852475cd694"}' @{ 'X-Internal-Token' = $token }
} else {
  $results += [pscustomobject]@{ id='CO-036'; expected=409; actual=-1; result='FAIL'; body='waitlist offer setup failed' }
}

if (Offer-Waitlist $wl '020bccd4-e822-43b8-932c-5d646cb8a4dd') {
  Invoke-Case 'CO-037' 200 'POST' 'http://localhost:6003/orchestrator/cancellation/reallocation/confirm' '{"bookingID":"70000000-0000-0000-0000-000000000001","newHoldID":"020bccd4-e822-43b8-932c-5d646cb8a4dd","waitlistID":"6d3a5c49-7600-49d1-9632-a852475cd694","newUserID":"00000000-0000-0000-0000-000000000001"}' @{ 'X-Internal-Token' = $token }
} else {
  $results += [pscustomobject]@{ id='CO-037'; expected=200; actual=-1; result='FAIL'; body='waitlist offer setup failed' }
}

if (Offer-Waitlist $wl 'fbd05e17-93d3-4ffe-a23a-a2bcbb1e9174') {
  Invoke-Case 'CO-038' 502 'POST' 'http://localhost:6003/orchestrator/cancellation/reallocation/confirm' '{"bookingID":"70000000-0000-0000-0000-000000000001","newHoldID":"fbd05e17-93d3-4ffe-a23a-a2bcbb1e9174","waitlistID":"6d3a5c49-7600-49d1-9632-a852475cd694","newUserID":"00000000-0000-0000-0000-000000000001"}' @{ 'X-Internal-Token' = $token }
} else {
  $results += [pscustomobject]@{ id='CO-038'; expected=502; actual=-1; result='FAIL'; body='waitlist offer setup failed' }
}

# Group D parity
Invoke-Case 'CO-040-DIRECT' 409 'POST' 'http://localhost:6003/bookings/cancel/7b100000-0000-0000-0000-000000000006' '{"userID":"00000000-0000-0000-0000-000000000001"}'
Invoke-Case 'CO-040-KONG' 409 'POST' 'http://localhost:8000/bookings/cancel/7b100000-0000-0000-0000-000000000006' '{"userID":"00000000-0000-0000-0000-000000000001"}'
Invoke-Case 'CO-041-DIRECT' 400 'POST' 'http://localhost:6003/bookings/cancel/not-a-uuid' '{"userID":"00000000-0000-0000-0000-000000000001"}'
Invoke-Case 'CO-041-KONG' 400 'POST' 'http://localhost:8000/bookings/cancel/not-a-uuid' '{"userID":"00000000-0000-0000-0000-000000000001"}'

# Cleanup waitlist fixture
try {
  Invoke-WebRequest -UseBasicParsing -Method Put -Uri ('http://localhost:5005/waitlist/' + $wl + '/cancel') -Headers @{ 'X-Internal-Token'=$token } -ContentType 'application/json' -Body '{"reason":"manual-suite-cleanup"}' -TimeoutSec 45 -ErrorAction Stop | Out-Null
} catch {}

# Summary
$passCount = ($results | Where-Object { $_.result -eq 'PASS' }).Count
$failCount = ($results | Where-Object { $_.result -eq 'FAIL' }).Count
Write-Output ("TOTAL=" + $results.Count + " PASS=" + $passCount + " FAIL=" + $failCount)
$results | ForEach-Object { Write-Output ($_.id + " expected=" + $_.expected + " actual=" + $_.actual + " result=" + $_.result) }
Write-Output "---FAILED_CASE_DETAILS---"
$results | Where-Object { $_.result -eq 'FAIL' } | ForEach-Object { Write-Output ($_.id + " body=" + $_.body) }
