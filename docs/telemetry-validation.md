# Validate an annual assessment with security logs

WACC compares fourteen checks with the selected department/year workbook. Each finding
links to the control workspace, WA policy requirement, Microsoft reference and
underlying events. A reviewer can accept evidence, confirm a gap, explain an
exception or request more evidence. The submitted workbook ratings stay intact.

Start with the offline examples. All storage names, tenant IDs and events are
fictional; an Azure account or connection is not required. The examples demonstrate
how plausible Sentinel and Defender evidence can support or challenge a rating
against the 2024 WA policy. Storage is an optional collection method, not the basis
for selecting the checks.

## Try the fictional example

1. Start WACC with `python -m wacc serve` and open **Assessments**.
2. Select **Import the three examples** if the Silly Walks workbooks are not loaded.
3. Open **Validate the 2025 assessment** and select **Validate this year's example logs**.
4. Open **Application control → Event evidence**. A harmless demonstration program
   ran on laptop 2 during an approved test that required it to be blocked.
5. Open **Multi-factor authentication**. One successful sign-in used only a password
   and shows no Conditional Access policy applied. Another reused an MFA claim;
   that event supports MFA. A rejected sign-in is not treated as a bypass.
6. Record a review decision and its evidence reference. Download the JSON report
   to retain the findings, hashes and review history.
7. Select 2023 and 2024 and validate their example logs. Return to **Assessments**
   to see the fourteen-check evidence bars alongside the reported maturity trend.
8. Open **WA policy coverage** to see all 86 criteria, their contributing log checks
   and the documents needed for assessment. Twelve criteria have implemented log
   comparisons; other criteria require document review or separate tests.

The sample covers December of each year, three devices, three users and one app.
It adds a firewall, an incident and a protected backup item to the endpoint and
identity sample. It deliberately leaves two possible overstatements in 2025 despite a higher
self-reported maturity rating. Every identity, address, hash and event is fictional.
No executable or attack payload is included.

Native event files are in `examples/telemetry/2023`, `2024` and `2025`. They use
Microsoft Sentinel table columns: seven Defender endpoint/inventory tables, Entra
`SigninLogs` and `AuditLogs`, `AZFWNetworkRule`, `SecurityIncident` and
`AddonAzureBackupJobs`. The 2025 sign-in file demonstrates CSV with quoted JSON fields;
the other files demonstrate newline-delimited JSON. Browser example downloads
wrap these files in a WACC transport bundle. The wrapper and `manifest.json`
are WACC metadata, not Microsoft log formats.

## Prepare your own evidence window

Create a working folder under `data/local/telemetry/`. Copy a sample manifest there,
then replace its fictional values. Do not put real exports in the examples folder.

| Manifest field | What to enter |
| --- | --- |
| `schema` | Keep `wacc-sentinel-evidence-v1`. |
| `department`, `year` | Match an imported annual workbook. |
| `source_kind` | `adls-gen2`, `sentinel-lake-csv` or `sentinel-export`. |
| `start`, `end` | UTC evidence window within that year. Start is included; end is excluded. |
| `workspace_id` | Log Analytics workspace UUID. Match the row's `TenantId`, or the file descriptor for the two tables described below. |
| `entra_tenant_id` | Entra directory UUID. This is `AADTenantId` in `SigninLogs` and `AuditLogs`. |
| `scope_reference` | Inventory, MFA policy, approved exceptions and export/query references used to choose the sample. |
| `device_ids` | MDE device IDs expected in this assessment sample. Reconcile them with the asset inventory. |
| `mfa_user_ids`, `mfa_app_ids` | Entra object IDs of users and app IDs where MFA is required. All combinations are in scope. |
| `authentication_details_final` | `true` only after checking that sign-in authentication details have finished aggregating; otherwise `false`. |
| `sensor_freshness_days` | Maximum age of endpoint status at the window end, between 1 and 30; default 7. |
| `expected_rows` | Source query row counts per table for exactly this window and workspace, before WACC scope filtering and deduplication. |
| `expected_block_tests` | Approved negative application-control tests: device ID, SHA-1, start/end and approval reference. Use `[]` if no test was performed. |
| `identity_user_ids` | Users whose account and role changes are included in the identity review. |
| `firewall_resource_ids`, `incident_names`, `backup_item_ids` | Explicit scope for the corresponding cloud/resource tables. |
| `patch_deadlines` | Device, CVE and software name, due date and source reference from an approved patch schedule. No deadline is inferred from severity alone. |
| `restore_targets` | Backup item, maximum restore-job duration in hours and the recovery-plan reference. This measures the job, not end-to-end service recovery. |
| `files` | Unique local filename, table and format (`jsonl` or `csv`) for every export. Optional `sha256` checks a known source-file hash. |

For `AuditLogs` and `AddonAzureBackupJobs`, record `workspace_id` in each file
descriptor: the referenced schemas do not contain the `TenantId` workspace column.
Do not insert invented Microsoft columns into those rows. This descriptor is an
operator's statement of where the export came from; it is not independent proof.
`AuditLogs.AADTenantId` is checked against the declared Entra tenant.

Use independently checked inventories and source counts. A hash detects changed
bytes; it does not prove an export is genuine or that its scope is complete.
Remove the example file hashes and test references when preparing a real manifest.
Capture new hashes from your actual exports if available. Use simple filenames
such as `DeviceEvents-01.jsonl`; multiple files can belong to one table.

Limits are 20 MB, 50 event files and 50,000 rows per run. Select a focused sample
and window for larger tenants. Separate runs remain separate evidence sets;
WACC does not combine them into a claim of full-year coverage. Missing events
are an evidence gap, not proof that a protection is working.

## Optional: read real exports from Azure Data Lake Storage Gen2

Start here for logs held in an Azure storage account and container/filesystem.
Before configuring the import, identify the storage account, container/filesystem,
one example log-file path, Entra tenant ID and Sentinel workspace ID.

This path reads existing files from a customer-owned ADLS Gen2 account. It does
not create a storage account, change Sentinel connectors or configure export rules.

1. Confirm the correct Sentinel workspace and the tables being collected. Defender
   XDR alerts alone are not the raw endpoint tables. Enable the required raw-event
   connections through your normal administration process; collect Entra sign-in
   logs as well.
2. Select the stored export files for the evidence window. Azure Monitor continuous
   data export writes JSON lines into per-table storage containers with time-based
   paths. It exports new arrivals; it does not backfill historical records. Include
   late arrivals and retry files, then reconcile source counts. Historical export
   jobs may produce Parquet, which this importer does not read; use CSV query
   exports for that route. See [Microsoft's export documentation](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/logs-data-export).
3. Use an operator identity with **Storage Blob Data Reader** on the required
   container/account, or equivalent approved ADLS read/traverse ACL access.
   The computer must reach the storage endpoint, including any private endpoint.
   No Owner or write role is required for this reader. See [storage read authorization](https://learn.microsoft.com/en-us/rest/api/storageservices/get-blob).
4. Install Azure CLI and sign in to the directory in `entra_tenant_id`:

   ```powershell
   az login --tenant YOUR-ENTRA-TENANT-ID
   ```

5. Add `azure.account` and the exact filesystem and remote path to each manifest
   file entry. The following is a structural example; use real values:

   ```json
   {
     "source_kind": "adls-gen2",
     "azure": {"account": "yourstorageaccount"},
     "files": [
       {
         "name": "DeviceEvents-01.jsonl",
         "table": "DeviceEvents",
         "format": "jsonl",
         "filesystem": "am-deviceevents",
         "adls_path": "WorkspaceResourceId=/subscriptions/YOUR-SUBSCRIPTION/resourcegroups/YOUR-RG/providers/microsoft.operationalinsights/workspaces/YOUR-WORKSPACE/y=2025/m=12/d=15/h=10/m=00/PT05M.json"
       }
     ]
   }
   ```

   Keep the other required manifest fields. Copy actual paths from your storage
   inventory; capitalization and partition paths must match the stored files.

6. From the repository, run:

   ```powershell
   python -m wacc telemetry --manifest data/local/telemetry/manifest.json --adls
   ```

7. Open the validation link printed by the command. Check export counts and scope,
   then review the findings. The saved run is visible from the annual assessment.

WACC asks the current [Azure CLI login for a storage access token](https://learn.microsoft.com/en-us/cli/azure/account#az-account-get-access-token)
and performs HTTPS GET requests to the named account's `dfs.core.windows.net`
endpoint using the documented [ADLS file read API](https://learn.microsoft.com/en-us/rest/api/storageservices/datalakestoragegen2/path/read).
It refuses redirects and arbitrary hosts, bounds downloads, records returned ETags
and hashes, and does not persist or print the token. This connector supports Azure
public cloud and a user/service-principal CLI login in the same directory as the
manifest. It does not discover containers or log in on the user's behalf.

## Optional: export from Sentinel or Log Analytics

Sentinel's managed data lake in the Defender portal is a different service from a
customer ADLS Gen2 account. Use its **KQL query editor → Export CSV** workflow;
Microsoft documents [interactive and asynchronous CSV exports](https://learn.microsoft.com/en-us/azure/sentinel/datalake/kql-queries).

1. Select the correct Sentinel workspace and evidence dates in the query editor.
2. Use `examples/telemetry/export-sentinel.kql`. Run each table query separately
   and save its CSV. It selects Sentinel `TimeGenerated` columns and formats the
   date in UTC for import. Check the schema browser before running; these queries
   target the Sentinel table schemas, not a raw Defender advanced-hunting response
   using only `Timestamp`.
   Use Log Analytics for tables unavailable in the managed lake, including
   `AddonAzureBackupJobs`. Table availability depends on the enabled connectors.
3. Run the separate count query for each table, with the same window and workspace.
   Put the results in `expected_rows`. Check the export completed without row limits
   or truncation. Do not use `take` or a filtered security-event subset for coverage.
4. List each CSV in the manifest with `format: "csv"`. If a table is empty, include
   a header-only CSV and a zero source count. A missing connector/table needs
   investigation rather than an invented zero count.
5. In WACC, select the assessment and upload **manifest.json and all listed files**
   together. You can also run the command below against local exports:

   ```powershell
   python -m wacc telemetry --manifest data/local/telemetry/manifest.json
   ```

The same local import accepts Azure Monitor JSON-line exports. Bare JSON arrays,
REST query response envelopes, compressed files and Parquet are not accepted.

## Interpret and review results

| Check | Evidence and decision | Workspace / WA CSP |
| --- | --- | --- |
| Application control | Block events support observed enforcement. Audit events need policy review. An exact device/hash/time match for a process that an approved test required to be blocked is a gap. | AP-01, AP-02 / 3.1.1a |
| MFA | Successful, interactive in-scope sign-ins: completed MFA, passwordless strong methods and reused claims provide support. Final password-only steps with no Conditional Access applied need review as a possible overstatement. Failed/non-interactive sign-ins are excluded. | MF-01, PA-03 / 3.1.1a, 3.6d |
| Endpoint coverage | Latest recent `DeviceInfo` state for each expected device. Active/onboarded supports the sample. Other explicit states are gaps; stale, missing or incomplete states need review. | SM-01, AM-01 / 4.2a |
| ASR | Office child-process and LSASS credential-theft rule events distinguish block from audit. | UH-02 / 3.1.1a |
| Central logging | Process, network and logon records demonstrate delivery for observed devices. Review connector and retention evidence for missing records. | SM-01, SM-03 / 4.2a |
| Antivirus follow-up | Detection plus recorded remediation supports follow-up. Missing or incomplete remediation requires the alert/case record. | SM-03, IR-02 / 4.1a |
| Software inventory | Recent software/version records are reconciled with the declared device sample and asset register. | AM-01 / 2.1a, 2.1b |
| Vulnerability remediation | A recent vulnerability with an available update is compared with its specific documented patch deadline. Missing observations do not prove compliance. | VM-01 / 3.1.1a |
| Account lifecycle | Successful creation, change and removal events support observed operation; compare their timing with personnel records. | IA-01 / 3.6a |
| Privileged access changes | Role assignment/removal events identify requests and access reviews to inspect. The event itself cannot establish business approval. | IA-02, PA-01, PA-04 / 3.6b |
| Network boundaries | Deny events support observed firewall enforcement. Allowed traffic requires comparison with the approved design rather than an automatic failure. | NA-01, NA-02 / 3.6f |
| Incident review and triage | Case creation and first modification times identify cases to review. Automated changes and status fields cannot establish analyst triage or daily review. | SM-03, IN-01, IR-02 / 4.1a, 4.1b, 5.1b |
| Backup jobs | Latest status per job distinguishes completed, failed and outstanding work; reconcile it with the protected-item list and backup schedule. | BR-01, BR-02 / 3.1.1a |
| Restore duration | Completed restore-job duration is compared with an explicit recovery-plan job target. Review application availability and data integrity separately. | BR-03 / 6.1 |

These are contributing tests for broad WA policy requirements. They do not cover
the other Essential Eight strategies, administrative approvals or every requirement
in the workbook. The evidence view identifies the tested slice and dates.

For a reported rating of 3 or 4, an observed gap is labelled **Potential overstatement**.
For lower ratings it is **Gap observed**. These labels identify inconsistencies,
not an assessor's intent. Record the reviewer, decision, reason and evidence
reference; previous decisions remain in the history. An accepted exception does not
erase the underlying finding. Update and reimport the workbook if its rating needs
correction; old comparisons are marked stale and require a new validation run.

## WA SOC onboarding context

Use the [WA SOC onboarding guide, sections 6 and 7](https://soc.cyber.wa.gov.au/onboarding/#7-migrating-sentinel-to-defender-xdr-portal)
to confirm the primary workspace connected to the Defender portal, data-lake
retention and onboarding arrangements. Record the workspace and source period in
the manifest so a portal migration or retention boundary is not mistaken for
missing protection. The guide's elevated migration roles are for onboarding;
they are not required by WACC's file reader. No check here certifies forwarding
to the WA SOC or replaces its onboarding validation.

## Storage and implementation

Originals, immutable comparison inputs and a report with appended review decisions
are saved under `data/local/assessments/validation/<run-id>/`. `WACC_ASSESSMENTS`
changes the parent assessment folder. This folder is excluded from Git and releases.
Only the authored fictional fixtures are distributed. Back up the local assessment
folder as required; raw logs and report downloads contain security information.

The current server is local and has no user authentication. Reviewer names are
entered by the operator, not verified identities. Use controlled local access for
real assessments; a shared deployment needs authentication and department access
controls before storing live evidence.

The importer rejects malformed files, wrong tenants/workspaces, altered hashes and
missing declared files. It counts out-of-window and out-of-scope events separately,
deduplicates exact records, and withholds conflicting event versions from positive
findings. The original files, line references, event hashes, workbook hash and rule
version preserve a reproducible evidence trail. Source-count mismatches remain
visible even when individual events support a check.

Run `python tests/test_telemetry.py` for parser, decision, storage, HTTP, CSV/JSONL,
Azure transport and false-positive regression tests. Azure requests are tested with
fixtures; no live customer storage account was supplied or queried. KQL uses the
documented columns and operators and must be exercised against the target workspace.

## Schema and rule references

Reviewed 16–17 September 2026:

- [DeviceEvents](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/deviceevents),
  [DeviceInfo](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/deviceinfo),
  [DeviceProcessEvents](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/deviceprocessevents),
  [DeviceNetworkEvents](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/devicenetworkevents),
  [DeviceLogonEvents](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/devicelogonevents),
  [SigninLogs](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/signinlogs).
- [Software inventory](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/devicetvmsoftwareinventory),
  [software vulnerabilities](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/devicetvmsoftwarevulnerabilities),
  [Entra audit events](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/auditlogs),
  [Entra activity names](https://learn.microsoft.com/en-us/entra/identity/monitoring-health/reference-audit-activities),
  [firewall network rules](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/azfwnetworkrule),
  [incident records](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityincident),
  [backup jobs](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/addonazurebackupjobs) and
  [Microsoft's job-status queries](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/queries/addonazurebackupjobs).
- [Application-control event meanings](https://learn.microsoft.com/en-us/windows/security/application-security/application-control/app-control-for-business/operations/querying-application-control-events-centrally-using-advanced-hunting).
- [MFA sign-in interpretation and delayed authentication details](https://learn.microsoft.com/en-us/entra/identity/authentication/howto-mfa-reporting).
- [ASR rule reference](https://learn.microsoft.com/en-us/defender-endpoint/attack-surface-reduction-rules-reference).
- [Antivirus detection and remediation fields](https://learn.microsoft.com/en-us/defender-endpoint/detect-block-potentially-unwanted-apps-microsoft-defender-antivirus).
