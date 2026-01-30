param(
  [string]$ProjectId = "ffmpeg-mcp-server",
  [string]$Region = "asia-southeast1",
  [string]$Repo = "ffmpeg",
  [string]$ImageName = "ffmpeg-worker",
  [string]$Tag = "latest",
  [string]$JobName = "ffmpeg-worker"
)

$ErrorActionPreference = "Stop"

gcloud config set project $ProjectId | Out-Null

$Image = "$Region-docker.pkg.dev/$ProjectId/$Repo/$ImageName`:$Tag"

# 檢查 job 是否存在
$exists = $false
try {
  gcloud run jobs describe $JobName --region $Region | Out-Null
  $exists = $true
} catch {
  $exists = $false
}

if (-not $exists) {
  Write-Host "Creating job: $JobName"
  gcloud run jobs create $JobName `
    --image $Image `
    --region $Region `
    --tasks 1 `
    --cpu 2 `
    --memory 4Gi `
    --max-retries 0 `
    --task-timeout 36000
} else {
  Write-Host "Updating job: $JobName"
  gcloud run jobs update $JobName `
    --image $Image `
    --region $Region `
    --tasks 1 `
    --cpu 2 `
    --memory 4Gi `
    --max-retries 0 `
    --task-timeout 36000
}

Write-Host "DONE: $JobName -> $Image"
