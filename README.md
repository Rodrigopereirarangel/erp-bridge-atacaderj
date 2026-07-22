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
