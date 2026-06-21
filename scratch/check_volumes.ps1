$volumes = @(
    "4b8755a5fde2539462026e3273bdf9f4725532f2f5e21de5acbf1663a23e4ce9",
    "e5f27dcc1aa01f003d700f109a4aa89ac7ffd8e695425f87a9577277c8893d30",
    "91beebeab1e361db371549ddcda214ee417c6809838c20c8d23f1e7b4afe5a91",
    "231fc17e8995e7e83d5d3b0049bfb18e296e56afd81481da43a5da3d88a58b33",
    "0979beb91fb99d212785180bd30bae3ea1f6f90e71447a294584f9cef26c5c2f",
    "5279ad5b2407ff34c5e8ff468685e330bf2c2f782b7c111a35cb1caaea53e547",
    "8118944f814e667cacf4f9ccddeb33e983578a771cdbac2b50f7ebe884fd6924",
    "19cad3c6b46aec8043c5fa307f2fe9bbee3b65bdb3d2fa2d8d7383854f6d2b99",
    "fd83ecd0881aabfe14c5293368bdd9b3ad46c69e0ace47c6da0041811d3e75c8"
)

foreach ($vol in $volumes) {
    Write-Host "----------------------------------------"
    Write-Host "Checking volume: $vol"
    
    docker rm -f temp_check_db 2>$null | Out-Null
    
    $containerId = docker run -d --name temp_check_db -e POSTGRES_PASSWORD=password -e POSTGRES_DB=postgres -v "${vol}:/var/lib/postgresql/data" postgres:15
    
    Start-Sleep -Seconds 5
    
    $status = docker inspect --format='{{.State.Status}}' temp_check_db 2>$null
    $logs = docker logs temp_check_db 2>&1
    
    Write-Host "Status: $status"
    
    if ($logs -and ($logs -match "PostgreSQL Database directory appears to contain a database")) {
        Write-Host "-> FOUND existing database in volume: $vol"
        
        Start-Sleep -Seconds 5
        
        $targetDBs = @("nikke_arena", "tournament_db", "postgres")
        $found = $false
        foreach ($db in $targetDBs) {
            $output = docker exec temp_check_db psql -U postgres -d $db -c "\dt" 2>$null
            if ($output) {
                Write-Host "Tables in DB [$db]:"
                Write-Host $output
                if ($output -match "tournaments") {
                    Write-Host "SUCCESS: Found tournaments table in DB $db of volume $vol!"
                    $found = $true
                    break
                }
            }
        }
        if ($found) {
            docker stop temp_check_db >$null
            docker rm temp_check_db >$null
            exit 0
        }
    } else {
        Write-Host "-> Volume is empty or failed to boot."
    }
    
    docker stop temp_check_db >$null 2>$null
    docker rm temp_check_db >$null 2>$null
}
