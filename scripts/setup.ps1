param(
  [switch]$Dev
)

$ErrorActionPreference = "Stop"

function Test-Command($Name) {
  if (Get-Command $Name -ErrorAction SilentlyContinue) {
    Write-Host "PASS $Name"
    return $true
  }
  Write-Host "FAIL $Name not found"
  return $false
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
  $python = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $python) {
  throw "Python 3.11+ is required."
}

Test-Command git | Out-Null
Test-Command ao | Out-Null
Test-Command grep-ast | Out-Null
Test-Command ollama | Out-Null

if ($python.Name -eq "py.exe") {
  py -3 -m pip install -e ".[dev]"
} else {
  python -m pip install -e ".[dev]"
}

Write-Host ""
Write-Host "Next:"
Write-Host "  Copy .env.example to .env and set required values."
Write-Host "  bebop doctor"
