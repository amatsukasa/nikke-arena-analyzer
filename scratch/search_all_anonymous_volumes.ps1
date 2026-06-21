$volumes = @(
    "2a1a15a4ac167847e57a9e60c78e6784a7cbaf01f4f6fcaa38be95b9a375773c",
    "02af0ad10c1115d31714f3d3c08bea6d07366c317749b04b62fdb512b33b5d9d",
    "3ce2e3d4c959ebe49c34690d4def7c209253559aca3e7e1dbcd29837aea9a9d4",
    "19cad3c6b46aec8043c5fa307f2fe9bbee3b65bdb3d2fa2d8d7383854f6d2b99",
    "918a4be382363b64cc8bd49b549817b5d36861fa56edcee85584592cfeb23e82",
    "37724c37b38c2a3bfa9b763714194ed639e7d4d50f3d357d3fea2b93799a4e21",
    "b52ab9bb5eea88f8ed37fb1ccf39517dcf84e73e2250c49f09edbef84ccf57dd",
    "ec99eb23a7f2a2d9691ae221098dfc1225e53b5a25d7f800d4f6f6ebfe50637e",
    "f1bc7d6f1ddef1a3556003edcdd3923d38f8609a9da229403df290b570fa19c6",
    "f6be8f4b00161688c141ca04362814ba6a72a4f3beb51456827558d07fb22110",
    "f437e1592abb22866c7fecb02e6d397a87cde9ac951557a1d249448e2283ce45",
    "fd83ecd0881aabfe14c5293368bdd9b3ad46c69e0ace47c6da0041811d3e75c8"
)

foreach ($vol in $volumes) {
    Write-Host "========================================"
    Write-Host "SCANNING VOLUME: $vol"
    
    # マウントして SQLite ファイルを検索 (サイズ指定なし)
    $results = docker run --rm -v "${vol}:/mnt" alpine find /mnt -name "*.db" -o -name "*.sqlite" -o -name "*.sqlite3" 2>$null
    if ($results) {
        Write-Host "Found DB files:"
        foreach ($res in $results -split "`n") {
            # ファイルのサイズと更新日時を確認
            $cleaned_path = $res.Trim()
            if ($cleaned_path) {
                # コンテナ内で ls -la して情報を取得
                $info = docker run --rm -v "${vol}:/mnt" alpine ls -la $cleaned_path 2>$null
                Write-Host "  $info"
            }
        }
    } else {
        Write-Host "No DB files found."
    }
}
Write-Host "========================================"
Write-Host "SCAN COMPLETED"
