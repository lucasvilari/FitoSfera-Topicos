ESP32 conectada de A a I na configuração mais à esquerda (dado que o USB está para fora e o trilho azul está para baixo) com um slot inferior (linha J) sobrando.
3v3 de porta 3v3 a Z6 (fio vermelho)
Aterramento feito de porta GND a K1 (fio azul)

DHT11 em J45:
    - Da esquerda para a direita, de frente para a grade: DO vai de F até porta D18 (fio amarelo), VCC vai de F até trilho vermelho (fio cinza), GND vai de F até trilho azul (fio roxo). 

Barramento I2C do BH1750:
    - SDA: porta D21
    - SCL: porta D22

BH1750 (módulo GY-302, 5 pinos) em J55-59, no lugar do antigo FTR:
    - Confira os nomes na serigrafia da placa; a ordem usual, de frente para o sensor, ADDR, SDA, SCL, GND, VCC.
    - VCC vai de F até trilho vermelho (fio preto).
    - GND vai de F até trilho azul (fio marrom).
    - SCL vai de F até porta D22. (fio branco).
    - SDA vai de F até porta D21 (fio verde).
    - ADDR fica sem ligação (endereço 0x23).

Retirados do circuito anterior: os três LEDs, os três resistores de 220 Ω, o fio laranja de aterramento dos LEDs e o módulo FTR (fio verde de D19).

Todos os fios do projeto são macho-macho.

Verificação: ao ligar, o monitor serial lista os endereços I2C encontrados ("# I2C: 0x23"). Se o 0x23 não aparecer, revise SDA, SCL e alimentação do módulo.
