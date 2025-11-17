# Script pour copier la clé SSH publique sur le serveur VPS
# Ce script nécessite une seule saisie du mot de passe

$server = "nick@157.173.102.180"
$port = "22"
$publicKey = Get-Content "$env:USERPROFILE\.ssh\id_rsa.pub"

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Copie de la clé SSH publique sur le serveur" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Clé publique à copier:" -ForegroundColor Yellow
Write-Host $publicKey -ForegroundColor Gray
Write-Host ""
Write-Host "Vous allez être invité à entrer le mot de passe:" -ForegroundColor Yellow
Write-Host "Mot de passe: Ludvanne12@" -ForegroundColor Green
Write-Host ""
Write-Host "Appuyez sur Entrée pour continuer..." -ForegroundColor Cyan
Read-Host

# Créer le répertoire .ssh et copier la clé
$command = @"
mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo '$publicKey' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && echo 'Clé SSH copiée avec succès!'
"@

ssh -p $port $server $command

Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host "Configuration terminée!" -ForegroundColor Green
Write-Host "Vous pouvez maintenant vous connecter sans mot de passe:" -ForegroundColor Green
Write-Host "ssh nick@157.173.102.180 -p 22" -ForegroundColor Yellow
Write-Host "================================================" -ForegroundColor Green

