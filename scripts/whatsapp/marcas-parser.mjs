// Parser puro das mensagens de marcacao do operador (testavel sem rede).
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const TOKENS = { A: "falso", RA: "reabastecimento", RC: "compra" };

export function parseMarcas(texto) {
  const m = /^MARCAS (\d{4}-\d{2}-\d{2}):\s*(.+)$/s.exec(String(texto || "").trim());
  if (!m) return null;
  const marcas = {};
  for (const par of m[2].trim().split(/\s+/)) {
    const p = /^(\w+)=(A|RA|RC)$/.exec(par);
    if (p) marcas[p[1]] = TOKENS[p[2]];
  }
  return Object.keys(marcas).length ? { roundId: m[1], marcas } : null;
}

export function mesclarFeedback(dir, roundId, marcas, agoraIso) {
  mkdirSync(dir, { recursive: true });
  const arq = join(dir, `${roundId}.json`);
  const atual = existsSync(arq) ? JSON.parse(readFileSync(arq, "utf8")) : {};
  for (const [cod, opcao] of Object.entries(marcas)) {
    atual[cod] = { opcao, origem: "whatsapp", em: agoraIso };
  }
  writeFileSync(arq, JSON.stringify(atual, null, 2));
  return atual;
}
