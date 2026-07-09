# Robô de upload — cotação no claude.ai

Sobe o `catalogo_bridge.json` (gerado pelo bridge) no artifact da cotação,
pelo botão "📦 Catálogo" do próprio app. Determinístico (Playwright), sem IA.
O arquivo único carrega **catálogo + histórico de pedidos de venda** — um
upload alimenta a cotação E a aba 🔍 Auditoria de todos os usuários do
artifact (storage compartilhado). O app ainda faz a parte dele: quem já está
com a aba aberta detecta a versão nova sozinho em até 3min (polling) e o
upload manual fica travado enquanto o robô estiver saudável (< 5h).

## Estado (2026-07-09)

- ✅ Código pronto e **testado de ponta a ponta contra o HTML publicável
  local** com o arquivo real (4.606 produtos + 285 pedidos): upload, badge,
  auditoria por dia e trava anti-sobrescrita — tudo verificado.
- ✅ Tarefa agendada registrada: "AtacadeRJ - Robo Upload Cotacao"
  (08:05/12:05/15:05/16:05/18:05 — ~5min após cada rodada do bridge).
- ⏳ Falta SÓ (depois de publicar o artifact):
  1. colar o link em `robo/config_robo.json` → `artifact_url`
  2. `python robo/upload_catalogo.py --setup` → logar na conta Claude dona
     do artifact → fechar o navegador
  3. rodada assistida: `python robo/upload_catalogo.py` (assistir a primeira;
     se o claude.ai mudar o layout, o erro sai no log com a lista de frames)

## Comandos

```
python robo/upload_catalogo.py --teste     # fluxo completo no HTML local (sem claude.ai)
python robo/upload_catalogo.py --teste --headed   # idem, mostrando o navegador
python robo/upload_catalogo.py --setup     # login único no claude.ai (salva o perfil)
python robo/upload_catalogo.py             # rodada normal (a agendada)
```

## Operação

- A tarefa roda "somente quando o usuário estiver conectado" (o robô abre um
  Chrome visível). O PC-ponte fica logado 24h.
- Falha → exit 1 + `robo/robo_upload.log` + `robo/ultima_falha.png`. O app
  acusa banco velho na tela (trava de data) e **destrava o upload manual
  sozinho após 5h sem robô** — plano B: subir o arquivo pelo botão 📦 (30s).
- `robo/backups/` guarda o snapshot da biblioteca (apelidos/buscas) que o app
  exporta a cada substituição de catálogo.
- Se o `config_robo.json` ainda tiver o link placeholder, o robô sai com
  mensagem clara e não faz nada (as rodadas agendadas ficam inofensivas até
  o artifact existir).
- Segurança: `config_robo.json`, `perfil_navegador/` (sessão logada =
  credencial), logs e backups são gitignored.
