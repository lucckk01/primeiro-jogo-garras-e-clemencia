# =========================================================
# GARRAS E CLEMÊNCIA - RPG de aventura
# =========================================================
# Arquivo em UTF-8. Correções desta versão:
#  - Textos com acento corrigidos (antes apareciam como "BÃRBARO" etc.)
#  - Paredes de pedra só são desenhadas quando estão na tela
#  - Grama com tile 128x128 (16x menos blits por frame)
#  - Músicas pré-geradas em segundo plano (sem travada ao iniciar batalha)
#  - Áudio correto também quando o SDL abre o mixer em estéreo
#  - Usar item sem efeito não gasta mais o turno
#  - Hitbox do coração menor (colisões mais justas)
#  - Anéis desenham só o que cai dentro da arena
#  - solidos() agora usa cache; editor não grava o JSON a cada frame
#  - posicoes_mapa.json guarda "n_fixos" para não trocar obstáculos de lugar
#  - Todo chefe (inclusive Froggy, Batty e Flowey) ganha sprite desenhado
#  - PNGs gerados são salvos ao lado do .exe (funciona com PyInstaller)
#  - F11 = tela cheia / janela, M = som ligado/desligado
# =========================================================

import array
import json
import math
import os
import random
import sys
import threading
import time
from pathlib import Path

import pygame

PASTA_JOGO = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
os.chdir(PASTA_JOGO)
PASTA_DADOS = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else PASTA_JOGO
)
ARQUIVO_POSICOES = PASTA_DADOS / "posicoes_mapa.json"
ARQUIVO_SAVE = PASTA_DADOS / "save_rpg.json"

try:
    pygame.mixer.pre_init(22050, -16, 1, 512)
except pygame.error:
    pass
pygame.init()

SOM_OK = pygame.mixer.get_init() is not None
if not SOM_OK:
    try:
        pygame.mixer.init(22050, -16, 1, 512)
        SOM_OK = True
    except pygame.error:
        SOM_OK = False

# =========================================================
# CONFIGURAÇÃO
# =========================================================

LARGURA_JOGO = 800
ALTURA_JOGO = 600
LARGURA_MUNDO = 3200
ALTURA_MUNDO = 2400
ESPESSURA_PAREDE = 90

camera = pygame.Rect(0, 0, LARGURA_JOGO, ALTURA_JOGO)


def criar_tela():
    # SCALED cuida da escala/letterbox em qualquer resolução de monitor.
    try:
        return pygame.display.set_mode(
            (LARGURA_JOGO, ALTURA_JOGO), pygame.SCALED | pygame.FULLSCREEN
        )
    except pygame.error:
        return pygame.display.set_mode((LARGURA_JOGO, ALTURA_JOGO))


tela = criar_tela()
pygame.display.set_caption("Garras e Clemência")
pygame.mouse.set_visible(False)
S = pygame.Surface((LARGURA_JOGO, ALTURA_JOGO))  # superfície do jogo
relogio = pygame.time.Clock()

# =========================================================
# CORES E FONTES
# =========================================================

PRETO = (0, 0, 0)
BRANCO = (255, 255, 255)
VERMELHO = (220, 50, 50)
VERDE = (60, 200, 80)
AMARELO = (255, 220, 60)
AZUL = (60, 110, 255)
CINZA = (120, 120, 120)
ROXO = (180, 80, 220)
VERDE_GRAMA_ESCURO = (48, 105, 52)
VERDE_GRAMA = (72, 135, 65)
VERDE_GRAMA_CLARO = (92, 155, 75)
TERRA = (150, 105, 65)
TERRA_CLARA = (175, 125, 80)
VERDE_ARVORE_ESCURO = (35, 80, 40)

fonte = pygame.font.Font(None, 32)
fonte_p = pygame.font.Font(None, 24)
fonte_g = pygame.font.Font(None, 50)

_cache_texto = {}


def texto(txt, x, y, cor=BRANCO, f=None, centro=False):
    f = f or fonte
    chave = (str(txt), cor, id(f))
    img = _cache_texto.get(chave)
    if img is None:
        if len(_cache_texto) > 900:
            _cache_texto.clear()
        img = f.render(str(txt), True, cor)
        _cache_texto[chave] = img
    r = img.get_rect(topleft=(x, y))
    if centro:
        r.midtop = (x, y)
    S.blit(img, r)


def quebrar(txt, largura, f):
    linhas = []
    for par in str(txt).split("\n"):
        atual = ""
        for palavra in par.split(" "):
            teste = (atual + " " + palavra).strip()
            if not atual or f.size(teste)[0] <= largura:
                atual = teste
            else:
                linhas.append(atual)
                atual = palavra
        linhas.append(atual)
    return linhas


def barra(x, y, w, h, valor, maximo, cor, fundo=(70, 0, 0)):
    pygame.draw.rect(S, fundo, (x, y, w, h))
    if maximo > 0 and valor > 0:
        pygame.draw.rect(S, cor, (x, y, max(1, int(w * valor / maximo)), h))
    pygame.draw.rect(S, BRANCO, (x, y, w, h), 1)


# =========================================================
# ESTADO GLOBAL (um só objeto, sem dezenas de "global")
# =========================================================

MODO_TITULO = "titulo"
MODO_DIFICULDADE = "dificuldade"
MODO_MUNDO = "mundo"
MODO_TRANSICAO = "transicao"
MODO_BATALHA = "batalha"
MODO_PAUSA = "pausa"
MODO_GAME_OVER = "game_over"
MODO_VITORIA = "vitoria"
MODO_DIALOGO = "dialogo"
MODO_LOJA = "loja"


class Estado:
    pass


E = Estado()
E.modo = MODO_TITULO
E.modo_anterior = MODO_MUNDO
E.mudo = False
E.musica_atual = None
E.dificuldade = 1  # 0 facil, 1 medio, 2 dificil
E.mostrar_trajetoria = False
E.sel_titulo = 0
E.sel_dificuldade = 0
E.sel_pausa = 0
E.novo_jogo_pendente = False
E.sel_loja = 0
E.modo_teste = False
E.menu_teste = False
E.konami = 0
E.edicao = False
E.hitboxes = False
E.idx_edicao = 0
E.msg = ""
E.msg_t = 0
E.tick = 0
E.tremor_t = 0
E.tremor_f = 0
E.corte_t = 0
E.corte_f = 0
E.final_mostrado = False
E.final = "neutro"
E.bonus_dano = 0

CODIGO_KONAMI = [
    pygame.K_UP, pygame.K_UP, pygame.K_DOWN, pygame.K_DOWN,
    pygame.K_LEFT, pygame.K_RIGHT, pygame.K_LEFT, pygame.K_RIGHT,
    pygame.K_b, pygame.K_a,
]

# =========================================================
# SAVE (progresso permanente)
# =========================================================

SAVE = {"dificil": False, "finais": [], "partida": None}


def carregar_save():
    try:
        with ARQUIVO_SAVE.open("r", encoding="utf-8") as f:
            d = json.load(f)
        SAVE["partida"] = d.get("partida") if isinstance(d.get("partida"), dict) else None
        if SAVE["partida"] is None:
            # Saves antigos sem partida nao podem compartilhar desbloqueios globais.
            SAVE["dificil"] = False
            SAVE["finais"] = []
        else:
            desbloqueios = SAVE["partida"].get("desbloqueios")
            if not isinstance(desbloqueios, dict):
                # Migra o formato antigo, que guardava os desbloqueios fora da partida.
                desbloqueios = {
                    "dificil": bool(d.get("dificil", False)),
                    "finais": [x for x in d.get("finais", []) if isinstance(x, str)],
                }
                SAVE["partida"]["desbloqueios"] = desbloqueios
            SAVE["dificil"] = bool(desbloqueios.get("dificil", False))
            SAVE["finais"] = [x for x in desbloqueios.get("finais", []) if isinstance(x, str)]
    except (OSError, ValueError, TypeError, AttributeError):
        pass


def salvar_save():
    try:
        with ARQUIVO_SAVE.open("w", encoding="utf-8") as f:
            json.dump(SAVE, f, ensure_ascii=False, indent=2)
    except OSError as erro:
        print(f"Não foi possível salvar o progresso: {erro}")


def salvar_desbloqueios_da_partida():
    partida = SAVE.get("partida")
    if isinstance(partida, dict):
        partida["desbloqueios"] = {
            "dificil": bool(SAVE["dificil"]),
            "finais": list(SAVE["finais"]),
        }
    salvar_save()


carregar_save()

# =========================================================
# SOM E MÚSICA (sintetizados por código)
# =========================================================

_info_mixer = pygame.mixer.get_init() or (22050, -16, 1)
TAXA = _info_mixer[0]
CANAIS = _info_mixer[2]  # o SDL pode abrir em estéreo mesmo pedindo mono


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def _onda(fase, forma):
    x = fase % 1.0
    if forma == "quadrada":
        return 1.0 if x < 0.5 else -1.0
    if forma == "triangulo":
        return 4 * abs(x - 0.5) - 1
    if forma == "serra":
        return 2 * x - 1
    return math.sin(x * math.tau)


def sintetizar_bytes(vozes, vol=0.25, ceder=False):
    """vozes = [(lista[(freq, segundos)], forma, ganho), ...] -> bytes PCM 16 bits.

    ceder=True faz pequenas pausas para não travar o jogo quando roda em thread.
    """
    total = max(sum(d for _, d in notas) for notas, _, _ in vozes)
    n = int(total * TAXA)
    buf = [0.0] * n
    for notas, forma, ganho in vozes:
        pos = 0
        for freq, dur in notas:
            m = int(dur * TAXA)
            if freq > 0:
                for i in range(m):
                    if pos + i >= n:
                        break
                    env = min(1.0, i / 60.0) * (1 - i / m) ** 0.7
                    buf[pos + i] += _onda(freq * i / TAXA, forma) * env * ganho
                    if ceder and i % 4096 == 4095:
                        time.sleep(0.001)
            pos += m
    amostras = [int(max(-1.0, min(1.0, s * vol)) * 32767) for s in buf]
    if CANAIS >= 2:  # duplica cada amostra para cada canal
        dup = [0] * (len(amostras) * CANAIS)
        for c in range(CANAIS):
            dup[c::CANAIS] = amostras
        amostras = dup
    return array.array("h", amostras).tobytes()


def sintetizar(vozes, vol=0.25):
    return pygame.mixer.Sound(buffer=sintetizar_bytes(vozes, vol))


EFEITOS_DEF = {
    "selecionar": ([(660, 0.04)], "quadrada"),
    "confirmar": ([(660, 0.05), (880, 0.08)], "quadrada"),
    "erro": ([(200, 0.1), (150, 0.12)], "quadrada"),
    "dano": ([(180, 0.08), (120, 0.12)], "serra"),
    "bloqueio": ([(900, 0.04), (1200, 0.06)], "triangulo"),
    "acerto": ([(500, 0.05), (750, 0.05), (1000, 0.1)], "quadrada"),
    "perfeito": ([(600, 0.05), (900, 0.05), (1200, 0.05), (1800, 0.16)], "quadrada"),
    "cura": ([(520, 0.06), (660, 0.06), (780, 0.12)], "triangulo"),
    "moeda": ([(988, 0.05), (1319, 0.12)], "quadrada"),
    "levelup": ([(523, 0.1), (659, 0.1), (784, 0.1), (1047, 0.28)], "quadrada"),
    "game_over": ([(330, 0.25), (311, 0.25), (294, 0.25), (262, 0.7)], "serra"),
    "poupar": ([(784, 0.1), (988, 0.1), (1175, 0.22)], "triangulo"),
    "morte": ([(400, 0.05), (300, 0.05), (200, 0.06), (120, 0.22)], "serra"),
    "bau": ([(400, 0.05), (600, 0.05), (800, 0.12)], "quadrada"),
    "fala": ([(240, 0.03)], "quadrada"),
    "transicao": ([(1300 - i * 70, 0.02) for i in range(16)], "serra"),
}
_cache_efeitos = {}


def tocar(nome):
    if not SOM_OK or E.mudo:
        return
    try:
        if nome not in _cache_efeitos:
            notas, forma = EFEITOS_DEF[nome]
            _cache_efeitos[nome] = sintetizar([(notas, forma, 1.0)], 0.22)
        _cache_efeitos[nome].play()
    except pygame.error:
        pass


# nome: (nota raiz midi, escala, bpm, onda, semente)
MUSICAS = {
    "titulo": (57, [0, 2, 3, 5, 7, 8, 10], 80, "triangulo", 1),
    "mundo": (60, [0, 2, 4, 7, 9], 108, "triangulo", 2),
    "Froggy": (52, [0, 2, 4, 7, 9], 150, "quadrada", 3),
    "Flowey": (50, [0, 2, 3, 7, 8], 160, "quadrada", 4),
    "Batty": (45, [0, 1, 3, 5, 7, 8, 10], 170, "serra", 5),
    "Quimera Sombria": (43, [0, 2, 3, 5, 6, 8, 9, 11], 180, "serra", 6),
    "vitoria": (60, [0, 2, 4, 5, 7, 9, 11], 100, "triangulo", 7),
    "Urso Bárbaro": (40, [0, 3, 5, 7, 10], 120, "serra", 11),
    "Lobo Guerreiro": (45, [0, 2, 3, 5, 7, 8, 10], 165, "quadrada", 12),
    "Guaxinim Ladino": (55, [0, 2, 4, 7, 9], 175, "quadrada", 13),
    "Corvo Mago": (50, [0, 2, 3, 6, 7, 9, 10], 150, "triangulo", 14),
    "Javali Berserk": (41, [0, 1, 4, 5, 7, 8], 185, "serra", 15),
    "Raposa Arqueira": (57, [0, 2, 4, 5, 7, 9, 11], 168, "quadrada", 16),
    "Cobra Assassina": (46, [0, 1, 3, 6, 7, 10], 140, "triangulo", 17),
    "Texugo Tank": (38, [0, 2, 3, 5, 7, 8, 10], 100, "triangulo", 18),
}
_cache_musicas = {}  # nome -> Sound (criado na thread principal)
_bytes_musicas = {}  # nome -> bytes (pode ser gerado em segundo plano)


def gerar_musica_bytes(nome, ceder=False):
    raiz, escala, bpm, forma, semente = MUSICAS[nome]
    rnd = random.Random(semente)
    beat = 60.0 / bpm
    ext = [raiz + 12 * o + g for o in (1, 2) for g in escala]
    idx = len(escala)
    melodia = []
    for _ in range(32):
        idx = max(0, min(len(ext) - 1, idx + rnd.choice((-2, -1, -1, 0, 1, 1, 2))))
        melodia.append((0 if rnd.random() < 0.18 else hz(ext[idx]), beat / 2))
    baixo = []
    for _ in range(8):
        grau = rnd.choice((0, 0, escala[min(2, len(escala) - 1)], escala[min(3, len(escala) - 1)]))
        baixo.append((hz(raiz + grau), beat * 2))
    return sintetizar_bytes([(melodia, forma, 0.5), (baixo, "triangulo", 0.9)], 0.16, ceder)


def _pre_gerar_musicas():
    """Roda em thread: sintetiza todas as músicas logo na abertura do jogo."""
    ordem = ["titulo", "mundo"] + [n for n in MUSICAS if n not in ("titulo", "mundo")]
    for nome in ordem:
        if nome in _bytes_musicas:
            continue
        try:
            _bytes_musicas[nome] = gerar_musica_bytes(nome, ceder=True)
        except Exception as erro:  # a thread nunca deve derrubar o jogo
            print(f"Falha ao pré-gerar a música {nome}: {erro}")


def _obter_musica(nome):
    if nome not in _cache_musicas:
        dados = _bytes_musicas.get(nome)
        if dados is None:  # ainda não ficou pronta: gera agora
            dados = gerar_musica_bytes(nome)
            _bytes_musicas[nome] = dados
        _cache_musicas[nome] = pygame.mixer.Sound(buffer=dados)
    return _cache_musicas[nome]


def tocar_musica(nome):
    if not SOM_OK or E.musica_atual == nome:
        return
    E.musica_atual = nome
    try:
        canal = pygame.mixer.Channel(0)
        if nome is None or E.mudo:
            canal.stop()
            return
        canal.set_volume(0.55)
        canal.play(_obter_musica(nome), loops=-1)
    except (pygame.error, KeyError):
        pass


def alternar_som():
    E.mudo = not E.mudo
    atual = E.musica_atual
    E.musica_atual = "__reiniciar__"
    if E.mudo:
        try:
            pygame.mixer.Channel(0).stop()
        except pygame.error:
            pass
        E.musica_atual = atual
    else:
        tocar_musica(atual)


if SOM_OK:
    try:
        pygame.mixer.set_reserved(1)
    except pygame.error:
        pass
    threading.Thread(target=_pre_gerar_musicas, daemon=True).start()

# =========================================================
# IMAGENS
# =========================================================
# Para cada chefe, o jogo procura "imagens/<arquivo>.png".
# Se o arquivo não existir, desenha um sprite por código e SALVA o PNG
# na pasta "imagens" (ao lado do jogo/.exe) - assim todo inimigo sempre
# tem imagem e você pode trocar o arquivo pela sua arte quando quiser.


def _resolver(caminho):
    """Procura o arquivo ao lado do .exe e depois dentro do pacote."""
    for base in (PASTA_DADOS, PASTA_JOGO):
        p = base / caminho
        if p.exists():
            return str(p)
    return str(PASTA_DADOS / caminho)


def sprite_animal(animal, cor):
    """Desenha um sprite 64x64 (com fundo transparente) para cada chefe."""
    s = pygame.Surface((64, 64), pygame.SRCALPHA)
    d = pygame.draw
    escuro = tuple(max(0, c - 55) for c in cor)
    claro = tuple(min(255, c + 60) for c in cor)

    def olhos(y, dx=9, branco=BRANCO, pupila=PRETO, r=4):
        for sx in (-1, 1):
            d.circle(s, branco, (32 + sx * dx, y), r)
            d.circle(s, pupila, (32 + sx * dx, y), max(1, r // 2))

    if animal == "sapo":
        d.ellipse(s, cor, (6, 22, 52, 36))
        d.ellipse(s, claro, (16, 38, 32, 18))
        for sx in (-1, 1):
            d.circle(s, cor, (32 + sx * 15, 20), 10)
            d.circle(s, BRANCO, (32 + sx * 15, 20), 7)
            d.circle(s, PRETO, (32 + sx * 15, 21), 3)
        d.arc(s, escuro, pygame.Rect(14, 30, 36, 20), 3.4, 6.0, 3)
        d.circle(s, escuro, (28, 32), 1)
        d.circle(s, escuro, (36, 32), 1)
    elif animal == "morcego":
        asa = escuro
        d.polygon(s, asa, [(26, 30), (2, 14), (8, 34), (14, 48), (26, 46)])
        d.polygon(s, asa, [(38, 30), (62, 14), (56, 34), (50, 48), (38, 46)])
        for sx in (-1, 1):
            d.polygon(s, cor, [(32 + sx * 6, 16), (32 + sx * 13, 2), (32 + sx * 14, 20)])
        d.ellipse(s, cor, (20, 14, 24, 40))
        d.ellipse(s, claro, (25, 34, 14, 16))
        for sx in (-1, 1):
            d.circle(s, (255, 90, 90), (32 + sx * 5, 28), 3)
        d.line(s, BRANCO, (29, 40), (29, 44), 1)
        d.line(s, BRANCO, (35, 40), (35, 44), 1)
    elif animal == "flor":
        d.line(s, (50, 150, 60), (32, 36), (32, 63), 5)
        d.polygon(s, (60, 170, 70), [(32, 52), (14, 44), (22, 58)])
        d.polygon(s, (60, 170, 70), [(32, 56), (50, 48), (42, 62)])
        for ang in range(0, 360, 45):
            px = 32 + int(math.cos(math.radians(ang)) * 19)
            py = 26 + int(math.sin(math.radians(ang)) * 19)
            d.circle(s, claro, (px, py), 9)
        d.circle(s, cor, (32, 26), 14)
        olhos(24, 6, BRANCO, PRETO, 3)
        d.arc(s, PRETO, pygame.Rect(24, 24, 16, 12), 3.5, 5.9, 2)
    elif animal == "urso":
        for sx in (-1, 1):
            d.circle(s, escuro, (32 + sx * 19, 12), 8)
            d.circle(s, claro, (32 + sx * 19, 12), 4)
        d.circle(s, cor, (32, 32), 22)
        d.ellipse(s, claro, (22, 34, 20, 15))
        d.ellipse(s, PRETO, (28, 36, 8, 6))
        olhos(26)
        d.line(s, (190, 60, 60), (20, 18), (26, 28), 2)  # cicatriz
        d.line(s, (110, 70, 35), (57, 62), (57, 24), 3)  # cabo do machado
        d.polygon(s, (190, 195, 205), [(57, 20), (64, 25), (64, 38), (57, 42)])
    elif animal == "lobo":
        for sx in (-1, 1):
            d.polygon(s, escuro, [(32 + sx * 8, 16), (32 + sx * 22, 2), (32 + sx * 20, 22)])
        d.ellipse(s, cor, (10, 12, 44, 42))
        d.polygon(s, claro, [(32, 36), (20, 46), (32, 58), (44, 46)])
        d.polygon(s, PRETO, [(28, 44), (36, 44), (32, 49)])
        olhos(30, 10, (255, 230, 90), PRETO, 4)
        d.line(s, (205, 205, 220), (6, 62), (6, 20), 3)  # espada
        d.line(s, (150, 120, 60), (1, 46), (11, 46), 3)
    elif animal == "guaxinim":
        for sx in (-1, 1):
            d.circle(s, cor, (32 + sx * 17, 13), 7)
            d.circle(s, escuro, (32 + sx * 17, 13), 3)
        d.circle(s, cor, (32, 34), 22)
        d.rect(s, (35, 35, 42), (11, 24, 42, 13), border_radius=6)  # máscara
        olhos(30, 9, BRANCO, PRETO, 3)
        d.ellipse(s, claro, (24, 40, 16, 12))
        d.circle(s, PRETO, (32, 42), 3)
        for k in range(3):  # listras
            d.line(s, escuro, (26 + k * 6, 12), (27 + k * 6, 18), 2)
        d.polygon(s, (215, 220, 235), [(55, 38), (62, 58), (57, 60)])  # adaga
        d.line(s, (120, 80, 40), (54, 58), (60, 62), 3)
    elif animal == "corvo":
        d.circle(s, cor, (32, 40), 19)
        d.polygon(s, (240, 160, 40), [(26, 40), (38, 40), (32, 56)])
        olhos(34, 8, (255, 240, 120), PRETO, 4)
        d.rect(s, (50, 25, 100), (10, 20, 44, 6), border_radius=2)
        d.polygon(s, (70, 40, 140), [(16, 21), (48, 21), (32, 1)])
        d.circle(s, AMARELO, (32, 12), 3)
        d.line(s, (120, 80, 40), (59, 62), (59, 26), 3)
        d.circle(s, (170, 100, 255), (59, 22), 5)
        d.circle(s, BRANCO, (59, 22), 2)
    elif animal == "javali":
        for sx in (-1, 1):
            d.polygon(s, escuro, [(32 + sx * 14, 14), (32 + sx * 25, 6), (32 + sx * 23, 22)])
        d.ellipse(s, cor, (8, 14, 48, 42))
        d.ellipse(s, claro, (20, 34, 24, 18))
        d.circle(s, PRETO, (28, 42), 2)
        d.circle(s, PRETO, (36, 42), 2)
        for sx in (-1, 1):
            d.polygon(s, (245, 240, 220), [(32 + sx * 11, 46), (32 + sx * 19, 34), (32 + sx * 15, 52)])
        olhos(28, 10, (255, 80, 60), PRETO, 3)
        d.line(s, PRETO, (16, 19), (28, 26), 3)
        d.line(s, PRETO, (48, 19), (36, 26), 3)
        d.line(s, (190, 60, 60), (40, 14), (46, 22), 2)
    elif animal == "raposa":
        for sx in (-1, 1):
            d.polygon(s, cor, [(32 + sx * 8, 20), (32 + sx * 24, 0), (32 + sx * 22, 26)])
            d.polygon(s, escuro, [(32 + sx * 12, 20), (32 + sx * 21, 6), (32 + sx * 20, 22)])
        d.ellipse(s, cor, (10, 16, 44, 34))
        d.polygon(s, BRANCO, [(10, 36), (32, 62), (54, 36), (32, 44)])
        d.circle(s, PRETO, (32, 56), 3)
        olhos(30, 9, (255, 230, 120), PRETO, 3)
        d.arc(s, (120, 75, 35), pygame.Rect(42, 8, 20, 50), -1.57, 1.57, 3)
        d.line(s, (230, 230, 230), (52, 9), (52, 57), 1)
    elif animal == "cobra":
        pts = [(12, 58), (26, 50), (40, 56), (52, 46), (42, 36), (24, 40), (32, 26)]
        d.lines(s, cor, False, pts, 12)
        d.lines(s, claro, False, pts, 4)
        for p in pts[1:-1]:
            d.circle(s, escuro, p, 3)
        d.circle(s, cor, (32, 18), 13)
        d.ellipse(s, (255, 230, 60), (22, 11, 8, 10))
        d.ellipse(s, (255, 230, 60), (34, 11, 8, 10))
        d.line(s, PRETO, (26, 12), (26, 20), 2)
        d.line(s, PRETO, (38, 12), (38, 20), 2)
        d.line(s, (230, 40, 60), (32, 30), (32, 38), 2)
        d.line(s, (230, 40, 60), (32, 38), (29, 42), 2)
        d.line(s, (230, 40, 60), (32, 38), (35, 42), 2)
        d.polygon(s, (215, 220, 235), [(54, 6), (62, 22), (57, 24)])  # adaga
    elif animal == "texugo":
        for sx in (-1, 1):
            d.circle(s, escuro, (32 + sx * 18, 13), 7)
        d.circle(s, cor, (32, 32), 22)
        for sx in (-1, 1):
            d.ellipse(s, (40, 40, 48), (32 + sx * 11 - 7, 18, 14, 30))
        d.polygon(s, BRANCO, [(27, 10), (37, 10), (35, 56), (29, 56)])
        olhos(30, 12, BRANCO, PRETO, 3)
        d.circle(s, PRETO, (32, 50), 4)
        d.ellipse(s, (150, 150, 168), (0, 34, 26, 28))  # escudo
        d.ellipse(s, (100, 100, 118), (4, 38, 18, 20))
        d.circle(s, AMARELO, (13, 48), 3)
    elif animal == "quimera":
        asa = (90, 45, 125)
        d.polygon(s, asa, [(20, 32), (2, 14), (6, 44), (22, 46)])
        d.polygon(s, asa, [(44, 32), (62, 14), (58, 44), (42, 46)])
        for ang in range(0, 360, 60):
            px = 32 + int(math.cos(math.radians(ang)) * 19)
            py = 28 + int(math.sin(math.radians(ang)) * 19)
            d.circle(s, (220, 65, 145), (px, py), 9)
        d.circle(s, (55, 170, 45), (32, 28), 17)
        d.circle(s, (245, 210, 75), (32, 28), 9)
        d.circle(s, (35, 25, 45), (32, 28), 4)
        d.line(s, (55, 170, 45), (32, 44), (32, 62), 5)
    else:
        d.ellipse(s, cor, (6, 6, 52, 52))
        olhos(26)
    return s


def carregar_imagem(caminho, tamanho, cor=(200, 0, 200), animal=None):
    arquivo = _resolver(caminho)
    try:
        img = pygame.image.load(arquivo).convert_alpha()
    except (pygame.error, FileNotFoundError):
        if animal is not None:
            img = sprite_animal(animal, cor)
            try:  # salva o PNG para você poder editar/trocar depois
                os.makedirs(os.path.dirname(arquivo) or ".", exist_ok=True)
                pygame.image.save(img, arquivo)
            except (OSError, pygame.error):
                pass
        else:
            img = pygame.Surface((32, 32), pygame.SRCALPHA)
            pygame.draw.ellipse(img, cor, (2, 2, 28, 28))
            pygame.draw.circle(img, BRANCO, (11, 13), 4)
            pygame.draw.circle(img, BRANCO, (21, 13), 4)
            pygame.draw.circle(img, PRETO, (11, 13), 2)
            pygame.draw.circle(img, PRETO, (21, 13), 2)
    return pygame.transform.scale(img, tamanho)


def carregar_imagem_proporcional(caminho, tamanho, cor):
    """Encaixa a imagem na área sem alterar sua proporção e alinha pela base."""
    try:
        img = pygame.image.load(_resolver(caminho)).convert_alpha()
    except (pygame.error, FileNotFoundError):
        return carregar_imagem(caminho, tamanho, cor)

    escala = min(tamanho[0] / img.get_width(), tamanho[1] / img.get_height())
    novo_tamanho = (
        max(1, round(img.get_width() * escala)),
        max(1, round(img.get_height() * escala)),
    )
    img = pygame.transform.smoothscale(img, novo_tamanho)
    area = pygame.Surface(tamanho, pygame.SRCALPHA)
    area.blit(img, ((tamanho[0] - novo_tamanho[0]) // 2, tamanho[1] - novo_tamanho[1]))
    return area


IMG = {
    "flowey1": carregar_imagem("imagens/flowey_1.png", (50, 50), (250, 210, 60)),
    "flowey2": carregar_imagem("imagens/flowey_2.png", (50, 50), (255, 235, 100)),
    "arvore": carregar_imagem("imagens/arvore.png", (60, 70), (40, 120, 50)),
    "pedra": carregar_imagem("imagens/pedra.png", (50, 45), (130, 130, 130)),
}
IMG_NPCS = {
    "guia": carregar_imagem_proporcional("imagens/coruja_guia.png", (56, 54), (150, 110, 70)),
    "loja": carregar_imagem_proporcional("imagens/gato_mercante.png", (56, 54), (90, 90, 110)),
}

# animal -> cor principal usada no sprite desenhado e na cor do chefe
ANIMAIS = {
    "sapo": (70, 190, 90),
    "morcego": (150, 80, 200),
    "flor": (250, 210, 60),
    "urso": (150, 95, 55),
    "lobo": (130, 140, 165),
    "guaxinim": (125, 125, 135),
    "corvo": (70, 55, 110),
    "javali": (140, 90, 70),
    "raposa": (235, 130, 50),
    "cobra": (80, 180, 80),
    "texugo": (150, 150, 160),
    "quimera": (165, 90, 205),
}

# chefe: (arquivo do sprite, animal usado se o arquivo não existir)
SPRITES_CHEFES = {
    "Froggy": ("froggy.png", "sapo"),
    "Batty": ("batty.png", "morcego"),
    "Flowey": ("flowey_1.png", "flor"),
    "Urso Bárbaro": ("urso_barbaro.png", "urso"),
    "Lobo Guerreiro": ("lobo_guerreiro.png", "lobo"),
    "Guaxinim Ladino": ("guaxinim_ladino.png", "guaxinim"),
    "Corvo Mago": ("corvo_mago.png", "corvo"),
    "Javali Berserk": ("javali_berserk.png", "javali"),
    "Raposa Arqueira": ("raposa_arqueira.png", "raposa"),
    "Cobra Assassina": ("cobra_assassina.png", "cobra"),
    "Texugo Tank": ("texugo_tank.png", "texugo"),
    "Quimera Sombria": ("quimera_sombria.png", "quimera"),
}
IMG_CHEFES = {}
for _nome, (_arquivo, _animal) in SPRITES_CHEFES.items():
    # A Quimera (chefe secreto) é maior que os demais.
    _tam = (90, 90) if _nome == "Quimera Sombria" else (54, 54)
    IMG_CHEFES[_nome] = carregar_imagem(
        f"imagens/{_arquivo}", _tam, ANIMAIS[_animal], _animal
    )

ANIM_FLOWEY = [IMG["flowey1"], IMG["flowey2"]]
VELOCIDADE_ANIMACAO_FLOWEY = 14
VELOCIDADE_ANIMACAO_JOGADOR = 8
TAMANHO_FRAME_JOGADOR = 40

animacoes_jogador = {"baixo": [], "cima": [], "direita": [], "esquerda": []}
try:
    _sheet = pygame.image.load(_resolver("imagens/personagem_spritesheet.png")).convert_alpha()
    for _i in range(12):
        _f = _sheet.subsurface(
            pygame.Rect(_i * TAMANHO_FRAME_JOGADOR, 0, TAMANHO_FRAME_JOGADOR, TAMANHO_FRAME_JOGADOR)
        ).copy()
        _d = ("baixo", "cima", "direita", "esquerda")[_i // 3]
        animacoes_jogador[_d].append(_f)
except (pygame.error, FileNotFoundError, ValueError):
    animacoes_jogador = {"baixo": [], "cima": [], "direita": [], "esquerda": []}
    for _d, _off in (("baixo", (0, 6)), ("cima", (0, -6)), ("direita", (6, 0)), ("esquerda", (-6, 0))):
        for _k in range(3):
            _f = pygame.Surface((40, 40), pygame.SRCALPHA)
            pygame.draw.rect(_f, (60, 90, 200), (12, 14 + (_k % 2) * 2, 16, 20), border_radius=4)
            pygame.draw.circle(_f, (240, 200, 160), (20, 11), 8)
            pygame.draw.circle(_f, PRETO, (20 + _off[0] // 2, 11 + _off[1] // 3), 2)
            animacoes_jogador[_d].append(_f)

# =========================================================
# TEXTURAS DO MUNDO
# =========================================================

# Tile grande (128x128): 16x menos blits por frame que o tile de 32x32.
TAM_BLOCO = 128
textura_grama = pygame.Surface((TAM_BLOCO, TAM_BLOCO))
textura_grama.fill(VERDE_GRAMA)
for _ in range(560):
    _x = random.randint(2, TAM_BLOCO - 3)
    _y = random.randint(2, TAM_BLOCO - 5)
    _c = random.choice([VERDE_GRAMA_ESCURO, VERDE_GRAMA_CLARO, (65, 125, 60)])
    pygame.draw.line(textura_grama, _c, (_x, _y + 3), (_x + random.randint(-2, 2), _y), 1)

flores = [
    {
        "x": random.randint(80, LARGURA_MUNDO - 80),
        "y": random.randint(80, ALTURA_MUNDO - 80),
        "cor": random.choice([(255, 120, 150), (255, 230, 100), (180, 130, 255), (255, 255, 255)]),
    }
    for _ in range(420)
]
detalhes_grama = [
    (random.randint(70, LARGURA_MUNDO - 70), random.randint(70, ALTURA_MUNDO - 70))
    for _ in range(750)
]

caminhos = [
    pygame.Rect(70, 280, LARGURA_MUNDO - 140, 90),    # estrada norte (leste-oeste)
    pygame.Rect(700, 280, 100, ALTURA_MUNDO - 380),   # estrada oeste (norte-sul)
    pygame.Rect(70, 1250, LARGURA_MUNDO - 140, 90),   # estrada central (leste-oeste)
    pygame.Rect(2300, 280, 100, ALTURA_MUNDO - 380),  # estrada leste (norte-sul)
]

# =========================================================
# ITENS
# =========================================================
# chave: (nome, cura, descrição, preço)

ITENS = {
    "pocao": ("Poção", 40, "Cura 40 de vida", 15),
    "doce": ("Doce", 20, "Cura 20 de vida", 8),
    "escudo": ("Escudo", 0, "Bloqueia 3 golpes", 22),
}

# =========================================================
# OBSTÁCULOS, SEGREDOS, NPCS E BAÚS
# =========================================================


def _obst(tipo, x, y, **extra):
    img = IMG[tipo]
    d = {"tipo": tipo, "retangulo": pygame.Rect(x, y, *img.get_size()), "imagem": img}
    d.update(extra)
    return d


# IMPORTANTE: mantenha os 12 primeiros na ordem (compatível com o
# posicoes_mapa.json antigo). Os novos entram depois.
OBSTACULOS = [
    _obst("arvore", 180, 150),
    _obst("arvore", 500, 120),
    _obst("arvore", 950, 180, chefe_secreto=True),
    _obst("arvore", 1250, 500),
    _obst("arvore", 300, 800),
    _obst("arvore", 1100, 900),
    _obst("pedra", 280, 350),
    _obst("pedra", 650, 170),
    _obst("pedra", 750, 500),
    _obst("pedra", 1050, 700),
    _obst("pedra", 1450, 950, segredo="amuleto", aberto=False),
    _obst("pedra", 500, 1050),
    # ---- novos segredos (brilham quando você chega perto; aperte E) ----
    _obst("arvore", 3000, 150, segredo="pocoes", aberto=False),
    _obst("pedra", 2950, 2200, segredo="runa", aberto=False),
    _obst("pedra", 150, 2200, segredo="tesouro", aberto=False),
    _obst("pedra", 1600, 2250, segredo="escudos", aberto=False),
    _obst("pedra", 2500, 1100, segredo="coracao", aberto=False),
    _obst("arvore", 120, 1650, segredo="tesouro", aberto=False),
    _obst("arvore", 1000, 1800, segredo="runa", aberto=False),
]
# Quantidade de obstáculos fixos (os gerados por _povoar_mapa vêm depois).
# Vai no JSON de posições para não trocar obstáculos de lugar se esta lista mudar.
N_FIXOS = len(OBSTACULOS)

NPCS = [
    {
        "nome": "Coruja Guia", "ret": pygame.Rect(150, 300, 34, 44),
        "cor": (150, 110, 70), "cor2": (200, 160, 110), "tipo": "guia",
        "imagem": IMG_NPCS["guia"], "idx": 0,
        "falas": [
            "Olá, viajante! Cada criatura daqui tem um jeito de ser acalmada.",
            "Em AGIR, use CHECAR para descobrir o que cada uma deseja.",
            "O sapo vive faminto... o morcego se assusta com barulho... a flor parece sedenta.",
            "Dizem que a árvore ao norte guarda uma criatura sombria. Ela só confia em quem nunca feriu ninguém.",
            "O mundo cresceu! Oito guerreiros vagam por aqui: um urso, um lobo, um guaxinim, um corvo, um javali, uma raposa, uma cobra e um texugo.",
            "Cada um tem uma classe: o bárbaro bate forte, o ladino rouba moedas, o mago enche a arena de neblina e a assassina usa veneno.",
            "O javali enlouquece quanto mais ferido está, a raposa esquiva dos golpes e o texugo tem uma armadura grossa.",
            "Pedras e árvores escondem segredos. Quando algo brilhar perto de você, aperte E!",
            "Há duas estradas cruzando o mapa de leste a oeste e duas de norte a sul. Os baús estão espalhados longe delas.",
            "Inimigos perseguem quem chega perto. Fuja deles e procure os baús!",
        ],
    },
    {
        "nome": "Gato Mercador", "ret": pygame.Rect(560, 300, 34, 44),
        "cor": (90, 90, 110), "cor2": (160, 160, 190), "tipo": "loja",
        "imagem": IMG_NPCS["loja"], "idx": 0,
        "falas": ["Miau! Tenho coisas úteis para quem tem moedas.", "O que vai querer?"],
    },
]

BAUS = [
    {"nome": "Baú 1", "ret": pygame.Rect(1380, 310, 36, 30), "conteudo": ("pocao", 2), "aberto": False},
    {"nome": "Baú 2", "ret": pygame.Rect(730, 1060, 36, 30), "conteudo": ("moedas", 30), "aberto": False},
    {"nome": "Baú 3", "ret": pygame.Rect(120, 900, 36, 30), "conteudo": ("escudo", 1), "aberto": False},
    # ---- novos baús ----
    {"nome": "Baú 4", "ret": pygame.Rect(2900, 380, 36, 30), "conteudo": ("moedas", 50), "aberto": False},
    {"nome": "Baú 5", "ret": pygame.Rect(1900, 700, 36, 30), "conteudo": ("pocao", 3), "aberto": False},
    {"nome": "Baú 6", "ret": pygame.Rect(2600, 1500, 36, 30), "conteudo": ("escudo", 2), "aberto": False},
    {"nome": "Baú 7", "ret": pygame.Rect(400, 1900, 36, 30), "conteudo": ("doce", 4), "aberto": False},
    {"nome": "Baú 8", "ret": pygame.Rect(1500, 2100, 36, 30), "conteudo": ("vida_max", 10), "aberto": False},
    {"nome": "Baú 9", "ret": pygame.Rect(3000, 1900, 36, 30), "conteudo": ("moedas", 90), "aberto": False},
    {"nome": "Baú 10", "ret": pygame.Rect(1200, 1500, 36, 30), "conteudo": ("pocao", 2), "aberto": False},
    {"nome": "Baú 11", "ret": pygame.Rect(2000, 2250, 36, 30), "conteudo": ("escudo", 1), "aberto": False},
    {"nome": "Baú 12", "ret": pygame.Rect(250, 1500, 36, 30), "conteudo": ("moedas", 40), "aberto": False},
    {"nome": "Baú 13", "ret": pygame.Rect(2700, 250, 36, 30), "conteudo": ("vida_max", 10), "aberto": False},
    {"nome": "Baú 14", "ret": pygame.Rect(1750, 1850, 36, 30), "conteudo": ("pocao", 2), "aberto": False},
]

# =========================================================
# INIMIGOS
# =========================================================
# opcoes de AGIR: (nome, reação, tipo, so_pacifista)
# tipos: checar | ok (torna poupável) | neutro | irrita (próximo turno mais rápido)


def _opcoes(*extra):
    return [("Checar", "", "checar", False)] + list(extra)


INIMIGOS = [
    {
        "nome": "Froggy", "classe": "Anfíbio", "retangulo": pygame.Rect(350, 200, 50, 50), "cor": VERDE,
        "imagem": IMG_CHEFES["Froggy"], "vida_max": 100, "mov": "pula", "vel": 1.3,
        "ataques": ["linguas", "moscas"], "prob_azul": 0.0, "exp": 20, "moedas": 12,
        "checar": "FROGGY - Seu estômago ronca alto. Ele só pensa em comida.",
        "falas": ["Croac! Que fome...", "Nenhuma mosca por aqui?!", "Vou te engolir... de brincadeira!"],
        "falas2": ["AGORA ESTOU FURIOSO! CROAC!", "Chega de brincadeira!"],
        "opcoes": _opcoes(
            ("Elogiar", "Froggy fica corado, mas continua com fome.", "neutro", False),
            ("Oferecer mosca", "Você oferece uma mosca. Froggy sorri! Ele aceita ser poupado.", "ok", False),
            ("Imitar coaxar", "Você coaxa. Froggy acha ofensivo!", "irrita", False),
        ),
    },
    {
        "nome": "Batty", "classe": "Voador", "retangulo": pygame.Rect(1200, 350, 50, 50), "cor": ROXO,
        "imagem": IMG_CHEFES["Batty"], "vida_max": 60, "mov": "voa", "vel": 1.8,
        "ataques": ["morcegos", "sangue"], "prob_azul": 0.0, "exp": 18, "moedas": 10,
        "checar": "BATTY - Treme ao menor ruído. Parece um morcego assustado.",
        "falas": ["Eeek! Fique longe!", "Sangue... eu preciso de sangue!", "Não grite comigo!"],
        "falas2": ["NÃO ME ENCURRALE!", "Meus morcegos vão te pegar!"],
        "opcoes": _opcoes(
            ("Gritar", "O eco assusta Batty! Ele fica agressivo.", "irrita", False),
            ("Assobiar", "Batty vira a cabeça, curioso, mas segue tenso.", "neutro", False),
            ("Ficar parado", "Você fica imóvel. Batty se acalma devagar. Ele aceita ser poupado.", "ok", False),
        ),
    },
    {
        "nome": "Flowey", "classe": "Planta", "retangulo": pygame.Rect(850, 800, 50, 50), "cor": AMARELO,
        "imagem": IMG_CHEFES["Flowey"], "vida_max": 80, "mov": "fixo", "vel": 0,
        "ataques": ["petalas", "raizes"], "prob_azul": 0.3, "exp": 25, "moedas": 15,
        "checar": "FLOWEY - Suas folhas estão murchas. Ele precisa de algo essencial.",
        "falas": ["Howdy! Que tal ficar aqui para sempre?", "Suas raízes vão adorar este chão...", "Tão sedento..."],
        "falas2": ["ISSO É O QUE VOCÊ QUER?!", "Eu vou te enterrar!"],
        "opcoes": _opcoes(
            ("Conversar", "Flowey finge ouvir, mas suas pétalas tremem.", "neutro", False),
            ("Regar", "Você derrama água. Flowey suspira aliviado! Ele aceita ser poupado.", "ok", False),
            ("Cantar", "Sua voz desafina. Flowey tapa as folhas, irritado!", "irrita", False),
        ),
    },
]


def _chefe(nome, classe, x, y, cor, animal, vida, mov, vel, ataques, azul, exp, moedas,
           checar, falas, falas2, opcoes, **extra):
    # "animal" fica na assinatura por compatibilidade; o sprite vem de IMG_CHEFES[nome].
    d = {
        "nome": nome, "classe": classe, "retangulo": pygame.Rect(x, y, 54, 54), "cor": cor,
        "imagem": IMG_CHEFES[nome], "vida_max": vida, "mov": mov, "vel": vel, "ataques": ataques,
        "prob_azul": azul, "exp": exp, "moedas": moedas, "checar": checar,
        "falas": falas, "falas2": falas2, "opcoes": opcoes,
    }
    d.update(extra)  # forca, armadura, esquiva, berserk
    return d


# ---------------------------------------------------------
# OS 8 NOVOS CHEFES (cada um com classe e ataques próprios)
# ---------------------------------------------------------
INIMIGOS += [
    _chefe(
        "Urso Bárbaro", "Bárbaro", 2200, 300, ANIMAIS["urso"], "urso", 190, "anda", 1.2,
        ["machado", "rocha", "tremor"], 0.0, 40, 25,
        "URSO BÁRBARO - Classe Bárbaro. Golpes devastadores, mas ele adora algo bem doce...",
        ["GRAAAH! Meu machado tem sede!", "Eu esmago tudo no caminho!", "Vem cá, pequeno!"],
        ["SÓ RAIVA! SÓ RAIVA!", "VOU PARTIR VOCÊ AO MEIO!"],
        _opcoes(
            ("Provocar", "O urso bate no peito, furioso!", "irrita", False),
            ("Oferecer mel", "O urso lambe os beiços e baixa o machado. Ele aceita ser poupado.", "ok", False),
            ("Aplaudir", "O urso inclina a cabeça, confuso.", "neutro", False),
        ),
        forca=1.4,
    ),
    _chefe(
        "Lobo Guerreiro", "Guerreiro", 2700, 700, ANIMAIS["lobo"], "lobo", 160, "anda", 1.7,
        ["garras", "uivo", "investida"], 0.15, 38, 22,
        "LOBO GUERREIRO - Classe Guerreiro. Orgulhoso: só respeita quem o encara sem agredir.",
        ["Meu bando nunca recua!", "Mostre sua honra!", "Auuuu! Lute comigo!"],
        ["AGORA É UMA CAÇADA!", "SENTE AS MINHAS GARRAS!"],
        _opcoes(
            ("Uivar", "Você uiva. O lobo entende como um desafio!", "irrita", False),
            ("Reverenciar", "Você faz uma reverência de guerreiro. O lobo assente, honrado. Ele aceita ser poupado.", "ok", False),
            ("Mostrar as mãos", "O lobo observa suas mãos vazias, desconfiado.", "neutro", False),
        ),
    ),
    _chefe(
        "Guaxinim Ladino", "Ladino", 1700, 1000, ANIMAIS["guaxinim"], "guaxinim", 90, "anda", 2.0,
        ["adagas", "armadilha"], 0.0, 30, 30,
        "GUAXINIM LADINO - Classe Ladino. Rouba suas moedas! No fundo, só quer atenção e brilho.",
        ["Hehe! Suas moedas são minhas!", "Rápido demais pra você!", "Cuidado com os bolsos!"],
        ["CHEGA DE JOGOS! ADAGAS!", "EU PEGO TUDO!"],
        _opcoes(
            ("Esconder a bolsa", "O guaxinim se sente desafiado!", "irrita", False),
            ("Mostrar uma moeda", "Os olhos do guaxinim brilham! Ele larga as adagas e aceita ser poupado.", "ok", False),
            ("Perguntar o nome", "Ele ri, lisonjeado, mas ainda desconfia.", "neutro", False),
        ),
    ),
    _chefe(
        "Corvo Mago", "Mago", 2900, 1500, ANIMAIS["corvo"], "corvo", 110, "voa", 1.6,
        ["orbes", "raios", "nova"], 0.0, 36, 24,
        "CORVO MAGO - Classe Mago. Adora enigmas e odeia ser interrompido. Suas magias nublam a visão.",
        ["Kraa! Os astros me obedecem!", "Prove ser digno da minha magia!", "Ignorante mortal..."],
        ["PODER ARCANO ILIMITADO!", "KRAAA! TREMA!"],
        _opcoes(
            ("Interromper", "O corvo se enfurece e murmura um feitiço!", "irrita", False),
            ("Contar enigma", "O corvo fica fascinado e esquece a magia. Ele aceita ser poupado.", "ok", False),
            ("Aplaudir", "O corvo faz uma reverência exagerada.", "neutro", False),
        ),
    ),
    _chefe(
        "Javali Berserk", "Berserk", 500, 1500, ANIMAIS["javali"], "javali", 170, "anda", 2.1,
        ["carga", "rocha"], 0.0, 40, 22,
        "JAVALI BERSERK - Classe Berserk. Quanto mais ferido, mais furioso! Só se acalma com bolotas.",
        ["GRUNF! SANGUE NOS OLHOS!", "Não consigo parar!", "FORA DO MEU CAMINHO!"],
        ["FÚRIA TOTAL!!!", "NADA ME DETÉM!"],
        _opcoes(
            ("Gritar", "O javali bufa, enfurecido!", "irrita", False),
            ("Oferecer bolota", "O javali fareja a bolota e se acalma aos poucos. Ele aceita ser poupado.", "ok", False),
            ("Ficar imóvel", "O javali raspa o chão, mas não ataca por ora.", "neutro", False),
        ),
        forca=1.2, berserk=True,
    ),
    _chefe(
        "Raposa Arqueira", "Arqueira", 1500, 1700, ANIMAIS["raposa"], "raposa", 100, "anda", 1.8,
        ["flechas", "chuva"], 0.2, 34, 26,
        "RAPOSA ARQUEIRA - Classe Arqueira. Esquiva de golpes com facilidade. Adora um desafio amigável.",
        ["Nunca erro um alvo!", "Fique parado, quero mirar!", "Suas costas são um ótimo alvo!"],
        ["CHUVA DE FLECHAS!", "AGORA VOCÊ NÃO ESCAPA!"],
        _opcoes(
            ("Zombar da mira", "A raposa estreita os olhos, ofendida!", "irrita", False),
            ("Propor tiro ao alvo", "Você propõe um duelo de pontaria amigável. Ela ri e aceita ser poupada.", "ok", False),
            ("Elogiar o arco", "A raposa sorri, vaidosa, mas segue de arco em punho.", "neutro", False),
        ),
        esquiva=0.25,
    ),
    _chefe(
        "Cobra Assassina", "Assassina", 2300, 1900, ANIMAIS["cobra"], "cobra", 85, "anda", 1.6,
        ["bote", "dardos", "emboscada"], 0.0, 36, 28,
        "COBRA ASSASSINA - Classe Assassina. Ataca das sombras com veneno. Está sempre com frio.",
        ["Sssó um golpe bassta...", "Você nem me viu chegar.", "Sssinta o meu veneno."],
        ["SSSSAIA DAÍ!", "ACABO COM VOCÊ!"],
        _opcoes(
            ("Movimento brusco", "A cobra se retesa, pronta para o bote!", "irrita", False),
            ("Oferecer calor", "Você acende uma pequena fogueira. A cobra se enrosca perto, relaxada. Ela aceita ser poupada.", "ok", False),
            ("Assobiar", "A cobra balança a cabeça no ritmo, mas segue atenta.", "neutro", False),
        ),
    ),
    _chefe(
        "Texugo Tank", "Tank", 800, 2100, ANIMAIS["texugo"], "texugo", 320, "anda", 0.9,
        ["muralha", "tremor", "onda"], 0.0, 50, 35,
        "TEXUGO TANK - Classe Tank. Armadura grossa: seus golpes causam bem menos dano. Só quer descansar.",
        ["Ninguém passa por mim.", "Sua força é fraca...", "Zzz... ah, ainda está aí?"],
        ["MURALHA INABALÁVEL!", "VOU TE ESMAGAR COM O ESCUDO!"],
        _opcoes(
            ("Bater no escudo", "O texugo bufa, irritado com o barulho!", "irrita", False),
            ("Oferecer descanso", "Você estende uma manta. O texugo bufa, aliviado, e se deita. Ele aceita ser poupado.", "ok", False),
            ("Elogiar a armadura", "O texugo estufa o peito, orgulhoso.", "neutro", False),
        ),
        armadura=0.6, forca=1.1,
    ),
]

CHEFE_SECRETO = {
    "nome": "Quimera Sombria", "classe": "Quimera", "retangulo": pygame.Rect(950, 180, 50, 60),
    "cor": (165, 90, 205), "imagem": IMG_CHEFES["Quimera Sombria"], "vida_max": 240, "mov": "fixo", "vel": 0,
    "ataques": list(dict.fromkeys(
        ataque for inimigo in INIMIGOS for ataque in inimigo["ataques"]
    )),
    "prob_azul": 0.25, "exp": 80, "moedas": 60,
    "checar": "QUIMERA SOMBRIA - Três almas em um corpo. Ela só confia em mãos limpas.",
    "falas": ["Três vozes falam por mim...", "Você ousou me acordar.", "Sinto o cheiro do seu medo."],
    "falas2": ["AGORA VOCÊ CONHECE A FÚRIA!", "NÃO HÁ ESCAPATÓRIA!"],
    "opcoes": _opcoes(
        ("Encarar", "Ela rosna. Isso não ajudou.", "irrita", False),
        ("Oferecer fruta", "Ela cheira a fruta e vira o rosto.", "neutro", False),
        ("Cantar", "Uma melodia suave ecoa pela floresta... Ela aceita ser poupada.", "ok", True),
    ),
}

TODOS_INIMIGOS = INIMIGOS + [CHEFE_SECRETO]


def resetar_inimigo(i, posicao_inicial=False):
    i["vida"] = i["vida_max"]
    i["vivo"] = True
    i["destino"] = None
    i["piedade"] = False
    i["raiva"] = 0
    i["fase2"] = False
    i["escalado"] = False
    i["cooldown"] = 0
    i["tick"] = random.randint(0, 100)
    i["alvo"] = None
    i["alerta"] = False
    if posicao_inicial or "home" not in i:
        i["home"] = i["retangulo"].center
    i["retangulo"].center = i["home"]
    i["pos"] = [float(i["retangulo"].centerx), float(i["retangulo"].centery)]


for _i in TODOS_INIMIGOS:
    resetar_inimigo(_i, True)


def _povoar_mapa():
    """Espalha árvores e pedras pelo mapa grande (sempre o mesmo resultado)."""
    rnd = random.Random(7)
    livres = [c.inflate(40, 40) for c in caminhos]
    livres.append(pygame.Rect(40, 40, 260, 260))  # área inicial
    livres += [i["retangulo"].inflate(170, 170) for i in INIMIGOS]
    livres += [n["ret"].inflate(90, 90) for n in NPCS]
    livres += [b["ret"].inflate(70, 70) for b in BAUS]
    livres += [o["retangulo"].inflate(30, 30) for o in OBSTACULOS]
    for tipo, qtd in (("arvore", 46), ("pedra", 36)):
        feito = 0
        tentativas = 0
        while feito < qtd and tentativas < 6000:
            tentativas += 1
            o = _obst(
                tipo,
                rnd.randint(90, LARGURA_MUNDO - 170),
                rnd.randint(90, ALTURA_MUNDO - 170),
            )
            if o["retangulo"].collidelist(livres) != -1:
                continue
            OBSTACULOS.append(o)
            livres.append(o["retangulo"].inflate(30, 30))
            feito += 1


_povoar_mapa()
SEGREDOS_TOTAL = sum(1 for _o in OBSTACULOS if "segredo" in _o)

# =========================================================
# EDITOR DE MAPA (F2 no mundo)
# =========================================================


def _rects_salvos():
    return {
        "n_fixos": N_FIXOS,
        "inimigos": {i["nome"]: list(i["retangulo"]) for i in INIMIGOS},
        "npcs": {n["nome"]: list(n["ret"]) for n in NPCS},
        "baus": [list(b["ret"]) for b in BAUS],
        "obstaculos": [list(o["retangulo"]) for o in OBSTACULOS],
    }


def salvar_posicoes_mapa():
    try:
        with ARQUIVO_POSICOES.open("w", encoding="utf-8") as arq:
            json.dump(_rects_salvos(), arq, ensure_ascii=False, indent=2)
    except OSError as erro:
        print(f"Não foi possível salvar as posições: {erro}")


def _aplicar(rect, pos):
    if isinstance(pos, list) and len(pos) in (2, 4):
        rect.topleft = tuple(map(int, pos[:2]))
        if len(pos) == 4:
            rect.size = tuple(max(8, int(v)) for v in pos[2:])


def carregar_posicoes_mapa():
    if not ARQUIVO_POSICOES.exists():
        return
    try:
        with ARQUIVO_POSICOES.open("r", encoding="utf-8") as arq:
            d = json.load(arq)
        for i in INIMIGOS:
            _aplicar(i["retangulo"], d.get("inimigos", {}).get(i["nome"]))
        for n in NPCS:
            _aplicar(n["ret"], d.get("npcs", {}).get(n["nome"]))
        for b, pos in zip(BAUS, d.get("baus", [])):
            _aplicar(b["ret"], pos)
        if d.get("n_fixos", N_FIXOS) == N_FIXOS:
            for o, pos in zip(OBSTACULOS, d.get("obstaculos", [])):
                _aplicar(o["retangulo"], pos)
        else:
            print(
                "A lista de obstáculos fixos mudou desde o último salvamento; "
                "as posições salvas dos obstáculos foram ignoradas."
            )
        # O chefe secreto usa a hitbox da árvore secreta.
        for o in OBSTACULOS:
            if o.get("chefe_secreto"):
                CHEFE_SECRETO["retangulo"] = o["retangulo"].copy()
        for i in TODOS_INIMIGOS:
            resetar_inimigo(i, True)
    except (OSError, ValueError, TypeError, AttributeError) as erro:
        print(f"Não foi possível carregar as posições salvas: {erro}")


carregar_posicoes_mapa()


def objetos_editaveis():
    lista = [(i["nome"], i["retangulo"], i) for i in INIMIGOS]
    lista += [(n["nome"], n["ret"], None) for n in NPCS]
    lista += [(b["nome"], b["ret"], None) for b in BAUS]
    lista += [(f"Obstáculo {k + 1} ({o['tipo']})", o["retangulo"], None) for k, o in enumerate(OBSTACULOS)]
    return lista


def limitar_objeto_ao_mundo(r):
    r.left = max(ESPESSURA_PAREDE, min(r.left, LARGURA_MUNDO - ESPESSURA_PAREDE - r.width))
    r.top = max(ESPESSURA_PAREDE, min(r.top, ALTURA_MUNDO - ESPESSURA_PAREDE - r.height))


def mover_objeto_edicao(teclas):
    # Não grava o JSON aqui (seria a cada frame): o F2 salva ao sair do editor.
    lista = objetos_editaveis()
    _, r, inim = lista[E.idx_edicao % len(lista)]
    passo = 10 if teclas[pygame.K_LSHIFT] or teclas[pygame.K_RSHIFT] else 2
    dx = (teclas[pygame.K_RIGHT] - teclas[pygame.K_LEFT]) * passo
    dy = (teclas[pygame.K_DOWN] - teclas[pygame.K_UP]) * passo
    if dx or dy:
        r.move_ip(dx, dy)
        limitar_objeto_ao_mundo(r)
        if inim is not None:
            inim["home"] = r.center
            inim["pos"] = [float(r.centerx), float(r.centery)]


def redimensionar_hitbox_edicao(aumento):
    lista = objetos_editaveis()
    _, r, inim = lista[E.idx_edicao % len(lista)]
    c = r.center
    r.width = max(8, r.width + aumento)
    r.height = max(8, r.height + aumento)
    r.center = c
    limitar_objeto_ao_mundo(r)
    if inim is not None:
        inim["home"] = r.center


# =========================================================
# JOGADOR E PROGRESSO
# =========================================================

jogador = pygame.Rect(111, 130, 18, 10)
VELOCIDADE_JOGADOR = 4
E.direcao = "baixo"
E.frame_j = 0
E.cont_anim_j = 0
E.frame_flowey = 0
E.cont_flowey = 0


def exp_necessaria():
    return 20 + E.nivel * 15


def novo_jogo():
    """Começa uma aventura nova (o save permanente não é apagado)."""
    E.vida_max = 100
    E.vida = 100
    E.nivel = 1
    E.exp = 0
    E.moedas = 10
    E.itens = {"pocao": 1, "doce": 1, "escudo": 0}
    E.mortes = 0
    E.poupados = 0
    E.bonus_dano = 0
    E.final_mostrado = False
    E.inimigo = None
    E.msg = ""
    E.msg_t = 0
    E.dialogo = None
    E.particulas = []
    E.flutuantes = []
    E.edicao = False
    E.menu_teste = False
    for i in TODOS_INIMIGOS:
        resetar_inimigo(i)
    for b in BAUS:
        b["aberto"] = False
    for o in OBSTACULOS:
        if "segredo" in o:
            o["aberto"] = False
    for n in NPCS:
        n["idx"] = 0
    limpar_estado_batalha()
    jogador.topleft = (111, 130)
    E.direcao = "baixo"
    E.frame_j = 0
    atualizar_camera()


def salvar_partida():
    """Salva o progresso atual para continuar depois pelo menu inicial."""
    SAVE["partida"] = {
        "versao": 1,
        "desbloqueios": {
            "dificil": bool(SAVE["dificil"]),
            "finais": list(SAVE["finais"]),
        },
        "jogador": [jogador.x, jogador.y],
        "estado": {
            chave: getattr(E, chave)
            for chave in (
                "vida", "vida_max", "nivel", "exp", "moedas", "mortes", "poupados",
                "bonus_dano", "dificuldade", "final_mostrado", "final",
            )
        },
        "itens": dict(E.itens),
        "bau_aberto": {b["nome"]: bool(b["aberto"]) for b in BAUS},
        "segredos": [bool(o.get("aberto", False)) for o in OBSTACULOS],
        "npcs": {n["nome"]: int(n["idx"]) for n in NPCS},
        "inimigos": {
            i["nome"]: {
                "pos": list(i["retangulo"].center),
                "home": list(i["home"]),
                "vivo": bool(i["vivo"]),
                "vida_max": int(i["vida_max"]),
                "vida": int(i["vida"]),
                "destino": i["destino"],
                "piedade": bool(i["piedade"]),
                "raiva": int(i["raiva"]),
                "fase2": bool(i["fase2"]),
                "escalado": bool(i["escalado"]),
            }
            for i in TODOS_INIMIGOS
        },
    }
    salvar_save()


def carregar_partida():
    """Restaura um checkpoint manual e volta para a exploracao do mundo."""
    dados = SAVE.get("partida")
    if not isinstance(dados, dict) or dados.get("versao") != 1:
        return False

    try:
        novo_jogo()
        desbloqueios = dados.get("desbloqueios", {})
        if not isinstance(desbloqueios, dict):
            desbloqueios = {}
        SAVE["dificil"] = bool(desbloqueios.get("dificil", False))
        finais_salvos = desbloqueios.get("finais", [])
        SAVE["finais"] = [final for final in finais_salvos if isinstance(final, str)]
        estado = dados.get("estado", {})
        E.vida_max = max(1, int(estado.get("vida_max", E.vida_max)))
        E.vida = max(1, min(E.vida_max, int(estado.get("vida", E.vida))))
        E.nivel = max(1, int(estado.get("nivel", E.nivel)))
        E.exp = max(0, int(estado.get("exp", E.exp)))
        E.moedas = max(0, int(estado.get("moedas", E.moedas)))
        E.mortes = max(0, int(estado.get("mortes", E.mortes)))
        E.poupados = max(0, int(estado.get("poupados", E.poupados)))
        E.bonus_dano = max(0, int(estado.get("bonus_dano", E.bonus_dano)))
        E.dificuldade = max(0, min(2, int(estado.get("dificuldade", E.dificuldade))))
        E.mostrar_trajetoria = E.dificuldade == 0
        E.final_mostrado = bool(estado.get("final_mostrado", False))
        final = estado.get("final", "neutro")
        E.final = final if final in FINAIS else "neutro"

        itens = dados.get("itens", {})
        for chave in ITENS:
            E.itens[chave] = max(0, int(itens.get(chave, E.itens[chave])))

        pos_jogador = dados.get("jogador", [111, 130])
        jogador.topleft = (int(pos_jogador[0]), int(pos_jogador[1]))
        jogador.left = max(ESPESSURA_PAREDE, min(jogador.left, LARGURA_MUNDO - ESPESSURA_PAREDE - jogador.width))
        jogador.top = max(ESPESSURA_PAREDE, min(jogador.top, ALTURA_MUNDO - ESPESSURA_PAREDE - jogador.height))

        bau_aberto = dados.get("bau_aberto", {})
        for bau in BAUS:
            bau["aberto"] = bool(bau_aberto.get(bau["nome"], False))
        segredos = dados.get("segredos", [])
        for indice, obstaculo in enumerate(OBSTACULOS):
            if "segredo" in obstaculo and indice < len(segredos):
                obstaculo["aberto"] = bool(segredos[indice])
        npcs = dados.get("npcs", {})
        for npc in NPCS:
            npc["idx"] = max(0, int(npcs.get(npc["nome"], 0))) % len(npc["falas"])

        inimigos_salvos = dados.get("inimigos", {})
        for inimigo in TODOS_INIMIGOS:
            estado_inimigo = inimigos_salvos.get(inimigo["nome"])
            if not isinstance(estado_inimigo, dict):
                continue
            inimigo["home"] = tuple(map(int, estado_inimigo.get("home", inimigo["home"])))
            inimigo["vida_max"] = max(1, int(estado_inimigo.get("vida_max", inimigo["vida_max"])))
            pos = estado_inimigo.get("pos", inimigo["home"])
            inimigo["retangulo"].center = tuple(map(int, pos))
            limitar_objeto_ao_mundo(inimigo["retangulo"])
            inimigo["pos"] = [float(inimigo["retangulo"].centerx), float(inimigo["retangulo"].centery)]
            inimigo["vivo"] = bool(estado_inimigo.get("vivo", True))
            inimigo["vida"] = max(0, min(inimigo["vida_max"], int(estado_inimigo.get("vida", inimigo["vida_max"]))))
            inimigo["destino"] = estado_inimigo.get("destino")
            inimigo["piedade"] = bool(estado_inimigo.get("piedade", False))
            inimigo["raiva"] = max(0, int(estado_inimigo.get("raiva", 0)))
            inimigo["fase2"] = bool(estado_inimigo.get("fase2", False))
            inimigo["escalado"] = bool(estado_inimigo.get("escalado", False))

        E.modo = MODO_MUNDO
        E.msg = "Partida carregada."
        E.msg_t = 120
        atualizar_camera()
        return True
    except (KeyError, TypeError, ValueError, IndexError):
        return False


def ganhar_exp(qtd):
    linhas = []
    E.exp += qtd
    while E.exp >= exp_necessaria():
        E.exp -= exp_necessaria()
        E.nivel += 1
        E.vida_max += 10
        E.vida = min(E.vida_max, E.vida + 10)
        tocar("levelup")
        linhas.append(f"Subiu para o nível {E.nivel}! Vida máx +10")
    return linhas


def usar_item(chave):
    """Usa um item (retorna o texto do resultado ou None).

    Se o item não foi gasto (ex.: vida já cheia), E.itens[chave] não muda.
    """
    if E.itens.get(chave, 0) <= 0:
        return None
    nome, cura, _, _ = ITENS[chave]
    if chave == "escudo":
        E.itens[chave] -= 1
        E.escudo = 3
        tocar("cura")
        return "Você usou o Escudo! Os próximos 3 golpes serão bloqueados."
    if E.vida >= E.vida_max:
        return "Sua vida já está cheia."
    E.itens[chave] -= 1
    antes = E.vida
    E.vida = min(E.vida_max, E.vida + cura)
    tocar("cura")
    return f"Você usou {nome}. +{E.vida - antes} de vida!"


def aplicar_segredo(tipo):
    """Recompensa de pedras/árvores secretas. Retorna a mensagem."""
    if tipo == "amuleto":
        E.vida_max += 15
        E.vida += 15
        return "Atrás da pedra havia um Amuleto antigo! Vida máxima +15!"
    if tipo == "runa":
        E.bonus_dano += 3
        return "Você encontrou uma Runa de Poder! Seus golpes causam +3 de dano para sempre."
    if tipo == "tesouro":
        E.moedas += 80
        return "Um tesouro escondido! +80 moedas!"
    if tipo == "pocoes":
        E.itens["pocao"] += 3
        return "Um ninho de poções escondido! +3 Poções!"
    if tipo == "escudos":
        E.itens["escudo"] += 2
        return "Escudos abandonados por um velho herói! +2 Escudos!"
    if tipo == "coracao":
        E.vida_max += 10
        E.vida = E.vida_max
        return "Um Fragmento de Coração! Vida máxima +10 e vida restaurada!"
    return "Nada de especial..."

# =========================================================
# EFEITOS VISUAIS
# =========================================================


def criar_particulas(x, y, cor, qtd=20, vel=4.0, vida=40):
    for _ in range(qtd):
        ang = random.random() * math.tau
        v = random.random() * vel + 0.5
        E.particulas.append(
            [x, y, math.cos(ang) * v, math.sin(ang) * v, vida, vida, cor, random.randint(2, 4)]
        )


def texto_flutuante(x, y, txt, cor=BRANCO):
    E.flutuantes.append([x, y, str(txt), cor, 45])


def atualizar_efeitos():
    for p in E.particulas[:]:
        p[0] += p[2]
        p[1] += p[3]
        p[3] += 0.08
        p[4] -= 1
        if p[4] <= 0:
            E.particulas.remove(p)
    for t in E.flutuantes[:]:
        t[1] -= 1
        t[4] -= 1
        if t[4] <= 0:
            E.flutuantes.remove(t)


def desenhar_efeitos():
    for p in E.particulas:
        tam = max(1, int(p[7] * p[4] / p[5]))
        pygame.draw.rect(S, p[6], (int(p[0]), int(p[1]), tam, tam))
    for t in E.flutuantes:
        texto(t[2], int(t[0]), int(t[1]), t[3], fonte_g if len(t[2]) < 4 else fonte, centro=True)


def iniciar_tremor_tela(forca, duracao):
    E.tremor_t = max(E.tremor_t, duracao)
    E.tremor_f = max(E.tremor_f, forca)


def mostrar_mensagem(txt, duracao=150):
    E.msg = txt
    E.msg_t = duracao


# =========================================================
# MUNDO: DESENHO
# =========================================================


def atualizar_camera(alvo=None):
    camera.center = (alvo or jogador).center
    camera.left = max(0, camera.left)
    camera.top = max(0, camera.top)
    camera.right = min(LARGURA_MUNDO, camera.right)
    camera.bottom = min(ALTURA_MUNDO, camera.bottom)


def desenhar_grama():
    ini_x = (camera.x // TAM_BLOCO) * TAM_BLOCO
    ini_y = (camera.y // TAM_BLOCO) * TAM_BLOCO
    for ym in range(ini_y, camera.y + ALTURA_JOGO + TAM_BLOCO, TAM_BLOCO):
        for xm in range(ini_x, camera.x + LARGURA_JOGO + TAM_BLOCO, TAM_BLOCO):
            # pula blocos que ficam inteiros fora da área jogável (sob as paredes)
            if (xm + TAM_BLOCO <= 50 or ym + TAM_BLOCO <= 50
                    or xm >= LARGURA_MUNDO - 50 or ym >= ALTURA_MUNDO - 50):
                continue
            S.blit(textura_grama, (xm - camera.x, ym - camera.y))


def desenhar_caminhos():
    area = camera.inflate(100, 100)
    for c in caminhos:
        if not c.colliderect(area):
            continue
        pygame.draw.rect(S, TERRA, (c.x - camera.x, c.y - camera.y, c.width, c.height))
        for x in range(c.x, c.right, 45):
            if not area.left <= x <= area.right:
                continue
            for y in range(c.y, c.bottom, 40):
                if not area.top <= y <= area.bottom:
                    continue
                xt, yt = x - camera.x, y - camera.y
                if -10 < xt < LARGURA_JOGO + 10 and -10 < yt < ALTURA_JOGO + 10:
                    pygame.draw.circle(S, TERRA_CLARA, (xt + 10, yt + 10), 2)


def desenhar_decoracoes():
    for x, y in detalhes_grama:
        xt, yt = x - camera.x, y - camera.y
        if -10 < xt < LARGURA_JOGO + 10 and -10 < yt < ALTURA_JOGO + 10:
            pygame.draw.line(S, VERDE_GRAMA_ESCURO, (xt, yt + 5), (xt - 2, yt), 1)
            pygame.draw.line(S, VERDE_GRAMA_ESCURO, (xt + 2, yt + 5), (xt + 3, yt), 1)
    for f in flores:
        xt, yt = f["x"] - camera.x, f["y"] - camera.y
        if -10 < xt < LARGURA_JOGO + 10 and -10 < yt < ALTURA_JOGO + 10:
            pygame.draw.line(S, (35, 100, 40), (xt, yt + 4), (xt, yt + 9), 1)
            pygame.draw.circle(S, f["cor"], (xt, yt + 2), 3)


def _desenhar_tijolo_mapa(x, y, largura, altura, variacao):
    tela_x, tela_y = x - camera.x, y - camera.y
    rng = random.Random((x * 131 + y * 719 + variacao * 137) & 0xFFFFFFFF)
    tons = [(92, 101, 113), (105, 113, 124), (83, 92, 104), (114, 119, 125)]
    cor = tons[variacao % len(tons)]
    contorno = [
        (tela_x + 5, tela_y + 3),
        (tela_x + largura - 9, tela_y + 2),
        (tela_x + largura - 3, tela_y + 8),
        (tela_x + largura - 2, tela_y + altura - 8),
        (tela_x + largura - 8, tela_y + altura - 3),
        (tela_x + 8, tela_y + altura - 2),
        (tela_x + 2, tela_y + altura - 8),
        (tela_x + 3, tela_y + 9),
    ]
    pygame.draw.polygon(S, (38, 45, 55), contorno)
    face = [
        (tela_x + 7, tela_y + 6),
        (tela_x + largura - 10, tela_y + 5),
        (tela_x + largura - 6, tela_y + 10),
        (tela_x + largura - 6, tela_y + altura - 10),
        (tela_x + largura - 11, tela_y + altura - 6),
        (tela_x + 10, tela_y + altura - 5),
        (tela_x + 6, tela_y + altura - 10),
        (tela_x + 6, tela_y + 10),
    ]
    pygame.draw.polygon(S, cor, face)
    pygame.draw.line(S, (158, 166, 174), face[0], face[1], 2)
    pygame.draw.line(S, (158, 166, 174), face[0], face[-1], 2)
    sombra = (max(0, cor[0] - 35), max(0, cor[1] - 35), max(0, cor[2] - 35))
    pygame.draw.line(S, sombra, face[4], face[5], 3)
    pygame.draw.line(S, sombra, face[3], face[4], 2)

    # Brilhos de pixel e tufos de musgo quebram a superfície da pedra.
    pygame.draw.rect(S, (184, 190, 194), (tela_x + 11, tela_y + 9, 5, 2))
    pygame.draw.rect(S, (133, 143, 151), (tela_x + largura - 20, tela_y + 12, 4, 2))
    if rng.random() < 0.3:
        mx = tela_x + rng.randint(7, max(8, largura - 15))
        my = tela_y + rng.choice((5, max(5, altura - 9)))
        verdes = ((49, 77, 48), (66, 99, 55), (83, 119, 64), (112, 139, 74))
        for _ in range(rng.randint(10, 16)):
            px = mx + rng.randint(-7, 9)
            py = my + rng.randint(-4, 4)
            pygame.draw.rect(S, rng.choice(verdes), (px, py, rng.randint(2, 5), rng.randint(2, 3)))


def _desenhar_tijolo_lateral(x, y, largura, altura, variacao):
    """Blocos mais retos e escuros para distinguir as paredes laterais."""
    tx, ty = x - camera.x, y - camera.y
    tons = ((71, 82, 96), (79, 89, 101), (66, 77, 90), (86, 94, 103))
    cor = tons[variacao % len(tons)]
    pygame.draw.rect(S, (35, 43, 53), (tx, ty, largura, altura))
    pygame.draw.rect(S, cor, (tx + 3, ty + 3, largura - 6, altura - 6))
    pygame.draw.line(S, (137, 148, 158), (tx + 4, ty + 4), (tx + largura - 5, ty + 4), 2)
    pygame.draw.line(S, (137, 148, 158), (tx + 4, ty + 4), (tx + 4, ty + altura - 5), 2)
    pygame.draw.line(S, (43, 52, 63), (tx + 4, ty + altura - 4), (tx + largura - 4, ty + altura - 4), 2)
    pygame.draw.line(S, (43, 52, 63), (tx + largura - 4, ty + 4), (tx + largura - 4, ty + altura - 4), 2)
    pygame.draw.line(S, (105, 116, 127), (tx + 7, ty + altura // 2), (tx + largura - 8, ty + altura // 2), 1)


def desenhar_parede_pedras():
    """Desenha a muralha de blocos irregulares, só nas paredes visíveis na câmera."""
    largura, altura, passo_x, passo_y, fiadas = 54, 34, 48, 28, 3
    espessura = ESPESSURA_PAREDE
    inicio_x = max(0, (camera.left // passo_x) * passo_x - passo_x)
    fim_x = min(LARGURA_MUNDO, camera.right + passo_x)
    inicio_y = max(0, (camera.top // passo_x) * passo_x - passo_x)
    fim_y = min(ALTURA_MUNDO, camera.bottom + passo_x)

    for base_y in (0, ALTURA_MUNDO - espessura):
        if not camera.colliderect((0, base_y, LARGURA_MUNDO, espessura)):
            continue  # parede horizontal fora da tela: não desenha
        for fiada in range(fiadas):
            y = base_y + fiada * passo_y
            offset = (passo_x // 2) if fiada % 2 else 0
            for x in range(inicio_x - passo_x + offset, fim_x + passo_x, passo_x):
                idx = (x // passo_x + fiada * 3) % 4
                _desenhar_tijolo_mapa(x, y, largura, altura, idx)

    for base_x in (0, LARGURA_MUNDO - espessura):
        if not camera.colliderect((base_x, 0, espessura, ALTURA_MUNDO)):
            continue  # parede vertical fora da tela: não desenha
        for coluna in range(fiadas):
            x = base_x + coluna * passo_y
            offset = (passo_x // 2) if coluna % 2 else 0
            for y in range(inicio_y - passo_x + offset, fim_y + passo_x, passo_x):
                idx = (y // passo_x + coluna * 3) % 4
                _desenhar_tijolo_lateral(x, y, altura, largura, idx)


def desenhar_obstaculo(o):
    r = o["retangulo"]
    img = o["imagem"]
    S.blit(img, img.get_rect(center=(r.centerx - camera.x, r.centery - camera.y)))
    if o.get("chefe_secreto") and CHEFE_SECRETO["vivo"]:
        x, y = r.centerx - camera.x, r.top - camera.y
        brilho = 4 + int(abs(math.sin(E.tick / 20)) * 3)
        pygame.draw.circle(S, (190, 110, 255), (x, y - 8), brilho)
        pygame.draw.circle(S, (245, 225, 255), (x, y - 8), 2)
    elif o.get("segredo") and not o["aberto"]:
        # Brilhinho discreto quando o jogador chega perto de um segredo.
        dist = math.hypot(jogador.centerx - r.centerx, jogador.centery - r.centery)
        if dist < 150:
            x = r.centerx - camera.x + int(math.sin(E.tick / 9) * 12)
            y = r.top - camera.y - 4 + int(math.cos(E.tick / 7) * 5)
            pygame.draw.circle(S, (255, 240, 140), (x, y), 3)
            pygame.draw.circle(S, BRANCO, (x, y), 1)
            x2 = r.centerx - camera.x - int(math.sin(E.tick / 11) * 14)
            pygame.draw.circle(S, (255, 220, 120), (x2, y + 12), 2)


def desenhar_npc(n):
    r = n["ret"]
    x, y = r.centerx - camera.x, r.bottom - camera.y
    pygame.draw.ellipse(S, (30, 70, 35), (x - 16, y - 6, 32, 10))
    S.blit(n["imagem"], n["imagem"].get_rect(midbottom=(x, y - 2)))
    texto(n["nome"], x, y - 74, (200, 255, 200), fonte_p, centro=True)


def desenhar_bau(b):
    r = b["ret"]
    x, y = r.x - camera.x, r.y - camera.y
    pygame.draw.rect(S, (120, 75, 35), (x, y + 8, r.width, r.height - 8))
    if b["aberto"]:
        pygame.draw.rect(S, (60, 40, 20), (x + 3, y + 10, r.width - 6, 8))
        pygame.draw.rect(S, (150, 100, 50), (x, y - 4, r.width, 8))
    else:
        pygame.draw.rect(S, (150, 100, 50), (x, y, r.width, 12), border_top_left_radius=8, border_top_right_radius=8)
        pygame.draw.rect(S, AMARELO, (x + r.width // 2 - 3, y + 8, 6, 8))
    pygame.draw.rect(S, PRETO, (x, y, r.width, r.height), 1)


def desenhar_inimigo_mundo(i):
    r = i["retangulo"]
    cx, cy = r.centerx - camera.x, r.centery - camera.y
    pygame.draw.ellipse(S, (30, 70, 35), (cx - 20, cy + 14, 40, 12))
    if i["imagem"] is not None:
        S.blit(i["imagem"], i["imagem"].get_rect(center=(cx, cy)))
    else:
        pygame.draw.rect(S, i["cor"], (r.x - camera.x, r.y - camera.y, r.width, r.height))
    texto(i["nome"], cx, r.y - camera.y - 30, BRANCO, fonte, centro=True)
    if i.get("alerta"):
        texto("!", cx, r.y - camera.y - 50, VERMELHO, fonte_g, centro=True)


def desenhar_jogador_mundo():
    img = animacoes_jogador[E.direcao][E.frame_j]
    S.blit(img, img.get_rect(midbottom=(jogador.centerx - camera.x, jogador.bottom - camera.y)))


def chefes_restantes():
    return sum(1 for i in INIMIGOS if i["vivo"])


def desenhar_minimapa():
    esc = 0.04
    x0, y0 = 662, 56
    w, h = int(LARGURA_MUNDO * esc), int(ALTURA_MUNDO * esc)
    pygame.draw.rect(S, (14, 34, 16), (x0, y0, w, h))
    for c in caminhos:
        pygame.draw.rect(S, TERRA, (x0 + int(c.x * esc), y0 + int(c.y * esc), max(1, int(c.width * esc)), max(1, int(c.height * esc))))
    for b in BAUS:
        if not b["aberto"]:
            pygame.draw.rect(S, (200, 150, 60), (x0 + int(b["ret"].centerx * esc) - 1, y0 + int(b["ret"].centery * esc) - 1, 2, 2))
    for i in INIMIGOS:
        if i["vivo"]:
            pygame.draw.circle(S, i["cor"], (x0 + int(i["retangulo"].centerx * esc), y0 + int(i["retangulo"].centery * esc)), 2)
    pygame.draw.rect(S, BRANCO, (x0 + int(camera.x * esc), y0 + int(camera.y * esc), int(LARGURA_JOGO * esc), int(ALTURA_JOGO * esc)), 1)
    if (E.tick // 15) % 2 == 0:
        pygame.draw.circle(S, BRANCO, (x0 + int(jogador.centerx * esc), y0 + int(jogador.centery * esc)), 2)
    pygame.draw.rect(S, BRANCO, (x0, y0, w, h), 1)
    texto(f"Chefes: {chefes_restantes()}", x0, y0 + h + 4, BRANCO, fonte_p)


def desenhar_hud_mundo():
    pygame.draw.rect(S, (0, 0, 0), (10, 8, 250, 46))
    texto(f"LV {E.nivel}", 18, 12, AMARELO, fonte_p)
    barra(70, 14, 120, 12, E.vida, E.vida_max, VERDE)
    texto(f"{E.vida}/{E.vida_max}", 196, 12, BRANCO, fonte_p)
    texto(f"Moedas: {E.moedas}", 18, 32, AMARELO, fonte_p)
    texto(f"Poção(Q): {E.itens['pocao']}", 130, 32, BRANCO, fonte_p)
    texto("ESC = pausa", 690, 10, BRANCO, fonte_p)
    texto("WASD andar | E interagir | Q poção", 20, 575, (230, 230, 230), fonte_p)
    if E.modo_teste:
        texto("MODO DE TESTE", 640, 32, AMARELO, fonte_p)
    desenhar_minimapa()


def desenhar_caixa_mensagem():
    if E.msg_t <= 0 or not E.msg:
        return
    linhas = quebrar(E.msg, 560, fonte_p)
    altura = 20 + len(linhas) * 20
    ret = pygame.Rect(100, 560 - altura, 600, altura)
    pygame.draw.rect(S, PRETO, ret)
    pygame.draw.rect(S, BRANCO, ret, 2)
    for k, l in enumerate(linhas):
        texto(l, 120, ret.y + 10 + k * 20, BRANCO, fonte_p)


def desenhar_mundo():
    S.fill(VERDE_ARVORE_ESCURO)
    desenhar_grama()
    desenhar_caminhos()
    desenhar_decoracoes()
    desenhar_parede_pedras()

    vis = camera.inflate(260, 260)
    itens = []
    for o in OBSTACULOS:
        if o["retangulo"].colliderect(vis):
            itens.append((o["retangulo"].bottom, lambda o=o: desenhar_obstaculo(o)))
    for b in BAUS:
        if b["ret"].colliderect(vis):
            itens.append((b["ret"].bottom, lambda b=b: desenhar_bau(b)))
    for n in NPCS:
        if n["ret"].colliderect(vis):
            itens.append((n["ret"].bottom, lambda n=n: desenhar_npc(n)))
    for i in INIMIGOS:
        if i["vivo"] and i["retangulo"].colliderect(vis):
            itens.append((i["retangulo"].bottom, lambda i=i: desenhar_inimigo_mundo(i)))
    itens.append((jogador.bottom, desenhar_jogador_mundo))
    itens.sort(key=lambda t: t[0])
    for _, f in itens:
        f()

    if E.edicao:
        lista = objetos_editaveis()
        nome, r, _ = lista[E.idx_edicao % len(lista)]
        pygame.draw.rect(S, AMARELO, (r.x - camera.x, r.y - camera.y, r.width, r.height), 2)
        pygame.draw.rect(S, PRETO, (10, 470, 780, 100))
        texto(f"EDITANDO: {nome}  ({E.idx_edicao % len(lista) + 1}/{len(lista)})", 20, 478, AMARELO)
        texto("Setas: mover | Shift: rápido | Tab / Shift+Tab: próximo/anterior | F2: sair", 20, 510, BRANCO, fonte_p)
        texto(f"F3 hitboxes: {'ligadas' if E.hitboxes else 'desligadas'} | +/- tamanho", 20, 538)
        if E.hitboxes:
            for o in OBSTACULOS:
                rr = o["retangulo"]
                pygame.draw.rect(S, (80, 220, 255), (rr.x - camera.x, rr.y - camera.y, rr.width, rr.height), 1)
            for i in INIMIGOS:
                rr = i["retangulo"]
                pygame.draw.rect(S, (255, 100, 100), (rr.x - camera.x, rr.y - camera.y, rr.width, rr.height), 1)

    desenhar_hud_mundo()
    desenhar_efeitos()
    desenhar_caixa_mensagem()


# =========================================================
# MUNDO: LÓGICA
# =========================================================

_solidos_cache = None


def solidos():
    """Retângulos sólidos do mundo. A lista é montada uma vez e reaproveitada.

    Os Rects são os mesmos objetos do jogo (o editor os altera no lugar),
    então o cache continua valendo depois de mover/redimensionar algo.
    """
    global _solidos_cache
    if _solidos_cache is None:
        _solidos_cache = (
            [o["retangulo"] for o in OBSTACULOS]
            + [n["ret"] for n in NPCS]
            + [b["ret"] for b in BAUS]
            + [
                pygame.Rect(0, 0, LARGURA_MUNDO, ESPESSURA_PAREDE),
                pygame.Rect(0, ALTURA_MUNDO - ESPESSURA_PAREDE, LARGURA_MUNDO, ESPESSURA_PAREDE),
                pygame.Rect(0, 0, ESPESSURA_PAREDE, ALTURA_MUNDO),
                pygame.Rect(LARGURA_MUNDO - ESPESSURA_PAREDE, 0, ESPESSURA_PAREDE, ALTURA_MUNDO),
            ]
        )
    return _solidos_cache


def atualizar_inimigos_mundo():
    sol = solidos()
    for i in INIMIGOS:
        if not i["vivo"]:
            continue
        i["tick"] += 1
        if i["cooldown"] > 0:
            i["cooldown"] -= 1
        r = i["retangulo"]
        dist = math.hypot(jogador.centerx - r.centerx, jogador.centery - r.centery)
        voa = i["mov"] == "voa"

        if i["mov"] != "fixo":
            dx = dy = 0.0
            if dist < 170 and i["cooldown"] == 0:
                i["alerta"] = True
                vx, vy = jogador.centerx - r.centerx, jogador.centery - r.centery
                n = math.hypot(vx, vy) or 1
                v = i["vel"] * 1.25
                dx, dy = vx / n * v, vy / n * v
            else:
                i["alerta"] = False
                if i["alvo"] is None or i["tick"] % 150 == 0:
                    hx, hy = i["home"]
                    i["alvo"] = (hx + random.randint(-80, 80), hy + random.randint(-80, 80))
                vx, vy = i["alvo"][0] - r.centerx, i["alvo"][1] - r.centery
                n = math.hypot(vx, vy)
                if n > 4:
                    v = i["vel"] * 0.6
                    if i["mov"] == "pula" and (i["tick"] % 60) >= 30:
                        v = 0
                    dx, dy = vx / n * v, vy / n * v

            for eixo in (0, 1):
                px, py = i["pos"]
                if eixo == 0:
                    px += dx
                else:
                    py += dy
                teste = r.copy()
                teste.center = (int(px), int(py))
                if not voa and teste.collidelist(sol) != -1:
                    continue
                i["pos"] = [px, py]
                r.center = (int(px), int(py))
            limitar_objeto_ao_mundo(r)
            i["pos"] = [float(r.centerx), float(r.centery)]

        # Contato com o jogador inicia a batalha.
        if i["cooldown"] == 0 and r.colliderect(jogador.inflate(10, 10)):
            iniciar_transicao(i)
            return


def atualizar_animacao_flowey():
    E.cont_flowey += 1
    if E.cont_flowey >= VELOCIDADE_ANIMACAO_FLOWEY:
        E.cont_flowey = 0
        E.frame_flowey = (E.frame_flowey + 1) % len(ANIM_FLOWEY)
    for i in INIMIGOS:
        if i["nome"] == "Flowey":
            i["imagem"] = ANIM_FLOWEY[E.frame_flowey]


def atualizar_mundo():
    teclas = pygame.key.get_pressed()
    if E.edicao:
        mover_objeto_edicao(teclas)
        lista = objetos_editaveis()
        atualizar_camera(lista[E.idx_edicao % len(lista)][1])
        return

    dx = dy = 0
    if teclas[pygame.K_w]:
        dy -= VELOCIDADE_JOGADOR
    if teclas[pygame.K_s]:
        dy += VELOCIDADE_JOGADOR
    if teclas[pygame.K_a]:
        dx -= VELOCIDADE_JOGADOR
    if teclas[pygame.K_d]:
        dx += VELOCIDADE_JOGADOR

    if dy < 0:
        E.direcao = "cima"
    elif dy > 0:
        E.direcao = "baixo"
    elif dx < 0:
        E.direcao = "esquerda"
    elif dx > 0:
        E.direcao = "direita"

    if dx or dy:
        E.cont_anim_j += 1
        if E.cont_anim_j >= VELOCIDADE_ANIMACAO_JOGADOR:
            E.cont_anim_j = 0
            E.frame_j = (E.frame_j + 1) % 3
    else:
        E.frame_j = 0
        E.cont_anim_j = 0

    if dx and dy:
        dx = int(dx / abs(dx) * VELOCIDADE_JOGADOR * 0.9)
        dy = int(dy / abs(dy) * VELOCIDADE_JOGADOR * 0.9)

    sol = solidos()

    jogador.x += dx
    jogador.left = max(ESPESSURA_PAREDE, jogador.left)
    jogador.right = min(LARGURA_MUNDO - ESPESSURA_PAREDE, jogador.right)
    for r in sol:
        if jogador.colliderect(r):
            if dx > 0:
                jogador.right = r.left
            elif dx < 0:
                jogador.left = r.right

    jogador.y += dy
    jogador.top = max(ESPESSURA_PAREDE, jogador.top)
    jogador.bottom = min(ALTURA_MUNDO - ESPESSURA_PAREDE, jogador.bottom)
    for r in sol:
        if jogador.colliderect(r):
            if dy > 0:
                jogador.bottom = r.top
            elif dy < 0:
                jogador.top = r.bottom

    atualizar_camera()
    atualizar_inimigos_mundo()


def abrir_bau(b):
    b["aberto"] = True
    tipo, qtd = b["conteudo"]
    tocar("bau")
    if tipo == "moedas":
        E.moedas += qtd
        mostrar_mensagem(f"Você encontrou {qtd} moedas!")
    elif tipo == "vida_max":
        E.vida_max += qtd
        E.vida += qtd
        mostrar_mensagem(f"Um Cristal de Vida! Vida máxima +{qtd}!")
    else:
        E.itens[tipo] += qtd
        mostrar_mensagem(f"Você encontrou {qtd}x {ITENS[tipo][0]}!")


def falar(npc):
    if npc["tipo"] == "guia":
        k = npc["idx"]
        linhas = [npc["falas"][k % len(npc["falas"])], npc["falas"][(k + 1) % len(npc["falas"])]]
        npc["idx"] = (k + 2) % len(npc["falas"])
        acao = None
    else:
        linhas = list(npc["falas"])
        acao = abrir_loja
    E.dialogo = {"nome": npc["nome"], "linhas": linhas, "i": 0, "acao": acao}
    E.modo = MODO_DIALOGO
    tocar("fala")


def abrir_loja():
    E.sel_loja = 0
    E.modo = MODO_LOJA


def interagir():
    area = jogador.inflate(30, 30)
    for o in OBSTACULOS:
        if not area.colliderect(o["retangulo"]):
            continue
        if o.get("chefe_secreto"):
            if CHEFE_SECRETO["vivo"]:
                iniciar_transicao(CHEFE_SECRETO)
            else:
                mostrar_mensagem("A árvore está em silêncio.")
            return
        if o.get("segredo") and not o["aberto"]:
            o["aberto"] = True
            msg = aplicar_segredo(o["segredo"])
            tocar("bau")
            criar_particulas(o["retangulo"].centerx - camera.x, o["retangulo"].centery - camera.y, AMARELO, 25)
            achados = sum(1 for x in OBSTACULOS if x.get("segredo") and x["aberto"])
            mostrar_mensagem(f"{msg}\nSegredos: {achados}/{SEGREDOS_TOTAL}", 220)
            return
    for n in NPCS:
        if area.inflate(20, 20).colliderect(n["ret"]):
            falar(n)
            return
    for b in BAUS:
        if area.colliderect(b["ret"]) and not b["aberto"]:
            abrir_bau(b)
            return
    for i in INIMIGOS:
        if i["vivo"] and area.colliderect(i["retangulo"]):
            iniciar_transicao(i)
            return
    mostrar_mensagem("Não há ninguém perto.", 90)

# =========================================================
# BATALHA: ESTADO
# =========================================================

CAIXA_CENTRO = (400, 290)
CAIXA = pygame.Rect(0, 0, 360, 220)
CAIXA.center = CAIXA_CENTRO
CAIXAS = {
    "normal": (360, 220),
    "estreita": (220, 220),
    "baixa": (360, 130),
    "pequena": (220, 140),
    "azul": (360, 190),
}

coracao = pygame.Rect(0, 0, 20, 20)


def hitbox_coracao():
    """Área que realmente leva dano: menor que o desenho do coração."""
    return coracao.inflate(-8, -8)


ACOES = ["LUTAR", "AGIR", "ITEM", "POUPAR"]
INVENCIBILIDADE = (60, 45, 36)
MULT_DANO = (0.75, 1.0, 1.0)
PADROES = {  # intervalo entre ataques, multiplicador de velocidade
    "normal": (45, 1.0),
    "rapido": (30, 1.2),
    "rajada": (70, 1.0),
    "caotico": (25, 1.3),
    "paredao": (85, 1.0),
}
# Tipos que usam o aviso de "trajetória" do modo FÁCIL (os novos têm aviso próprio).
TIPOS_ANTIGOS = {"lingua", "raiz", "cobra", "mosca", "petala", "morcego", "gota", "espinho"}
_imagens_batalha = {}


def ajustar_caixa(modo):
    CAIXA.size = CAIXAS[modo]
    CAIXA.center = CAIXA_CENTRO


def limpar_estado_batalha():
    E.inimigo = None
    E.fase = "menu"
    E.sel_acao = 0
    E.sel_sub = 0
    E.msg_batalha = ""
    E.timer = 0
    E.timer_fase = 0
    E.timer_spawn = 0
    E.ataques = []
    E.tipo_turno = None
    E.padrao = "normal"
    E.intervalo = 45
    E.vm = 1.0
    E.azul = False
    E.preso = False
    E.t_lento = 0
    E.t_nevoa = 0
    E.veneno = False
    E.escudo = 0
    E.invencivel = 0
    E.vy = 0.0
    E.no_chao = False
    E.fala = ""
    E.resultado = None
    E.trans = 0
    E.pendente = None
    E.minigame_x = 230
    E.minigame_dir = 1
    E.fx = 0.0
    E.fy = 0.0
    E.t_tremor_inimigo = 0
    ajustar_caixa("normal")
    coracao.center = CAIXA.center


def iniciar_transicao(inimigo):
    E.pendente = inimigo
    E.trans = 0
    E.modo = MODO_TRANSICAO
    tocar("transicao")
    tocar_musica(None)


def iniciar_batalha(inimigo):
    limpar_estado_batalha()
    E.modo = MODO_BATALHA
    E.inimigo = inimigo
    if inimigo is CHEFE_SECRETO and not inimigo["escalado"]:
        # A rota violenta deixa a Quimera mais forte.
        inimigo["vida_max"] = 200 + 50 * E.mortes
        inimigo["vida"] = inimigo["vida_max"]
        inimigo["escalado"] = True
    E.msg_batalha = f"{inimigo['nome']} apareceu!"
    coracao.center = CAIXA.center
    E.fx, E.fy = float(coracao.x), float(coracao.y)
    tocar_musica(inimigo["nome"])


# =========================================================
# BATALHA: DANO
# =========================================================


def pode_ser_atingido():
    return E.invencivel <= 0 and not E.preso


def dano_jogador(base, efeito=None):
    """Aplica dano no coração, respeitando escudo, dificuldade e força do chefe."""
    if E.escudo > 0:
        E.escudo -= 1
        E.invencivel = 20
        tocar("bloqueio")
        texto_flutuante(coracao.centerx, coracao.top - 10, "BLOQ", (120, 200, 255))
        return
    forca = E.inimigo.get("forca", 1.0) if E.inimigo else 1.0
    dano = max(1, int(round(base * MULT_DANO[E.dificuldade] * forca)))
    E.vida = max(0, E.vida - dano)
    E.invencivel = INVENCIBILIDADE[E.dificuldade]
    tocar("dano")
    iniciar_tremor_tela(2, 6)
    criar_particulas(coracao.centerx, coracao.centery, VERMELHO, 8, 3, 20)
    texto_flutuante(coracao.centerx, coracao.top - 10, f"-{dano}", VERMELHO)
    if efeito:
        efeito()
    if E.vida <= 0:
        game_over()


def dano_base():
    return random.randint(4, 9)


def efeito_lento():
    E.t_lento = max(E.t_lento, 180)


def efeito_nevoa():
    E.t_nevoa = max(E.t_nevoa, 240)


def efeito_veneno():
    E.veneno = True


def efeito_roubo():
    """Ladino: rouba moedas ao acertar."""
    perdido = min(E.moedas, random.randint(2, 5))
    if perdido > 0:
        E.moedas -= perdido
        texto_flutuante(coracao.centerx, coracao.top - 30, f"-{perdido}$", AMARELO)


def game_over():
    E.modo = MODO_GAME_OVER
    E.morreu_para = E.inimigo
    E.ataques = []
    E.preso = False
    tocar_musica(None)
    tocar("game_over")


def continuar_apos_game_over():
    """Revive no mundo mantendo o progresso (perde metade das moedas)."""
    E.moedas //= 2
    E.vida = E.vida_max
    for i in TODOS_INIMIGOS:
        if i["vivo"]:
            i["vida"] = i["vida_max"]
            i["piedade"] = False
            i["raiva"] = 0
            i["fase2"] = False
            i["retangulo"].center = i["home"]
            i["pos"] = [float(i["retangulo"].centerx), float(i["retangulo"].centery)]
            i["cooldown"] = 240
    limpar_estado_batalha()
    E.modo = MODO_MUNDO
    tocar_musica("mundo")


# =========================================================
# BATALHA: ATAQUES (criação)
# =========================================================


def adicionar_ataque(a):
    a["aviso"] = 24 if (E.mostrar_trajetoria and a["tipo"] in TIPOS_ANTIGOS) else 0
    E.ataques.append(a)


def central(a, b):
    """Sorteio que favorece o centro, mas permite as bordas."""
    if b <= a:
        return a
    return int(random.triangular(a, b, (a + b) / 2))


def vel(v):
    return max(1, int(round(v * E.vm)))


def aviso_t():
    """Tempo de aviso (frames) dos ataques novos: maior na dificuldade fácil."""
    return (44, 34, 26)[E.dificuldade]


def ret_haste(lado, comp, centro, esp):
    comp = int(comp)
    if lado == "esquerda":
        return pygame.Rect(CAIXA.left, centro - esp // 2, comp, esp)
    if lado == "direita":
        return pygame.Rect(CAIXA.right - comp, centro - esp // 2, comp, esp)
    if lado == "cima":
        return pygame.Rect(centro - esp // 2, CAIXA.top, esp, comp)
    return pygame.Rect(centro - esp // 2, CAIXA.bottom - comp, esp, comp)


def centro_aleatorio(lado, margem=10):
    if lado in ("esquerda", "direita"):
        return central(CAIXA.top + margem, CAIXA.bottom - margem)
    return central(CAIXA.left + margem, CAIXA.right - margem)


def spawn_haste(tipo, lado=None, centro=None, esp=None, velocidade=6):
    lado = lado or random.choice(["cima", "baixo", "esquerda", "direita"])
    esp = esp or (16 if tipo == "lingua" else 14)
    if centro is None:
        centro = centro_aleatorio(lado, esp // 2 + 4)
    maximo = CAIXA.width if lado in ("esquerda", "direita") else CAIXA.height
    adicionar_ataque({
        "tipo": tipo, "lado": lado, "centro": centro, "esp": esp,
        "vel": vel(velocidade), "max": maximo, "atual": 0, "fase": "crescendo",
        "preso": False, "ret": ret_haste(lado, 0, centro, esp),
    })


def spawn_paredao(tipo):
    """Fileira de línguas/raízes/cobras com um corredor seguro de 2 colunas."""
    lado = random.choice(["cima", "baixo", "esquerda", "direita"])
    comprimento_borda = CAIXA.width if lado in ("cima", "baixo") else CAIXA.height
    inicio = (CAIXA.left if lado in ("cima", "baixo") else CAIXA.top)
    n = comprimento_borda // 36
    margem = (comprimento_borda - n * 36) // 2
    buraco = random.randint(1, n - 3)
    for k in range(n):
        if k in (buraco, buraco + 1):
            continue
        centro = inicio + margem + k * 36 + 18
        spawn_haste(tipo, lado, centro, esp=24, velocidade=7)


def spawn_mosca(lado=None):
    lado = lado or random.choice(["cima", "baixo", "esquerda", "direita"])
    t = 12
    v = vel(random.randint(5, 8))
    if lado == "cima":
        x, y, mov = central(CAIXA.left, CAIXA.right - t), CAIXA.top - t, [0, v]
    elif lado == "baixo":
        x, y, mov = central(CAIXA.left, CAIXA.right - t), CAIXA.bottom, [0, -v]
    elif lado == "esquerda":
        x, y, mov = CAIXA.left - t, central(CAIXA.top, CAIXA.bottom - t), [v, 0]
    else:
        x, y, mov = CAIXA.right, central(CAIXA.top, CAIXA.bottom - t), [-v, 0]
    adicionar_ataque({"tipo": "mosca", "ret": pygame.Rect(x, y, t, t), "mov": mov, "lado": lado})


def spawn_petalas(qtd=8):
    for _ in range(qtd):
        p = pygame.Rect(central(CAIXA.left + 5, CAIXA.right - 15), CAIXA.top - 20, 10, 10)
        adicionar_ataque({"tipo": "petala", "ret": p, "vel": vel(random.randint(2, 5))})


def spawn_morcegos(padrao):
    qtd = {"normal": 4, "rapido": 6, "rajada": 8}.get(padrao, random.randint(4, 8))
    sentido = random.choice((1, -1))
    v = vel(4 if padrao == "normal" else 5)
    centro_y = central(CAIXA.top + 14, CAIXA.bottom - 30)
    for k in range(qtd):
        x = CAIXA.left - 20 - k * 12 if sentido > 0 else CAIXA.right + k * 12
        y = centro_y + ((k % 3) - 1) * 14
        adicionar_ataque({
            "tipo": "morcego", "ret": pygame.Rect(x, y, 20, 16), "mov": sentido * v,
            "linha_y": y + 8, "fase_anim": random.random() * math.tau, "t": 0,
        })


def spawn_gotas(padrao):
    qtd = {"normal": 2, "rapido": 4, "rajada": 7}.get(padrao, random.randint(3, 8))
    for _ in range(qtd):
        x = central(CAIXA.left + 8, CAIXA.right - 20)
        adicionar_ataque({
            "tipo": "gota", "ret": pygame.Rect(x, CAIXA.top, 12, 18), "vel": vel(random.randint(3, 5)),
            "x_base": x, "fase_anim": random.random() * math.tau, "t": 0,
        })


def spawn_espinho(lado=None):
    """Espinho no chão (para o coração azul pular)."""
    lado = lado or random.choice(("esquerda", "direita"))
    w, h = random.randint(14, 24), random.randint(16, 28)
    x = CAIXA.left - w if lado == "esquerda" else CAIXA.right
    v = vel(4) * (1 if lado == "esquerda" else -1)
    adicionar_ataque({"tipo": "espinho", "ret": pygame.Rect(x, CAIXA.bottom - h, w, h), "mov": v})


# ---------------------------------------------------------
# NOVOS ATAQUES (chefes de classe)
# ---------------------------------------------------------
# proj  = projétil genérico (adaga, flecha, dardo, orbe, machado, rocha,
#         javali, lobo) com aviso em linha vermelha antes de sair
# corte = faixa/área que pisca em vermelho (aviso) e depois machuca
# anel  = onda circular com uma abertura por onde dá para passar
# barra = muralha que atravessa a arena com uma brecha


def spawn_proj(forma, x, y, vx, vy, tam, dano=None, efeito=None, delay=0, guia=0, vida=240):
    r = pygame.Rect(0, 0, *tam)
    r.center = (int(x), int(y))
    adicionar_ataque({
        "tipo": "proj", "forma": forma, "ret": r, "pos": [float(x), float(y)],
        "v": [float(vx), float(vy)], "dano": dano, "efeito": efeito,
        "delay": int(delay), "guia": guia, "t": 0, "vida": vida,
        "ang": random.random() * 360.0,
    })


def spawn_mira(forma, n, v, tam, dano=None, efeito=None, delay=0, jit=0, guia=0, vida=240, espaco=8):
    """Projéteis que saem das bordas da arena e miram onde o coração está agora."""
    for k in range(n):
        lado = random.choice(("cima", "baixo", "esquerda", "direita"))
        if lado == "cima":
            x, y = central(CAIXA.left, CAIXA.right), CAIXA.top - 30
        elif lado == "baixo":
            x, y = central(CAIXA.left, CAIXA.right), CAIXA.bottom + 30
        elif lado == "esquerda":
            x, y = CAIXA.left - 30, central(CAIXA.top, CAIXA.bottom)
        else:
            x, y = CAIXA.right + 30, central(CAIXA.top, CAIXA.bottom)
        ax = coracao.centerx + random.randint(-jit, jit)
        ay = coracao.centery + random.randint(-jit, jit)
        dx, dy = ax - x, ay - y
        n_ = math.hypot(dx, dy) or 1
        sp = v * E.vm
        spawn_proj(forma, x, y, dx / n_ * sp, dy / n_ * sp, tam, dano, efeito,
                   delay + k * espaco, guia, vida)


def spawn_corte(ret, warn, dur=14, dano=None, efeito=None, cor=(255, 240, 200), forma="reto"):
    r = pygame.Rect(ret).clip(CAIXA)
    if r.width <= 0 or r.height <= 0:
        return
    adicionar_ataque({
        "tipo": "corte", "ret": r, "t": 0, "warn": warn, "dur": dur, "dano": dano,
        "efeito": efeito, "cor": cor, "forma": forma, "acertou": False,
    })


def spawn_anel(cor, dano=None, v=3.2, delay=24):
    pontos = [
        (CAIXA.left, CAIXA.top), (CAIXA.right, CAIXA.top),
        (CAIXA.left, CAIXA.bottom), (CAIXA.right, CAIXA.bottom),
        (CAIXA.centerx, CAIXA.top), (CAIXA.centerx, CAIXA.bottom),
        (CAIXA.left, CAIXA.centery), (CAIXA.right, CAIXA.centery),
    ]
    cx, cy = random.choice(pontos)
    ang = math.atan2(coracao.centery - cy, coracao.centerx - cx) + random.uniform(-0.9, 0.9)
    adicionar_ataque({
        "tipo": "anel", "cx": cx, "cy": cy, "r": 0.0, "vr": v * E.vm, "esp": 8,
        "delay": delay + aviso_t() // 2, "gap": ang, "meia": (0.62, 0.5, 0.42)[E.dificuldade],
        "cor": cor, "dano": dano, "acertou": False, "ret": pygame.Rect(cx, cy, 1, 1),
    })


def spawn_barra():
    """Muralha que cruza a arena com uma brecha (2 blocos com o mesmo grupo)."""
    lado = random.choice(("esquerda", "direita", "cima", "baixo"))
    esp = 34
    brecha = (96, 84, 74)[E.dificuldade]
    v = 2.4 * E.vm
    grupo = random.random()
    if lado in ("esquerda", "direita"):
        gy = random.randint(CAIXA.top + 8, CAIXA.bottom - brecha - 8)
        x0 = CAIXA.left - esp if lado == "esquerda" else CAIXA.right
        mov = (v, 0) if lado == "esquerda" else (-v, 0)
        blocos = [
            pygame.Rect(x0, CAIXA.top, esp, gy - CAIXA.top),
            pygame.Rect(x0, gy + brecha, esp, CAIXA.bottom - (gy + brecha)),
        ]
    else:
        gx = random.randint(CAIXA.left + 8, CAIXA.right - brecha - 8)
        y0 = CAIXA.top - esp if lado == "cima" else CAIXA.bottom
        mov = (0, v) if lado == "cima" else (0, -v)
        blocos = [
            pygame.Rect(CAIXA.left, y0, gx - CAIXA.left, esp),
            pygame.Rect(gx + brecha, y0, CAIXA.right - (gx + brecha), esp),
        ]
    for b in blocos:
        if b.width > 0 and b.height > 0:
            adicionar_ataque({
                "tipo": "barra", "ret": b, "pos": [float(b.x), float(b.y)],
                "mov": mov, "grupo": grupo,
            })


def ativos(tipo, forma=None):
    """Quantos ataques (por grupo) de um tipo existem agora."""
    return len({
        a.get("grupo", id(a)) for a in E.ataques
        if a["tipo"] == tipo and (forma is None or a.get("forma") == forma)
    })


def spawn_machado():
    """Urso Bárbaro: machado giratório lento e pesado."""
    lado = random.choice(("esquerda", "direita", "cima", "baixo"))
    v = 3.6 * E.vm
    if lado in ("esquerda", "direita"):
        y = central(CAIXA.top + 16, CAIXA.bottom - 16)
        x = CAIXA.left - 30 if lado == "esquerda" else CAIXA.right + 30
        vx, vy = (v if lado == "esquerda" else -v), 0
    else:
        x = central(CAIXA.left + 16, CAIXA.right - 16)
        y = CAIXA.top - 30 if lado == "cima" else CAIXA.bottom + 30
        vx, vy = 0, (v if lado == "cima" else -v)
    spawn_proj("machado", x, y, vx, vy, (30, 30), dano=dano_base() + 3, delay=aviso_t() // 2)


def spawn_rocha():
    """Urso/Javali: rocha que despenca do teto."""
    x = central(CAIXA.left + 12, CAIXA.right - 12)
    spawn_proj(
        "rocha", x, CAIXA.top - 24, 0, random.uniform(4.5, 7.0) * E.vm, (22, 22),
        dano=dano_base() + 2, delay=random.randint(aviso_t() // 2, aviso_t() + 16),
    )


def spawn_tremor(n):
    """Faixas horizontais de impacto no chão (sempre sobra uma faixa livre)."""
    alt, slot = 26, 40
    slots = max(2, CAIXA.height // slot)
    n = max(1, min(n, slots // 2))
    for s in random.sample(range(slots), n):
        y = CAIXA.top + s * slot + 6
        spawn_corte((CAIXA.left, y, CAIXA.width, alt), aviso_t() + 6, 14,
                    dano=dano_base() + 2, cor=(205, 150, 95))


def spawn_garras(padrao):
    """Lobo: cortes paralelos de garra com espaço entre eles."""
    n = 5 if padrao == "rajada" else 3
    largura = 18
    warn = aviso_t() + 10
    if random.random() < 0.6:
        base = coracao.centerx + random.randint(-50, 50)
        for k in range(n):
            x = base + (k - n // 2) * 58
            spawn_corte((x - largura // 2, CAIXA.top, largura, CAIXA.height), warn, 12,
                        dano=dano_base() + 2, cor=(235, 240, 255))
    else:
        base = coracao.centery + random.randint(-40, 40)
        for k in range(n):
            y = base + (k - n // 2) * 52
            spawn_corte((CAIXA.left, y - largura // 2, CAIXA.width, largura), warn, 12,
                        dano=dano_base() + 2, cor=(235, 240, 255))


def spawn_raios(n):
    """Corvo Mago: colunas de raio verticais."""
    warn = aviso_t() + 4
    for k in range(n):
        if k == 0:
            x = coracao.centerx
        else:
            x = central(CAIXA.left + 10, CAIXA.right - 10)
        spawn_corte((x - 9, CAIXA.top, 18, CAIXA.height), warn + k * 6, 10,
                    dano=dano_base() + 3, cor=(255, 255, 140))


def spawn_armadilhas(n):
    """Guaxinim: armadilhas de espinhos que ficam um tempo no chão."""
    for _ in range(n):
        x = central(CAIXA.left, CAIXA.right - 44)
        y = central(CAIXA.top, CAIXA.bottom - 44)
        spawn_corte((x, y, 44, 44), aviso_t() + 16, 70, dano=max(2, dano_base() // 2 + 1),
                    efeito=efeito_lento, forma="armadilha")


def spawn_emboscada(n):
    """Cobra: poças venenosas que surgem perto do coração."""
    for _ in range(n):
        x = coracao.centerx + random.randint(-70, 70) - 18
        y = coracao.centery + random.randint(-50, 50) - 18
        spawn_corte((x, y, 36, 36), aviso_t() + 4, 18, dano=dano_base(),
                    efeito=efeito_veneno, cor=(120, 230, 90), forma="veneno")


def spawn_carga(n):
    """Javali: investida em linha reta, de um lado ao outro."""
    base = aviso_t() + 6
    for k in range(n):
        lado = random.choice(("esquerda", "direita"))
        y = central(CAIXA.top + 18, CAIXA.bottom - 18)
        x = CAIXA.left - 40 if lado == "esquerda" else CAIXA.right + 40
        v = 6.5 * E.vm * (1 if lado == "esquerda" else -1)
        spawn_proj("javali", x, y, v, 0, (46, 32), dano=dano_base() + 4,
                   delay=base + k * 14, vida=200)


def executar_ataque(tipo, padrao):
    lados = ["cima", "baixo", "esquerda", "direita"]
    if tipo == "linguas":
        if padrao == "paredao":
            return spawn_paredao("lingua")
        n = {"normal": 1, "rapido": 2, "rajada": 5}.get(padrao, random.randint(1, 3))
        for k in range(n):
            spawn_haste("lingua", lados[k % 4] if padrao == "rajada" else None)
    elif tipo == "moscas":
        n = {"normal": 1, "rapido": 2 + (random.random() < 0.5), "rajada": 8}.get(padrao, random.randint(3, 7))
        for _ in range(n):
            spawn_mosca(random.choice(lados) if padrao == "rajada" else None)
    elif tipo == "petalas":
        spawn_petalas({"normal": 6, "rapido": 9, "rajada": 13}.get(padrao, random.randint(6, 12)))
    elif tipo == "raizes":
        if padrao == "paredao":
            return spawn_paredao("raiz")
        n = {"normal": 1, "rapido": 2, "rajada": 3}.get(padrao, random.randint(1, 3))
        for _ in range(n):
            spawn_haste("raiz")
    elif tipo == "morcegos":
        spawn_morcegos(padrao)
    elif tipo == "sangue":
        spawn_gotas(padrao)
    elif tipo == "azul":
        if padrao == "rajada":
            spawn_espinho("esquerda")
            spawn_espinho("direita")
        elif padrao == "caotico":
            spawn_espinho()
            if random.random() < 0.5:
                spawn_petalas(3)
        else:
            spawn_espinho()

    # ---------------- Urso Bárbaro ----------------
    elif tipo == "machado":
        for _ in range({"normal": 1, "rapido": 2, "rajada": 3}.get(padrao, random.randint(1, 3))):
            spawn_machado()
    elif tipo == "rocha":
        for _ in range({"normal": 3, "rapido": 5, "rajada": 8}.get(padrao, random.randint(3, 7))):
            spawn_rocha()
    elif tipo == "tremor":
        spawn_tremor({"normal": 2, "rapido": 3, "rajada": 4}.get(padrao, random.randint(2, 3)))

    # ---------------- Lobo Guerreiro ----------------
    elif tipo == "garras":
        spawn_garras(padrao)
    elif tipo == "uivo":
        if ativos("anel") < (3 if padrao in ("rajada", "caotico") else 2):
            spawn_anel((170, 215, 255))
    elif tipo == "investida":
        spawn_mira("lobo", {"normal": 1, "rapido": 2, "rajada": 4}.get(padrao, random.randint(1, 3)),
                   8.5, (34, 16), dano=dano_base() + 2, delay=aviso_t() + 4, jit=18, espaco=14)

    # ---------------- Guaxinim Ladino ----------------
    elif tipo == "adagas":
        spawn_mira("adaga", {"normal": 2, "rapido": 3, "rajada": 6}.get(padrao, random.randint(2, 5)),
                   7.5, (14, 14), dano=max(2, dano_base() - 1), efeito=efeito_roubo,
                   delay=aviso_t() // 2 + 6, jit=14, espaco=9)
    elif tipo == "armadilha":
        if ativos("corte", "armadilha") < 4:
            spawn_armadilhas({"normal": 2, "rapido": 2, "rajada": 3}.get(padrao, random.randint(2, 3)))

    # ---------------- Corvo Mago ----------------
    elif tipo == "orbes":
        spawn_mira("orbe", {"normal": 2, "rapido": 3, "rajada": 5}.get(padrao, random.randint(2, 4)),
                   2.3, (18, 18), dano=dano_base(), efeito=efeito_nevoa,
                   delay=10, guia=130, vida=260, espaco=16)
    elif tipo == "raios":
        spawn_raios({"normal": 2, "rapido": 3, "rajada": 5}.get(padrao, random.randint(2, 4)))
    elif tipo == "nova":
        if ativos("anel") < (3 if padrao in ("rajada", "caotico") else 2):
            spawn_anel((190, 120, 255), dano=dano_base() + 1)

    # ---------------- Javali Berserk ----------------
    elif tipo == "carga":
        spawn_carga({"normal": 1, "rapido": 2, "rajada": 3}.get(padrao, random.randint(1, 3)))

    # ---------------- Raposa Arqueira ----------------
    elif tipo == "flechas":
        spawn_mira("flecha", {"normal": 2, "rapido": 3, "rajada": 5}.get(padrao, random.randint(2, 4)),
                   9.0, (12, 12), dano=dano_base(), delay=aviso_t() + 2, jit=10, espaco=12)
    elif tipo == "chuva":
        for _ in range({"normal": 5, "rapido": 8, "rajada": 12}.get(padrao, random.randint(5, 10))):
            x = central(CAIXA.left + 8, CAIXA.right - 8)
            spawn_proj("flecha", x, CAIXA.top - 24, 0, random.uniform(5.5, 7.5) * E.vm, (10, 16),
                       dano=max(2, dano_base() - 1),
                       delay=random.randint(aviso_t() // 2, aviso_t() + 22))

    # ---------------- Cobra Assassina ----------------
    elif tipo == "bote":
        if padrao == "paredao":
            return spawn_paredao("cobra")
        n = {"normal": 1, "rapido": 2, "rajada": 4}.get(padrao, random.randint(1, 3))
        for k in range(n):
            spawn_haste("cobra", lados[k % 4] if padrao == "rajada" else None, velocidade=8)
    elif tipo == "dardos":
        spawn_mira("dardo", {"normal": 2, "rapido": 3, "rajada": 6}.get(padrao, random.randint(2, 5)),
                   9.5, (10, 10), dano=max(2, dano_base() - 2), efeito=efeito_veneno,
                   delay=aviso_t() // 2, jit=12, espaco=8)
    elif tipo == "emboscada":
        spawn_emboscada({"normal": 2, "rapido": 3, "rajada": 4}.get(padrao, random.randint(2, 4)))

    # ---------------- Texugo Tank ----------------
    elif tipo == "muralha":
        if ativos("barra") < (2 if padrao in ("rajada", "caotico") else 1):
            spawn_barra()
    elif tipo == "onda":
        if ativos("anel") < 2:
            spawn_anel((215, 160, 90), dano=dano_base() + 2, v=2.8)


def escolher_turno():
    b = E.inimigo
    E.azul = random.random() < b["prob_azul"] * (1.5 if b["fase2"] else 1.0)
    if E.azul:
        E.tipo_turno = "azul"
        E.padrao = random.choice(["normal", "rapido", "rajada", "caotico"])
    else:
        E.tipo_turno = random.choice(b["ataques"])
        opcoes = ["normal", "rapido", "rajada", "caotico"]
        if E.tipo_turno in ("linguas", "raizes", "bote"):
            opcoes.append("paredao")
        E.padrao = random.choice(opcoes)
    intervalo, mult = PADROES[E.padrao]
    E.vm = mult
    if b["fase2"]:
        intervalo = int(intervalo * 0.8)
        E.vm *= 1.25
    if b["raiva"] > 0:
        E.vm *= 1.15
    if b.get("berserk"):  # quanto mais ferido, mais rápido
        E.vm *= 1 + 0.5 * (1 - b["vida"] / b["vida_max"])
    if E.dificuldade == 2 and not E.azul:
        intervalo = max(intervalo, 55)
    E.intervalo = intervalo

    if E.azul:
        ajustar_caixa("azul")
    else:
        modos = ["normal", "normal", "estreita", "baixa", "pequena"]
        if b["fase2"]:
            modos = ["estreita", "baixa", "pequena", "normal"]
        if E.padrao == "paredao" or E.tipo_turno == "muralha":
            modos = ["normal"]  # precisa de espaço
        ajustar_caixa(random.choice(modos))
    coracao.center = CAIXA.center
    E.fx, E.fy = float(coracao.x), float(coracao.y)
    E.vy = 0.0
    E.no_chao = False


def criar_ataques_do_turno():
    b = E.inimigo
    if E.dificuldade == 2 and not E.azul:
        tipos = b["ataques"] if len(b["ataques"]) <= 3 else random.sample(b["ataques"], 3)
        for t in tipos:
            executar_ataque(t, "normal")
    else:
        executar_ataque(E.tipo_turno, E.padrao)

# =========================================================
# BATALHA: ATUALIZAÇÃO DOS ATAQUES
# =========================================================


def ponta_haste(a):
    r = a["ret"]
    return {
        "esquerda": (r.right, r.centery),
        "direita": (r.left, r.centery),
        "cima": (r.centerx, r.bottom),
        "baixo": (r.centerx, r.top),
    }[a["lado"]]


def remover(a):
    if a in E.ataques:
        E.ataques.remove(a)


def atualizar_ataques():
    hit = hitbox_coracao()  # colisões usam uma área menor que o desenho
    for a in E.ataques[:]:
        if a not in E.ataques:
            continue
        if a["aviso"] > 0:
            a["aviso"] -= 1
            continue
        t = a["tipo"]
        r = a["ret"]

        if t in ("lingua", "raiz", "cobra"):
            if a["fase"] == "crescendo":
                a["atual"] += a["vel"]
                if a["atual"] >= a["max"]:
                    a["atual"] = a["max"]
                    a["fase"] = "recuando"
            else:
                a["atual"] -= a["vel"]
            if a["atual"] <= 0:
                if a["preso"]:
                    E.preso = False
                remover(a)
                continue
            a["ret"] = r = ret_haste(a["lado"], a["atual"], a["centro"], a["esp"])
            if a["preso"]:
                coracao.center = ponta_haste(a)
                coracao.clamp_ip(CAIXA)
                E.fx, E.fy = float(coracao.x), float(coracao.y)
            elif r.width > 0 and r.height > 0 and r.colliderect(hit) and pode_ser_atingido():
                if t == "lingua":
                    a["preso"] = True
                    E.preso = True
                    dano_jogador(dano_base())
                else:  # raiz e cobra envenenam
                    dano_jogador(dano_base(), efeito_veneno)
                    remover(a)
                if E.modo != MODO_BATALHA:
                    return

        elif t == "mosca":
            r.x += a["mov"][0]
            r.y += a["mov"][1]
            if r.colliderect(hit) and pode_ser_atingido():
                dano_jogador(max(1, dano_base() // 3), efeito_lento)
                remover(a)
                if E.modo != MODO_BATALHA:
                    return
            elif (r.right < CAIXA.left - 30 or r.left > CAIXA.right + 30
                  or r.bottom < CAIXA.top - 30 or r.top > CAIXA.bottom + 30):
                remover(a)

        elif t == "petala":
            r.y += a["vel"]
            if r.colliderect(hit) and pode_ser_atingido():
                dano_jogador(max(1, dano_base() // 3), efeito_nevoa)
                remover(a)
                if E.modo != MODO_BATALHA:
                    return
            elif r.top > CAIXA.bottom:
                remover(a)

        elif t == "morcego":
            r.x += a["mov"]
            a["t"] += 1
            r.y = a["linha_y"] - r.height // 2 + int(math.sin(a["t"] / 7 + a["fase_anim"]) * 3)
            if r.colliderect(hit) and pode_ser_atingido():
                b = E.inimigo
                dano_jogador(max(1, dano_base() // 2))
                b["vida"] = min(b["vida_max"], b["vida"] + 1)
                texto_flutuante(400, 60, "+1", VERDE)
                remover(a)
                if E.modo != MODO_BATALHA:
                    return
            elif r.right < CAIXA.left - 40 or r.left > CAIXA.right + 40:
                remover(a)

        elif t == "gota":
            r.y += a["vel"]
            a["t"] += 1
            r.centerx = a["x_base"] + 6 + int(math.sin(a["t"] / 9 + a["fase_anim"]) * 2)
            if r.colliderect(hit) and pode_ser_atingido():
                dano_jogador(dano_base(), efeito_lento)
                remover(a)
                if E.modo != MODO_BATALHA:
                    return
            elif r.bottom >= CAIXA.bottom:
                remover(a)

        elif t == "espinho":
            r.x += a["mov"]
            if r.colliderect(hit) and pode_ser_atingido():
                dano_jogador(dano_base())
                remover(a)
                if E.modo != MODO_BATALHA:
                    return
            elif r.right < CAIXA.left - 40 or r.left > CAIXA.right + 40:
                remover(a)

        # ------------------- ataques novos -------------------
        elif t == "proj":
            if a["delay"] > 0:
                a["delay"] -= 1
                continue
            a["t"] += 1
            a["ang"] += 14
            if a["guia"] > 0 and a["t"] < a["guia"]:  # teleguiado
                dx = coracao.centerx - a["pos"][0]
                dy = coracao.centery - a["pos"][1]
                n_ = math.hypot(dx, dy) or 1
                vel_atual = math.hypot(a["v"][0], a["v"][1]) or 1
                a["v"][0] += dx / n_ * 0.16
                a["v"][1] += dy / n_ * 0.16
                m = math.hypot(a["v"][0], a["v"][1]) or 1
                a["v"][0] *= vel_atual / m
                a["v"][1] *= vel_atual / m
            a["pos"][0] += a["v"][0]
            a["pos"][1] += a["v"][1]
            r.center = (int(a["pos"][0]), int(a["pos"][1]))
            if r.colliderect(hit) and pode_ser_atingido():
                dano_jogador(a["dano"] or dano_base(), a["efeito"])
                remover(a)
                if E.modo != MODO_BATALHA:
                    return
            elif a["t"] > a["vida"] or not r.colliderect(CAIXA.inflate(160, 160)):
                remover(a)

        elif t == "corte":
            a["t"] += 1
            if a["t"] > a["warn"] + a["dur"]:
                remover(a)
                continue
            if (a["t"] > a["warn"] and not a["acertou"]
                    and r.colliderect(hit) and pode_ser_atingido()):
                a["acertou"] = True
                dano_jogador(a["dano"] or dano_base(), a["efeito"])
                if E.modo != MODO_BATALHA:
                    return

        elif t == "anel":
            if a["delay"] > 0:
                a["delay"] -= 1
                continue
            a["r"] += a["vr"]
            if a["r"] > 650:
                remover(a)
                continue
            if not a["acertou"]:
                dx = coracao.centerx - a["cx"]
                dy = coracao.centery - a["cy"]
                dist = math.hypot(dx, dy)
                if abs(dist - a["r"]) < a["esp"] / 2 + 5:
                    diff = abs((math.atan2(dy, dx) - a["gap"] + math.pi) % math.tau - math.pi)
                    if diff > a["meia"] and pode_ser_atingido():
                        a["acertou"] = True
                        dano_jogador(a["dano"] or dano_base())
                        if E.modo != MODO_BATALHA:
                            return

        elif t == "barra":
            a["pos"][0] += a["mov"][0]
            a["pos"][1] += a["mov"][1]
            r.topleft = (int(a["pos"][0]), int(a["pos"][1]))
            if r.colliderect(hit) and pode_ser_atingido():
                dano_jogador(dano_base() + 2)
                if E.modo != MODO_BATALHA:
                    return
            elif not r.colliderect(CAIXA.inflate(100, 100)):
                remover(a)


# =========================================================
# BATALHA: ATUALIZAÇÃO GERAL
# =========================================================


def mover_coracao(teclas):
    if E.preso:
        return
    esq = teclas[pygame.K_a] or teclas[pygame.K_LEFT]
    dir_ = teclas[pygame.K_d] or teclas[pygame.K_RIGHT]
    cima = teclas[pygame.K_w] or teclas[pygame.K_UP]
    baixo = teclas[pygame.K_s] or teclas[pygame.K_DOWN]
    v = 2 if E.t_lento > 0 else min(7.0, 5.0 + 0.2 * (E.nivel - 1))

    E.fx += (int(bool(dir_)) - int(bool(esq))) * v
    if E.azul:
        pulo = cima or teclas[pygame.K_SPACE]
        if E.no_chao and pulo:
            E.vy = -9.2
            E.no_chao = False
        elif not pulo and E.vy < -3:
            E.vy = -3.0
        E.vy += 0.5
        E.fy += E.vy
    else:
        E.fy += (int(bool(baixo)) - int(bool(cima))) * v

    E.fx = max(CAIXA.left, min(E.fx, CAIXA.right - coracao.width))
    limite_baixo = CAIXA.bottom - coracao.height
    if E.fy >= limite_baixo:
        E.fy = limite_baixo
        if E.azul:
            E.vy = 0.0
            E.no_chao = True
    elif E.fy <= CAIXA.top:
        E.fy = CAIXA.top
        E.vy = max(E.vy, 0.0)
        E.no_chao = False
    elif E.azul:
        E.no_chao = False
    coracao.topleft = (round(E.fx), round(E.fy))


def comecar_fala():
    b = E.inimigo
    falas = b["falas2"] if b["fase2"] else b["falas"]
    E.fala = random.choice(falas)
    E.fase = "fala"
    E.timer = 80
    tocar("fala")


def iniciar_fase_ataque():
    E.fase = "ataque"
    E.timer_fase = 0
    E.ataques = []
    E.preso = False
    escolher_turno()
    E.timer_spawn = max(0, E.intervalo - 12)
    E.msg_batalha = (
        "Coração AZUL! Use W/ESPAÇO para pular." if E.azul
        else f"{E.inimigo['nome']} está atacando!"
    )


def terminar_turno():
    b = E.inimigo
    E.fase = "menu"
    E.ataques = []
    E.preso = False
    E.timer_fase = 0
    E.azul = False
    E.msg_batalha = "Escolha sua ação!"
    ajustar_caixa("normal")
    coracao.center = CAIXA.center
    if b["raiva"] > 0:
        b["raiva"] -= 1
    if E.veneno:
        E.veneno = False
        if E.vida > 1:
            E.vida -= 1
            texto_flutuante(coracao.centerx, coracao.top, "-1", (150, 255, 100))
            E.msg_batalha = "O veneno queima... Escolha sua ação!"


def atualizar_batalha():
    b = E.inimigo
    if b is None:
        return
    if E.t_nevoa > 0:
        E.t_nevoa -= 1
    if E.t_tremor_inimigo > 0:
        E.t_tremor_inimigo -= 1

    if E.fase == "minigame":
        E.minigame_x += E.minigame_dir * 5
        if E.minigame_x >= 570:
            E.minigame_x, E.minigame_dir = 570, -1
        elif E.minigame_x <= 230:
            E.minigame_x, E.minigame_dir = 230, 1
        return

    if E.fase == "fala":
        E.timer -= 1
        if E.timer <= 0:
            iniciar_fase_ataque()
        return

    if E.fase == "fim":
        E.timer -= 1
        if E.timer <= 0:
            finalizar_batalha(E.resultado)
        return

    if E.fase != "ataque":
        return

    if E.invencivel > 0:
        E.invencivel -= 1
    if E.t_lento > 0:
        E.t_lento -= 1

    mover_coracao(pygame.key.get_pressed())

    E.timer_spawn += 1
    if E.timer_spawn >= E.intervalo:
        criar_ataques_do_turno()
        E.timer_spawn = 0

    atualizar_ataques()
    if E.modo != MODO_BATALHA:
        return

    E.timer_fase += 1
    if E.timer_fase >= 300:
        terminar_turno()


# =========================================================
# BATALHA: AÇÕES DO JOGADOR
# =========================================================


def calcular_dano_timing(pos):
    distancia = abs(pos - 400)
    dano = round(20 - (distancia / 170) * 18)
    dano = max(2, min(20, dano))
    return dano + 2 * (E.nivel - 1) + E.bonus_dano


def iniciar_minigame_luta():
    E.fase = "minigame"
    E.minigame_x = 230
    E.minigame_dir = 1
    E.msg_batalha = "Acerte o centro para causar mais dano! (ESPAÇO)"


def checar_fase2(b):
    if not b["fase2"] and b["vida"] > 0 and b["vida"] <= b["vida_max"] / 2:
        b["fase2"] = True
        return f" {b['nome']} está furioso!"
    return ""


def lutar(dano):
    b = E.inimigo
    # Arqueira: chance de esquivar do golpe.
    if random.random() < b.get("esquiva", 0.0):
        E.msg_batalha = f"{b['nome']} esquivou do seu golpe!"
        tocar("erro")
        texto_flutuante(400, 40, "MISS", CINZA)
        comecar_fala()
        return
    # Tank: armadura reduz o dano.
    reduzido = ""
    if b.get("armadura", 1.0) < 1.0:
        antes = dano
        dano = max(1, int(dano * b["armadura"]))
        if dano < antes:
            reduzido = " (armadura!)"
    b["vida"] -= dano
    E.corte_t = 10
    E.corte_f = min(10, 2 + int(dano * 0.4))
    E.t_tremor_inimigo = 12
    iniciar_tremor_tela(min(9, 2 + int(dano * 0.35)), 9)
    qualidade = "PERFEITO!" if dano >= 18 else "Bom!" if dano >= 10 else "Fraco..."
    tocar("perfeito" if dano >= 18 else "acerto")
    texto_flutuante(400, 40, f"-{dano}", AMARELO)
    criar_particulas(400, 100, (255, 230, 120), 10 + dano, 3.5, 25)
    E.msg_batalha = f"{qualidade} Você causou {dano} de dano!{reduzido}"

    if b["vida"] <= 0:
        b["vida"] = 0
        E.fase = "fim"
        E.resultado = "morto"
        E.timer = 45
        E.msg_batalha = f"{b['nome']} foi derrotado!"
        tocar("morte")
        criar_particulas(400, 100, b["cor"], 60, 5, 50)
    else:
        E.msg_batalha += checar_fase2(b)
        comecar_fala()


def executar_agir(idx):
    b = E.inimigo
    nome, reacao, tipo, so_pacifista = b["opcoes"][idx]
    tocar("confirmar")
    if tipo == "checar":
        extra = " Está FURIOSO!" if b["fase2"] else ""
        poup = " Parece disposto a ser poupado." if b["piedade"] else ""
        E.msg_batalha = f"{b['checar']}{poup}{extra}"
    elif tipo == "ok":
        if so_pacifista and E.mortes > 0:
            E.msg_batalha = "Ela sente o cheiro de sangue em suas mãos e recusa a música."
            tocar("erro")
        else:
            b["piedade"] = True
            E.msg_batalha = reacao
            tocar("poupar")
            criar_particulas(400, 100, (255, 255, 200), 14, 2.5, 30)
    elif tipo == "irrita":
        b["raiva"] = 2
        E.msg_batalha = reacao + " (Ataques mais rápidos!)"
        tocar("erro")
    else:
        E.msg_batalha = reacao
    comecar_fala()


def executar_item(chave):
    antes = E.itens.get(chave, 0)
    resultado = usar_item(chave)
    if resultado is None:
        E.msg_batalha = "Você não tem esse item."
        E.fase = "menu"
        return
    if E.itens.get(chave, 0) >= antes:
        # O item não foi gasto (ex.: vida cheia): volta ao menu sem perder o turno.
        E.msg_batalha = resultado
        E.fase = "menu"
        tocar("erro")
        return
    E.msg_batalha = resultado
    if chave != "escudo":
        texto_flutuante(coracao.centerx, 420, "+VIDA", VERDE)
    comecar_fala()


def poupar():
    b = E.inimigo
    if b["piedade"]:
        E.fase = "fim"
        E.resultado = "poupado"
        E.timer = 50
        E.msg_batalha = f"{b['nome']} foi poupado!"
        tocar("poupar")
        criar_particulas(400, 100, (255, 255, 255), 50, 4, 50)
    else:
        E.msg_batalha = f"{b['nome']} ainda não quer ser poupado."
        tocar("erro")
        comecar_fala()


# =========================================================
# FINAIS E RECOMPENSAS
# =========================================================

FINAIS = {
    "pacifico": (
        "FINAL PACÍFICO",
        ["Você atravessou a floresta sem ferir ninguém.",
         "As criaturas agora te veem como amigo.",
         "Dizem que ainda existe alguém esperando por você ao norte..."],
    ),
    "verdadeiro": (
        "FINAL VERDADEIRO",
        ["Nem mesmo a Quimera Sombria foi ferida.",
         "A floresta inteira canta a sua passagem.",
         "Você provou que misericórdia é a maior força."],
    ),
    "neutro": (
        "FINAL NEUTRO",
        ["Você poupou alguns e derrotou outros.",
         "A floresta está em paz, mas lembra de você",
         "com um misto de respeito e receio."],
    ),
    "genocida": (
        "FINAL SANGRENTO",
        ["Ninguém foi poupado.",
         "A floresta ficou em silêncio absoluto.",
         "Só restou o eco dos seus passos..."],
    ),
}


def calcular_final():
    if E.mortes == 0 and CHEFE_SECRETO["destino"] == "poupado":
        return "verdadeiro"
    if E.mortes == 0:
        return "pacifico"
    if E.poupados == 0:
        return "genocida"
    return "neutro"


def finalizar_batalha(resultado):
    b = E.inimigo
    if b is None:
        return
    b["vivo"] = False
    b["destino"] = resultado
    morto = resultado == "morto"
    if morto:
        b["vida"] = 0
        E.mortes += 1
    else:
        E.poupados += 1

    exp = int(b["exp"] * (1.25 if morto else 1.0))
    E.moedas += b["moedas"]
    linhas = [
        f"{b['nome']} {'foi derrotado' if morto else 'foi poupado'}!",
        f"+{exp} EXP   +{b['moedas']} moedas   +20 vida",
    ]
    tocar("moeda")
    linhas += ganhar_exp(exp)
    E.vida = min(E.vida_max, E.vida + 20)
    if random.random() < 0.35:
        item = random.choice(["pocao", "doce"])
        E.itens[item] += 1
        linhas.append(f"Encontrou: {ITENS[item][0]}")
    if b is CHEFE_SECRETO and not SAVE["dificil"]:
        SAVE["dificil"] = True
        salvar_desbloqueios_da_partida()
        linhas.append("Modo DIFÍCIL desbloqueado!")

    chefe_foi_secreto = b is CHEFE_SECRETO
    limpar_estado_batalha()
    mostrar_mensagem("\n".join(linhas), 260)

    todos = all(not i["vivo"] for i in INIMIGOS)
    if todos and (not E.final_mostrado or chefe_foi_secreto):
        E.final_mostrado = True
        E.final = calcular_final()
        if E.final not in SAVE["finais"]:
            SAVE["finais"].append(E.final)
            salvar_desbloqueios_da_partida()
        E.modo = MODO_VITORIA
        tocar_musica("vitoria")
    else:
        E.modo = MODO_MUNDO
        tocar_musica("mundo")


# =========================================================
# BATALHA: DESENHO
# =========================================================


def imagem_batalha(img):
    tamanho = (100, 100) if E.inimigo is CHEFE_SECRETO else (70, 70)
    chave = (id(img), tamanho)
    if chave not in _imagens_batalha:
        _imagens_batalha[chave] = pygame.transform.smoothscale(img, tamanho)
    return _imagens_batalha[chave]


def desenhar_coracao(x, y, cor=VERMELHO):
    pixels = ["01100110", "11111111", "11111111", "01111110", "00111100", "00011000"]
    tp = 2
    ix = x - (len(pixels[0]) * tp) // 2
    iy = y - (len(pixels) * tp) // 2
    for linha, txt in enumerate(pixels):
        for coluna, p in enumerate(txt):
            if p == "1":
                pygame.draw.rect(S, cor, (ix + coluna * tp, iy + linha * tp, tp, tp))


def eixo_haste(a):
    c = a["centro"]
    return {
        "esquerda": ((CAIXA.left, c), (1, 0)),
        "direita": ((CAIXA.right, c), (-1, 0)),
        "cima": ((c, CAIXA.top), (0, 1)),
        "baixo": ((c, CAIXA.bottom), (0, -1)),
    }[a["lado"]]


def ponto(o, d, u, v):
    return (int(o[0] + d[0] * u - d[1] * v), int(o[1] + d[1] * u + d[0] * v))


def desenhar_lingua(a):
    L = a["atual"]
    if L < 2:
        return
    o, d = eixo_haste(a)
    s = a["esp"] / 16.0
    rosa, clara, escura = (235, 85, 145), (255, 125, 175), (190, 55, 110)
    perfil = [(0, 8), (0.12, 7), (0.28, 5), (0.45, 4), (0.62, 5), (0.78, 7)]
    lado_a = [ponto(o, d, L * f, w * s) for f, w in perfil]
    lado_b = [ponto(o, d, L * f, -w * s) for f, w in reversed(perfil)]
    pts = lado_a + [ponto(o, d, max(L - 5, 0), 9 * s), ponto(o, d, L + 6, 0), ponto(o, d, max(L - 5, 0), -9 * s)] + lado_b
    pygame.draw.polygon(S, rosa, pts)
    if L > 18:
        pygame.draw.line(S, clara, ponto(o, d, 8, 0), ponto(o, d, L - 8, 0), 4)
    pygame.draw.circle(S, rosa, ponto(o, d, L - 3, 0), int(11 * s))
    pygame.draw.line(S, escura, ponto(o, d, L + 4, 0), ponto(o, d, L - 5, 6 * s), 2)
    pygame.draw.line(S, escura, ponto(o, d, L + 4, 0), ponto(o, d, L - 5, -6 * s), 2)


def desenhar_raiz(a):
    L = int(a["atual"])
    if L < 2:
        return
    o, d = eixo_haste(a)
    s = a["esp"] / 14.0

    def eixo(u):
        return ponto(o, d, u, math.sin(u / 10.0) * 3)

    pts = [eixo(u) for u in range(0, L + 1, 6)] + [eixo(L)]
    if len(pts) > 1:
        pygame.draw.lines(S, (24, 94, 34), False, pts, int(14 * s))
        pygame.draw.lines(S, (55, 170, 45), False, pts, int(10 * s))
        pygame.draw.lines(S, (112, 210, 70), False, pts, 3)
    for u in range(0, L + 1, 32):
        c = eixo(u)
        pygame.draw.circle(S, (24, 94, 34), c, 7)
        pygame.draw.circle(S, (55, 170, 45), c, 4)
        pygame.draw.circle(S, (112, 210, 70), c, 2)
    for k, u in enumerate(range(18, L, 25)):
        lado = 1 if k % 2 == 0 else -1
        off = math.sin(u / 10.0) * 3
        p1 = ponto(o, d, u - 5, off)
        p2 = ponto(o, d, u + 5, off)
        ponta = ponto(o, d, u, off + lado * 13 * s)
        pygame.draw.polygon(S, (190, 48, 38), [p1, p2, ponta])
        m1 = ((p1[0] * 0.4 + ponta[0] * 0.6), (p1[1] * 0.4 + ponta[1] * 0.6))
        m2 = ((p2[0] * 0.4 + ponta[0] * 0.6), (p2[1] * 0.4 + ponta[1] * 0.6))
        pygame.draw.polygon(S, (236, 207, 157), [m1, m2, ponta])


def desenhar_cobra(a):
    """Cobra do chefe Cobra Assassina: corpo ondulado verde com cabeça e língua."""
    L = int(a["atual"])
    if L < 2:
        return
    o, d = eixo_haste(a)
    s = a["esp"] / 14.0

    def eixo(u):
        return ponto(o, d, u, math.sin(u / 7.0) * 6 * s)

    pts = [eixo(u) for u in range(0, L + 1, 5)] + [eixo(L)]
    if len(pts) > 1:
        pygame.draw.lines(S, (20, 80, 35), False, pts, int(13 * s))
        pygame.draw.lines(S, (70, 175, 70), False, pts, int(9 * s))
        pygame.draw.lines(S, (170, 235, 110), False, pts, 2)
    for u in range(10, L, 22):  # manchas
        pygame.draw.circle(S, (30, 100, 45), eixo(u), max(2, int(3 * s)))
    cab = eixo(L)
    pygame.draw.circle(S, (70, 175, 70), cab, int(9 * s))
    pygame.draw.circle(S, (20, 80, 35), cab, int(9 * s), 2)
    pygame.draw.circle(S, (255, 230, 60), ponto(o, d, L + 2, 4 * s), 2)
    pygame.draw.circle(S, (255, 230, 60), ponto(o, d, L + 2, -4 * s), 2)
    ponta = ponto(o, d, L + 14, 0)
    pygame.draw.line(S, (235, 40, 60), ponto(o, d, L + 8, 0), ponta, 2)
    pygame.draw.line(S, (235, 40, 60), ponta, ponto(o, d, L + 18, 4), 2)
    pygame.draw.line(S, (235, 40, 60), ponta, ponto(o, d, L + 18, -4), 2)


def desenhar_trajetos():
    if not E.mostrar_trajetoria:
        return
    camada = pygame.Surface(S.get_size(), pygame.SRCALPHA)
    camada.set_clip(CAIXA)
    cor = (255, 255, 255, 105)
    for a in E.ataques:
        t, r = a["tipo"], a["ret"]
        if t in ("lingua", "raiz", "cobra"):
            o, d = eixo_haste(a)
            pygame.draw.line(camada, cor, ponto(o, d, 0, 0), ponto(o, d, a["max"], 0), 2)
        elif t == "mosca":
            if a["lado"] in ("esquerda", "direita"):
                pygame.draw.line(camada, cor, (CAIXA.left, r.centery), (CAIXA.right, r.centery), 2)
            else:
                pygame.draw.line(camada, cor, (r.centerx, CAIXA.top), (r.centerx, CAIXA.bottom), 2)
        elif t in ("petala", "gota"):
            pygame.draw.line(camada, cor, (r.centerx, CAIXA.top), (r.centerx, CAIXA.bottom), 2)
        elif t == "morcego":
            pygame.draw.line(camada, cor, (CAIXA.left, a["linha_y"]), (CAIXA.right, a["linha_y"]), 2)
        elif t == "espinho":
            y = CAIXA.bottom - 3
            pygame.draw.line(camada, cor, (CAIXA.left, y), (CAIXA.right, y), 2)
    camada.set_clip(None)
    S.blit(camada, (0, 0))


# ---------- desenho dos ataques novos ----------


def _rot(pts, ang, cx, cy):
    c, s = math.cos(ang), math.sin(ang)
    return [(int(cx + x * c - y * s), int(cy + x * s + y * c)) for x, y in pts]


def desenhar_proj(a):
    r = a["ret"]
    cx, cy = r.center
    forma = a["forma"]

    if a["delay"] > 0:  # aviso: linha vermelha piscando na direção do disparo
        if (E.timer_fase // 3) % 2 == 0:
            vx, vy = a["v"]
            n_ = math.hypot(vx, vy) or 1
            S.set_clip(CAIXA)
            largura = max(2, min(22, min(r.width, r.height) // 2))
            pygame.draw.line(
                S, (200, 60, 60), (cx, cy),
                (cx + vx / n_ * 900, cy + vy / n_ * 900), largura,
            )
            S.set_clip(None)
        return

    ang = math.atan2(a["v"][1], a["v"][0])
    if forma == "adaga":
        pygame.draw.line(S, (120, 80, 40), _rot([(-12, 0)], ang, cx, cy)[0], _rot([(-5, 0)], ang, cx, cy)[0], 4)
        pygame.draw.polygon(S, (225, 230, 245), _rot([(11, 0), (-5, -4), (-5, 4)], ang, cx, cy))
        pygame.draw.polygon(S, (120, 130, 150), _rot([(11, 0), (-5, -4), (-5, 4)], ang, cx, cy), 1)
    elif forma == "flecha":
        pygame.draw.line(S, (150, 105, 55), _rot([(-11, 0)], ang, cx, cy)[0], _rot([(7, 0)], ang, cx, cy)[0], 2)
        pygame.draw.polygon(S, (200, 205, 215), _rot([(13, 0), (6, -4), (6, 4)], ang, cx, cy))
        pygame.draw.line(S, (220, 80, 60), _rot([(-11, 0)], ang, cx, cy)[0], _rot([(-7, -4)], ang, cx, cy)[0], 2)
        pygame.draw.line(S, (220, 80, 60), _rot([(-11, 0)], ang, cx, cy)[0], _rot([(-7, 4)], ang, cx, cy)[0], 2)
    elif forma == "dardo":
        pygame.draw.line(S, (60, 170, 60), _rot([(-8, 0)], ang, cx, cy)[0], _rot([(6, 0)], ang, cx, cy)[0], 3)
        pygame.draw.polygon(S, (170, 255, 120), _rot([(10, 0), (5, -3), (5, 3)], ang, cx, cy))
    elif forma == "orbe":
        pulso = int(abs(math.sin(a["t"] / 6)) * 3)
        pygame.draw.circle(S, (90, 40, 160), (cx, cy), 11 + pulso)
        pygame.draw.circle(S, (170, 110, 255), (cx, cy), 8)
        pygame.draw.circle(S, BRANCO, (cx, cy), 3)
    elif forma == "machado":
        g = math.radians(a["ang"])
        pygame.draw.polygon(S, (120, 80, 40), _rot([(-3, -15), (3, -15), (3, 15), (-3, 15)], g, cx, cy))
        pygame.draw.polygon(S, (200, 205, 215), _rot([(3, -13), (17, -9), (17, 9), (3, 13)], g, cx, cy))
        pygame.draw.polygon(S, (90, 95, 110), _rot([(3, -13), (17, -9), (17, 9), (3, 13)], g, cx, cy), 2)
    elif forma == "rocha":
        pygame.draw.circle(S, (110, 105, 100), (cx, cy), 11)
        pygame.draw.circle(S, (150, 145, 138), (cx - 3, cy - 3), 6)
        pygame.draw.circle(S, (60, 58, 55), (cx, cy), 11, 2)
    elif forma == "javali":
        sx = 1 if a["v"][0] > 0 else -1
        pygame.draw.ellipse(S, (125, 78, 55), r)
        pygame.draw.ellipse(S, (70, 40, 28), r, 2)
        cab = (cx + sx * 15, cy)
        pygame.draw.circle(S, (150, 98, 72), cab, 11)
        pygame.draw.circle(S, (255, 70, 50), (cab[0] + sx * 2, cy - 4), 2)
        pygame.draw.polygon(S, (245, 240, 220), [(cab[0] + sx * 6, cy + 3), (cab[0] + sx * 14, cy - 3), (cab[0] + sx * 10, cy + 7)])
        for k in range(3):  # poeira
            pygame.draw.circle(S, (170, 150, 120), (cx - sx * (26 + k * 7), cy + 8 - k * 5), 3 - k // 2 + 1)
    elif forma == "lobo":
        pygame.draw.polygon(S, (150, 195, 245), _rot([(18, 0), (0, -8), (-18, -3), (-18, 3), (0, 8)], ang, cx, cy))
        pygame.draw.polygon(S, BRANCO, _rot([(18, 0), (0, -8), (-18, -3), (-18, 3), (0, 8)], ang, cx, cy), 1)
        pygame.draw.circle(S, (255, 250, 150), _rot([(8, -2)], ang, cx, cy)[0], 2)
    else:
        pygame.draw.circle(S, BRANCO, (cx, cy), 6)


def desenhar_corte(a):
    r = a["ret"]
    if a["t"] <= a["warn"]:
        piscando = (a["t"] // 4) % 2 == 0
        pygame.draw.rect(S, (110, 25, 25) if piscando else (70, 15, 15), r)
        pygame.draw.rect(S, (255, 90, 90), r, 2)
        if a["forma"] == "armadilha":
            pygame.draw.line(S, (255, 140, 140), r.topleft, r.bottomright, 1)
            pygame.draw.line(S, (255, 140, 140), r.topright, r.bottomleft, 1)
        return
    if a["forma"] == "armadilha":
        pygame.draw.rect(S, (60, 60, 72), r)
        n = max(1, r.width // 11)
        for k in range(n):
            x0 = r.left + k * r.width // n
            x1 = r.left + (k + 1) * r.width // n
            pygame.draw.polygon(S, (215, 215, 230), [(x0, r.bottom), ((x0 + x1) // 2, r.top), (x1, r.bottom)])
        pygame.draw.rect(S, (230, 90, 90), r, 2)
    elif a["forma"] == "veneno":
        pygame.draw.ellipse(S, (60, 150, 50), r)
        pygame.draw.ellipse(S, a["cor"], r.inflate(-10, -10))
        pygame.draw.ellipse(S, BRANCO, r, 2)
    else:
        pygame.draw.rect(S, a["cor"], r)
        pygame.draw.rect(S, BRANCO, r, 2)


def desenhar_anel(a):
    S.set_clip(CAIXA)
    if a["delay"] > 0:
        pulso = 4 + (a["delay"] % 8)
        pygame.draw.circle(S, a["cor"], (a["cx"], a["cy"]), pulso, 2)
        gx = a["cx"] + math.cos(a["gap"]) * 60
        gy = a["cy"] + math.sin(a["gap"]) * 60
        pygame.draw.line(S, BRANCO, (a["cx"], a["cy"]), (int(gx), int(gy)), 2)  # direção da abertura
    else:
        rad = a["r"]
        passo = min(0.12, 5.0 / max(rad, 30.0))
        area = CAIXA.inflate(12, 12)  # só desenha o que cai dentro da arena
        k = 0.0
        while k < math.tau:
            diff = abs((k - a["gap"] + math.pi) % math.tau - math.pi)
            if diff > a["meia"]:
                px = int(a["cx"] + math.cos(k) * rad)
                py = int(a["cy"] + math.sin(k) * rad)
                if area.collidepoint(px, py):
                    pygame.draw.circle(S, a["cor"], (px, py), 5)
            k += passo
    S.set_clip(None)


def desenhar_barra(a):
    r = a["ret"].clip(CAIXA)
    if r.width <= 0 or r.height <= 0:
        return
    pygame.draw.rect(S, (120, 115, 125), r)
    for y in range(r.top, r.bottom, 12):
        pygame.draw.line(S, (80, 76, 86), (r.left, y), (r.right, y), 1)
    for x in range(r.left, r.right, 17):
        pygame.draw.line(S, (80, 76, 86), (x, r.top), (x, r.bottom), 1)
    pygame.draw.rect(S, (200, 195, 205), r, 2)


def desenhar_ataques():
    desenhar_trajetos()
    for a in E.ataques:
        if a["aviso"] > 0:
            continue
        t, r = a["tipo"], a["ret"]
        if t == "lingua":
            desenhar_lingua(a)
        elif t == "raiz":
            desenhar_raiz(a)
        elif t == "cobra":
            desenhar_cobra(a)
        elif t == "proj":
            desenhar_proj(a)
        elif t == "corte":
            desenhar_corte(a)
        elif t == "anel":
            desenhar_anel(a)
        elif t == "barra":
            desenhar_barra(a)
        elif t == "petala":
            pygame.draw.ellipse(S, (255, 100, 170), r)
        elif t == "mosca":
            pygame.draw.ellipse(S, (30, 30, 30), (r.x + 2, r.y + 2, 8, 9))
            pygame.draw.ellipse(S, (180, 180, 180), (r.x - 5, r.y + 2, 8, 6))
            pygame.draw.ellipse(S, (180, 180, 180), (r.right - 3, r.y + 2, 8, 6))
            pygame.draw.circle(S, BRANCO, (r.left + 4, r.top + 4), 2)
            pygame.draw.circle(S, BRANCO, (r.left + 8, r.top + 4), 2)
            pygame.draw.line(S, (100, 100, 100), (r.left + 4, r.top + 2), (r.left + 1, r.top - 3), 1)
            pygame.draw.line(S, (100, 100, 100), (r.left + 8, r.top + 2), (r.left + 11, r.top - 3), 1)
        elif t == "morcego":
            cx, cy = r.centerx, r.centery
            flap = math.sin(pygame.time.get_ticks() / 65 + a["fase_anim"]) * 6
            corpo, asa = (92, 48, 126), (135, 75, 165)
            pygame.draw.polygon(S, asa, [(cx - 3, cy), (r.left - 2, int(cy - 2 - flap)), (r.left + 2, int(cy + 6 + flap * 0.35)), (cx - 1, cy + 5)])
            pygame.draw.polygon(S, asa, [(cx + 3, cy), (r.right + 2, int(cy - 2 - flap)), (r.right - 2, int(cy + 6 + flap * 0.35)), (cx + 1, cy + 5)])
            pygame.draw.ellipse(S, corpo, (cx - 5, cy - 5, 10, 12))
            pygame.draw.polygon(S, corpo, [(cx - 4, cy - 2), (cx - 5, cy - 8), (cx - 1, cy - 4)])
            pygame.draw.polygon(S, corpo, [(cx + 4, cy - 2), (cx + 5, cy - 8), (cx + 1, cy - 4)])
            pygame.draw.circle(S, (255, 90, 90), (cx - 2, cy - 1), 1)
            pygame.draw.circle(S, (255, 90, 90), (cx + 2, cy - 1), 1)
        elif t == "gota":
            pygame.draw.ellipse(S, (145, 12, 35), r)
            pygame.draw.polygon(S, (145, 12, 35), [(r.left + 2, r.top + 7), (r.centerx, r.top - 4), (r.right - 2, r.top + 7)])
            pygame.draw.ellipse(S, (255, 105, 125), (r.left + 3, r.top + 7, 3, 5))
        elif t == "espinho":
            n = max(1, r.width // 8)
            for k in range(n):
                x0 = r.left + k * r.width // n
                x1 = r.left + (k + 1) * r.width // n
                pygame.draw.polygon(S, (200, 60, 60), [(x0, r.bottom), ((x0 + x1) // 2, r.top), (x1, r.bottom)])
                pygame.draw.polygon(S, (255, 210, 190), [(x0, r.bottom), ((x0 + x1) // 2, r.top), (x1, r.bottom)], 1)


def _criar_barra_minigame():
    cores = [
        (0.00, (210, 45, 45)), (0.13, (235, 125, 35)), (0.27, (240, 210, 55)),
        (0.42, (140, 210, 75)), (0.50, (45, 190, 75)), (0.58, (140, 210, 75)),
        (0.73, (240, 210, 55)), (0.87, (235, 125, 35)), (1.00, (210, 45, 45)),
    ]
    surf = pygame.Surface((340, 38))
    for px in range(340):
        prog = px / 339
        for k in range(len(cores) - 1):
            p0, c0 = cores[k]
            p1, c1 = cores[k + 1]
            if p0 <= prog <= p1:
                t = (prog - p0) / (p1 - p0)
                cor = tuple(round(c0[c] + (c1[c] - c0[c]) * t) for c in range(3))
                pygame.draw.line(surf, cor, (px, 0), (px, 37))
                break
    return surf


BARRA_MINIGAME = _criar_barra_minigame()


def desenhar_minigame_luta():
    painel = pygame.Rect(225, 225, 350, 125)
    pygame.draw.rect(S, (12, 12, 20), painel)
    pygame.draw.rect(S, BRANCO, painel, 2)
    S.blit(BARRA_MINIGAME, (230, 274))
    pygame.draw.rect(S, BRANCO, (230, 274, 340, 38), 2)
    x = E.minigame_x
    pygame.draw.line(S, PRETO, (x, 269), (x, 317), 6)
    pygame.draw.line(S, BRANCO, (x, 269), (x, 317), 2)
    texto("ESPAÇO para atacar", 400, 236, AMARELO, fonte_p, centro=True)


def desenhar_painel_sub(titulo, linhas, selecao):
    painel = pygame.Rect(40, 455, 720, 118)
    pygame.draw.rect(S, PRETO, painel)
    pygame.draw.rect(S, BRANCO, painel, 3)
    texto(titulo, 56, 460, CINZA, fonte_p)
    for k, l in enumerate(linhas):
        col, lin = k % 2, k // 2
        cor = AMARELO if k == selecao else BRANCO
        texto(("> " if k == selecao else "  ") + l, 60 + col * 350, 484 + lin * 30, cor, fonte_p)


def desenhar_batalha():
    S.fill(PRETO)
    b = E.inimigo
    if b is None:
        return

    # ---------- inimigo ----------
    ox = random.randint(-3, 3) if E.t_tremor_inimigo > 0 else 0
    cx, cy = 400 + ox, 100
    if b["fase2"]:
        pygame.draw.circle(S, (170, 30, 40), (cx, cy), 48 + int(abs(math.sin(E.tick / 10)) * 4), 2)
    if b["imagem"] is not None:
        img = imagem_batalha(b["imagem"])
        S.blit(img, img.get_rect(center=(cx, cy)))
    else:
        pygame.draw.circle(S, b["cor"], (cx, cy), 32)
    if E.corte_t > 0:
        alc = 32 + E.corte_f
        ini, fim = (400 - alc, 100 - alc // 2), (400 + alc, 100 + alc // 2)
        esp = max(2, E.corte_f // 3)
        pygame.draw.line(S, (220, 35, 55), ini, fim, esp + 4)
        pygame.draw.line(S, (255, 245, 225), ini, fim, esp)

    texto(b["nome"], 30, 12, b["cor"], fonte_g if len(b["nome"]) <= 8 else fonte)
    barra(30, 48, 190, 12, b["vida"], b["vida_max"], b["cor"])
    texto(f"{b['vida']}/{b['vida_max']}", 30, 64, BRANCO, fonte_p)
    if b["piedade"]:
        texto("Poupável", 110, 64, AMARELO, fonte_p)
    if b.get("classe"):
        texto(f"Classe: {b['classe']}", 30, 82, CINZA, fonte_p)
    if E.modo_teste:
        texto("MODO DE TESTE", 640, 12, AMARELO, fonte_p)

    # fala do inimigo
    if E.fase == "fala":
        bolha = pygame.Rect(455, 40, 320, 84)
        pygame.draw.rect(S, BRANCO, bolha, border_radius=8)
        pygame.draw.polygon(S, BRANCO, [(455, 80), (437, 90), (455, 96)])
        for k, l in enumerate(quebrar(E.fala, 296, fonte_p)[:3]):
            texto(l, 467, 50 + k * 22, PRETO, fonte_p)

    # ---------- arena ----------
    desenhar_ataques()
    pygame.draw.rect(S, BRANCO, CAIXA, 3)

    visivel = E.fase in ("ataque", "fala")
    if (E.modo != MODO_GAME_OVER and visivel) or E.fase in ("menu", "agir", "item", "minigame"):
        if E.fase != "minigame":
            if E.invencivel <= 0 or (E.invencivel // 4) % 2 == 0:
                cor_c = AZUL if E.azul else VERMELHO
                desenhar_coracao(coracao.centerx, coracao.centery, cor_c)
                if E.preso:
                    pygame.draw.circle(S, (255, 125, 175), coracao.center, 13, 2)
                if E.escudo > 0:
                    pygame.draw.circle(S, (120, 200, 255), coracao.center, 15, 2)

    if E.t_nevoa > 0:
        neblina = pygame.Surface(CAIXA.size, pygame.SRCALPHA)
        inten = 95 + int(25 * abs(math.sin(E.t_nevoa / 18)))
        neblina.fill((185, 195, 205, inten))
        fase_n = E.t_nevoa / 12
        for k in range(7):
            x = int((k * 61 + fase_n * (k % 2 + 1)) % CAIXA.width)
            y = int((k * 43 + fase_n * 0.6) % CAIXA.height)
            pygame.draw.circle(neblina, (220, 225, 230, 45), (x, y), 35 + k % 3 * 12)
        S.blit(neblina, CAIXA.topleft)
        pygame.draw.rect(S, BRANCO, CAIXA, 3)

    if E.fase == "minigame":
        desenhar_minigame_luta()

    desenhar_efeitos()

    # ---------- status do jogador ----------
    texto(f"LV {E.nivel}", 40, 418, AMARELO, fonte)
    barra(110, 421, 200, 18, E.vida, E.vida_max, AMARELO, (110, 0, 0))
    texto(f"{E.vida}/{E.vida_max}", 320, 420, BRANCO, fonte)
    status = []
    if E.t_lento > 0:
        status.append(("LENTO", (140, 200, 255)))
    if E.veneno:
        status.append(("VENENO", (150, 255, 100)))
    if E.t_nevoa > 0:
        status.append(("NEBLINA", (200, 200, 220)))
    if E.escudo > 0:
        status.append((f"ESCUDO x{E.escudo}", (120, 200, 255)))
    if b["raiva"] > 0:
        status.append(("IRRITADO", (255, 120, 100)))
    for k, (s, c) in enumerate(status):
        texto(s, 440 + (k % 2) * 160, 412 + (k // 2) * 20, c, fonte_p)

    # ---------- menus ----------
    if E.fase == "agir":
        nomes = [o[0] for o in b["opcoes"]] + ["Voltar"]
        desenhar_painel_sub("AGIR - W/S escolhe, ESPAÇO confirma, X volta", nomes, E.sel_sub)
    elif E.fase == "item":
        chaves = [k for k in ITENS if E.itens[k] > 0]
        nomes = [f"{ITENS[k][0]} x{E.itens[k]} - {ITENS[k][2]}" for k in chaves] + ["Voltar"]
        desenhar_painel_sub("ITEM - W/S escolhe, ESPAÇO confirma, X volta", nomes, E.sel_sub)
    else:
        for k, linha in enumerate(quebrar(E.msg_batalha, 720, fonte_p)[:2]):
            texto(linha, 40, 452 + k * 20, BRANCO, fonte_p)
        ativo = E.fase == "menu"
        for k, acao in enumerate(ACOES):
            x = 40 + k * 185
            if not ativo:
                cor = CINZA
            else:
                cor = AMARELO if k == E.sel_acao else BRANCO
            pygame.draw.rect(S, cor, (x, 505, 160, 50), 3)
            texto(acao, x + 80, 519, cor, fonte, centro=True)
        if ativo:
            texto("A/D escolher   ESPAÇO confirmar", 400, 572, CINZA, fonte_p, centro=True)

# =========================================================
# MENUS E TELAS
# =========================================================


def dificuldades_disponiveis():
    opcoes = ["FÁCIL", "MÉDIO"]
    desbloqueado_no_save = SAVE["dificil"] and not E.novo_jogo_pendente
    if desbloqueado_no_save or E.modo_teste:
        opcoes.append("DIFÍCIL")
    return opcoes


def definir_dificuldade(indice):
    E.dificuldade = max(0, min(indice, len(dificuldades_disponiveis()) - 1))
    E.mostrar_trajetoria = E.dificuldade == 0


def ciclo_dificuldade_teste():
    definir_dificuldade((E.dificuldade + 1) % len(dificuldades_disponiveis()))
    nome = dificuldades_disponiveis()[E.dificuldade]
    mostrar_mensagem(f"Dificuldade: {nome}")


def desenhar_painel_madeira(rect):
    """Desenha uma placa de madeira com borda escura e cantos reforçados."""
    r = pygame.Rect(rect)
    pygame.draw.rect(S, (35, 24, 22), r.move(0, 7), border_radius=22)
    pygame.draw.rect(S, (61, 38, 31), r, border_radius=22)
    pygame.draw.rect(S, (155, 94, 59), r.inflate(-10, -10), border_radius=18)
    pygame.draw.rect(S, (183, 119, 75), r.inflate(-20, -20), border_radius=15)
    pygame.draw.line(S, (207, 150, 98), (r.left + 24, r.top + 22), (r.right - 24, r.top + 22), 3)
    # Reforços claros nos quatro cantos.
    cantos = [
        ((r.left + 8, r.top + 18), (r.left + 29, r.top + 39)),
        ((r.right - 8, r.top + 18), (r.right - 29, r.top + 39)),
        ((r.left + 8, r.bottom - 18), (r.left + 29, r.bottom - 39)),
        ((r.right - 8, r.bottom - 18), (r.right - 29, r.bottom - 39)),
    ]
    for inicio, fim in cantos:
        pygame.draw.line(S, (61, 38, 31), inicio, fim, 14)
        pygame.draw.line(S, (228, 198, 151), inicio, fim, 8)


def desenhar_botao_madeira(rect, rotulo, selecionado=False, f=None):
    r = pygame.Rect(rect)
    pygame.draw.rect(S, (40, 25, 23), r.move(0, 5), border_radius=15)
    pygame.draw.rect(S, (59, 35, 29), r, border_radius=15)
    pygame.draw.rect(S, (142, 80, 52), r.inflate(-6, -6), border_radius=12)
    pygame.draw.rect(S, (174, 105, 67) if selecionado else (151, 86, 56), r.inflate(-12, -12), border_radius=10)
    pygame.draw.line(S, (207, 144, 94), (r.left + 15, r.top + 9), (r.right - 15, r.top + 9), 2)
    if selecionado:
        pygame.draw.rect(S, (246, 210, 145), r.inflate(-2, -2), 2, border_radius=14)
    texto(rotulo, r.centerx, r.centery - 12, (255, 246, 226) if selecionado else BRANCO, f or fonte, centro=True)


def desenhar_fundo_menu():
    S.fill(PRETO)


def opcoes_menu_titulo():
    partida = SAVE.get("partida")
    if isinstance(partida, dict) and partida.get("versao") == 1:
        return ["CONTINUAR", "NOVO JOGO", "SAIR"]
    return ["NOVO JOGO", "SAIR"]


def desenhar_titulo():
    desenhar_fundo_menu()
    desenhar_painel_madeira((150, 48, 500, 500))
    pygame.draw.rect(S, (75, 43, 37), (180, 91, 440, 64), border_radius=18)
    pygame.draw.rect(S, (57, 35, 31), (180, 91, 440, 64), 3, border_radius=18)
    texto("GARRAS E CLEMÊNCIA", 400, 108, (255, 246, 226), fonte, centro=True)
    texto("UMA PEQUENA AVENTURA", 400, 174, BRANCO, fonte_p, centro=True)

    opcoes = opcoes_menu_titulo()
    E.sel_titulo %= len(opcoes)
    inicio_y = 255 - (len(opcoes) - 1) * 25
    for k, op in enumerate(opcoes):
        desenhar_botao_madeira((265, inicio_y + k * 52, 270, 44), op, E.sel_titulo == k, fonte_p)

    texto(f"Finais descobertos: {len(SAVE['finais'])}/4", 400, 370, (255, 244, 223), fonte_p, centro=True)
    if SAVE["dificil"]:
        texto("Modo DIFÍCIL desbloqueado", 400, 393, (255, 220, 170), fonte_p, centro=True)
    texto("W / S  Selecionar     ENTER  Confirmar", 400, 452, (255, 246, 226), fonte_p, centro=True)
    texto("M  Som     F11  Tela cheia", 400, 480, (235, 220, 198), fonte_p, centro=True)


def desenhar_selecao_dificuldade():
    desenhar_fundo_menu()
    desenhar_painel_madeira((75, 42, 650, 520))
    pygame.draw.rect(S, (75, 43, 37), (190, 78, 420, 58), border_radius=16)
    texto("ESCOLHA A DIFICULDADE", 400, 86, (255, 246, 226), fonte, centro=True)
    descr = [
        ("FÁCIL", "Mostra o caminho dos ataques."),
        ("MÉDIO", "Ataques sem caminho indicado."),
        ("DIFÍCIL", "Combina ataques de vários chefes."),
    ]
    n = len(dificuldades_disponiveis())
    E.sel_dificuldade = min(E.sel_dificuldade, n - 1)
    for k in range(n):
        selecionado = E.sel_dificuldade == k
        nome, detalhe = descr[k]
        y = 157 + k * 91
        desenhar_botao_madeira((135, y, 530, 76), nome, selecionado, fonte)
        texto(detalhe, 400, y + 44, (255, 238, 214), fonte_p, centro=True)
    texto("W / S  Selecionar     ENTER  Iniciar     ESC  Voltar", 400, 500, (255, 246, 226), fonte_p, centro=True)


def opcoes_menu_pausa():
    opcoes = ["VOLTAR AO JOGO"]
    if E.modo_anterior == MODO_MUNDO:
        opcoes.append("SALVAR PARTIDA")
    opcoes.append("SOM: " + ("DESLIGADO" if E.mudo else "LIGADO"))
    opcoes.append("TELA INICIAL")
    return opcoes


def desenhar_pausa():
    sobre = pygame.Surface((LARGURA_JOGO, ALTURA_JOGO), pygame.SRCALPHA)
    sobre.fill((0, 0, 0, 170))
    S.blit(sobre, (0, 0))
    desenhar_painel_madeira((150, 32, 500, 536))
    pygame.draw.rect(S, (75, 43, 37), (265, 59, 270, 54), border_radius=16)
    texto("PAUSA", 400, 67, (255, 246, 226), fonte_g, centro=True)
    opcoes = opcoes_menu_pausa()
    for k, op in enumerate(opcoes):
        desenhar_botao_madeira((235, 124 + k * 46, 330, 40), op, E.sel_pausa == k, fonte_p)
    texto(f"Nível {E.nivel}   EXP {E.exp}/{exp_necessaria()}", 400, 327, BRANCO, fonte_p, centro=True)
    texto(f"Vida {E.vida}/{E.vida_max}   Moedas {E.moedas}", 400, 352, BRANCO, fonte_p, centro=True)
    itens = "   ".join(f"{ITENS[k][0]} x{v}" for k, v in E.itens.items())
    texto(itens, 400, 377, BRANCO, fonte_p, centro=True)
    texto(f"Poupados: {E.poupados}   Derrotados: {E.mortes}", 400, 402, (255, 236, 211), fonte_p, centro=True)
    achados = sum(1 for o in OBSTACULOS if o.get("segredo") and o["aberto"])
    baus = sum(1 for b in BAUS if b["aberto"])
    texto(f"Segredos: {achados}/{SEGREDOS_TOTAL}   Baús: {baus}/{len(BAUS)}   Bônus de dano: +{E.bonus_dano}", 400, 427, (255, 236, 211), fonte_p, centro=True)
    texto("W / S  Selecionar     ENTER  Confirmar", 400, 510, (255, 246, 226), fonte_p, centro=True)


def desenhar_game_over():
    S.fill(PRETO)
    texto("FIM DE JOGO", 400, 200, VERMELHO, fonte_g, centro=True)
    if E.morreu_para is not None:
        texto(f"{E.morreu_para['nome']} venceu esta rodada...", 400, 255, CINZA, centro=True)
    texto("ENTER = tentar de novo (mantém seu progresso, perde metade das moedas)", 400, 310, BRANCO, fonte_p, centro=True)
    texto("ESC = voltar ao menu", 400, 345, CINZA, centro=True)


def desenhar_vitoria():
    S.fill(PRETO)
    titulo, linhas = FINAIS[E.final]
    texto(titulo, 400, 70, AMARELO, fonte_g, centro=True)
    for k, l in enumerate(linhas):
        texto(l, 400, 150 + k * 34, BRANCO, centro=True)
    texto(f"Poupados: {E.poupados}    Derrotados: {E.mortes}    Nível: {E.nivel}", 400, 300, (200, 200, 255), centro=True)
    texto(f"Finais descobertos: {len(SAVE['finais'])}/4", 400, 340, CINZA, centro=True)
    texto("ENTER = voltar ao menu", 400, 430, BRANCO, centro=True)
    texto("C = continuar explorando", 400, 465, BRANCO, centro=True)
    texto("ESC = sair", 400, 500, CINZA, centro=True)


def desenhar_dialogo():
    d = E.dialogo
    ret = pygame.Rect(40, 440, 720, 130)
    pygame.draw.rect(S, PRETO, ret)
    pygame.draw.rect(S, BRANCO, ret, 3)
    texto(d["nome"], 60, 448, AMARELO)
    for k, l in enumerate(quebrar(d["linhas"][d["i"]], 680, fonte)[:3]):
        texto(l, 60, 478 + k * 26, BRANCO)
    texto("E / ESPAÇO", 700, 548, CINZA, fonte_p, centro=True)


def desenhar_loja():
    sobre = pygame.Surface((LARGURA_JOGO, ALTURA_JOGO), pygame.SRCALPHA)
    sobre.fill((0, 0, 0, 200))
    S.blit(sobre, (0, 0))
    texto("LOJA DO GATO MERCADOR", 400, 70, AMARELO, fonte_g, centro=True)
    texto(f"Suas moedas: {E.moedas}", 400, 130, BRANCO, centro=True)
    chaves = list(ITENS)
    for k, chave in enumerate(chaves + ["sair"]):
        sel = E.sel_loja == k
        if chave == "sair":
            linha = "Sair"
        else:
            nome, _, desc, preco = ITENS[chave]
            linha = f"{nome} - {preco} moedas - {desc}   (você tem {E.itens[chave]})"
        texto(("> " if sel else "  ") + linha, 60, 200 + k * 50, AMARELO if sel else BRANCO)
    texto("W/S escolhe   ENTER compra   ESC sai", 400, 520, CINZA, fonte_p, centro=True)


def desenhar_transicao():
    desenhar_mundo()
    t = E.trans
    if t < 16:
        if (t // 4) % 2 == 0:
            flash = pygame.Surface((LARGURA_JOGO, ALTURA_JOGO), pygame.SRCALPHA)
            flash.fill((255, 255, 255, 150))
            S.blit(flash, (0, 0))
    else:
        h = int((t - 16) / 24 * (ALTURA_JOGO / 2)) + 1
        pygame.draw.rect(S, PRETO, (0, 0, LARGURA_JOGO, h))
        pygame.draw.rect(S, PRETO, (0, ALTURA_JOGO - h, LARGURA_JOGO, h))
        cx, cy = jogador.centerx - camera.x, jogador.centery - camera.y
        desenhar_coracao(cx, cy - 20)


def desenhar_menu_teste():
    sobre = pygame.Surface((LARGURA_JOGO, ALTURA_JOGO), pygame.SRCALPHA)
    sobre.fill((0, 0, 0, 225))
    S.blit(sobre, (0, 0))
    texto("MODO DE TESTE", 400, 50, AMARELO, fonte_g, centro=True)
    texto("DIFICULDADE ATUAL: " + dificuldades_disponiveis()[E.dificuldade], 400, 115, AMARELO, centro=True)
    comandos = [
        ("H", "Restaurar vida"), ("K", "Derrotar inimigo atual"),
        ("V", "Vitória instantânea"), ("R", "Restaurar todos os inimigos"),
        ("I", "+itens e +moedas"), ("L", "Subir de nível"),
        ("D", "Mudar dificuldade"), ("F1", "Abrir/fechar esta tela"),
    ]
    for k, (tecla, desc) in enumerate(comandos):
        y = 165 + k * 40
        texto(tecla, 220, y, AMARELO)
        texto("- " + desc, 290, y, BRANCO)


# =========================================================
# KONAMI E TRAPAÇAS
# =========================================================


def verificar_konami(tecla):
    if tecla == CODIGO_KONAMI[E.konami]:
        E.konami += 1
        if E.konami >= len(CODIGO_KONAMI):
            E.konami = 0
            E.modo_teste = True
            tocar("levelup")
            print("MODO DE TESTE ATIVADO!")
    else:
        E.konami = 1 if tecla == CODIGO_KONAMI[0] else 0


def usar_trapaca(tecla):
    if not E.modo_teste or E.modo in (MODO_TITULO, MODO_DIFICULDADE):
        return
    if tecla == pygame.K_F1:
        E.menu_teste = not E.menu_teste
        return
    if E.menu_teste:
        if tecla == pygame.K_d:
            ciclo_dificuldade_teste()
        return
    if tecla == pygame.K_h:
        E.vida = E.vida_max
        if E.modo == MODO_BATALHA:
            E.msg_batalha = "Vida restaurada!"
    elif tecla == pygame.K_k:
        if E.modo == MODO_BATALHA and E.inimigo is not None:
            E.inimigo["vida"] = 0
            finalizar_batalha("morto")
    elif tecla == pygame.K_v:
        for i in INIMIGOS:
            i["vivo"] = False
            i["vida"] = 0
            i["destino"] = "poupado"
        E.poupados = len(INIMIGOS)
        E.mortes = 0
        limpar_estado_batalha()
        E.final_mostrado = True
        E.final = calcular_final()
        E.modo = MODO_VITORIA
    elif tecla == pygame.K_r:
        for i in TODOS_INIMIGOS:
            resetar_inimigo(i)
        E.vida = E.vida_max
        E.mortes = E.poupados = 0
        E.ataques = []
        mostrar_mensagem("Inimigos restaurados!")
    elif tecla == pygame.K_i:
        for k in E.itens:
            E.itens[k] += 3
        E.moedas += 100
        mostrar_mensagem("+3 de cada item e +100 moedas")
    elif tecla == pygame.K_l:
        ganhar_exp(exp_necessaria())
        mostrar_mensagem(f"Nível {E.nivel}!")


# =========================================================
# EVENTOS
# =========================================================

UP = (pygame.K_UP, pygame.K_w)
DOWN = (pygame.K_DOWN, pygame.K_s)
LEFT = (pygame.K_LEFT, pygame.K_a)
RIGHT = (pygame.K_RIGHT, pygame.K_d)
OK = (pygame.K_RETURN, pygame.K_SPACE)
VOLTAR = (pygame.K_x, pygame.K_BACKSPACE)


def evento_titulo(k):
    if k in UP + DOWN:
        opcoes = opcoes_menu_titulo()
        E.sel_titulo = (E.sel_titulo + (-1 if k in UP else 1)) % len(opcoes)
        tocar("selecionar")
    elif k == pygame.K_RETURN:
        tocar("confirmar")
        opcao = opcoes_menu_titulo()[E.sel_titulo]
        if opcao == "CONTINUAR":
            if carregar_partida():
                E.novo_jogo_pendente = False
                tocar_musica("mundo")
            else:
                SAVE["partida"] = None
                salvar_save()
                E.sel_titulo = 0
        elif opcao == "NOVO JOGO":
            E.novo_jogo_pendente = True
            E.sel_dificuldade = min(E.dificuldade, len(dificuldades_disponiveis()) - 1)
            E.modo = MODO_DIFICULDADE
        else:
            return False
    elif k == pygame.K_ESCAPE:
        return False
    return True


def evento_dificuldade(k):
    if k in UP + DOWN:
        n = len(dificuldades_disponiveis())
        E.sel_dificuldade = (E.sel_dificuldade + (-1 if k in UP else 1)) % n
        tocar("selecionar")
    elif k == pygame.K_RETURN:
        definir_dificuldade(E.sel_dificuldade)
        SAVE["dificil"] = False
        SAVE["finais"] = []
        SAVE["partida"] = None
        novo_jogo()
        E.novo_jogo_pendente = False
        salvar_partida()
        E.modo = MODO_MUNDO
        tocar("confirmar")
        tocar_musica("mundo")
    elif k == pygame.K_ESCAPE:
        E.novo_jogo_pendente = False
        E.modo = MODO_TITULO
    return True


def evento_mundo(k):
    if k == pygame.K_F2:
        E.edicao = not E.edicao
        if E.edicao:
            for i in INIMIGOS:
                i["retangulo"].center = i["home"]
            E.idx_edicao %= len(objetos_editaveis())
            mostrar_mensagem("Editor de mapa ativado. Tab troca o objeto.", 180)
        else:
            salvar_posicoes_mapa()
            for i in TODOS_INIMIGOS:
                i["pos"] = [float(i["retangulo"].centerx), float(i["retangulo"].centery)]
            atualizar_camera()
            mostrar_mensagem("Posições do mapa salvas.", 120)
    elif E.edicao and k == pygame.K_TAB:
        passo = -1 if pygame.key.get_mods() & pygame.KMOD_SHIFT else 1
        E.idx_edicao = (E.idx_edicao + passo) % len(objetos_editaveis())
    elif E.edicao and k == pygame.K_F3:
        E.hitboxes = not E.hitboxes
    elif E.edicao and k in (pygame.K_EQUALS, pygame.K_KP_PLUS):
        redimensionar_hitbox_edicao(4)
    elif E.edicao and k in (pygame.K_MINUS, pygame.K_KP_MINUS):
        redimensionar_hitbox_edicao(-4)
    elif k == pygame.K_e and not E.edicao:
        interagir()
    elif k == pygame.K_q and not E.edicao:
        r = usar_item("pocao")
        mostrar_mensagem(r or "Você não tem Poções.", 100)
    elif k == pygame.K_ESCAPE:
        if E.edicao:  # não perde as edições ao pausar/fechar durante o editor
            salvar_posicoes_mapa()
        E.sel_pausa = 0
        E.modo_anterior = MODO_MUNDO
        E.modo = MODO_PAUSA
    return True


def evento_pausa(k):
    opcoes = opcoes_menu_pausa()
    if k in UP + DOWN:
        E.sel_pausa = (E.sel_pausa + (-1 if k in UP else 1)) % len(opcoes)
        tocar("selecionar")
    elif k == pygame.K_RETURN:
        E.sel_pausa %= len(opcoes)
        opcao = opcoes[E.sel_pausa]
        if opcao == "VOLTAR AO JOGO":
            E.modo = E.modo_anterior
        elif opcao == "SALVAR PARTIDA":
            salvar_partida()
            E.modo = MODO_MUNDO
            mostrar_mensagem("Partida salva!", 120)
        elif opcao.startswith("SOM:"):
            alternar_som()
        else:
            E.modo = MODO_TITULO
            E.sel_titulo = 0
            tocar_musica("titulo")
    elif k == pygame.K_ESCAPE:
        E.modo = E.modo_anterior
    return True


def evento_dialogo(k):
    if k in (pygame.K_e, pygame.K_SPACE, pygame.K_RETURN):
        d = E.dialogo
        d["i"] += 1
        tocar("fala")
        if d["i"] >= len(d["linhas"]):
            E.modo = MODO_MUNDO
            E.dialogo = None
            if d["acao"]:
                d["acao"]()
    elif k == pygame.K_ESCAPE:
        E.modo = MODO_MUNDO
        E.dialogo = None
    return True


def evento_loja(k):
    chaves = list(ITENS)
    if k in UP + DOWN:
        E.sel_loja = (E.sel_loja + (-1 if k in UP else 1)) % (len(chaves) + 1)
        tocar("selecionar")
    elif k == pygame.K_RETURN:
        if E.sel_loja >= len(chaves):
            E.modo = MODO_MUNDO
        else:
            chave = chaves[E.sel_loja]
            preco = ITENS[chave][3]
            if E.moedas >= preco:
                E.moedas -= preco
                E.itens[chave] += 1
                tocar("moeda")
            else:
                tocar("erro")
    elif k == pygame.K_ESCAPE:
        E.modo = MODO_MUNDO
    return True


def evento_batalha(k):
    if k == pygame.K_ESCAPE:
        E.sel_pausa = 0
        E.modo_anterior = MODO_BATALHA
        E.modo = MODO_PAUSA
        return True
    b = E.inimigo
    if b is None:
        return True

    if E.fase == "minigame":
        if k == pygame.K_SPACE:
            lutar(calcular_dano_timing(E.minigame_x))

    elif E.fase == "fala":
        if k in OK:
            E.timer = 0

    elif E.fase == "menu":
        if k in LEFT:
            E.sel_acao = (E.sel_acao - 1) % len(ACOES)
            tocar("selecionar")
        elif k in RIGHT:
            E.sel_acao = (E.sel_acao + 1) % len(ACOES)
            tocar("selecionar")
        elif k in OK:
            tocar("confirmar")
            if E.sel_acao == 0:
                iniciar_minigame_luta()
            elif E.sel_acao == 1:
                E.fase = "agir"
                E.sel_sub = 0
            elif E.sel_acao == 2:
                if any(E.itens[c] > 0 for c in ITENS):
                    E.fase = "item"
                    E.sel_sub = 0
                else:
                    E.msg_batalha = "Você não tem itens!"
                    tocar("erro")
            else:
                poupar()

    elif E.fase in ("agir", "item"):
        if E.fase == "agir":
            total = len(b["opcoes"]) + 1
        else:
            chaves = [c for c in ITENS if E.itens[c] > 0]
            total = len(chaves) + 1
        if k in UP:
            E.sel_sub = (E.sel_sub - 1) % total
            tocar("selecionar")
        elif k in DOWN:
            E.sel_sub = (E.sel_sub + 1) % total
            tocar("selecionar")
        elif k in LEFT or k in RIGHT:
            E.sel_sub = (E.sel_sub + (2 if k in RIGHT else -2)) % total
            tocar("selecionar")
        elif k in VOLTAR:
            E.fase = "menu"
        elif k in OK:
            if E.sel_sub == total - 1:
                E.fase = "menu"
            elif E.fase == "agir":
                executar_agir(E.sel_sub)
            else:
                executar_item(chaves[E.sel_sub])
    return True


def evento_game_over(k):
    if k == pygame.K_RETURN:
        continuar_apos_game_over()
    elif k == pygame.K_ESCAPE:
        E.modo = MODO_TITULO
        E.sel_titulo = 0
        tocar_musica("titulo")
    return True


def evento_vitoria(k):
    if k == pygame.K_RETURN:
        E.modo = MODO_TITULO
        E.sel_titulo = 0
        tocar_musica("titulo")
    elif k == pygame.K_c:
        E.modo = MODO_MUNDO
        tocar_musica("mundo")
    elif k == pygame.K_ESCAPE:
        return False
    return True


TRATADORES = {
    MODO_TITULO: evento_titulo,
    MODO_DIFICULDADE: evento_dificuldade,
    MODO_MUNDO: evento_mundo,
    MODO_PAUSA: evento_pausa,
    MODO_DIALOGO: evento_dialogo,
    MODO_LOJA: evento_loja,
    MODO_BATALHA: evento_batalha,
    MODO_GAME_OVER: evento_game_over,
    MODO_VITORIA: evento_vitoria,
}


def tratar_tecla(k):
    """Retorna False quando o jogo deve fechar."""
    if k == pygame.K_F11:
        try:
            pygame.display.toggle_fullscreen()
        except pygame.error:
            pass
        return True
    if k == pygame.K_m:
        alternar_som()
        return True
    verificar_konami(k)
    usar_trapaca(k)
    if E.menu_teste:
        return True
    tratador = TRATADORES.get(E.modo)
    return tratador(k) if tratador else True


# =========================================================
# QUADRO (um frame) E LOOP PRINCIPAL
# =========================================================


def desenhar_tudo():
    m = E.modo
    if m == MODO_TITULO:
        desenhar_titulo()
    elif m == MODO_DIFICULDADE:
        desenhar_selecao_dificuldade()
    elif m in (MODO_MUNDO, MODO_DIALOGO, MODO_LOJA):
        desenhar_mundo()
        if m == MODO_DIALOGO and E.dialogo:
            desenhar_dialogo()
        elif m == MODO_LOJA:
            desenhar_loja()
    elif m == MODO_TRANSICAO:
        desenhar_transicao()
    elif m == MODO_BATALHA:
        desenhar_batalha()
    elif m == MODO_PAUSA:
        if E.modo_anterior == MODO_BATALHA:
            desenhar_batalha()
        else:
            desenhar_mundo()
        desenhar_pausa()
    elif m == MODO_GAME_OVER:
        desenhar_game_over()
    elif m == MODO_VITORIA:
        desenhar_vitoria()
    if E.modo_teste and E.menu_teste:
        desenhar_menu_teste()


def quadro(eventos):
    """Processa eventos, atualiza e desenha 1 frame. False = fechar."""
    E.tick += 1
    for ev in eventos:
        if ev.type == pygame.QUIT:
            if E.edicao:
                salvar_posicoes_mapa()
            return False
        if ev.type == pygame.KEYDOWN:
            if not tratar_tecla(ev.key):
                return False

    if E.modo in (MODO_MUNDO, MODO_BATALHA, MODO_TRANSICAO):
        atualizar_animacao_flowey()

    if E.modo == MODO_MUNDO:
        atualizar_mundo()
    elif E.modo == MODO_TRANSICAO:
        E.trans += 1
        if E.trans >= 40:
            alvo = E.pendente
            iniciar_batalha(alvo)
    elif E.modo == MODO_BATALHA:
        atualizar_batalha()

    if E.modo in (MODO_MUNDO, MODO_BATALHA, MODO_DIALOGO):
        atualizar_efeitos()
    if E.msg_t > 0:
        E.msg_t -= 1
        if E.msg_t <= 0:
            E.msg = ""

    desenhar_tudo()

    tx = ty = 0
    if E.tremor_t > 0:
        tx = random.randint(-E.tremor_f, E.tremor_f)
        ty = random.randint(-E.tremor_f, E.tremor_f)
        E.tremor_t -= 1
        if E.tremor_t == 0:
            E.tremor_f = 0
    if E.corte_t > 0:
        E.corte_t -= 1

    tela.fill(PRETO)
    tela.blit(S, (tx, ty))
    pygame.display.flip()
    return True


def principal():
    novo_jogo()
    E.modo = MODO_TITULO
    tocar_musica("titulo")
    executando = True
    while executando:
        relogio.tick(60)
        executando = quadro(pygame.event.get())
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    # Sistema de equipamentos (arquivo equipamentos.py ao lado deste jogo).
    # Precisa ser instalado ANTES de principal().
    import equipamentos

    equipamentos.instalar(globals())
    principal()