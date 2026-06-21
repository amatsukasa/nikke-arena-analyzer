$volumes = docker volume ls -q

foreach ($vol in $volumes) {
    if ($vol -eq "nikke-arena-analyzer_postgres_data") {
        continue
    }
    
    # PostgreSQL用のディレクトリ構造（PG_VERSIONファイル）があるか事前にチェックして、PGのボリューム以外はスキップする
    $hasPgVersion = docker run --rm -v "${vol}:/mnt" alpine test -f /mnt/PG_VERSION 2>$null
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        # PG_VERSION がないボリュームはスキップ
        continue
    }
    
    Write-Host "========================================"
    Write-Host "Checking PostgreSQL Volume: $vol"
    
    docker rm -f temp_check_db 2>$null | Out-Null
    
    # PostgreSQLコンテナを起動
    # postgres:15 ではなく、以前使われていたイメージがあればそれに合わせたいですが、まずは postgres:15 で起動を試みます
    $containerId = docker run -d --name temp_check_db -e POSTGRES_PASSWORD=password -v "${vol}:/var/lib/postgresql/data" postgres:15
    
    # 起動を待機 (pg_isready)
    $ready = $false
    for ($i = 0; $i -lt 15; $i++) {
        $check = docker exec temp_check_db pg_isready -U postgres 2>$null
        if ($check -match "accepting connections") {
            $ready = $true
            break
        }
        Start-Sleep -Seconds 2
    }
    
    if ($ready) {
        Write-Host "-> PostgreSQL is ready."
        
        # データベース一覧を取得して確認
        $dblist = docker exec temp_check_db psql -U postgres -t -A -c "SELECT datname FROM pg_database;" 2>$null
        Write-Host "   Databases: $($dblist -join ', ')"
        
        # 各データベースで tournaments テーブルを探す
        $targetDBs = $dblist | Where-Object { $_ -ne "template1" -and $_ -ne "template0" }
        foreach ($db in $targetDBs) {
            # テーブル一覧に tournaments があるか
            $tables = docker exec temp_check_db psql -U postgres -d $db -t -A -c "SELECT tablename FROM pg_tables WHERE schemaname='public';" 2>$null
            if ($tables -contains "tournaments") {
                $count = docker exec temp_check_db psql -U postgres -d $db -t -A -c "SELECT COUNT(*) FROM tournaments;" 2>$null
                Write-Host "   [SUCCESS] Found 'tournaments' table in DB '$db' with $count records!"
            }
        }
    } else {
        Write-Host "-> Failed to boot PostgreSQL or pg_isready timeout."
        # エラーログを表示してみる
        $logs = docker logs temp_check_db 2>&1 | Select-Object -Last 10
        Write-Host "   Logs: $logs"
    }
    
    docker stop temp_check_db >$null 2>$null
    docker rm temp_check_db >$null 2>$null
}
