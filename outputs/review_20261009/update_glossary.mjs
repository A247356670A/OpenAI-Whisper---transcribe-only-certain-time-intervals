import fs from 'node:fs/promises';
import {Workbook} from '@oai/artifact-tool';
const root = new URL('./', import.meta.url);
const baseline = await fs.readFile('Z:/Moives/四月一日/glossary/zenless-zone-zero-ja-zh_expanded-only.tsv','utf8');
const rows=baseline.replace(/^\uFEFF/,'').trimEnd().split(/\r?\n/).map(x=>x.split('\t'));
if(rows.some(x=>x.length!==2)) throw Error('Unexpected glossary columns');
const wb=Workbook.create();
const sheet=wb.worksheets.add('词汇表');
sheet.getRange(`A1:B${rows.length}`).values=rows;
const map=new Map(rows);
if(map.size!==rows.length) throw Error('Duplicate source keys in baseline');
const updates=new Map([
 ['ロビン','知更鸟'],['カフカ','卡芙卡'],['トリヴィア','特里薇娅'],['トリビア','特里薇娅'],
 ['プロメイア','普罗米亚'],['プロメイヤー','普罗米亚'],['プロメイヤ','普罗米亚'],['プロメーア','普罗米亚'],['プロメちゃん','普罗米亚酱'],
 ['クロウ','科洛'],['クロー','科洛'],['クロヲ','科洛'],['クロエダ','黑枝'],['黒枝','黑枝'],
 ['セヴェリアン','塞布里安'],['セメリアン','塞布里安'],['セベリアン','塞布里安'],
 ['ヴェリナ','维琳娜'],['ベリナ','维琳娜'],['ウェリナ','维琳娜'],
 ['聖約','圣约'],['業核','业核'],['コーラ','可乐'],
 ['四月一日ベレト','四月一日'],['渡瀬ベルト','四月一日'],['渡木ベルト','四月一日'],
 ['渡瀬','四月一日'],['ワタヌキ','四月一日'],['ワタネキ','四月一日'],['綿根木','四月一日'],
]);
// Retain earlier locally delivered streamer/Roxy/Claretta terms missing on NAS.
const previous=await fs.readFile(new URL('../glossary_20261004/zenless-zone-zero-ja-zh_expanded-only.tsv',root),'utf8');
for(const line of previous.replace(/^\uFEFF/,'').trimEnd().split(/\r?\n/)) {
 const [ja,zh]=line.split('\t');
 if(!map.has(ja) && /四月一日|洛克茜|克拉蕾/.test(zh)) updates.set(ja,zh);
}
const changes=[];
for(const [ja,zh] of updates) {
 if(map.get(ja)!==zh) { changes.push([ja,map.get(ja)??'（新增）',zh]); map.set(ja,zh); }
}
const output=[...map];
sheet.getRange(`A1:B${output.length}`).values=output;
wb.recalculate();
const verified=sheet.getRange(`A1:B${output.length}`).values;
if(JSON.stringify(verified)!==JSON.stringify(output)) throw Error('Roundtrip mismatch');
const filename='zenless-zone-zero-ja-zh_expanded-only_20261009.tsv';
await fs.writeFile(new URL(filename,root),verified.map(row=>row.join('\t')).join('\n')+'\n','utf8');
const review=wb.worksheets.add('更新核对');
review.getRange(`A1:C${changes.length+1}`).values=[['日语源词','原译','新译'],...changes];
review.getRange(`A1:C${changes.length+1}`).format.columnWidth=28;
review.getRange(`A1:C${changes.length+1}`).format.rowHeight=24;
wb.recalculate();
const preview=await wb.render({sheetName:'更新核对',range:'A1:C12',scale:1,format:'png'});
await fs.writeFile(new URL('glossary_check.png',root),new Uint8Array(await preview.arrayBuffer()));
await fs.writeFile(new URL('词汇表更新说明.md',root),
 '# 词汇表更新\n\n依据 20261009 人工 review 和此前已交付词条。保留无表头、日语与中文两列的 TSV 格式。\n\n'+
 `原有 ${rows.length} 条，更新后 ${output.length} 条，本次新增或修改 ${changes.length} 条。\n\n`+
 '以下易误伤内容仅存入上下文案例，不加入全局映射：合格→业核、制约→圣约、カンか→卡芙卡、オラゴン→洛克茜、ボリミアン→特里薇娅。男性称谓仅在具体字幕修正。\n\n'+
 '维琳娜沿用原词表；普罗米亚按本次批注。新词表未覆盖 NAS 文件，请在软件中选择此更新版。\n\n'+
 changes.map(([ja,b,a])=>`- ${ja}：${b} → ${a}`).join('\n'),'utf8');
console.log(JSON.stringify({before:rows.length,after:output.length,updates:changes.length}));
