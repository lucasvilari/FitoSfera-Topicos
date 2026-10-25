# Conjunto de dados da campanha (AP2)

| Arquivo | O que é | Gerado por |
|---|---|---|
| `mensagens.csv` | bruto: uma linha por pacote BLE recebido | `gravador/gravador.py` |
| `eventos.csv` | conexões, quedas e erros do gravador | `gravador/gravador.py` |
| `mensagens_limpo.csv` | sem repetidas nem linhas fora do contrato, com hora local e marcas de lacuna | `dados/limpar.py` |
| `qualidade.txt` | saída do `qualidade.py` sobre o arquivo final | `gravador/qualidade.py` |

A descrição de cada coluna está em `gravador/README.md` (bruto) e na Seção 5.8 do
relatório (limpo). Toda hora é a de chegada no computador do gravador, porque o nó
não tem relógio.

Arquivo acima de 50 MB vai compactado em `.zip`. Com uma linha a cada 5 min, uma
semana dá cerca de 2.000 linhas, ou menos de 300 kB.
