$ErrorActionPreference = "Stop"

$chromeCandidates = @(
  "C:\Program Files\Google\Chrome\Application\chrome.exe",
  "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
  "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
)

$chromePath = $chromeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $chromePath) {
  throw "실행 가능한 Chrome 또는 Edge 브라우저를 찾지 못했습니다."
}

$targets = @("ko", "en", "zh-CN")
$outputDir = Join-Path $env:USERPROFILE "propai-qg"
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$env:TEMP = $outputDir
$env:TMP = $outputDir
Set-Location $outputDir

function Start-DebugBrowser {
  param(
    [string]$BrowserPath,
    [int]$Port,
    [string]$ProfileDir
  )

  if (Test-Path $ProfileDir) {
    Remove-Item -Recurse -Force $ProfileDir
  }

  New-Item -ItemType Directory -Force -Path $ProfileDir | Out-Null

  return Start-Process -FilePath $BrowserPath -ArgumentList @(
    "--headless=new",
    "--no-sandbox",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--remote-debugging-port=$Port",
    "--user-data-dir=$ProfileDir",
    "about:blank"
  ) -PassThru
}

function Wait-DebugBrowser {
  param(
    [int]$Port
  )

  for ($attempt = 0; $attempt -lt 20; $attempt += 1) {
    try {
      Invoke-WebRequest -UseBasicParsing -Uri ("http://127.0.0.1:" + $Port + "/json/version") | Out-Null
      return
    } catch {
      Start-Sleep -Milliseconds 500
    }
  }

  throw ("원격 디버깅 포트가 열리지 않았습니다: " + $Port)
}

Write-Output "[axe]"
foreach ($locale in $targets) {
  $jsonText = & npx.cmd -y @axe-core/cli ("http://127.0.0.1:3000/" + $locale) --tags wcag2aa --browser chrome --chrome-path $chromePath --stdout 2>$null
  $json = $jsonText | ConvertFrom-Json
  $result = $json[0]
  Write-Output ($locale + " violations=" + [string]$result.violations.Count + " incomplete=" + [string]$result.incomplete.Count)
  foreach ($violation in $result.violations) {
    $target = ($violation.nodes[0].target -join ", ")
    Write-Output ("  violation=" + $violation.id + " target=" + $target)
  }
  foreach ($incomplete in $result.incomplete) {
    $target = ($incomplete.nodes[0].target -join ", ")
    Write-Output ("  incomplete=" + $incomplete.id + " target=" + $target)
  }
}

Write-Output "[lighthouse]"
foreach ($locale in $targets) {
  $port = switch ($locale) {
    "ko" { 9222 }
    "en" { 9223 }
    default { 9224 }
  }
  $browserProcess = $null

  try {
    $outputPath = Join-Path $outputDir ("lh-" + $locale + ".json")
    $profileDir = Join-Path $outputDir ("lh-profile-" + $locale)
    $browserProcess = Start-DebugBrowser -BrowserPath $chromePath -Port $port -ProfileDir $profileDir
    Wait-DebugBrowser -Port $port
    & npx.cmd -y lighthouse ("http://127.0.0.1:3000/" + $locale) --quiet --port=$port --only-categories=accessibility --output=json --output-path=$outputPath 2>$null
    $json = Get-Content $outputPath -Raw | ConvertFrom-Json
    $score = [math]::Round(($json.categories.accessibility.score * 100), 0)
    Write-Output ($locale + " accessibility=" + [string]$score)
  } catch {
    Write-Output ($locale + " accessibility=error " + $_.Exception.Message)
  } finally {
    if ($null -ne $browserProcess) {
      Stop-Process -Id $browserProcess.Id -Force -ErrorAction SilentlyContinue
    }
  }
}
