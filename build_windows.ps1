<# 
Windows 本地构建脚本
使用方法：
1. 在 PowerShell 中运行：.\build_windows.ps1
2. 或者右键选择"使用 PowerShell 运行"

这将模拟 GitHub Actions 的构建过程，生成可执行的 NeoXtractor
#>

param(
    [switch]$Clean = $false,  # 清理构建目录
    [switch]$Test = $false,   # 构建后测试运行
    [switch]$Help = $false    # 显示帮助
)

function Write-Header {
    param([string]$Title)
    Write-Host "`n" -NoNewline
    Write-Host "="*50 -ForegroundColor Cyan
    Write-Host "  $Title" -ForegroundColor Cyan
    Write-Host "="*50 -ForegroundColor Cyan
}

function Show-Help {
    Write-Header "NeoXtractor Windows 构建脚本"
    Write-Host "用法: .\build_windows.ps1 [选项]`n" -ForegroundColor Yellow
    Write-Host "选项:" -ForegroundColor Yellow
    Write-Host "  -Clean        清理之前的构建目录 (build/, dist/)" -ForegroundColor White
    Write-Host "  -Test         构建完成后测试运行可执行文件" -ForegroundColor White
    Write-Host "  -Help         显示此帮助信息" -ForegroundColor White
    Write-Host "  (无参数)      正常构建" -ForegroundColor White
    exit 0
}

if ($Help) { Show-Help }

Write-Header "NeoXtractor Windows 构建脚本"
Write-Host "当前目录: $(Get-Location)" -ForegroundColor Gray
Write-Host "Python 版本要求: >=3.12 (项目锁定: 3.13.5)" -ForegroundColor Gray

# 检查 Python 版本
$pythonVersion = & python --version 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ 未找到 Python。请先安装 Python 3.13.5 或更高版本。" -ForegroundColor Red
    Write-Host "  下载: https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}
Write-Host "✅ 找到 Python: $pythonVersion" -ForegroundColor Green

# 检查 uv
$uvVersion = & uv --version 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠️  未找到 uv，正在安装..." -ForegroundColor Yellow
    pip install uv
    $uvVersion = & uv --version 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ 安装 uv 失败。请手动安装: pip install uv" -ForegroundColor Red
        exit 1
    }
}
Write-Host "✅ 找到 uv: $uvVersion" -ForegroundColor Green

# 清理旧构建
if ($Clean) {
    Write-Header "清理构建目录"
    $dirsToRemove = @("build", "dist", "out")
    foreach ($dir in $dirsToRemove) {
        if (Test-Path $dir) {
            Remove-Item -Recurse -Force $dir -ErrorAction SilentlyContinue
            Write-Host "🗑️  删除目录: $dir" -ForegroundColor Yellow
        }
    }
}

# 安装依赖
Write-Header "安装依赖"
Write-Host "同步 uv 依赖 (使用锁定文件)..." -ForegroundColor Gray
& uv sync --locked
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ 依赖同步失败" -ForegroundColor Red
    exit 1
}
Write-Host "✅ 依赖同步完成" -ForegroundColor Green

Write-Host "安装 PyInstaller..." -ForegroundColor Gray
& uv pip install pyinstaller
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ PyInstaller 安装失败" -ForegroundColor Red
    exit 1
}
Write-Host "✅ PyInstaller 安装完成" -ForegroundColor Green

# 生成构建信息
Write-Header "生成构建信息"
Write-Host "运行构建信息工具..." -ForegroundColor Gray
& python tools/build_info_tool.py gen
if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠️  构建信息生成失败 (可能是 git 不可用)" -ForegroundColor Yellow
}

# 使用 PyInstaller 构建
Write-Header "使用 PyInstaller 构建"
Write-Host "运行: uv run pyinstaller main.spec" -ForegroundColor Gray
& uv run pyinstaller main.spec
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ PyInstaller 构建失败" -ForegroundColor Red
    exit 1
}
Write-Host "✅ PyInstaller 构建完成" -ForegroundColor Green

# 检查输出
Write-Header "构建结果"
$exePath = "dist/main/neoxtractor.exe"
if (Test-Path $exePath) {
    $fileSize = (Get-Item $exePath).Length / 1MB
    Write-Host "✅ 可执行文件生成成功: $exePath" -ForegroundColor Green
    Write-Host "   文件大小: $([math]::Round($fileSize, 2)) MB" -ForegroundColor Gray
    Write-Host "   完整路径: $(Resolve-Path $exePath)" -ForegroundColor Gray
    
    # 列出输出目录内容
    Write-Host "`n📁 输出目录内容:" -ForegroundColor Cyan
    Get-ChildItem "dist/main" | ForEach-Object {
        $type = if ($_.PSIsContainer) { "目录" } else { "文件" }
        $size = if ($_.Length -eq 0) { "" } else { "$([math]::Round($_.Length/1KB, 2)) KB" }
        Write-Host "  - $($_.Name) ($type) $size" -ForegroundColor Gray
    }
} else {
    Write-Host "❌ 未找到可执行文件: $exePath" -ForegroundColor Red
    exit 1
}

# 测试运行
if ($Test) {
    Write-Header "测试运行"
    Write-Host "运行: $exePath --version" -ForegroundColor Gray
    $versionOutput = & $exePath --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ 可执行文件运行成功:" -ForegroundColor Green
        Write-Host "   $versionOutput" -ForegroundColor White
    } else {
        Write-Host "⚠️  版本检查失败，但程序可能仍可运行:" -ForegroundColor Yellow
        Write-Host "   $versionOutput" -ForegroundColor Gray
    }
}

# 创建 ZIP 包
Write-Header "创建发布包"
$zipPath = "dist/neoxtractor-windows.zip"
Write-Host "创建 ZIP 包: $zipPath" -ForegroundColor Gray
Compress-Archive -Path "dist/main/*" -DestinationPath $zipPath -CompressionLevel Optimal -Force
if (Test-Path $zipPath) {
    $zipSize = (Get-Item $zipPath).Length / 1MB
    Write-Host "✅ ZIP 包创建成功: $zipPath" -ForegroundColor Green
    Write-Host "   文件大小: $([math]::Round($zipSize, 2)) MB" -ForegroundColor Gray
} else {
    Write-Host "❌ ZIP 包创建失败" -ForegroundColor Red
}

Write-Header "构建完成"
Write-Host "🎉 NeoXtractor Windows 版本构建成功！" -ForegroundColor Green
Write-Host "`n下一步:" -ForegroundColor Cyan
Write-Host "1. 可执行文件位于: dist/main/neoxtractor.exe" -ForegroundColor White
Write-Host "2. 发布包位于: dist/neoxtractor-windows.zip" -ForegroundColor White
Write-Host "3. 可以直接运行 neoxtractor.exe 启动 GUI" -ForegroundColor White
Write-Host "`n提示:" -ForegroundColor Yellow
Write-Host "- 使用 -Clean 参数清理之前的构建" -ForegroundColor Gray
Write-Host "- 使用 -Test 参数构建后测试运行" -ForegroundColor Gray
Write-Host "- GitHub Actions 会自动构建所有平台版本" -ForegroundColor Gray