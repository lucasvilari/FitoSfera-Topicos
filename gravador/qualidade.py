"""Relatório de qualidade de um arquivo do gravador do FitoSfera.

    python gravador/qualidade.py dados/mensagens.csv --eventos dados/eventos.csv

As leituras esperadas saem de uma conta (duração / período), não do arquivo.
Por padrão a duração vai da primeira à última leitura; use --inicio e --fim
(hora local de Teresina, "AAAA-MM-DD HH:MM") para a duração declarada da
campanha.

Como o pacote BLE não traz hora (o nó não tem relógio), toda hora aqui é a de
chegada no gravador. O que o pacote traz é a sequência (uint8, volta a 0 depois
de 255) e o id do reinício, e é deles que saem perdas, duplicatas e reinícios:

- duplicata: o mesmo pacote (mesmos 19 bytes) gravado duas vezes;
- reinício: o id do reinício mudou; a sequência e o acumulado recomeçam;
- perdida: dentro do mesmo reinício, a sequência pulou. O nó mediu, mas
  ninguém recebeu (o firmware incrementa a sequência mesmo sem celular).
  Como a sequência dá a volta em 256, o salto é corrigido pelo tempo decorrido;
- extra: leitura que chegou a menos de meio período da anterior, disparada
  pela assinatura da notificação (reconexão) ou pelo comando 0x01.
"""

import argparse
import csv
import statistics
import sys
from collections import Counter, OrderedDict
from datetime import datetime, timedelta, timezone

import protocolo

FUSO_LOCAL = timezone(timedelta(hours=-3))  # Teresina, sem horário de verão
FAIXA_TEMP = (0.0, 50.0)     # DHT11, folha de dados
FAIXA_UMID = (20.0, 90.0)    # DHT11, folha de dados
FAIXA_LUX = (0, 121557)      # BH1750 com MTreg = 31
FATOR_DLI = 0.0185           # µmol/m²/s por lux, luz solar (README)


def hora_local(ts):
    return datetime.fromtimestamp(ts, FUSO_LOCAL)


def fmt_hora(ts):
    return hora_local(ts).strftime("%d/%m %H:%M:%S")


def fmt_duracao(segundos):
    segundos = int(round(segundos))
    h, resto = divmod(segundos, 3600)
    m, s = divmod(resto, 60)
    return f"{h}h{m:02d}min{s:02d}s" if h else f"{m}min{s:02d}s"


def ler_hora(texto):
    try:
        return float(texto)
    except ValueError:
        return datetime.strptime(texto, "%Y-%m-%d %H:%M").replace(tzinfo=FUSO_LOCAL).timestamp()


def numero(texto, tipo=float):
    return None if texto in ("", None) else tipo(texto)


def ler_mensagens(caminho):
    """Devolve (leituras no contrato, ordenadas por chegada; linhas fora do contrato)."""
    validas, fora = [], []
    with open(caminho, newline="", encoding="utf-8") as arquivo:
        for linha in csv.DictReader(arquivo):
            if linha.get("tamanho") != str(protocolo.TAMANHO_PACOTE) or linha.get("seq") in ("", None):
                fora.append(linha)
                continue
            validas.append({
                "ts": float(linha["ts_recebido"]),
                "bytes_hex": linha["bytes_hex"],
                "seq": int(linha["seq"]),
                "boot": int(linha["id_reinicio"]),
                "acum": int(linha["lux_min_acum"]),
                "sem_sucesso": int(linha["seg_sem_sucesso"]),
                "temp_c": numero(linha["temp_c"]),
                "umid_pct": numero(linha["umid_pct"]),
                "lux": numero(linha["lux"], int),
            })
    validas.sort(key=lambda r: r["ts"])
    return validas, fora


def ler_eventos(caminho):
    if not caminho:
        return []
    with open(caminho, newline="", encoding="utf-8") as arquivo:
        return [{"ts": float(e["ts"]), "evento": e["evento"], "detalhe": e["detalhe"]}
                for e in csv.DictReader(arquivo)]


def analisar(validas, periodo):
    """Marca cada leitura única com o que se sabe dela e devolve (únicas, duplicatas)."""
    vistos = set()
    unicas, duplicatas = [], 0
    for r in validas:
        if r["bytes_hex"] in vistos:
            duplicatas += 1
            continue
        vistos.add(r["bytes_hex"])
        unicas.append(r)

    anterior = None
    for r in unicas:
        r.update(reinicio=False, perdidas_antes=0, extra=False, intervalo=None, luz_nova=None)
        # Antes da primeira leitura não se sabe nada: o gravador pode ter começado com o nó já ligado
        if anterior is not None:
            r["intervalo"] = r["ts"] - anterior["ts"]
            if r["boot"] != anterior["boot"]:
                r["reinicio"] = True
                # Depois de ligar, a sequência começa em 1: o que veio antes disso no novo boot se perdeu
                r["perdidas_antes"] = max(r["seq"] - 1, 0)
                r["luz_nova"] = r["acum"]
            else:
                salto = (r["seq"] - anterior["seq"]) % 256
                voltas = max(0, round((r["intervalo"] / periodo - salto) / 256))
                r["perdidas_antes"] = max(salto + 256 * voltas - 1, 0)
                r["extra"] = r["intervalo"] < periodo / 2
                r["luz_nova"] = (r["acum"] - anterior["acum"]) % 2**32
        anterior = r
    return unicas, duplicatas


def lacunas(unicas, eventos, periodo):
    encontradas = []
    for antes, depois in zip(unicas, unicas[1:]):
        dt = depois["ts"] - antes["ts"]
        if dt <= 1.5 * periodo:
            continue
        no_meio = Counter(e["evento"] for e in eventos if antes["ts"] <= e["ts"] <= depois["ts"])
        if depois["reinicio"]:
            causa = "o no reiniciou (id do reinicio mudou)"
        elif depois["perdidas_antes"] > 0:
            causa = f"o no mediu {depois['perdidas_antes']} vez(es) sem entregar"
        else:
            causa = "o no nao mediu nem reiniciou (travou com o radio de pe?)"
        if no_meio["fim_gravador"] or no_meio["inicio_gravador"]:
            causa += "; gravador parado"
        elif no_meio["desconectado"]:
            causa += f"; {no_meio['desconectado']} desconexao(oes)"
        encontradas.append({
            "inicio": antes["ts"], "fim": depois["ts"], "duracao": dt,
            "perdidas": max(round(dt / periodo) - 1, 0), "causa": causa,
        })
    return encontradas


def tempos_de_conexao(eventos, unicas):
    """Tempos do enlace medidos pelo relógio do gravador, e o RSSI de cada vez que o nó foi achado."""
    tempos = {"conectar": [], "primeiro": [], "reconectar": [], "rssi": []}
    chegadas = [r["ts"] for r in unicas]
    encontrado = desconectado = None
    for e in eventos:
        if e["evento"] == "encontrado":
            encontrado = e["ts"]
            if "rssi=" in e["detalhe"]:
                try:
                    tempos["rssi"].append(int(e["detalhe"].split("rssi=")[1].split()[0]))
                except ValueError:
                    pass
        elif e["evento"] == "conectado":
            if encontrado is not None:
                tempos["conectar"].append(e["ts"] - encontrado)
            if desconectado is not None:
                tempos["reconectar"].append(e["ts"] - desconectado)
            depois = [t for t in chegadas if t >= e["ts"]]
            if depois and depois[0] - e["ts"] < protocolo.PERIODO_S:
                tempos["primeiro"].append(depois[0] - e["ts"])
            encontrado = desconectado = None
        elif e["evento"] == "desconectado":
            desconectado = e["ts"]
        elif e["evento"] == "inicio_gravador":
            encontrado = desconectado = None
    return tempos


def mediana_max(valores):
    return (statistics.median(valores), max(valores)) if valores else (None, None)


def faixa(valores):
    valores = [v for v in valores if v is not None]
    return (min(valores), max(valores)) if valores else (None, None)


def relatorio(caminho, caminho_eventos, periodo, inicio=None, fim=None, saida=sys.stdout):
    validas, fora = ler_mensagens(caminho)
    eventos = ler_eventos(caminho_eventos)
    p = lambda *a: print(*a, file=saida)

    p(f"# qualidade.py sobre {caminho}" + (f" (eventos: {caminho_eventos})" if caminho_eventos else ""))
    if not validas:
        p("nenhuma leitura no contrato; nada a analisar")
        return
    unicas, duplicatas = analisar(validas, periodo)

    t0 = inicio if inicio is not None else unicas[0]["ts"]
    t1 = fim if fim is not None else unicas[-1]["ts"]
    duracao = t1 - t0
    esperadas = int(duracao // periodo) + 1
    no_intervalo = [r for r in unicas if t0 <= r["ts"] <= t1]
    janelas = {int((r["ts"] - t0) // periodo) for r in no_intervalo}
    janelas = {j for j in janelas if 0 <= j < esperadas}
    extras = sum(r["extra"] for r in unicas)
    reinicios = [r for r in unicas if r["reinicio"]]
    perdidas_seq = sum(r["perdidas_antes"] for r in unicas)

    p("\n## Campanha")
    p(f"inicio                      {fmt_hora(t0)} (hora de Teresina)")
    p(f"fim                         {fmt_hora(t1)}")
    p(f"duracao                     {fmt_duracao(duracao)} ({duracao / 3600:.2f} h)")
    p(f"periodo nominal             {periodo} s")
    p(f"leituras esperadas          {esperadas}  (duracao / periodo, +1)")

    p("\n## Contagens")
    p(f"linhas no arquivo           {len(validas) + len(fora)}")
    p(f"fora do contrato            {len(fora)}  (tamanho diferente de {protocolo.TAMANHO_PACOTE} bytes)")
    p(f"repetidas (descartadas)     {duplicatas}")
    p(f"leituras unicas             {len(unicas)}")
    p(f"  extras (fora do ciclo)    {extras}  (assinatura ao reconectar ou comando 0x01)")
    p(f"  {'no ciclo de ' + str(periodo) + ' s':<26}{len(unicas) - extras}")
    p(f"faltam (a sequencia pulou)  {perdidas_seq}  (o no mediu, ninguem recebeu)")
    p(f"reinicios do no             {len(reinicios)}")
    for r in reinicios:
        p(f"  {fmt_hora(r['ts'])}  novo id {r['boot']:04x}, primeira seq recebida {r['seq']}")
    p(f"leituras sem hora do no     {len(unicas)} de {len(unicas)}  (o no nao tem relogio; hora = chegada no gravador)")

    p("\n## Completude")
    p(f"janelas de {periodo} s c/ leitura {len(janelas)} de {esperadas}  -> {100 * len(janelas) / esperadas:.1f} %")
    p(f"unicas no ciclo / esperadas {len(unicas) - extras} de {esperadas}  -> {100 * (len(unicas) - extras) / esperadas:.1f} %")

    intervalos = [r["intervalo"] for r in unicas if r["intervalo"] is not None and not r["extra"]]
    sem_sucesso = [r["sem_sucesso"] for r in unicas]
    p("\n## Tempo")
    if intervalos:
        p(f"intervalo entre leituras    mediana {statistics.median(intervalos):.1f} s; "
          f"min {min(intervalos):.1f} s; max {max(intervalos):.1f} s")
    med, mx = mediana_max(sem_sucesso)
    p(f"seg. sem confirmacao        mediana {med:.0f} s; max {mx} s  (no pacote; ~{periodo} s = confirmacao anterior chegou)")
    atrasadas = sum(1 for v in sem_sucesso if v > periodo + 60)
    p(f"  {'acima de ' + str(periodo + 60) + ' s':<26}{atrasadas}  (a confirmacao anterior nao chegou ao no)")

    p("\n## Sensores")
    for campo, nome, (lo, hi) in (("temp_c", "temperatura (C)", FAIXA_TEMP),
                                  ("umid_pct", "umidade (%)", FAIXA_UMID),
                                  ("lux", "luz (lux)", FAIXA_LUX)):
        valores = [r[campo] for r in unicas]
        ausentes = sum(v is None for v in valores)
        fora_faixa = sum(1 for v in valores if v is not None and not lo <= v <= hi)
        a, b = faixa(valores)
        observada = f"{a} a {b}" if a is not None else "sem leituras"
        p(f"{nome:<18} ausentes {ausentes:>4}; fora de {lo}..{hi}: {fora_faixa:>3}; observada {observada}")

    achadas = lacunas(unicas, eventos, periodo)
    p(f"\n## Lacunas (intervalo > {1.5 * periodo:.0f} s): {len(achadas)}")
    for l in achadas:
        p(f"{fmt_hora(l['inicio'])} -> {fmt_hora(l['fim'])}  {fmt_duracao(l['duracao']):>12}  "
          f"~{l['perdidas']} leituras  {l['causa']}")
    p(f"tempo total em lacunas      {fmt_duracao(sum(l['duracao'] for l in achadas))}")

    p("\n## Luz integrada por dia (diferenca do acumulado, dia da chegada)")
    por_dia = OrderedDict()
    for r in unicas:
        dia = hora_local(r["ts"]).date()
        luz, n = por_dia.get(dia, (0, 0))
        por_dia[dia] = (luz + (r["luz_nova"] or 0), n + 1)
    for dia, (luz, n) in por_dia.items():
        dli = luz * 60 * FATOR_DLI / 1e6
        p(f"{dia:%d/%m}  {luz:>10} lux.min  ~{dli:6.2f} mol/m2/dia  ({n} leituras de {86400 // periodo} num dia)")

    if eventos:
        p("\n## Enlace BLE (do arquivo de eventos)")
        tempos = tempos_de_conexao(eventos, unicas)
        for chave, nome in (("conectar", "encontrado -> conectado"),
                            ("primeiro", "conectado -> 1o pacote"),
                            ("reconectar", "desconectado -> conectado")):
            v = tempos[chave]
            if v:
                p(f"{nome:<28}mediana {statistics.median(v):.1f} s; max {max(v):.1f} s; n = {len(v)}")
        if tempos["rssi"]:
            r = tempos["rssi"]
            p(f"{'RSSI ao encontrar':<28}mediana {statistics.median(r):.0f} dBm; "
              f"pior {min(r)} dBm; melhor {max(r)} dBm; n = {len(r)}")

        p("\n## Eventos do gravador")
        for nome, n in Counter(e["evento"] for e in eventos).most_common():
            p(f"{nome:<22} {n}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mensagens", help="CSV gravado pelo gravador.py")
    parser.add_argument("--eventos", help="CSV de eventos do gravador, para explicar as lacunas")
    parser.add_argument("--periodo", type=int, default=protocolo.PERIODO_S, help="período nominal em segundos")
    parser.add_argument("--inicio", help="início declarado da campanha (AAAA-MM-DD HH:MM, hora local)")
    parser.add_argument("--fim", help="fim declarado da campanha (AAAA-MM-DD HH:MM, hora local)")
    args = parser.parse_args()
    relatorio(args.mensagens, args.eventos, args.periodo,
              ler_hora(args.inicio) if args.inicio else None,
              ler_hora(args.fim) if args.fim else None)


if __name__ == "__main__":
    main()
