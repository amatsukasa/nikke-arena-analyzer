$volumes = @(
    "02af0ad10c1115d31714f3d3c08bea6d07366c317749b04b62fdb512b33b5d9d",
    "ec99eb23a7f2a2d9691ae221098dfc1225e53b5a25d7f800d4f6f6ebfe50637e",
    "918a4be382363b64cc8bd49b549817b5d36861fa56edcee85584592cfeb23e82",
    "f1bc7d6f1ddef1a3556003edcdd3923d38f8609a9da229403df290b570fa19c6",
    "f437e1592abb22866c7fecb02e6d397a87cde9ac951557a1d249448e2283ce45"
)

foreach ($vol in $volumes) {
    Write-Host "========================================"
    Write-Host "VOLUME: $vol"
    docker rm -f temp_explorer 2>$null | Out-Null
    
    # alpine でボリュームをマウントしてファイル一覧を取得
    docker run --rm -v "${vol}:/data" alpine ls -la /data 2>&1
}
