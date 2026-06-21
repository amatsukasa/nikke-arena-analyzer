$volumes = docker volume ls -q

foreach ($vol in $volumes) {
    if ($vol -eq "nikke-arena-analyzer_postgres_data") {
        continue
    }
    Write-Host "========================================"
    Write-Host "Checking Volume: $vol"
    
    docker rm -f temp_check_db 2>$null | Out-Null
    
    $containerId = docker run -d --name temp_check_db -e POSTGRES_PASSWORD=password -e POSTGRES_DB=nikke_arena -v "${vol}:/var/lib/postgresql/data" postgres:15
    Start-Sleep -Seconds 5
    
    $status = docker inspect --format='{{.State.Status}}' temp_check_db 2>$null
    $logs = docker logs temp_check_db 2>&1
    
    if ($logs -and ($logs -match "PostgreSQL Database directory appears to contain a database")) {
        Write-Host "-> FOUND existing database in volume: $vol"
        
        $dbs = @("nikke_arena", "postgres")
        foreach ($db in $dbs) {
            $tables = docker exec temp_check_db psql -U postgres -d $db -c "\dt" 2>$null
            if ($tables) {
                Write-Host "  Found DB: $db"
                if ($tables -match "tournaments") {
                    Write-Host "  -> Found 'tournaments' table!"
                    $count = docker exec temp_check_db psql -U postgres -d $db -t -c "SELECT COUNT(*) FROM tournaments;" 2>$null
                    if ($count) {
                        Write-Host "  -> Records in tournaments: $($count.Trim())"
                    }
                } else {
                    Write-Host "  -> 'tournaments' table NOT found."
                }
            }
        }
    } else {
        Write-Host "-> Not a PostgreSQL database or empty."
    }
    
    docker stop temp_check_db >$null 2>$null
    docker rm temp_check_db >$null 2>$null
}
