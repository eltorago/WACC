param([string]$OutputPath)
# Parse only. No assessment command is executed by this validation utility.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$data = Get-Content -LiteralPath (Join-Path $root 'data/assessment-procedures.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$results = foreach ($entry in $data.checks.PSObject.Properties) {
    $tokens = $null; $parseErrors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseInput($entry.Value.command, [ref]$tokens, [ref]$parseErrors)
    $commands = @($ast.FindAll({param($node) $node -is [System.Management.Automation.Language.CommandAst]},$true) | ForEach-Object {
        [pscustomobject]@{
            name=$_.GetCommandName()
            parameters=@($_.CommandElements | Where-Object {$_ -is [System.Management.Automation.Language.CommandParameterAst]} | ForEach-Object {$_.ParameterName})
        }
    })
    [pscustomobject]@{id=$entry.Name;engine=$PSVersionTable.PSVersion.ToString();errors=@($parseErrors | ForEach-Object {$_.Message});commands=$commands}
}
$json = ConvertTo-Json -InputObject @($results) -Depth 20
if ($OutputPath) { $json | Set-Content -LiteralPath $OutputPath -Encoding UTF8 } else { $json }
if (@($results | Where-Object {$_.errors.Count}).Count) { exit 1 }
