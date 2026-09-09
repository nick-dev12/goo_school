# Helpers Redis/Memurai pour Windows
# Usage : . "$PSScriptRoot\redis_windows.ps1"

function Get-RedisCliPath {
    $redisCli = Get-Command redis-cli -ErrorAction SilentlyContinue
    if ($redisCli) {
        return $redisCli.Source
    }

    $memuraiCli = Get-Command memurai-cli -ErrorAction SilentlyContinue
    if ($memuraiCli) {
        return $memuraiCli.Source
    }

    $defaultMemurai = "C:\Program Files\Memurai\memurai-cli.exe"
    if (Test-Path $defaultMemurai) {
        return $defaultMemurai
    }

    return $null
}

function Test-RedisConnection {
    $cli = Get-RedisCliPath
    if ($cli) {
        try {
            $result = & $cli ping 2>$null
            if ($result -eq "PONG") {
                return $true
            }
        } catch {
            # fallback port check below
        }
    }

    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect("127.0.0.1", 6379)
        $connected = $tcp.Connected
        $tcp.Close()
        return $connected
    } catch {
        return $false
    }
}

function Invoke-RedisPing {
    $cli = Get-RedisCliPath
    if ($cli) {
        return & $cli ping
    }
    if (Test-RedisConnection) {
        return "PONG"
    }
    throw "Redis/Memurai indisponible sur 127.0.0.1:6379"
}
