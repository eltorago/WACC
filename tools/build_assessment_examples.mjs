// Run with the bundled artifact-tool dependency. WACC itself needs only Python.
import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
const root=process.cwd();
const require=createRequire(path.join(root,'data/review/assessment-build/runner.mjs'));
const {Workbook,SpreadsheetFile}=await import(pathToFileURL(require.resolve('@oai/artifact-tool')));
const policy=JSON.parse(await fs.readFile(path.join(root,'data/department-assessment-policy.json'),'utf8'));
const examples=JSON.parse(await fs.readFile(path.join(root,'data/department-assessment-examples.json'),'utf8'));
const out=path.resolve(root,'../outputs/department-assessments-20260916');
const published=path.join(root,'examples/assessments');
await fs.mkdir(out,{recursive:true}); await fs.mkdir(published,{recursive:true});
const blank={department:'',year:2026,date:'',assessor:'',scope:'',retrospective:'No',authority:'',approval_date:'',air_status:'Not requested',air_reference:'',exemptions:'',
 rows:policy.requirements.map(r=>({id:r.id,rating:'Not assessed',evidence:'',owner:'',action:'',due:'',exclusion:''}))};
const headers=['Requirement ID','Area','Assessment prompt','Rating','Evidence','Owner','Next action','Due date','Exclusion reason','Score','Policy reference'];
const end=6+policy.requirements.length;
const navy='#21364C',gray='#596B7C',amber='#FFF6D9';
function values(sheet,address,data){sheet.getRange(address).values=data;}
function formula(sheet,address,text){sheet.getRange(address).formulas=[[text]];}
function header(sheet,address){sheet.getRange(address).format={fill:navy,font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},rowHeight:30,wrapText:true};}
function text(sheet,cell,value){values(sheet,cell,[[value]]);}
for(const example of [...examples,blank]){
 const isBlank=example===blank;
 const wb=Workbook.create();
 const overview=wb.worksheets.add('Overview');
 const assessment=wb.worksheets.add('Assessment');
 for(const sh of [overview,assessment]){sh.showGridLines=false;sh.getRange(sh===overview?'A1:H40':`A1:K${end}`).format={font:{name:'Arial',size:10,color:navy},rowHeight:24,verticalAlignment:'center'};}
 overview.tabColor=navy;
 overview.getRange('A1:A34').format.columnWidth=26;
 overview.getRange('B1:B34').format.columnWidth=48;
 overview.getRange('C1:C34').format.columnWidth=3;
 overview.getRange('D1:D34').format.columnWidth=19;
 overview.getRange('E1:G34').format.columnWidth=14;
 overview.getRange('H1:H34').format.columnWidth=3;
 text(overview,'A2',isBlank?'WA policy self-assessment':'Department of Silly Walks');
 overview.getRange('A2:G2').format.font={name:'Arial',size:16,bold:true,color:navy};
 text(overview,'A3',isBlank?'Complete the amber input cells.':`${example.year} fictional self-assessment${example.year===2023?' · retrospective against the 2024 policy':''}`);
 overview.getRange('A3:G3').format.font={name:'Arial',size:10,color:gray};
 const metadata=[['Department',example.department],['Assessment year',example.year],['Assessment date',example.date?new Date(example.date+'T00:00:00Z'):null],['Assessor',example.assessor],['Scope',example.scope],['Policy edition',policy.policy],['Template version',policy.schema],['Retrospective',example.retrospective]];
 values(overview,'A5:B12',metadata);
 overview.getRange('B5:B9').format.fill=amber;
 overview.getRange('B12').format.fill=amber;
 overview.getRange('B5:B12').format.wrapText=true;
 overview.getRange('A5:B5').format.rowHeight=32;
 overview.getRange('A8:B9').format.rowHeight=45;
 overview.getRange('B7').setNumberFormat('yyyy-mm-dd');
 overview.getRange('B12').dataValidation={rule:{type:'list',values:['Yes','No']}};
 overview.dataValidations.add({range:'B6',rule:{type:'whole',operator:'between',formula1:2000,formula2:2100}});
 text(assessment,'A2','Requirement assessments');
 assessment.getRange('A2:K2').format.font={name:'Arial',size:16,bold:true,color:navy};
 text(assessment,'A3',policy.attribution);
 text(assessment,'A4',`Source: ${policy.source_url}`);
 assessment.getRange('A3:K4').format.font={name:'Arial',size:10,color:gray};
 values(assessment,'A6:K6',[headers]);
 const rows=example.rows.map(row=>{
  const req=policy.requirements.find(r=>r.id===row.id);
  return [row.id,req.area,req.prompt,/^[0-4]$/.test(row.rating)?Number(row.rating):row.rating,row.evidence,row.owner,row.action,row.due?new Date(row.due+'T00:00:00Z'):null,row.exclusion,null,`wa-csp:${row.id}`];
 });
 values(assessment,`A7:K${end}`,rows);
 const widths={A:15,B:13,C:60,D:16,E:76,F:26,G:56,H:14,I:36,J:10,K:20};
 for(const [col,width] of Object.entries(widths))assessment.getRange(`${col}1:${col}${end}`).format.columnWidth=width;
 assessment.getRange(`A7:K${end}`).format.wrapText=true;
 assessment.getRange(`A7:K${end}`).format.rowHeight=60;
 assessment.getRange(`D7:I${end}`).format.fill=amber;
 assessment.getRange(`H7:H${end}`).setNumberFormat('yyyy-mm-dd');
 assessment.getRange(`D7:D${end}`).dataValidation={rule:{type:'list',values:['0','1','2','3','4','Not assessed','N/A']}};
 for(let n=7;n<=end;n++)formula(assessment,`J${n}`,`=IF(OR(D${n}="",D${n}="Not assessed",D${n}="N/A"),"",IFERROR(VALUE(D${n}),"Invalid rating"))`);
 assessment.getRange(`J7:J${end}`).setNumberFormat('0');
 assessment.getRange(`D7:D${end}`).conditionalFormats.add('cellIs',{operator:'lessThan',formula:2,format:{fill:'#FCE5D5'}});
 assessment.getRange(`D7:D${end}`).conditionalFormats.add('cellIs',{operator:'greaterThanOrEqual',formula:3,format:{fill:'#E2F0E7'}});
 const table=assessment.tables.add(`A6:K${end}`,true,'PolicyAssessment');
 table.showBandedRows=false;
 header(assessment,'A6:K6');
 assessment.freezePanes.freezeRows(6);assessment.freezePanes.freezeColumns(2);
 values(overview,'D5:G5',[['Policy area','Mean (0–4)','Rated','Applicable']]);header(overview,'D5:G5');
 for(let i=0;i<policy.areas.length;i++){
  const r=6+i; text(overview,`D${r}`,policy.areas[i]);
  const count=[0,1,2,3,4].map(n=>`COUNTIFS(Assessment!$B$7:$B$${end},D${r},Assessment!$D$7:$D$${end},${n})`).join('+');
  formula(overview,`F${r}`,`=${count}`);
  formula(overview,`G${r}`,`=COUNTIFS(Assessment!$B$7:$B$${end},D${r})-COUNTIFS(Assessment!$B$7:$B$${end},D${r},Assessment!$D$7:$D$${end},"N/A")`);
  formula(overview,`E${r}`,`=IF(OR(F${r}=0,F${r}<>G${r}),"Not assessed",SUMIFS(Assessment!$J$7:$J$${end},Assessment!$B$7:$B$${end},D${r})/F${r})`);
 }
 text(overview,'D12','Overall');formula(overview,'F12','=SUM(F6:F11)');formula(overview,'G12','=SUM(G6:G11)');
 formula(overview,'E12',`=IF(OR(F12=0,F12<>G12),"Not assessed",SUM(Assessment!J7:J${end})/F12)`);
 overview.getRange('D12:G12').format.font.bold=true;
 overview.getRange('E6:E12').setNumberFormat('0.00');
 text(overview,'A15','WACC rating scale');overview.getRange('A15:B15').format.font.bold=true;
 values(overview,'A16:B22',[[0,'Not started'],[1,'Planned'],[2,'Partly implemented'],[3,'Implemented'],[4,'Tested and reviewed'],['Not assessed','Outstanding assessment work'],['N/A','Excluded with a recorded reason']]);
 text(overview,'D15','Completing this assessment');overview.getRange('D15:G15').format.font.bold=true;
 const instructions=['1. Set department, year, date, assessor and scope.','2. Rate all 86 rows on the Assessment sheet.','3. Record evidence, owners and next actions.','4. Save as XLSX; import on WACC Assessments.','Keep requirement IDs, prompts and headings.','Ratings 3–4 need evidence. N/A needs a reason.','Mark years before 2024 as retrospective.'];
 instructions.forEach((s,i)=>text(overview,`D${16+i}`,s));
 text(overview,'A25','Calculation');overview.getRange('A25:B25').format.font.bold=true;
 ['WACC uses an equal-weight mean of the 0–4 ratings.','A score is shown only when every applicable requirement is rated.','N/A is excluded. Not assessed remains outstanding.','This scale tracks progress; it is not an official WA or Essential Eight level.','The chart in WACC compares the same applicable requirements across years.'].forEach((s,i)=>text(overview,`A${26+i}`,s));
 text(overview,'A32','Approval and reporting');overview.getRange('A32:B32').format.font.bold=true;
 values(overview,'A33:B37',[
  ['Accountable authority',example.authority],['Approval date',example.approval_date?new Date(example.approval_date+'T00:00:00Z'):null],
  ['AIR status',example.air_status],['AIR reference',example.air_reference],['Exemptions reference',example.exemptions]]);
 overview.getRange('B33:B37').format.fill=amber;
 overview.getRange('B33:B37').format.wrapText=true;
 overview.getRange('A33:B37').format.rowHeight=32;
 overview.getRange('B34').setNumberFormat('yyyy-mm-dd');
 overview.getRange('B35').dataValidation={rule:{type:'list',values:['Not requested','Not submitted','Prepared','Approved','Submitted','Retrospective example']}};
 text(overview,'D33','Policy reference: Reporting and Exemptions, p. 22.');
 text(overview,'D35','Record approval references for applicable exclusions.');
 wb.recalculate();
 const actual=overview.getRange('E12').values[0][0];
 const expected=isBlank?'Not assessed':example.rows.reduce((sum,r)=>sum+Number(r.rating),0)/example.rows.length;
 if(typeof expected==='number'?Math.abs(actual-expected)>1e-8:actual!==expected)throw Error(`Overall mismatch: ${actual} vs ${expected}`);
 // Verify dependencies react to a changed, missing and excluded rating, then restore.
 const original=assessment.getRange('D7').values;
 text(assessment,'D7','Not assessed');wb.recalculate();
 if(overview.getRange('E12').values[0][0]!=='Not assessed')throw Error('Missing rating was scored');
 if(!isBlank){text(assessment,'D7','N/A');wb.recalculate();const want=(example.rows.reduce((s,r)=>s+Number(r.rating),0)-Number(example.rows[0].rating))/(example.rows.length-1);if(Math.abs(overview.getRange('E12').values[0][0]-want)>1e-8)throw Error('Exclusion denominator mismatch');}
 assessment.getRange('D7').values=original;wb.recalculate();
 const errors=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!',options:{useRegex:true,maxResults:20}});
 console.log(JSON.stringify({year:isBlank?'template':example.year,mean:actual,errors:errors.ndjson}));
 const name=isBlank?'wa-csp-2024-template':`department-of-silly-walks-${example.year}`;
 for(const [sheetName,range] of [['Overview','A1:H38'],['Assessment','A1:F10']]){
  const image=await wb.render({sheetName,range,scale:1.4,format:'png'});
  await fs.writeFile(path.join(root,`data/review/assessment-build/${name}-${sheetName}.png`),new Uint8Array(await image.arrayBuffer()));
 }
 const output=await SpreadsheetFile.exportXlsx(wb);
 await output.save(path.join(out,name+'.xlsx'));
 await fs.copyFile(path.join(out,name+'.xlsx'),path.join(published,name+'.xlsx'));
}
