#!/usr/bin/env node
// Replay retroativo do detector de ruptura (spec §13 do painel).
// Uso: node scripts/replay_ruptura.js <dirDetector> <ref1,ref2,...>
// Corta vendas/entradas do data/input em cada refDate (nada "do futuro" vaza
// para o passado), roda o motor real (detectAll) e conta o corte do painel —
// prob > 0.75, parado > 1 dia, guardrail entrega <=30d com cobertura sobrando.
// MESMA regra de Q.ruptura.corte (template) e corte_ruptura (historico_painel.py)
// — manter os tres em sincronia.
// Limitacoes honestas: replays mais antigos tem menos historico de vendas atras
// de si (janela do ERP ~120d), entao os primeiros pontos sao menos firmes; o
// refDate e a propria segunda-feira; pedidos/curva ficam vazios (o corte nao os usa).
const fs = require("node:fs");
const path = require("node:path");

const det = process.argv[2];
const datas = (process.argv[3] || "").split(",").filter(Boolean);
if (!det || datas.length === 0) {
  console.error("uso: node replay_ruptura.js <dirDetector> <ref1,ref2,...>");
  process.exit(2);
}
const req = (p) => require(path.join(det, p));
const { importSales } = req("src/core/import/sales.js");
const { importAbc } = req("src/core/import/abc.js");
const { detectAll } = req("src/core/detect/detectAll.js");
const cfgArq = ["config.local.json", "config.example.json"]
  .map((a) => path.join(det, a)).find((a) => fs.existsSync(a));
const cfg = JSON.parse(fs.readFileSync(cfgArq, "utf8"));
// modelo treinado (ml/): o replay usa a MESMA regua da rodada ao vivo
const modeloArq = path.join(det, "data", "modelo.json");
if (fs.existsSync(modeloArq)) {
  try { cfg.modelo = JSON.parse(fs.readFileSync(modeloArq, "utf8")); }
  catch (e) { /* corrompido: replay segue com a formula */ }
}

const inputDir = path.join(det, "data", "input");
const vendasLinhas = fs.readFileSync(path.join(inputDir, "vendas.csv"), "utf8")
  .split(/\r?\n/);
const vendasCab = vendasLinhas[0];
const iData = vendasCab.split(";").indexOf("data");
const entradas = fs.readFileSync(path.join(inputDir, "entradas.csv"), "utf8")
  .split(/\r?\n/).slice(1).map((l) => l.split(";"))
  .filter((c) => c.length >= 3 && c[0] && c[1]);
// curva ABC ATUAL aplicada ao passado (nao ha curva historica) — aproximacao
// documentada; o grafico do painel usa so A+B (dono, 21/07)
const abc = importAbc(fs.readFileSync(path.join(inputDir, "curva_abc.csv"), "utf8"));

const saida = {};
for (const ref of datas) {
  const vendasCsv = [vendasCab]
    .concat(vendasLinhas.slice(1).filter((l) => {
      const c = l.split(";");
      return c.length > iData && c[iData] && c[iData] <= ref;
    })).join("\n");
  const receipts = new Map(); // ultima entrega ATE o refDate, por item
  for (const [cod, data, qtd] of entradas) {
    if (data > ref) continue;
    const prev = receipts.get(cod);
    if (!prev || data > prev.date) receipts.set(cod, { date: data, qty: Number(qtd) || 0 });
  }
  const itens = detectAll(importSales(vendasCsv), receipts, new Map(), abc, ref, cfg);
  const cont = { a: 0, b: 0 };
  for (const i of itens) {
    if ((i.probabilidade || 0) <= 0.75) continue;
    if ((i.diasParado || 0) <= 1) continue;
    const r = i.receipt;
    if (r && r.date) {
      const dias = Math.round(
        (Date.parse(ref) - Date.parse(String(r.date).slice(0, 10))) / 86400000);
      if (dias <= 30 && (i.coverageRemaining || 0) > 0) continue;
    }
    if (i.curvaABC === "A") cont.a++;
    else if (i.curvaABC === "B") cont.b++;
  }
  saida[ref] = cont;
}
process.stdout.write(JSON.stringify(saida));
