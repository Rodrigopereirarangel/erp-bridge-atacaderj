import { test } from "node:test";
import assert from "node:assert";
import { parseMarcas, mesclarFeedback, remetentePermitido } from "./marcas-parser.mjs";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

test("parseMarcas: mensagem valida com os 3 tokens", () => {
  const r = parseMarcas("MARCAS 2026-07-14: 36011=RA 14576=A 319=RC");
  assert.strictEqual(r.roundId, "2026-07-14");
  assert.deepStrictEqual(r.marcas, { "36011": "reabastecimento", "14576": "falso", "319": "compra" });
});

test("parseMarcas: token invalido e pulado; sem par valido -> null; texto qualquer -> null", () => {
  assert.deepStrictEqual(parseMarcas("MARCAS 2026-07-14: 1=XX 2=A").marcas, { "2": "falso" });
  assert.strictEqual(parseMarcas("MARCAS 2026-07-14: 1=XX"), null);
  assert.strictEqual(parseMarcas("bom dia"), null);
});

test("remetentePermitido: tolera JID brasileiro sem o 9o digito; estranho -> false", () => {
  const lista = ["5521970117082"];
  assert.strictEqual(remetentePermitido("5521970117082", lista), true); // com 9o digito
  assert.strictEqual(remetentePermitido("552170117082", lista), true); // sem 9o digito (quirk do WhatsApp)
  assert.strictEqual(remetentePermitido("5511999998888", lista), false); // numero estranho
});

test("mesclarFeedback: cria, mescla e ultima marcacao vence", () => {
  const dir = mkdtempSync(join(tmpdir(), "fb-"));
  mesclarFeedback(dir, "2026-07-14", { "1": "falso" }, "2026-07-14T10:00:00Z");
  mesclarFeedback(dir, "2026-07-14", { "1": "compra", "2": "reabastecimento" }, "2026-07-14T11:00:00Z");
  const j = JSON.parse(readFileSync(join(dir, "2026-07-14.json"), "utf8"));
  assert.strictEqual(j["1"].opcao, "compra");
  assert.strictEqual(j["1"].origem, "whatsapp");
  assert.strictEqual(j["2"].opcao, "reabastecimento");
});
