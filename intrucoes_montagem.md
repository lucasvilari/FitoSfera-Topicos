ESP32 conectada de A a I na configuração mais à esquerda (dado que o USB está para fora e o trilho azul está para baixo) com um slot inferior (linha J) sobrando.
3v3 de porta 3v3 a Z6 (fio vermelho)
Aterramento feito de porta GND a K1 (fio azul)
DHT11 em J45:
    - Da esquerda para a direita, de frente para a grade: DO vai de G até porta D18 (fio amarelo), VCC vai de G até trilho vermelho (fio cinza), GND vai de G até trilho azul (fio roxo). 
FTR em J55-60:
    - Da esquerda para a direita, de frente para o sensor: DO vai de G até porta D19 (fio verde), GND vai de G até trilho azul (fio marrom), VCC vai de G até trilho vermelho (fio preto).
Aterramento (fio laranja) até coluna J25-30, das pernas menores (cátodo) dos LEDs.
LED vermelho: perna longa (ânodo) afasta três slots para a esquerda
    - Resistor de porta D21 até coluna dessa perna longa
LED amarelo: perna longa afasta dois slots para a equerda
    - Resistor de porta D22 até coluna dessa perna longa
LED verde: perna longa afasta um slot para a esquerda
    - Resistor de porta D23 até coluna dessa perna longa

Sobra fio branco; todos os fios do projeto são macho-macho.