# Offline fixtures exercise selected collection/decision logic, never a tenant/device.
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$data=Get-Content -LiteralPath (Join-Path $root 'data/assessment-procedures.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$script:passed=0
function Assert-Check { param($Condition,[string]$Name)
    if (-not $Condition) { throw "FAILED: $Name" }
    $script:passed++; Write-Output "PASS: $Name"
}
function Run-Example { param([string]$Id)
    & ([scriptblock]::Create($data.checks.$Id.command))
}
function Read-Host { param([string]$Prompt)
    if (-not $script:answers.ContainsKey($Prompt)) { throw "Unexpected prompt: $Prompt" }
    $script:answers[$Prompt]
}
function Invoke-MgGraphRequest { param($Method,$Uri,$OutputType,$ErrorAction)
    if ($script:graphFailure) { throw 'Fixture: access denied' }
    if (-not $script:pages.ContainsKey($Uri)) { throw "Unexpected Graph URI: $Uri" }
    $script:pages[$Uri]
}
$script:answers=@{}; $script:pages=@{}; $script:graphFailure=$false

# Install the actual shared paging function from the authored example AST.
$tokens=$null;$parseErrors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseInput($data.checks.'TECH-CA'.command,[ref]$tokens,[ref]$parseErrors)
$function=$ast.Find({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Read-GraphCollection'},$true)
. ([scriptblock]::Create($function.Extent.Text))
$first='https://graph.microsoft.com/v1.0/users'
$second='https://graph.microsoft.com/v1.0/users?$skiptoken=test'
$script:pages=@{$first=@{value=@(@{id='one'});'@odata.nextLink'=$second};$second=@{value=@(@{id='two'})}}
$result=@(Read-GraphCollection $first)
Assert-Check ($result.Count -eq 2 -and $result[1]['id'] -eq 'two') 'Graph follows all pages without losing hashtable objects'
$script:pages=@{$first=@{value=@()}}
Assert-Check (@(Read-GraphCollection $first).Count -eq 0) 'Graph empty collection is empty, not an invented pass'
$script:pages=@{$first=@{value=@();'@odata.nextLink'='https://example.invalid/steal'}}
$caught=$false;try{Read-GraphCollection $first}catch{$caught=$true}
Assert-Check $caught 'Graph refuses a cross-host nextLink'
$script:pages=@{$first=@{value=@();'@odata.nextLink'=$first}}
$caught=$false;try{Read-GraphCollection $first}catch{$caught=$true}
Assert-Check $caught 'Graph refuses repeated paging links'
$script:pages=@{$first=@{unexpected='schema'}}
$caught=$false;try{Read-GraphCollection $first}catch{$caught=$true}
Assert-Check $caught 'Graph schema mismatch is unknown/error'
$script:graphFailure=$true
$caught=$false;try{Read-GraphCollection $first}catch{$caught=$true}
Assert-Check $caught 'Graph permission failure cannot become empty/pass'
$script:graphFailure=$false

# SMTP mailbox null inherits organisation setting; explicit false overrides true.
function Get-TransportConfig { [pscustomobject]@{SmtpClientAuthenticationDisabled=$script:orgDisabled} }
function Get-CASMailbox { param($ResultSize)
    [pscustomobject]@{PrimarySmtpAddress='inherited';SmtpClientAuthenticationDisabled=$null;PopEnabled=$false;ImapEnabled=$false}
    [pscustomobject]@{PrimarySmtpAddress='exception';SmtpClientAuthenticationDisabled=$false;PopEnabled=$false;ImapEnabled=$false}
    [pscustomobject]@{PrimarySmtpAddress='disabled';SmtpClientAuthenticationDisabled=$true;PopEnabled=$false;ImapEnabled=$false}
}
$script:orgDisabled=$true;$result=@(Run-Example 'TECH-LEGACY')
Assert-Check ($result.Count -eq 3 -and $result[0].EffectiveSmtpAuthDisabled -and -not $result[1].EffectiveSmtpAuthDisabled -and $result[2].EffectiveSmtpAuthDisabled) 'SMTP inherits null and respects explicit mailbox overrides'
$script:orgDisabled=$false;$result=@(Run-Example 'TECH-LEGACY')
Assert-Check (-not $result[0].EffectiveSmtpAuthDisabled) 'SMTP inherited false stays false'
$script:orgDisabled=$null;$caught=$false;try{Run-Example 'TECH-LEGACY'}catch{$caught=$true}
Assert-Check $caught 'Unknown SMTP organisation setting stops assessment'

# Credential lifetime calculations use typed timestamps, retain expired findings and no secrets.
$script:answers=@{'Maximum credential lifetime in days from your approved standard'='90'}
$app=@{id='app';displayName='Test';passwordCredentials=@(@{keyId='long';startDateTime='2025-01-01T00:00:00Z';endDateTime='2025-12-31T00:00:00Z'});keyCredentials=@()}
$script:pages=@{
 'https://graph.microsoft.com/v1.0/applications?$select=id,appId,displayName,passwordCredentials,keyCredentials'=@{value=@($app)}
 'https://graph.microsoft.com/v1.0/servicePrincipals?$select=id,appId,displayName,passwordCredentials,keyCredentials'=@{value=@()}
}
$result=@(Run-Example 'CLOUD-CHECK-04')
Assert-Check ($result.Count -eq 1 -and $result[0].ExceedsStandard -and $result[0].Expired) 'Credential lifetime and expiry are independent findings'
$script:answers['Maximum credential lifetime in days from your approved standard']='0'
$caught=$false;try{Run-Example 'CLOUD-CHECK-04'}catch{$caught=$true}
Assert-Check $caught 'Credential policy must be a positive chosen threshold'

# Supply controlled records in memory; never create or query real personnel/files.
function Import-Csv { param($LiteralPath)
    if (-not $script:csv.ContainsKey($LiteralPath)) { throw 'Unexpected fixture input' }
    $script:csv[$LiteralPath]
}
$script:answers=@{'Physical-access approvals CSV path'='approvals';'Sampled badge events CSV path'='events'}
$script:csv=@{
 approvals=@([pscustomobject]@{BadgeId='A';Zone='DC';StartUtc='2026-01-01T00:00:00Z';EndUtc='2026-02-01T00:00:00Z'})
 events=@([pscustomobject]@{BadgeId='A';Zone='DC';EventUtc='2026-01-15T00:00:00Z';Result='Granted'},[pscustomobject]@{BadgeId='A';Zone='DC';EventUtc='2026-02-01T00:00:00Z';Result='Granted'},[pscustomobject]@{BadgeId='B';Zone='DC';EventUtc='2026-01-15T00:00:00Z';Result='Denied'})
}
$result=@(Run-Example 'TECH-PHYSICAL')
Assert-Check ($result.Count -eq 1 -and $result[0].Time -eq '2026-02-01T00:00:00Z') 'Badge approval expiry is exclusive and denied events are not false positives'
$script:csv.events=@();$caught=$false;try{Run-Example 'TECH-PHYSICAL'}catch{$caught=$true}
Assert-Check $caught 'Missing badge event population cannot become a passing result'

$script:answers=@{'Finding retest register CSV path'='findings'}
$script:csv=@{findings=@(
 [pscustomobject]@{FindingId='F1';ControlId='AP-01';Owner='Team';DueUtc='2099-01-01T00:00:00Z';TestCaseId='T1';Status='Closed';RetestUtc='2026-01-01T00:00:00Z';RetestResult='Fail';EvidenceRef='ticket-1'},
 [pscustomobject]@{FindingId='F2';ControlId='AP-01';Owner='Team';DueUtc='2099-01-01T00:00:00Z';TestCaseId='T2';Status='Closed';RetestUtc='2026-01-01T00:00:00Z';RetestResult='Pass';EvidenceRef='ticket-2'}
)}
$result=@(Run-Example 'TECH-ASSURANCE')
Assert-Check ($result.Count -eq 1 -and $result[0].Finding -eq 'F1') 'Closed finding with failed retest remains a review item'

$script:answers=@{'Supplier access register CSV path'='suppliers'}
$script:csv=@{suppliers=@([pscustomobject]@{ObjectId='one';Supplier='Provider';Owner='Owner';RiskId='R1';AccessUntilUtc='2020-01-01T00:00:00Z'})}
$guestUri='https://graph.microsoft.com/v1.0/users?$filter='+[uri]::EscapeDataString("userType eq 'Guest'")+'&$select=id,userPrincipalName,accountEnabled'
$script:pages=@{$guestUri=@{value=@(@{id='one';userPrincipalName='guest';accountEnabled=$true})}}
$result=@(Run-Example 'TECH-SUPPLIER')
Assert-Check ($result.Count -eq 1 -and $result[0].Review -match 'Expired approval') 'Expired supplier approval with enabled guest is flagged'
$script:csv.suppliers=@($script:csv.suppliers[0],$script:csv.suppliers[0]);$result=@(Run-Example 'TECH-SUPPLIER')
Assert-Check ($result[0].Review -match 'unique') 'Duplicate supplier approvals cannot silently match'

Write-Output ("OFFLINE FIXTURES: $script:passed passed; engine "+$PSVersionTable.PSVersion)
