import { test } from "node:test";
import assert from "node:assert";
import { adquirirLock, soltarLock } from "./sessao-lock.mjs";
import { mkdtempSync, writeFileSync, existsSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

test("adquirirLock: livre -> adquire, grava o proprio PID; soltarLock remove", async () => {
  const arq = join(mkdtempSync(join(tmpdir(), "lk-")), ".sessao.lock");
  assert.strictEqual(await adquirirLock(arq), true);
  assert.strictEqual(readFileSync(arq, "utf8"), String(process.pid));
  soltarLock(arq);
  assert.strictEqual(existsSync(arq), false);
});

test("adquirirLock: ocupado por PID vivo -> false (esperarMs=0 nao espera)", async () => {
  const arq = join(mkdtempSync(join(tmpdir(), "lk-")), ".sessao.lock");
  writeFileSync(arq, String(process.pid)); // o proprio processo do teste esta vivo
  assert.strictEqual(await adquirirLock(arq), false);
  assert.strictEqual(readFileSync(arq, "utf8"), String(process.pid)); // lock intacto
});

test("adquirirLock: PID morto (stale) -> assume o lock", async () => {
  const arq = join(mkdtempSync(join(tmpdir(), "lk-")), ".sessao.lock");
  writeFileSync(arq, "999999999"); // PID inexistente
  assert.strictEqual(await adquirirLock(arq), true);
  assert.strictEqual(readFileSync(arq, "utf8"), String(process.pid));
});
