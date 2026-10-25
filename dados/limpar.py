"""Gera o arquivo limpo da campanha a partir do bruto do gravador.

    python dados/limpar.py dados/mensagens.csv dados/mensagens_limpo.csv

O que muda do bruto para o limpo (nada é interpolado):
- saem as linhas fora do contrato e os pacotes repetidos;
- as linhas ficam em ordem de chegada;
- entra a hora local de Teresina e as marcas que o qualidade.py calcula
  (reinício, leituras perdidas antes, leitura extra, lacuna antes);
- entra a luz nova desde a leitura anterior (diferença do acumulado, com a
  volta de 32 bits), que é o que se soma para a luz do dia.
"""

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gravador"))

import protocolo  # noqa: E402
import qualidade  # noqa: E402

COLUNAS = [
    "ts", "hora_local", "id_reinicio", "seq", "temp_c", "umid_pct", "lux",
    "lux_min_acum", "luz_nova_lux_min", "seg_sem_sucesso",
    "reinicio", "perdidas_antes", "extra", "lacuna_antes_s",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("bruto")
    parser.add_argument("limpo")
    parser.add_argument("--periodo", type=int, default=protocolo.PERIODO_S)
    args = parser.parse_args()

    validas, fora = qualidade.ler_mensagens(args.bruto)
    unicas, duplicatas = qualidade.analisar(validas, args.periodo)

    vazio = lambda v: "" if v is None else v
    with open(args.limpo, "w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS)
        escritor.writeheader()
        for r in unicas:
            lacuna = r["intervalo"] if r["intervalo"] and r["intervalo"] > 1.5 * args.periodo else None
            escritor.writerow({
                "ts": f"{r['ts']:.3f}",
                "hora_local": qualidade.hora_local(r["ts"]).strftime("%Y-%m-%d %H:%M:%S"),
                "id_reinicio": f"{r['boot']:04x}",
                "seq": r["seq"],
                "temp_c": vazio(r["temp_c"]),
                "umid_pct": vazio(r["umid_pct"]),
                "lux": vazio(r["lux"]),
                "lux_min_acum": r["acum"],
                "luz_nova_lux_min": vazio(r["luz_nova"]),
                "seg_sem_sucesso": r["sem_sucesso"],
                "reinicio": int(r["reinicio"]),
                "perdidas_antes": r["perdidas_antes"],
                "extra": int(r["extra"]),
                "lacuna_antes_s": "" if lacuna is None else round(lacuna),
            })
    print(f"{len(unicas)} leituras em {args.limpo}; descartadas {duplicatas} repetidas "
          f"e {len(fora)} fora do contrato")


if __name__ == "__main__":
    main()
