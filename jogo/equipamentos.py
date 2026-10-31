# -*- coding: utf-8 -*-
"""
equipamentos.py - Sistema de equipamentos para "Garras e Clemência".

COMO USAR (uma única mudança no jogo): no final do arquivo do jogo, troque

    if __name__ == "__main__":
        principal()

por

    if __name__ == "__main__":
        import equipamentos
        equipamentos.instalar(globals())
        principal()

O módulo "pluga" no jogo sozinho (envolve as funções existentes), então não é
preciso editar mais nada.

O QUE ELE ADICIONA
  * Menu de equipamentos (tecla C ou TAB no mundo) com 5 slots:
    Arma, Elmo, Armadura, Botas e Amuleto.
  * 8 atributos: Dano, Defesa, Vida máx., Agilidade, Crítico, Sorte,
    Regeneração e Invencibilidade. Tudo é aplicado de verdade na batalha.
  * 5 raridades (Comum -> Lendário) com atributos sorteados.
  * Comparação automática com o item equipado (+/-).
  * Toupeira Ferreira (NPC): comprar, vender, aprimorar (+5) e fundir itens.
  * Formas de conseguir itens:
      1. Chefes: cada um solta um item ÚNICO (matar e poupar dão itens
         diferentes!) e pode soltar um item aleatório.
      2. 8 baús novos de equipamento espalhados pelo mapa.
      3. 4 segredos novos (pedras/árvores que brilham).
      4. Recompensa a cada 3 níveis.
      5. Loja da Ferreira (estoque muda conforme você progride).
      6. Fusão: 3 itens da mesma raridade viram 1 de raridade maior.
  * Tudo entra no save da partida.
"""

import json
import math
import random

import pygame

MODO_EQUIP = "equip"
MAX_MOCHILA = 24
MAX_UP = 5
VISIVEIS = 8

SLOTS = ["arma", "elmo", "armadura", "botas", "amuleto"]
NOME_SLOT = {
    "arma": "Arma", "elmo": "Elmo", "armadura": "Armadura",
    "botas": "Botas", "amuleto": "Amuleto",
}

# nome, cor, multiplicador dos atributos base
RARIDADES = [
    ("Comum", (205, 205, 205), 1.0),
    ("Incomum", (110, 225, 110), 1.3),
    ("Raro", (90, 160, 255), 1.7),
    ("Épico", (200, 110, 255), 2.2),
    ("Lendário", (255, 170, 40), 3.0),
]
EXTRAS = [0, 1, 1, 2, 3]  # atributos extras sorteados por raridade

# chave, nome, abreviação, sufixo
STATS = [
    ("dano", "Dano", "Dano", ""),
    ("def", "Defesa", "Def", ""),
    ("vida", "Vida máx.", "Vida", ""),
    ("agil", "Agilidade", "Agi", ""),
    ("crit", "Crítico", "Crít", "%"),
    ("sorte", "Sorte", "Sorte", "%"),
    ("regen", "Regeneração", "Reg", ""),
    ("invenc", "Invencib.", "Inv", ""),
]
ABREV = {k: ab for k, _, ab, _ in STATS}
NOME_STAT = {k: n for k, n, _, _ in STATS}
SUFIXO = {k: s for k, _, _, s in STATS}

EXTRA_RANGE = {
    "dano": (1, 2), "def": (1, 2), "vida": (4, 8), "agil": (1, 1),
    "crit": (2, 5), "sorte": (4, 8), "regen": (1, 1), "invenc": (3, 6),
}
PESO = {"dano": 3, "def": 3, "vida": 0.6, "agil": 3, "crit": 1.2,
        "sorte": 0.8, "regen": 4, "invenc": 0.6}

BASES = {
    "arma": [
        ("Graveto Afiado", {"dano": 2}),
        ("Adaga Enferrujada", {"dano": 2, "crit": 4}),
        ("Espada de Ferro", {"dano": 4}),
        ("Machado de Guerra", {"dano": 6, "agil": -1}),
        ("Cajado Místico", {"dano": 3, "regen": 1}),
    ],
    "elmo": [
        ("Capuz de Pano", {"def": 1}),
        ("Elmo de Ferro", {"def": 2, "vida": 5}),
        ("Coroa de Folhas", {"vida": 8, "sorte": 3}),
    ],
    "armadura": [
        ("Túnica Simples", {"def": 1, "vida": 5}),
        ("Armadura de Couro", {"def": 2, "agil": 1}),
        ("Cota de Malha", {"def": 3, "vida": 8}),
        ("Placas Pesadas", {"def": 5, "agil": -1}),
    ],
    "botas": [
        ("Sandálias", {"agil": 1}),
        ("Botas de Couro", {"agil": 2}),
        ("Botas do Vento", {"agil": 3, "invenc": 3}),
    ],
    "amuleto": [
        ("Anel de Cobre", {"crit": 5}),
        ("Amuleto da Sorte", {"sorte": 10}),
        ("Pingente de Cura", {"regen": 2}),
        ("Talismã Antigo", {"invenc": 6, "vida": 5}),
    ],
}
SUFIXOS_NOME = ["da Floresta", "do Vento", "da Aurora", "das Sombras", "do Trovão", "do Bosque"]

# Itens únicos: chefe -> (item ao DERROTAR, item ao POUPAR)
UNICOS = {
    "Froggy": (("Língua de Sapo", "arma", {"dano": 4, "crit": 3}),
               ("Lágrima de Sapo", "amuleto", {"regen": 2, "vida": 6})),
    "Batty": (("Presas de Morcego", "arma", {"dano": 5, "crit": 6}),
              ("Capa de Asas", "armadura", {"def": 2, "agil": 2})),
    "Flowey": (("Espinho Dourado", "arma", {"dano": 5, "sorte": 5}),
               ("Pétala Dourada", "amuleto", {"regen": 3, "sorte": 5})),
    "Urso Bárbaro": (("Machado do Bárbaro", "arma", {"dano": 9, "agil": -1}),
                     ("Colar de Mel", "amuleto", {"vida": 15, "regen": 1})),
    "Lobo Guerreiro": (("Espada do Guerreiro", "arma", {"dano": 8, "crit": 5}),
                       ("Manto de Honra", "armadura", {"def": 4, "vida": 8})),
    "Guaxinim Ladino": (("Adagas Gêmeas", "arma", {"dano": 6, "crit": 10}),
                        ("Moeda da Sorte", "amuleto", {"sorte": 18})),
    "Corvo Mago": (("Cajado Arcano", "arma", {"dano": 7, "regen": 2}),
                   ("Pena Sagrada", "elmo", {"vida": 10, "invenc": 6})),
    "Javali Berserk": (("Presa Furiosa", "arma", {"dano": 10, "def": -1}),
                       ("Bolota Dourada", "amuleto", {"vida": 12, "def": 1})),
    "Raposa Arqueira": (("Arco Curto", "arma", {"dano": 7, "agil": 2}),
                        ("Aljava de Honra", "botas", {"agil": 4, "crit": 4})),
    "Cobra Assassina": (("Presa Venenosa", "arma", {"dano": 8, "crit": 8}),
                        ("Escama Aquecida", "armadura", {"def": 3, "invenc": 6})),
    "Texugo Tank": (("Martelo de Escudo", "arma", {"dano": 6, "def": 2}),
                    ("Manta do Descanso", "armadura", {"def": 6, "vida": 12})),
    "Quimera Sombria": (("Garra da Quimera", "arma", {"dano": 14, "crit": 10}),
                        ("Coração da Quimera", "amuleto", {"vida": 25, "regen": 3, "sorte": 10})),
}

# (nome, x, y, raridade mínima, slot ou None)
BAUS_EQUIP = [
    ("Baú E1", 1700, 420, 1, None),
    ("Baú E2", 3050, 800, 1, "armadura"),
    ("Baú E3", 300, 1100, 1, "elmo"),
    ("Baú E4", 1900, 1100, 2, None),
    ("Baú E5", 3000, 2100, 2, "arma"),
    ("Baú E6", 220, 2150, 2, "botas"),
    ("Baú E7", 2100, 1700, 3, None),
    ("Baú E8", 1650, 1500, 2, "amuleto"),
]
# (tipo do obstáculo, x, y, código do segredo)
SEGREDOS_EQUIP = [
    ("pedra", 2750, 1750, "equip_2_arma"),
    ("arvore", 600, 1350, "equip_1"),
    ("pedra", 1850, 400, "equip_2_amuleto"),
    ("arvore", 3000, 1300, "equip_3"),
]

# ---------------------------------------------------------
# ESTADO
# ---------------------------------------------------------
ST = {}
UI = {}
G = None  # namespace do jogo (globals())


def resetar():
    ST["mochila"] = [
        novo_item("Graveto Afiado", "arma", 0, {"dano": 2}),
        novo_item("Túnica Simples", "armadura", 0, {"def": 1, "vida": 5}),
    ]
    ST["equip"] = {s: None for s in SLOTS}
    ST["vida_aplicada"] = 0
    ST["loja"] = {"seed": None, "itens": []}
    UI.update({"aba": 0, "foco": 1, "sel_slot": 0, "sel": 0, "scroll": 0,
               "marcados": [], "confirma": None, "msg": "", "msg_t": 0,
               "ferreiro": False})


def novo_item(nome, slot, r, mods, unico=False):
    return {"nome": nome, "slot": slot, "r": r, "mods": dict(mods), "up": 0, "unico": unico}


resetar()


# ---------------------------------------------------------
# ATRIBUTOS
# ---------------------------------------------------------
def mods_item(it):
    up = it.get("up", 0)
    out = {}
    for k, v in it["mods"].items():
        out[k] = v + math.ceil(v * 0.2 * up) if v > 0 else v
    return out


def total(stat):
    soma = 0
    for it in ST["equip"].values():
        if it:
            soma += mods_item(it).get(stat, 0)
    return soma


def ef_agil():
    return max(-0.3, min(0.5, total("agil") * 0.03))


def ef_crit():
    return max(0, min(60, total("crit")))


def ef_sorte():
    return max(0, min(100, total("sorte")))


def sincronizar():
    """Ajusta a vida máxima do jogo conforme o equipamento vestido."""
    E = G["E"]
    novo = total("vida")
    delta = novo - ST["vida_aplicada"]
    if delta:
        E.vida_max = max(1, E.vida_max + delta)
        if delta > 0:
            E.vida += delta
        E.vida = max(1, min(E.vida, E.vida_max))
        ST["vida_aplicada"] = novo


def valor(it):
    s = sum(max(0, v) * PESO.get(k, 1) for k, v in it["mods"].items())
    return int(12 + s * 3 + 14 * it["r"] ** 2 + it.get("up", 0) * 10)


def preco_compra(it):
    return int(valor(it) * 1.4)


def preco_venda(it):
    return max(1, valor(it) // 3)


def custo_up(it):
    return 20 * (it.get("up", 0) + 1) * (it["r"] + 1)


# ---------------------------------------------------------
# GERAÇÃO DE ITENS
# ---------------------------------------------------------
def rolar_raridade(rnd, bonus=0.0, min_r=0, usar_sorte=True):
    sorte = ef_sorte() / 100.0 if usar_sorte else 0.0
    pesos = [55, 28, 12, 4, 1]
    pesos = [p * (1 + (bonus + sorte) * i * 0.6) for i, p in enumerate(pesos)]
    for i in range(min(min_r, 4)):
        pesos[i] = 0
    return rnd.choices(range(5), weights=pesos)[0]


def gerar_item(min_r=0, slot=None, rnd=random, bonus=0.0, usar_sorte=True, r_fixo=None):
    slot = slot or rnd.choice(SLOTS)
    r = r_fixo if r_fixo is not None else rolar_raridade(rnd, bonus, min_r, usar_sorte)
    nome, base = rnd.choice(BASES[slot])
    mult = RARIDADES[r][2]
    mods = {}
    for k, v in base.items():
        mods[k] = v if v < 0 else max(1, round(v * mult))
    for _ in range(EXTRAS[r]):
        livres = [s for s in EXTRA_RANGE if s not in mods] or list(EXTRA_RANGE)
        k = rnd.choice(livres)
        lo, hi = EXTRA_RANGE[k]
        mods[k] = mods.get(k, 0) + max(1, round(rnd.randint(lo, hi) * (1 + 0.3 * r)))
    if r >= 2:
        nome = f"{nome} {rnd.choice(SUFIXOS_NOME)}"
    return novo_item(nome, slot, r, mods)


def item_unico(chefe, poupado):
    dados = UNICOS.get(chefe)
    if not dados:
        return None
    nome, slot, mods = dados[1 if poupado else 0]
    r = 4 if chefe == "Quimera Sombria" else 3
    return novo_item(nome, slot, r, mods, True)


def dar_item(it):
    """Coloca na mochila (ou vende se estiver cheia). Retorna uma linha de texto."""
    E = G["E"]
    rar = RARIDADES[it["r"]][0]
    if len(ST["mochila"]) >= MAX_MOCHILA:
        v = preco_venda(it)
        E.moedas += v
        return f"Mochila cheia! {it['nome']} foi vendido por {v} moedas."
    ST["mochila"].append(it)
    return f"Item: {it['nome']} ({rar})"


def _bonus_dif():
    return (0.0, 0.3, 0.6)[max(0, min(2, G["E"].dificuldade))]


# ---------------------------------------------------------
# SAVE
# ---------------------------------------------------------
def _limpo(it):
    try:
        if not isinstance(it, dict) or it.get("slot") not in SLOTS:
            return None
        mods = {k: int(v) for k, v in it.get("mods", {}).items() if k in NOME_STAT}
        return {
            "nome": str(it.get("nome", "Item")),
            "slot": it["slot"],
            "r": max(0, min(4, int(it.get("r", 0)))),
            "mods": mods,
            "up": max(0, min(MAX_UP, int(it.get("up", 0)))),
            "unico": bool(it.get("unico", False)),
        }
    except (TypeError, ValueError, AttributeError):
        return None


def exportar():
    return json.loads(json.dumps({
        "mochila": ST["mochila"],
        "equip": ST["equip"],
        "vida_aplicada": ST["vida_aplicada"],
        "loja": ST["loja"],
    }))


def importar(d):
    if not isinstance(d, dict):
        return
    mochila = [x for x in (_limpo(i) for i in d.get("mochila", [])) if x]
    ST["mochila"] = mochila[:MAX_MOCHILA]
    ST["equip"] = {s: None for s in SLOTS}
    for s, it in (d.get("equip") or {}).items():
        c = _limpo(it)
        if c and s in SLOTS and c["slot"] == s:
            ST["equip"][s] = c
    try:
        ST["vida_aplicada"] = int(d.get("vida_aplicada", 0))
    except (TypeError, ValueError):
        ST["vida_aplicada"] = 0
    loja = d.get("loja") or {}
    ST["loja"] = {
        "seed": loja.get("seed"),
        "itens": [x for x in (_limpo(i) for i in loja.get("itens", [])) if x],
    }


# ---------------------------------------------------------
# LOJA / ESTOQUE
# ---------------------------------------------------------
def garantir_estoque():
    E = G["E"]
    derrotados = sum(1 for i in G["TODOS_INIMIGOS"] if not i["vivo"])
    seed = f"{E.nivel}-{derrotados}-{E.dificuldade}"
    if ST["loja"]["seed"] == seed:
        return
    rnd = random.Random(seed)
    bonus = min(1.0, E.nivel / 15 + derrotados / 20)
    itens = [gerar_item(slot=s, rnd=rnd, bonus=bonus, usar_sorte=False) for s in SLOTS]
    for _ in range(2):
        itens.append(gerar_item(min_r=1, rnd=rnd, bonus=bonus + 0.3, usar_sorte=False))
    ST["loja"] = {"seed": seed, "itens": itens}


# ---------------------------------------------------------
# AÇÕES DO MENU
# ---------------------------------------------------------
def _aviso(txt, cor=None):
    UI["msg"] = txt
    UI["msg_t"] = 170
    UI["msg_cor"] = cor or (255, 230, 120)


def _lista():
    aba = UI["aba"]
    if aba == 1:
        return ST["loja"]["itens"]
    return ST["mochila"]


def _clamp():
    n = len(_lista())
    UI["sel"] = max(0, min(UI["sel"], max(0, n - 1)))
    UI["scroll"] = max(0, min(UI["scroll"], max(0, n - VISIVEIS)))
    if UI["sel"] < UI["scroll"]:
        UI["scroll"] = UI["sel"]
    if UI["sel"] >= UI["scroll"] + VISIVEIS:
        UI["scroll"] = UI["sel"] - VISIVEIS + 1


def _selecionado():
    """Retorna (item, item_para_comparar)."""
    if UI["foco"] == 0:
        return ST["equip"][SLOTS[UI["sel_slot"]]], None
    lst = _lista()
    if not lst:
        return None, None
    it = lst[min(UI["sel"], len(lst) - 1)]
    return it, ST["equip"][it["slot"]]


def _indice(lst, it):
    for i, x in enumerate(lst):
        if x is it:
            return i
    return -1


def _equipar(it):
    mochila = ST["mochila"]
    idx = _indice(mochila, it)
    if idx < 0:
        return
    slot = it["slot"]
    velho = ST["equip"][slot]
    ST["equip"][slot] = it
    if velho:
        mochila[idx] = velho
    else:
        mochila.pop(idx)
    sincronizar()
    G["tocar"]("confirmar")
    _aviso(f"{it['nome']} equipado.")
    _clamp()


def _desequipar(slot):
    it = ST["equip"][slot]
    if not it:
        _aviso("Este slot está vazio.", (200, 200, 200))
        G["tocar"]("erro")
        return
    if len(ST["mochila"]) >= MAX_MOCHILA:
        _aviso("Mochila cheia!", (255, 120, 100))
        G["tocar"]("erro")
        return
    ST["mochila"].append(it)
    ST["equip"][slot] = None
    sincronizar()
    G["tocar"]("selecionar")
    _aviso(f"{it['nome']} guardado na mochila.")


def _comprar():
    E = G["E"]
    lst = _lista()
    if not lst:
        return
    it = lst[UI["sel"]]
    p = preco_compra(it)
    if E.moedas < p:
        _aviso("Moedas insuficientes.", (255, 120, 100))
        G["tocar"]("erro")
    elif len(ST["mochila"]) >= MAX_MOCHILA:
        _aviso("Sua mochila está cheia!", (255, 120, 100))
        G["tocar"]("erro")
    else:
        E.moedas -= p
        lst.pop(UI["sel"])
        ST["mochila"].append(it)
        G["tocar"]("moeda")
        _aviso(f"Comprou {it['nome']} por {p} moedas.")
        _clamp()


def _vender():
    E = G["E"]
    lst = _lista()
    if not lst:
        return
    it = lst[UI["sel"]]
    if UI["confirma"] is not it:
        UI["confirma"] = it
        _aviso(f"Aperte ENTER de novo para vender por {preco_venda(it)} moedas.")
        G["tocar"]("selecionar")
        return
    UI["confirma"] = None
    E.moedas += preco_venda(it)
    lst.pop(UI["sel"])
    UI["marcados"] = [m for m in UI["marcados"] if m is not it]
    G["tocar"]("moeda")
    _aviso(f"Vendeu {it['nome']}.")
    _clamp()


def _aprimorar():
    E = G["E"]
    it, _ = _selecionado()
    if not it:
        _aviso("Escolha um item para aprimorar.", (200, 200, 200))
        return
    if it.get("up", 0) >= MAX_UP:
        _aviso("Este item já está no nível máximo.", (255, 200, 120))
        G["tocar"]("erro")
        return
    c = custo_up(it)
    if E.moedas < c:
        _aviso(f"Faltam moedas (custa {c}).", (255, 120, 100))
        G["tocar"]("erro")
        return
    E.moedas -= c
    it["up"] = it.get("up", 0) + 1
    sincronizar()
    G["tocar"]("levelup")
    _aviso(f"{it['nome']} aprimorado para +{it['up']}!")


def _marcar():
    if UI["aba"] != 3 or UI["foco"] != 1:
        return
    lst = _lista()
    if not lst:
        return
    it = lst[UI["sel"]]
    if any(m is it for m in UI["marcados"]):
        UI["marcados"] = [m for m in UI["marcados"] if m is not it]
    elif len(UI["marcados"]) < 3:
        UI["marcados"].append(it)
    G["tocar"]("selecionar")


def _fundir():
    E = G["E"]
    if UI["aba"] != 3:
        return
    ms = UI["marcados"]
    if len(ms) != 3:
        _aviso("Marque 3 itens da mochila com F.", (255, 200, 120))
        G["tocar"]("erro")
        return
    if len({m["r"] for m in ms}) > 1:
        _aviso("Os 3 itens precisam ter a mesma raridade.", (255, 120, 100))
        G["tocar"]("erro")
        return
    r = ms[0]["r"]
    if r >= 4:
        _aviso("Itens lendários não podem ser fundidos.", (255, 120, 100))
        G["tocar"]("erro")
        return
    c = 25 * (r + 1)
    if E.moedas < c:
        _aviso(f"A fusão custa {c} moedas.", (255, 120, 100))
        G["tocar"]("erro")
        return
    slot = random.choice([m["slot"] for m in ms])
    for m in ms:
        i = _indice(ST["mochila"], m)
        if i >= 0:
            ST["mochila"].pop(i)
    E.moedas -= c
    novo = gerar_item(slot=slot, r_fixo=r + 1)
    ST["mochila"].append(novo)
    UI["marcados"] = []
    _clamp()
    G["tocar"]("levelup")
    _aviso(f"Fusão! Você criou {novo['nome']} ({RARIDADES[novo['r']][0]}).",
           RARIDADES[novo["r"]][1])


def _confirmar():
    aba, foco = UI["aba"], UI["foco"]
    if aba == 0:
        if foco == 0:
            _desequipar(SLOTS[UI["sel_slot"]])
        else:
            lst = _lista()
            if lst:
                _equipar(lst[UI["sel"]])
    elif aba == 3:
        _aprimorar()
    elif foco == 0:
        _aviso("Aperte D para ir à lista da direita.", (200, 200, 200))
    elif aba == 1:
        _comprar()
    elif aba == 2:
        _vender()


def _aba(i):
    UI["aba"] = i
    UI["foco"] = 1
    UI["sel"] = 0
    UI["scroll"] = 0
    UI["marcados"] = []
    UI["confirma"] = None
    if i == 1:
        garantir_estoque()
    G["tocar"]("selecionar")


def abrir(ferreiro=False):
    UI["ferreiro"] = ferreiro
    UI["aba"] = 0
    UI["foco"] = 1 if ST["mochila"] else 0
    UI["sel"] = 0
    UI["scroll"] = 0
    UI["marcados"] = []
    UI["confirma"] = None
    UI["msg"] = ""
    UI["msg_t"] = 0
    if ferreiro:
        garantir_estoque()
    G["E"].modo = MODO_EQUIP
    G["tocar"]("confirmar")


def abrir_ferreiro():
    abrir(True)


def fechar():
    G["E"].modo = G["MODO_MUNDO"]
    G["tocar"]("selecionar")


def evento(k):
    if k in (pygame.K_ESCAPE, pygame.K_TAB, pygame.K_c, pygame.K_x, pygame.K_BACKSPACE):
        fechar()
        return True
    if UI["ferreiro"] and pygame.K_1 <= k <= pygame.K_4:
        _aba(k - pygame.K_1)
        return True
    up, down, left, right = G["UP"], G["DOWN"], G["LEFT"], G["RIGHT"]
    if k in up or k in down:
        dy = -1 if k in up else 1
        UI["confirma"] = None
        if UI["foco"] == 0:
            UI["sel_slot"] = (UI["sel_slot"] + dy) % len(SLOTS)
        else:
            n = len(_lista())
            if n:
                UI["sel"] = (UI["sel"] + dy) % n
            _clamp()
        G["tocar"]("selecionar")
    elif k in left:
        UI["foco"] = 0
        UI["confirma"] = None
        G["tocar"]("selecionar")
    elif k in right:
        UI["foco"] = 1
        UI["confirma"] = None
        G["tocar"]("selecionar")
    elif k in (pygame.K_RETURN, pygame.K_SPACE):
        _confirmar()
    elif k == pygame.K_f:
        _marcar()
    elif k == pygame.K_g:
        _fundir()
    return True


# ---------------------------------------------------------
# DESENHO
# ---------------------------------------------------------
_overlay = None
f_peq = None


def _t(txt, x, y, cor=None, f=None, alinhar="e"):
    f = f or G["fonte_p"]
    cor = cor or (255, 255, 255)
    txt = str(txt)
    if alinhar == "d":
        x -= f.size(txt)[0]
    elif alinhar == "c":
        G["texto"](txt, x, y, cor, f, True)
        return
    G["texto"](txt, x, y, cor, f)


def _cortar(txt, larg, f):
    if f.size(txt)[0] <= larg:
        return txt
    while txt and f.size(txt + "…")[0] > larg:
        txt = txt[:-1]
    return txt + "…"


def _fmt(k, v):
    return f"{'+' if v > 0 else ''}{v}{SUFIXO[k]}"


def _resumo(it):
    m = mods_item(it)
    partes = [f"{_fmt(k, m[k])} {ABREV[k]}" for k, _, _, _ in STATS if k in m and m[k]]
    return "  ".join(partes[:2])


def _caixa(r, titulo=None):
    S = G["S"]
    r = pygame.Rect(r)
    pygame.draw.rect(S, (33, 22, 20), r, border_radius=8)
    pygame.draw.rect(S, (110, 70, 48), r, 2, border_radius=8)
    if titulo:
        _t(titulo, r.x + 10, r.y + 5, (255, 236, 200), G["fonte_p"])


def _icone(slot, x, y, cor, s=24):
    S = G["S"]
    d = pygame.draw
    esc = tuple(max(0, c - 95) for c in cor)
    k = s / 24.0

    def p(a, b):
        return (int(x + a * k), int(y + b * k))

    def poli(pts):
        d.polygon(S, cor, [p(*q) for q in pts])
        d.polygon(S, esc, [p(*q) for q in pts], 1)

    if slot == "arma":
        d.line(S, esc, p(5, 19), p(19, 5), max(3, int(5 * k)))
        d.line(S, cor, p(5, 19), p(19, 5), max(1, int(3 * k)))
        d.line(S, (170, 120, 60), p(5, 12), p(12, 19), max(2, int(3 * k)))
        d.line(S, (110, 70, 35), p(2, 22), p(6, 18), max(2, int(3 * k)))
    elif slot == "elmo":
        poli([(4, 19), (4, 11), (8, 5), (16, 5), (20, 11), (20, 19)])
        d.rect(S, (30, 25, 30), (*p(6, 12), int(12 * k), max(2, int(3 * k))))
    elif slot == "armadura":
        poli([(3, 6), (8, 3), (10, 5), (14, 5), (16, 3), (21, 6), (18, 11), (18, 21), (6, 21), (6, 11)])
        d.line(S, esc, p(12, 6), p(12, 20), 1)
    elif slot == "botas":
        poli([(8, 3), (15, 3), (15, 14), (21, 16), (21, 21), (7, 21)])
    else:
        d.lines(S, (190, 190, 200), False, [p(6, 2), p(12, 11), p(18, 2)], 1)
        d.circle(S, esc, p(12, 16), int(7 * k))
        d.circle(S, cor, p(12, 16), int(6 * k))
        d.circle(S, (255, 255, 255), p(12, 16), max(1, int(2 * k)))


def _linha_stat(x, y, k, valor_, delta=None):
    _t(NOME_STAT[k], x, y, (190, 175, 160), f_peq)
    cor = (255, 255, 255) if valor_ else (130, 120, 115)
    _t(_fmt(k, valor_) if valor_ else "—", x + 128, y - 1, cor, G["fonte_p"], "d")
    if delta:
        c = (110, 235, 120) if delta > 0 else (255, 110, 100)
        _t(f"({'+' if delta > 0 else ''}{delta})", x + 190, y, c, f_peq, "d")


def _desenhar_slots():
    S, E = G["S"], G["E"]
    _caixa((34, 62, 240, 244), "PERSONAGEM")
    img = G["animacoes_jogador"]["baixo"][0]
    S.blit(img, img.get_rect(midright=(264, 78)))
    for k, slot in enumerate(SLOTS):
        y = 92 + k * 42
        rr = pygame.Rect(40, y, 228, 38)
        sel = UI["foco"] == 0 and UI["sel_slot"] == k
        it = ST["equip"][slot]
        pygame.draw.rect(S, (66, 44, 34) if sel else (46, 31, 27), rr, border_radius=6)
        cor_r = RARIDADES[it["r"]][1] if it else (95, 75, 65)
        pygame.draw.rect(S, (255, 220, 60) if sel else cor_r, rr, 2, border_radius=6)
        _icone(slot, rr.x + 6, rr.y + 7, cor_r if it else (85, 70, 65))
        _t(NOME_SLOT[slot], rr.x + 38, rr.y + 2, (170, 155, 145), f_peq)
        if it:
            nome = it["nome"] + (f" +{it['up']}" if it.get("up") else "")
            _t(_cortar(nome, 184, G["fonte_p"]), rr.x + 38, rr.y + 16, cor_r)
        else:
            _t("- vazio -", rr.x + 38, rr.y + 16, (120, 105, 98))


def _desenhar_atributos():
    E = G["E"]
    _caixa((34, 312, 240, 244), "ATRIBUTOS")
    dano_ex = 2 * (E.nivel - 1) + E.bonus_dano + total("dano")
    linhas = [
        ("Vida", f"{E.vida}/{E.vida_max}", total("vida")),
        ("Dano extra", f"+{dano_ex}", total("dano")),
        ("Defesa", f"{total('def')}", total("def")),
        ("Velocidade", f"{ef_agil() * 100:+.0f}%", total("agil")),
        ("Crítico", f"{ef_crit()}%", total("crit")),
        ("Sorte", f"{ef_sorte()}%", total("sorte")),
        ("Regen/turno", f"{total('regen')}", total("regen")),
        ("Invencib.", f"+{total('invenc')}f", total("invenc")),
    ]
    for k, (nome, val, eq) in enumerate(linhas):
        y = 338 + k * 21
        _t(nome, 46, y + 1, (190, 175, 160), f_peq)
        _t(val, 196, y, (255, 255, 255), G["fonte_p"], "d")
        if eq:
            _t(f"({'+' if eq > 0 else ''}{eq})", 262, y + 1,
               (110, 235, 120) if eq > 0 else (255, 110, 100), f_peq, "d")
    _t(f"Nível {E.nivel}   EXP {E.exp}/{G['exp_necessaria']()}", 46, 512, (200, 200, 255), f_peq)
    _t(f"Moedas: {E.moedas}", 46, 532, (255, 220, 60), G["fonte_p"])


def _desenhar_lista():
    S = G["S"]
    aba = UI["aba"]
    lst = _lista()
    titulos = ["MOCHILA", "LOJA DA FERREIRA", "VENDER ITENS", "FORJA"]
    _caixa((286, 62, 480, 244), f"{titulos[aba]}  ({len(ST['mochila'])}/{MAX_MOCHILA})"
           if aba != 1 else f"{titulos[aba]}  ({len(lst)} itens)")
    if not lst:
        _t("Nada por aqui.", 526, 170, (150, 135, 125), G["fonte_p"], "c")
        return
    for pos in range(VISIVEIS):
        idx = UI["scroll"] + pos
        if idx >= len(lst):
            break
        it = lst[idx]
        y = 90 + pos * 27
        rr = pygame.Rect(294, y, 464, 25)
        sel = UI["foco"] == 1 and idx == UI["sel"]
        cor_r = RARIDADES[it["r"]][1]
        pygame.draw.rect(S, (70, 48, 38) if sel else (44, 30, 26), rr, border_radius=5)
        pygame.draw.rect(S, (255, 220, 60) if sel else (70, 50, 42), rr, 2, border_radius=5)
        pygame.draw.rect(S, cor_r, (rr.x, rr.y + 3, 4, rr.height - 6))
        _icone(it["slot"], rr.x + 10, rr.y + 2, cor_r, 20)
        direita = rr.right - 8
        if aba == 1:
            p = preco_compra(it)
            _t(f"{p}$", direita, rr.y + 3, (110, 235, 120) if G["E"].moedas >= p else (255, 110, 100),
               G["fonte_p"], "d")
            direita -= 62
        elif aba == 2:
            _t(f"{preco_venda(it)}$", direita, rr.y + 3, (255, 220, 60), G["fonte_p"], "d")
            direita -= 62
        res = _resumo(it)
        _t(res, direita, rr.y + 4, (205, 190, 175), f_peq, "d")
        larg_nome = direita - f_peq.size(res)[0] - (rr.x + 36) - 10
        nome = it["nome"] + (f" +{it['up']}" if it.get("up") else "")
        _t(_cortar(nome, max(60, larg_nome), G["fonte_p"]), rr.x + 36, rr.y + 3, cor_r)
        if any(m is it for m in UI["marcados"]):
            pygame.draw.rect(S, (110, 235, 120), (rr.x + 30, rr.y + 2, 4, rr.height - 4))
            pygame.draw.rect(S, (110, 235, 120), rr, 2, border_radius=5)
    n = len(lst)
    if n > VISIVEIS:  # barra de rolagem
        h = int(216 * VISIVEIS / n)
        y0 = 90 + int(216 * UI["scroll"] / n)
        pygame.draw.rect(S, (120, 85, 60), (760, y0, 4, h), border_radius=2)


def _desenhar_detalhe():
    E = G["E"]
    _caixa((286, 312, 480, 244))
    it, ref = _selecionado()
    aba = UI["aba"]
    if not it:
        if UI["foco"] == 0:
            _t("Slot vazio. Equipe um item da mochila (D, depois ENTER).", 300, 330, (170, 155, 145), f_peq)
        else:
            _t("Nenhum item selecionado.", 300, 330, (170, 155, 145), f_peq)
    else:
        cor_r = RARIDADES[it["r"]][1]
        if it["r"] == 4:
            b = 40 * abs(math.sin(E.tick / 18))
            cor_r = (255, int(170 + b), int(40 + b))
        _t(_cortar(it["nome"], 320, G["fonte"]), 298, 318, cor_r, G["fonte"])
        _t(RARIDADES[it["r"]][0], 756, 322, cor_r, G["fonte_p"], "d")
        sub = f"{NOME_SLOT[it['slot']]}   |   Aprimoramento +{it.get('up', 0)}/{MAX_UP}"
        if it.get("unico"):
            sub += "   |   ITEM ÚNICO"
        _t(sub, 300, 348, (200, 185, 170), f_peq)
        m = mods_item(it)
        mr = mods_item(ref) if ref else {}
        chaves = [k for k, _, _, _ in STATS if m.get(k) or mr.get(k)]
        for n, k in enumerate(chaves[:8]):
            col, row = divmod(n, 4)
            delta = None
            if ref is not None or UI["foco"] == 1 and aba != 3:
                delta = m.get(k, 0) - mr.get(k, 0)
                if ref is None:
                    delta = None
            _linha_stat(300 + col * 236, 374 + row * 22, k, m.get(k, 0), delta)
        if not chaves:
            _t("Sem atributos.", 300, 374, (150, 135, 125), f_peq)
        if ref is None and UI["foco"] == 1 and aba != 3:
            _t(f"Slot de {NOME_SLOT[it['slot']]} vazio: tudo é ganho.", 300, 466, (110, 235, 120), f_peq)
        if aba == 1:
            p = preco_compra(it)
            _t(f"Preço: {p} moedas", 300, 480, (110, 235, 120) if E.moedas >= p else (255, 110, 100))
        elif aba == 2:
            _t(f"Valor de venda: {preco_venda(it)} moedas", 300, 480, (255, 220, 60))
        elif aba == 3:
            if it.get("up", 0) >= MAX_UP:
                _t("Aprimoramento máximo!", 300, 480, (255, 200, 120))
            else:
                c = custo_up(it)
                _t(f"Aprimorar custa {c} moedas (+20% nos atributos)", 300, 480,
                   (110, 235, 120) if E.moedas >= c else (255, 110, 100), f_peq)
            _t(f"Marcados para fusão: {len(UI['marcados'])}/3", 300, 462, (200, 200, 255), f_peq)

    dicas = [
        "A/D painel   W/S mover   ENTER equipar / guardar   C ou ESC fechar",
        "A/D painel   W/S mover   ENTER comprar   1-4 abas   ESC fechar",
        "A/D painel   W/S mover   ENTER vender (2x)   1-4 abas   ESC fechar",
        "ENTER aprimorar   F marcar   G fundir 3 iguais   1-4 abas   ESC fechar",
    ]
    _t(dicas[UI["aba"]], 300, 502, (160, 145, 135), f_peq)
    if UI["msg_t"] > 0:
        UI["msg_t"] -= 1
        _t(_cortar(UI["msg"], 456, G["fonte_p"]), 300, 526, UI.get("msg_cor", (255, 230, 120)))


def desenhar():
    global _overlay
    S = G["S"]
    if _overlay is None:
        _overlay = pygame.Surface((800, 600), pygame.SRCALPHA)
        _overlay.fill((0, 0, 0, 190))
    S.blit(_overlay, (0, 0))
    G["desenhar_painel_madeira"]((10, 8, 780, 586))
    _t("EQUIPAMENTOS", 62, 26, (255, 246, 226), G["fonte"])
    if UI["ferreiro"]:
        nomes = ["1 EQUIPAR", "2 COMPRAR", "3 VENDER", "4 FORJA"]
        for i, n in enumerate(nomes):
            r = pygame.Rect(290 + i * 118, 24, 112, 28)
            sel = UI["aba"] == i
            pygame.draw.rect(S, (174, 105, 67) if sel else (96, 58, 44), r, border_radius=8)
            pygame.draw.rect(S, (246, 210, 145) if sel else (50, 30, 26), r, 2, border_radius=8)
            _t(n, r.centerx, r.y + 6, (255, 246, 226) if sel else (215, 190, 165), f_peq, "c")
    else:
        _t("Fale com a Toupeira Ferreira para comprar, aprimorar e fundir.", 756, 32,
           (255, 238, 214), f_peq, "d")
    _desenhar_slots()
    _desenhar_atributos()
    _desenhar_lista()
    _desenhar_detalhe()


# ---------------------------------------------------------
# INSTALAÇÃO (envolve as funções do jogo)
# ---------------------------------------------------------
def _sprite_ferreira():
    s = pygame.Surface((56, 54), pygame.SRCALPHA)
    d = pygame.draw
    d.ellipse(s, (88, 64, 55), (10, 20, 36, 32))
    d.rect(s, (70, 70, 82), (17, 34, 22, 16), border_radius=4)
    d.circle(s, (104, 78, 66), (28, 17), 13)
    d.ellipse(s, (235, 160, 170), (23, 19, 10, 8))
    d.circle(s, (60, 30, 35), (28, 21), 2)
    for dx in (-6, 6):
        d.circle(s, (60, 60, 70), (28 + dx, 12), 5)
        d.circle(s, (150, 210, 230), (28 + dx, 12), 3)
    d.line(s, (60, 60, 70), (22, 12), (34, 12), 2)
    d.line(s, (120, 80, 40), (46, 42), (52, 24), 3)
    d.rect(s, (150, 155, 170), (46, 18, 12, 8), border_radius=2)
    d.rect(s, (90, 90, 105), (0, 42, 22, 5))
    d.rect(s, (60, 60, 70), (2, 47, 18, 5))
    return s


def _achar_livre(w, h, cx, cy):
    ocup = [o["retangulo"].inflate(30, 30) for o in G["OBSTACULOS"]]
    ocup += [n["ret"].inflate(60, 60) for n in G["NPCS"]]
    ocup += [b["ret"].inflate(50, 50) for b in G["BAUS"]]
    ocup += [i["retangulo"].inflate(140, 140) for i in G["TODOS_INIMIGOS"]]
    esp = G["ESPESSURA_PAREDE"] + 10
    lw, ah = G["LARGURA_MUNDO"], G["ALTURA_MUNDO"]
    for raio in range(0, 700, 24):
        passos = 1 if raio == 0 else max(8, raio // 6)
        for k in range(passos):
            ang = k / passos * math.tau
            r = pygame.Rect(0, 0, w, h)
            r.center = (int(cx + math.cos(ang) * raio), int(cy + math.sin(ang) * raio))
            if r.left < esp or r.top < esp or r.right > lw - esp or r.bottom > ah - esp:
                continue
            if r.collidelist(ocup) == -1:
                return r
    r = pygame.Rect(0, 0, w, h)
    r.center = (cx, cy)
    return r


def instalar(ns):
    """Pluga o sistema no jogo. Chame uma vez, antes de principal()."""
    global G, f_peq
    if ns.get("_EQUIP_INSTALADO"):
        return
    G = ns
    ns["_EQUIP_INSTALADO"] = True
    ns["MODO_EQUIP"] = MODO_EQUIP
    f_peq = pygame.font.Font(None, 20)
    E = ns["E"]

    # ---------- mundo: NPC, baús e segredos ----------
    ferr = {
        "nome": "Toupeira Ferreira", "ret": _achar_livre(34, 44, 360, 330),
        "cor": (95, 70, 60), "cor2": (160, 120, 100), "tipo": "ferreiro",
        "imagem": ns["carregar_imagem_proporcional"](
            "imagens/toupeira_ferreira.png", (56, 54), (115, 82, 65)
        ), "idx": 0,
        "falas": [
            "Ora, ora! Um cliente!",
            "Eu compro, vendo, aprimoro e fundo equipamentos. Traga moedas!",
        ],
    }
    ns["NPCS"].append(ferr)
    for n in ns["NPCS"]:
        if n["tipo"] == "guia":
            n["falas"] += [
                "Aperte C para abrir seus EQUIPAMENTOS: arma, elmo, armadura, botas e amuleto.",
                "Cada chefe solta um item único. E atenção: poupar e derrotar dão itens DIFERENTES!",
                "A Toupeira Ferreira vende, aprimora e funde equipamentos. Há baús e segredos com tesouros pelo mapa.",
            ]
    for nome, x, y, min_r, slot in BAUS_EQUIP:
        r = _achar_livre(36, 30, x, y)
        ns["BAUS"].append({"nome": nome, "ret": r, "conteudo": ("equip", (min_r, slot)), "aberto": False})
    for tipo, x, y, cod in SEGREDOS_EQUIP:
        w, h = ns["IMG"][tipo].get_size()
        r = _achar_livre(w, h, x, y)
        o = ns["_obst"](tipo, r.x, r.y, segredo=cod, aberto=False)
        ns["OBSTACULOS"].append(o)
    ns["SEGREDOS_TOTAL"] = ns["SEGREDOS_TOTAL"] + len(SEGREDOS_EQUIP)

    # ---------- modo do menu ----------
    ns["TRATADORES"][MODO_EQUIP] = evento

    orig_evento_mundo = ns["evento_mundo"]

    def evento_mundo(k):
        if k in (pygame.K_c, pygame.K_TAB) and not E.edicao:
            abrir(False)
            return True
        return orig_evento_mundo(k)

    ns["TRATADORES"][ns["MODO_MUNDO"]] = evento_mundo
    ns["evento_mundo"] = evento_mundo

    orig_desenhar_tudo = ns["desenhar_tudo"]

    def desenhar_tudo():
        if E.modo == MODO_EQUIP:
            ns["desenhar_mundo"]()
            desenhar()
            if E.modo_teste and E.menu_teste:
                ns["desenhar_menu_teste"]()
        else:
            orig_desenhar_tudo()

    ns["desenhar_tudo"] = desenhar_tudo

    orig_hud = ns["desenhar_hud_mundo"]

    def desenhar_hud_mundo():
        orig_hud()
        _t("C equipamentos", 340, 575, (230, 230, 230), ns["fonte_p"])

    ns["desenhar_hud_mundo"] = desenhar_hud_mundo

    orig_falar = ns["falar"]

    def falar(npc):
        if npc["tipo"] == "ferreiro":
            E.dialogo = {"nome": npc["nome"], "linhas": list(npc["falas"]), "i": 0,
                         "acao": abrir_ferreiro}
            E.modo = ns["MODO_DIALOGO"]
            ns["tocar"]("fala")
        else:
            orig_falar(npc)

    ns["falar"] = falar

    # ---------- novo jogo / save ----------
    orig_novo = ns["novo_jogo"]

    def novo_jogo():
        orig_novo()
        resetar()

    ns["novo_jogo"] = novo_jogo

    orig_salvar = ns["salvar_partida"]

    def salvar_partida():
        orig_salvar()
        p = ns["SAVE"].get("partida")
        if isinstance(p, dict):
            p["equip"] = exportar()
            ns["salvar_save"]()

    ns["salvar_partida"] = salvar_partida

    orig_carregar = ns["carregar_partida"]

    def carregar_partida():
        ok = orig_carregar()
        if ok:
            dados = (ns["SAVE"].get("partida") or {}).get("equip")
            if dados:
                importar(dados)
        return ok

    ns["carregar_partida"] = carregar_partida

    # ---------- efeitos na batalha ----------
    orig_dano_t = ns["calcular_dano_timing"]

    def calcular_dano_timing(pos):
        d = orig_dano_t(pos) + total("dano")
        if random.random() * 100 < ef_crit():
            d = int(d * 1.5)
            ns["texto_flutuante"](400, 72, "CRÍTICO!", (255, 140, 60))
        return d

    ns["calcular_dano_timing"] = calcular_dano_timing

    orig_dano_j = ns["dano_jogador"]

    def dano_jogador(base, efeito=None):
        if E.escudo > 0:
            return orig_dano_j(base, efeito)
        antes = E.vida
        forca = E.inimigo.get("forca", 1.0) if E.inimigo else 1.0
        m = ns["MULT_DANO"][E.dificuldade] * forca
        defesa = total("def")
        if defesa:
            red = min(defesa, 0.65 * base * m)
            base = max(0.0, base - red / m)
        orig_dano_j(base, efeito)
        if E.vida < antes and E.vida > 0:
            E.invencivel += total("invenc")

    ns["dano_jogador"] = dano_jogador

    orig_mover = ns["mover_coracao"]

    def mover_coracao(teclas):
        fx0, fy0 = E.fx, E.fy
        orig_mover(teclas)
        k = ef_agil()
        if k and not E.preso and E.t_lento <= 0:
            cx, co = ns["CAIXA"], ns["coracao"]
            E.fx = fx0 + (E.fx - fx0) * (1 + k)
            E.fx = max(cx.left, min(E.fx, cx.right - co.width))
            if not E.azul:
                E.fy = fy0 + (E.fy - fy0) * (1 + k)
                E.fy = max(cx.top, min(E.fy, cx.bottom - co.height))
            co.topleft = (round(E.fx), round(E.fy))

    ns["mover_coracao"] = mover_coracao

    orig_fim_turno = ns["terminar_turno"]

    def terminar_turno():
        orig_fim_turno()
        reg = total("regen")
        if reg > 0 and 0 < E.vida < E.vida_max:
            cura = min(reg, E.vida_max - E.vida)
            E.vida += cura
            co = ns["coracao"]
            ns["texto_flutuante"](co.centerx, co.top - 8, f"+{cura}", (110, 235, 120))

    ns["terminar_turno"] = terminar_turno

    # ---------- recompensas ----------
    orig_fim = ns["finalizar_batalha"]

    def finalizar_batalha(resultado):
        b = E.inimigo
        orig_fim(resultado)
        if b is None:
            return
        linhas = []
        extra = int(b["moedas"] * ef_sorte() / 100)
        if extra:
            E.moedas += extra
            linhas.append(f"Sorte: +{extra} moedas")
        unico = item_unico(b["nome"], resultado != "morto")
        if unico:
            linhas.append(dar_item(unico))
        chance = 0.40 + ef_sorte() / 200.0
        if random.random() < chance:
            it = gerar_item(min_r=1 if b["exp"] >= 30 else 0, bonus=_bonus_dif())
            linhas.append(dar_item(it))
        if linhas:
            ns["tocar"]("bau")
            E.msg = (E.msg + "\n" if E.msg else "") + "\n".join(linhas)
            E.msg_t = max(E.msg_t, 320)

    ns["finalizar_batalha"] = finalizar_batalha

    orig_exp = ns["ganhar_exp"]

    def ganhar_exp(qtd):
        antes = E.nivel
        linhas = orig_exp(qtd)
        for nv in range(antes + 1, E.nivel + 1):
            if nv % 3 == 0:
                it = gerar_item(min_r=1 if nv >= 6 else 0, bonus=_bonus_dif())
                linhas.append(f"Nível {nv}! " + dar_item(it))
        return linhas

    ns["ganhar_exp"] = ganhar_exp

    orig_bau = ns["abrir_bau"]

    def abrir_bau(b):
        if b["conteudo"][0] != "equip":
            return orig_bau(b)
        b["aberto"] = True
        min_r, slot = b["conteudo"][1]
        it = gerar_item(min_r=min_r, slot=slot, bonus=_bonus_dif())
        ns["tocar"]("bau")
        ns["mostrar_mensagem"](dar_item(it), 200)

    ns["abrir_bau"] = abrir_bau

    orig_segredo = ns["aplicar_segredo"]

    def aplicar_segredo(tipo):
        if not str(tipo).startswith("equip"):
            return orig_segredo(tipo)
        partes = tipo.split("_")
        min_r = int(partes[1]) if len(partes) > 1 else 1
        slot = partes[2] if len(partes) > 2 else None
        it = gerar_item(min_r=min_r, slot=slot, bonus=_bonus_dif())
        return "Um equipamento escondido! " + dar_item(it)

    ns["aplicar_segredo"] = aplicar_segredo
    print("Sistema de equipamentos instalado (tecla C / TAB no mundo).")
