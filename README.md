# listagem-fornecedor-atacaderj

Relatório HTML único: produtos por FORNECEDOR com código, nomenclatura,
curva, corredor (ruas do depósito) e estoque mínimo (mediana de janelas
rolantes de 45 dias; ruptura por curva A=10/B=20/C=30 dias sem venda).
Spec: docs/superpowers/specs/2026-07-22-listagem-fornecedor-design.md

## Como gerar (manual — SEM agendamento por enquanto, decisão do dono)

No PC-ponte:

1. `cd C:\Users\User\erp-bridge-atacaderj && git pull && python src\bridge.py --only listagem`
   (gera saida\listagem\*.csv — 4 arquivos)
2. `cd C:\Users\User\listagem-fornecedor-atacaderj && git pull && gerar-listagem.bat`
3. Abrir `saida\listagem-fornecedores.html` no navegador (PC ou celular).

Config: copie `config.example.json` -> `config.local.json`. O caminho
`ruas_estado_json` é o estado do deposito-atacaderj — confira o caminho real
no start do servidor de lá (parâmetro `estado_json`).

ARMADILHA: o visualizador do WhatsApp NÃO executa JavaScript — este HTML é
para abrir no navegador.

## Estado (22/07/2026 — ensaio com dados reais)

- Bridge real no ponte: 10,5s → 4.643 produtos, 233.635 linhas de vendas 180d,
  9.023 entradas c/ fornecedor, 20.099 pares de negociação.
- Relatório gerado no ponte: **4.534 produtos ativos, 437 fornecedores**.
- ⚠️ = possível ruptura (detector de estoque, mesma regra do painel); config precisa de entrada.ruptura_rounds_dir.
- Sanidade automática: óleo Soya 15450 só em COTACAO (corredor A25 TERreo,
  curva A); SEM FORNECEDOR = 77 itens (2%); ordenação por corredor ok;
  marcas: 3.727 normais / 313 `*` / 346 sem venda 6m / 148 novos;
  2.115 itens com corredor marcado no app do depósito.
- Publicação p/ celular: copiar o HTML para a pasta do painel (servida na
  8477): `copy /Y saida\listagem-fornecedores.html C:\Users\User\erp-bridge-atacaderj\saida\painel\`
  → http://100.99.176.6:8477/listagem-fornecedores.html (Tailscale)
  ou http://192.168.0.164:8477/... (Wi-Fi da loja).
- Repo chegou ao ponte por scp (C:\Users\User\listagem-fornecedor-atacaderj);
  criar remote no GitHub ainda é decisão pendente do dono.
- PENDENTE (dono): conferência de barriga dos estoques mínimos (ex.: 15450
  deu 369 cx/45d — validar), posição do "A24 vitrine" (ordena depois do A25
  por ser rua interna 26) e aí decidir sobre agendar. Antes de AGENDAR:
  revisitar listagem_dir relativo (bridge) e rotação do saida\gerar.log.
