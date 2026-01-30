param(
  [string]$ProjectId = "ffmpeg-mcp-server",
  [string]$Region = "asia-southeast1",
  [string]$Repo = "ffmpeg",
  [string]$ImageName = "ffmpeg-worker",
  [string]$Tag = "latest"
)

$ErrorActionPreference = "Stop"

gcloud config set project $ProjectId | Out-Null

# 確保 API
gcloud services enable cloudbuild.googleapis.com artifactregistry.googleapis.com run.googleapis.com | Out-Null

# 確保 Artifact Registry repo 存在（冇就建立）
$repoExists = gcloud artifacts repositories list --location=$Region --format="value(name)" | Select-String "/repositories/$Repo$"
if (-not $repoExists) {
  gcloud artifacts repositories create $Repo `
    --repository-format=docker `
    --location=$Region `
    --description="ffmpeg images"
}

# build + push（用 worker/ 作為 build context）
$Image = "$Region-docker.pkg.dev/$ProjectId/$Repo/$ImageName`:$Tag"
Write-Host "Building and pushing: $Image"

Push-Location (Join-Path $PSScriptRoot "..\worker")
gcloud builds submit --tag $Image
Pop-Location

Write-Host "DONE: $Image"
