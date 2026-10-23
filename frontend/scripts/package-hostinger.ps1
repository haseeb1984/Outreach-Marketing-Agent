param(
    [string]$OutputPath = (Join-Path (Get-Location) "outreach-marketing-agent-hostinger.zip")
)

$ErrorActionPreference = "Stop"
$frontendRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $frontendRoot
$resolvedOutput = [System.IO.Path]::GetFullPath($OutputPath)
$stage = Join-Path ([System.IO.Path]::GetTempPath()) ("outreach-hostinger-" + [guid]::NewGuid().ToString("N"))

$excludedDirectories = @("node_modules", ".next", ".git", "coverage", "dist", "build", ".turbo")
$requiredFiles = @("package.json", "next.config.ts", "tsconfig.json", "postcss.config.mjs", ".env.example")

try {
    New-Item -ItemType Directory -Path $stage -Force | Out-Null

    foreach ($name in $requiredFiles) {
        $path = Join-Path $frontendRoot $name
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Required frontend file missing: $name"
        }
        Copy-Item -LiteralPath $path -Destination $stage
    }

    foreach ($name in @("app", "public")) {
        $path = Join-Path $frontendRoot $name
        if (Test-Path -LiteralPath $path -PathType Container) {
            Copy-Item -LiteralPath $path -Destination $stage -Recurse
        }
    }

    $optionalFiles = @("middleware.ts", "instrumentation.ts", "server.js", "README.md", "DEPLOY_HOSTINGER.md")
    foreach ($name in $optionalFiles) {
        $path = Join-Path $frontendRoot $name
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            Copy-Item -LiteralPath $path -Destination $stage
        }
    }

    # Copy any remaining first-party source/config while excluding build outputs,
    # dependency trees, Git metadata, and every real .env file.
    Get-ChildItem -LiteralPath $frontendRoot -Force | ForEach-Object {
        $item = $_
        if ($item.Name -in $excludedDirectories) { return }
        if ($item.Name -match '^\.env(\..+)?$' -and $item.Name -ne '.env.example') { return }
        if ($item.Name -in @("package.json", "next.config.ts", "tsconfig.json", "postcss.config.mjs", ".env.example", "app", "public", "middleware.ts", "instrumentation.ts", "server.js", "README.md", "DEPLOY_HOSTINGER.md")) { return }
        if ($item.PSIsContainer) {
            Copy-Item -LiteralPath $item.FullName -Destination $stage -Recurse
        } else {
            Copy-Item -LiteralPath $item.FullName -Destination $stage
        }
    }

    # Refuse to package credentials accidentally present in a copied source tree.
    $leakedEnv = Get-ChildItem -LiteralPath $stage -Force -Recurse -File |
        Where-Object { $_.Name -match '^\.env(\..+)?$' -and $_.Name -ne '.env.example' }
    if ($leakedEnv) {
        throw "Refusing to package a real .env file. Remove it from frontend source first."
    }

    $outputDirectory = Split-Path -Parent $resolvedOutput
    if ($outputDirectory) {
        New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
    }
    if (Test-Path -LiteralPath $resolvedOutput) {
        Remove-Item -LiteralPath $resolvedOutput -Force
    }
    Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $resolvedOutput -CompressionLevel Optimal

    Write-Output ("Hostinger frontend ZIP created: " + $resolvedOutput)
    Write-Output "Included: Next.js application source and runtime configuration."
    Write-Output "Excluded: .env secrets, node_modules, .next, build output, and Git metadata."
    Write-Output "Next step on Hostinger: npm install, set BACKEND_API_ORIGIN server-side, npm run build, then start the Node.js app."
}
finally {
    if (Test-Path -LiteralPath $stage) {
        Remove-Item -LiteralPath $stage -Recurse -Force
    }
}
