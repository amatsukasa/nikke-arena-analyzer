$volumes = docker volume ls -q

foreach ($vol in $volumes) {
    if ($vol -eq "nikke-arena-analyzer_postgres_data") {
        continue
    }
    Write-Host "========================================"
    Write-Host "VOLUME: $vol"
    
    # alpine でボリュームをマウントして 0 バイトより大きいファイルを検索
    # あまりにも多くのファイルが出力されるのを防ぐため、階層や件数を適度に絞る、または find を使用
    $files = docker run --rm -v "${vol}:/mnt" alpine find /mnt -type f -size +0 2>$null
    if ($files) {
        # 行数をカウント
        $lines = $files -split "`n"
        Write-Host "Found $($lines.Count) files."
        # 最初の20件を表示
        $files | Select-Object -First 20 | ForEach-Object { Write-Host "  $_" }
        if ($lines.Count -gt 20) {
            Write-Host "  ... and $($lines.Count - 20) more files."
        }
    } else {
        Write-Host "No non-empty files found."
    }
}
