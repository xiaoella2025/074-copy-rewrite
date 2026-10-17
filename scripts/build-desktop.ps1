param([switch]$BackendOnly, [switch]$ShellOnly)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectRoot
$env:CARGO_HOME = Join-Path $projectRoot '.desktop-tools\cargo'
$env:RUSTUP_HOME = Join-Path $projectRoot '.desktop-tools\rustup'
$env:PATH = "$env:CARGO_HOME\bin;$env:PATH"
$vsScript = Join-Path $projectRoot '.desktop-tools\BuildTools\VC\Auxiliary\Build\vcvarsall.bat'
if (Test-Path -LiteralPath $vsScript) {
    $vsEnvironment = & cmd /c "`"$vsScript`" x64 >nul && set"
    foreach ($line in $vsEnvironment) {
        if ($line -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') }
    }
}
$pythonRuntime = Join-Path $projectRoot '.desktop-tools\python\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonRuntime)) { throw '缺少桌面 Python 构建环境' }
$packArgs = @('-m','PyInstaller','--noconfirm','--clean','--onedir','--console',
    '--name','app074-backend','--distpath','src-tauri/binaries','--workpath','desktop-build',
    '--specpath','desktop-build','--add-data', ($projectRoot + '\index.html;.'), '--add-data', ($projectRoot + '\settings.html;.'),
    '--add-data', ($projectRoot + '\workbench.html;.'), '--add-data', ($projectRoot + '\image-lab.html;.'), '--add-data', ($projectRoot + '\voice-lab.html;.'), '--add-data', ($projectRoot + '\prompt-editor.html;.'), '--add-data', ($projectRoot + '\template-editor.html;.'), '--add-data', ($projectRoot + '\library.html;.'), '--add-data', ($projectRoot + '\tasks.html;.'), '--add-data', ($projectRoot + '\result.html;.'), '--add-data', ($projectRoot + '\assets;assets'),
    '--add-data', ($projectRoot + '\prompts;prompts'),'--collect-all','sherpa_onnx','--collect-all','onnxruntime','--collect-all','jieba','--hidden-import','numpy')
$ffmpegCommand = Get-Command ffmpeg.exe -ErrorAction SilentlyContinue
if ($ffmpegCommand) { $packArgs += @('--add-binary', ($ffmpegCommand.Source + ';.')) }
else { throw '缺少 ffmpeg，不能打包图文音频功能' }
$ffprobeCommand = Get-Command ffprobe.exe -ErrorAction Stop
$packArgs += @('--add-binary', ($ffprobeCommand.Source + ';.'))
$storyGenerator = Join-Path $projectRoot '.desktop-tools\story-reference\draft-generator.exe'
if (-not (Test-Path -LiteralPath $storyGenerator)) { throw '缺少已提取的 Story 离线草稿生成器' }
$packArgs += @('--add-binary', ($storyGenerator + ';.'))
$nodeCommand = Get-Command node.exe -ErrorAction Stop
$packArgs += @('--add-binary', ($nodeCommand.Source + ';.'), '--add-data', ($projectRoot + '\creative.html;.'), '--add-data', ($projectRoot + '\scripts\render-motion.cjs;scripts'))
$packArgs += @('--add-data', ($projectRoot + '\scripts\run-image-pipeline.cjs;scripts'))
$packArgs += 'desktop_backend.py'
$packArgs += @('--add-data', ($projectRoot + '\market.html;.'), '--add-data', ($projectRoot + '\selection.html;.'), '--add-data', ($projectRoot + '\management.html;.'))
$packArgs += @('--add-data', ($projectRoot + '\benchmark.html;.'))
$packArgs += @('--add-data', ($projectRoot + '\default-bgm.mp3;.'))
if (-not $ShellOnly) {
& $pythonRuntime @packArgs
if ($LASTEXITCODE -ne 0) { throw 'Python 后台打包失败' }
& $pythonRuntime scripts/package-backend-runtime.py
if ($LASTEXITCODE -ne 0) { throw '独立 Python 后台运行时校验失败' }
}
if ($BackendOnly) { exit 0 }
# Compile the shell separately: tauri-build's resource recopy can fail with
# Windows error 5 against a previous release tree. The bundler consumes the
# freshly frozen resources directly from the normal tauri.conf.json mapping.
$shellConfig = Join-Path $projectRoot '.desktop-tools\shell-build-config.json'
'{"bundle":{"resources":[]}}' | Set-Content -LiteralPath $shellConfig -Encoding utf8
& npm.cmd exec tauri build -- --no-bundle --config $shellConfig
if ($LASTEXITCODE -ne 0) { throw 'Tauri 桌面程序编译失败' }
& npm.cmd exec tauri bundle -- --bundles nsis --ci
if ($LASTEXITCODE -ne 0) { throw 'Tauri 安装包构建失败' }
Write-Output '安装包目录：src-tauri\target\release\bundle\nsis'
