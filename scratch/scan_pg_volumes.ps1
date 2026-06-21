# 手動停止
docker stop temp_manual_check 2>$null | Out-Null
docker rm temp_manual_check 2>$null | Out-Null

$volumes = @(
    "4fd103eb763dc04790af3e322370d37b69187715a5635ed6f0e1a2a60265262d",
    "91beebeab1e361db371549ddcda214ee417c6809838c20c8d23f1e7b4afe5a91",
    "231fc17e8995e7e83d5d3b0049bfb18e296e56afd81481da43a5da3d88a58b33",
    "0979beb91fb99d212785180bd30bae3ea1f6f90e71447a294584f9cef26c5c2f",
    "5279ad5b2407ff34c5e8ff468685e330bf2c2f782b7c111a35cb1caaea53e547",
    "8118944f814e667cacf4f9ccddeb33e983578a771cdbac2b50f7ebe884fd6924",
    "e5f27dcc1aa01f003d700f109a4aa89ac7ffd8e695425f87a9577277c8893d30",
    "ec518f6a-c5b5-4935-a3bd-71616e26ed04_pgdata"
)

foreach ($vol in $volumes) {
    Write-Host "========================================"
    Write-Host "SCANNING VOLUME: $vol"
    
    docker stop temp_scan 2>$null | Out-Null
    docker rm temp_scan 2>$null | Out-Null
    
    $container = docker run -d --name temp_scan -e POSTGRES_PASSWORD=password -v "${vol}:/var/lib/postgresql/data" postgres:15
    
    # 起動待機
    $ready = $false
    for ($i = 0; $i -lt 10; $i++) {
        Start-Sleep -Seconds 2
        $status = docker exec temp_scan pg_isready -U postgres 2>$null
        if ($status -match "accepting connections") {
            $ready = $true
            break
        }
    }
    
    if ($ready) {
        $dblist = docker exec temp_scan psql -U postgres -t -A -c "SELECT datname FROM pg_database;" 2>$null
        Write-Host "  Databases found: $($dblist -join ', ')"
        
        foreach ($db in $dblist) {
            if ($db -eq "template1" -or $db -eq "template0") { continue }
            
            $tables = docker exec temp_scan psql -U postgres -d $db -t -A -c "SELECT tablename FROM pg_tables WHERE schemaname='public';" 2>$null
            if ($tables) {
                Write-Host "  DB '$db' tables: $($tables -join ', ')"
                if ($tables -contains "tournaments") {
                    $count = docker exec temp_scan psql -U postgres -d $db -t -A -c "SELECT COUNT(*) FROM tournaments;" 2>$null
                    Write-Host "  -> [FOUND] 'tournaments' table in '$db' with $count rows!"
                }
            }
        }
    } else {
        Write-Host "  -> Failed to boot database or pg_isready timeout."
        $logs = docker logs temp_scan 2>&1 | Select-Object -Last 5
        Write-Host "  Logs: $logs"
    }
    
    docker stop temp_scan 2>$null | Out-Null
    docker rm temp_scan 2>$null | Out-Null
}
Write-Host "========================================"
Write-Host "SCAN COMPLETED"
