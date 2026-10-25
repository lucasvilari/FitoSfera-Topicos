"""Série temporal da campanha, com as lacunas à vista.

    python dados/grafico.py dados/mensagens_limpo.csv docs/figuras/serie-campanha.pdf

Três painéis (temperatura, umidade, luz) com o mesmo eixo de tempo. A linha
é interrompida em toda lacuna maior que 1,5 período: nada é interpolado. As
faixas cinzas marcam as lacunas e as linhas verticais tracejadas, os
reinícios do nó. Precisa de matplotlib.
"""

import argparse
import csv
from datetime import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402


def ler(caminho):
    with open(caminho, newline="", encoding="utf-8") as arquivo:
        return list(csv.DictReader(arquivo))


def serie(linhas, campo):
    """Pontos (hora, valor), com None nas lacunas e nas leituras ausentes, para o traço quebrar."""
    x, y = [], []
    for l in linhas:
        hora = datetime.strptime(l["hora_local"], "%Y-%m-%d %H:%M:%S")
        if l["lacuna_antes_s"]:
            x.append(hora)
            y.append(None)
        x.append(hora)
        y.append(float(l[campo]) if l[campo] else None)
    return x, [float("nan") if v is None else v for v in y]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("limpo")
    parser.add_argument("saida")
    args = parser.parse_args()
    linhas = ler(args.limpo)

    paineis = [("temp_c", "Temperatura (°C)"), ("umid_pct", "Umidade relativa (%)"), ("lux", "Luz (lux)")]
    fig, eixos = plt.subplots(len(paineis), 1, sharex=True, figsize=(8, 6.5))
    horas = [datetime.strptime(l["hora_local"], "%Y-%m-%d %H:%M:%S") for l in linhas]
    for eixo, (campo, rotulo) in zip(eixos, paineis):
        x, y = serie(linhas, campo)
        eixo.plot(x, y, lw=0.9, color="#1f5f8b")
        eixo.set_ylabel(rotulo)
        eixo.grid(alpha=0.3)
        for i, l in enumerate(linhas):
            if l["lacuna_antes_s"] and i > 0:
                eixo.axvspan(horas[i - 1], horas[i], color="0.85", lw=0)
            if l["reinicio"] == "1":
                eixo.axvline(horas[i], color="#b03a2e", ls="--", lw=0.8)
    eixos[-1].set_xlabel("Hora local (Teresina, UTC−3)")
    eixos[-1].xaxis.set_major_formatter(mdates.DateFormatter("%d/%m\n%H:%M"))
    fig.tight_layout()
    fig.savefig(args.saida)
    print(f"figura em {args.saida}")


if __name__ == "__main__":
    main()
