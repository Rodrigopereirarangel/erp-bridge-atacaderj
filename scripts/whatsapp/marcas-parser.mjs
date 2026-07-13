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

// O WhatsApp as vezes entrega o remoteJid brasileiro SEM o 9o digito
// (5521970117082 -> 552170117082). Comparar o numero inteiro descartaria o
// feedback silenciosamente; por isso o match usa so os ULTIMOS 8 digitos de
// cada remetente configurado (a parte do numero que nunca muda).
export function remetentePermitido(jidDigits, remetentes) {
  const lista = (remetentes || []).map((n) => String(n).replace(/\D/g, "")).filter(Boolean);
  if (!lista.length) return true; // sem allowlist -> aceita qualquer remetente
  const de = String(jidDigits || "").replace(/\D/g, "");
  return lista.some((r) => de.includes(r.slice(-8)));
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
