$volumes = @(
    "4fd103eb763dc04790af3e322370d37b69187715a5635ed6f0e1a2a60265262d",
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
    Write-Host "========================================"
    Write-Host "VOLUME: $vol"
    docker rm -f temp_check_db 2>$null | Out-Null
    
    # バックグラウンド起動
    $containerId = docker run -d --name temp_check_db -e POSTGRES_PASSWORD=password -e POSTGRES_DB=nikke_arena -v "${vol}:/var/lib/postgresql/data" postgres:15
    Start-Sleep -Seconds 3
    
    # ログ取得
    $logs = docker logs temp_check_db 2>&1
    Write-Host "Logs:"
    Write-Host $logs
    
    docker stop temp_check_db >$null 2>$null
    docker rm temp_check_db >$null 2>$null
}
