"""
EXP-Option - Robo de Reversao M15 (2 velas + Gale 1)
====================================================
Estrategia:
  A cada hora cheia (fuso America/Sao_Paulo, UTC-3):
    Vela1 = HH:00-HH:15 | Vela2 = HH:15-HH:30
    Se Vela1 e Vela2 mesma cor (sem doji) -> entra REVERSAO na Vela3 (HH:30-HH:45)
    Se LOSS -> 1x Gale na Vela4 (HH:45-H:00), mesma direcao, valor x fator
    Expiracao sempre = fim da vela de 15min.

Uso: python bot.py
"""
import sys
import time
import logging
import traceback
from datetime import datetime, timedelta, timezone

import config

# --- Logging console + arquivo ---
_fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", "%H:%M:%S")
_h1 = logging.StreamHandler(sys.stdout)
_h1.setFormatter(_fmt)
_h2 = logging.FileHandler(config.LOG_FILE, encoding="utf-8")
_h2.setFormatter(_fmt)
log = logging.getLogger("EXP-Option")
log.setLevel(logging.INFO)
log.handlers.clear()
log.addHandler(_h1)
log.addHandler(_h2)

# --- Fuso horario local (UTC-3) sem dependencia externa ---
try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo(config.TIMEZONE_NAME)
except Exception:
    from datetime import timezone as _tz, timedelta as _td
    TZ = _tz(_td(hours=-3))  # fallback fixo UTC-3
    log.warning("zoneinfo indisponivel, usando UTC-3 fixo.")

# --- Import da API ---
try:
    from iqoptionapi.stable_api import IQ_Option
except ImportError:
    log.error("Pacote 'iqoptionapi' nao instalado. Rode: pip install -r requirements.txt")
    sys.exit(1)

# ================================================================
# HELPERS DE TEMPO
# ================================================================
def now_local() -> datetime:
    return datetime.now(TZ)


def next_hour_start(ref: datetime | None = None) -> datetime:
    ref = ref or now_local()
    h = ref.replace(minute=0, second=0, microsecond=0)
    return h if ref < h else h + timedelta(hours=1)


def wait_until(target: datetime, label: str = "") -> None:
    while True:
        agora = now_local()
        delta = (target - agora).total_seconds()
        if delta <= 0:
            return
        if delta > 60:
            log.info(f"Aguardando {label} ate {target:%H:%M:%S} ({delta/60:.1f} min)...")
            time.sleep(min(delta - 5, 30))
        else:
            time.sleep(min(max(delta, 0.2), 1.0))


def candle_color(candle: dict) -> str:
    o, c = float(candle.get("open", 0)), float(candle.get("close", 0))
    if c > o:
        return "verde"
    if c < o:
        return "vermelha"
    return "doji"

# ================================================================
# CONEXAO / CONTA
# ================================================================

def connect_with_retry() -> "IQ_Option":
    last_err = None
    for tentativa in range(1, config.RECONNECT_ATTEMPTS + 1):
        try:
            log.info(f"Conectando a IQ Option ({config.ACCOUNT_TYPE}) "
                     f"tentativa {tentativa}/{config.RECONNECT_ATTEMPTS}...")
            api = IQ_Option(config.EMAIL, config.PASSWORD)
            api.connect()
            for _ in range(15):
                if api.check_connect():
                    break
                time.sleep(1)
            if not api.check_connect():
                raise ConnectionError("check_connect() retornou False.")
            api.change_balance(config.ACCOUNT_TYPE)
            saldo = api.get_balance()
            log.info(f"Conectado! Saldo {config.ACCOUNT_TYPE}: {saldo}")
            try:
                srv = api.get_server_timestamp()
                log.info(f"Timestamp servidor: {srv} | Local: {now_local():%H:%M:%S %Z}")
            except Exception:
                pass
            return api
        except Exception as e:
            last_err = e
            log.error(f"Falha conexao: {e}. retry em {config.RECONNECT_DELAY_SEC}s...")
            time.sleep(config.RECONNECT_DELAY_SEC)
    raise ConnectionError(f"Nao conectou apos retries: {last_err}")

# ================================================================
# VELAS + PAYOUT
# ================================================================
def get_last_closed_m15(api, active: str, retries: int = 3):
    """Retorna a ultima vela M15 FECHADA (nao a em formacao)."""
    for t in range(retries):
        try:
            velas = api.get_candles(active, 900, 3, time.time())
            if velas and len(velas) >= 2:
                return velas[-2]  # [-1] ainda esta formando
        except Exception as e:
            log.warning(f"get_candles falhou ({t+1}/{retries}): {e}")
            time.sleep(2)
    return None


def get_two_first_candles(api, active: str, hour_start: datetime):
    """Captura Vela1 (HH:00-15) e Vela2 (HH:15-30) apos fechamento da Vela2 (HH:30)."""
    v2_close = hour_start + timedelta(minutes=30)
    wait_until(v2_close + timedelta(seconds=2), f"fechamento Vela2 {active}")
    time.sleep(3)  # margem p/ corretora consolidar
    velas = None
    for t in range(5):
        try:
            velas = api.get_candles(active, 900, 4, time.time())
            if velas and len(velas) >= 3:
                break
        except Exception as e:
            log.warning(f"retry velas {e}")
        time.sleep(3)
    if not velas or len(velas) < 3:
        log.error(f"[{active}] Nao obteve velas M15 suficientes.")
        return None, None
    vela1, vela2 = velas[-3], velas[-2]
    c1, c2 = candle_color(vela1), candle_color(vela2)
    log.info(f"[{active}] Vela1 (HH:00-15) O={vela1['open']} C={vela1['close']} -> {c1}")
    log.info(f"[{active}] Vela2 (HH:15-30) O={vela2['open']} C={vela2['close']} -> {c2}")
    return (vela1, c1), (vela2, c2)


def payout_ok(api, active: str) -> tuple[bool, float]:
    """Verifica payout minimo (filtro de qualidade)."""
    try:
        if config.OPTION_TYPE == "digital":
            try:
                api.subscribe_strike_list(active, 1)
                d = api.get_digital_current_profit(active, 1)
                api.unsubscribe_strike_list(active, 1)
                pay = float(d) / 100.0 if d and float(d) > 1 else float(d or 0)
            except Exception:
                pay = 0.0
        else:
            allp = api.get_all_profit()
            pay = float(allp.get(active, {}).get("binary", 0))
            if pay > 1:  # as vezes vem em %
                pay /= 100.0
        ok = pay >= config.MIN_PAYOUT
        log.info(f"[{active}] Payout {pay:.0%} (min {config.MIN_PAYOUT:.0%}) -> {'OK' if ok else 'BLOQUEADO'}")
        return ok, pay
    except Exception as e:
        log.warning(f"[{active}] Erro payout ({e}), liberando entrada.")
        return True, 0.0


# ================================================================
# ORDENS (binary 15min / digital 15min)
# ================================================================
def place_order(api, active: str, valor: float, direcao: str, tag: str = ""):
    direcao = direcao.lower()
    assert direcao in ("call", "put"), direcao
    try:
        saldo = api.get_balance()
        if saldo is not None and float(saldo) < float(valor):
            log.error(f"[{active}] SALDO INSUFICIENTE ({saldo} < {valor}). {tag}")
            return False, None
    except Exception:
        pass
    try:
        if config.OPTION_TYPE == "digital":
            ok, oid = api.buy_digital_spot(active, valor, direcao, 15)
        else:
            ok, oid = api.buy(valor, active, direcao, 15)
        if ok:
            log.info(f"[{active}] ORDEM {direcao.upper()} R${valor:.2f} {tag} id={oid}")
            return True, oid
        log.error(f"[{active}] buy() retornou False. {tag}")
        return False, None
    except Exception as e:
        log.error(f"[{active}] Excecao no buy: {e}")
        return False, None


def await_result(api, order_id, timeout: int = 16 * 60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if config.OPTION_TYPE == "digital":
                ok = api.check_win_digital_v2(order_id)
            else:
                ok = api.check_win_v3(order_id)
            if isinstance(ok, tuple):
                status, lucro = ok[0], float(ok[1] or 0)
            else:
                status, lucro = str(ok), 0.0
            s = status.lower()
            if "win" in s:
                return "WIN", abs(lucro)
            if "loose" in s or s == "loss":
                return "LOSS", -abs(lucro)
            if "equal" in s or "doji" in s:
                return "EQUAL", 0.0
        except Exception as e:
            log.warning(f"check_win retry: {e}")
        time.sleep(5)
    return "TIMEOUT", 0.0

def run_hour_cycle(api, active, hour_start, stats):
    log.info("=" * 64)
    try:
        banca = api.get_balance()
    except Exception:
        banca = "?"
    log.info(f"[{active}] CICLO {hour_start:%d/%m %H:00} | banca {banca}")
    got = get_two_first_candles(api, active, hour_start)
    (v1, c1), (v2, c2) = got
    if v1 is None:
        return 0.0
    if "doji" in (c1, c2) or c1 != c2:
        log.info(f"[{active}] SEM GATILHO ({c1} x {c2}). Proxima hora.")
        return 0.0
    direcao = "put" if c1 == "verde" else "call"
    log.info(f"[{active}] GATILHO 2x {c1.upper()} -> REVERSAO {direcao.upper()} Vela3.")
    ok_pay, _ = payout_ok(api, active)
    if not ok_pay:
        return 0.0
    v3_open = hour_start + timedelta(minutes=30)
    if now_local() < v3_open:
        wait_until(v3_open, f"Vela3 {active}")
    atraso = (now_local() - v3_open).total_seconds()
    if atraso > 60 + config.ENTRY_TOLERANCE_SEC:
        log.warning(f"[{active}] Vela3 avancada ({atraso:.0f}s). Abortado.")
        return 0.0
    ok, oid = place_order(api, active, config.ENTRY_VALUE, direcao, "ENTRADA Vela3")
    if not ok:
        return 0.0
    res, lucro = await_result(api, oid)
    log.info(f"[{active}] Vela3: {res} ({lucro:+.2f})")
    if res != "LOSS":
        return lucro
    v4_open = hour_start + timedelta(minutes=45)
    if now_local() < v4_open:
        wait_until(v4_open, f"Vela4/Gale {active}")
    vg = round(config.ENTRY_VALUE * config.MARTINGALE_FACTOR, 2)
    log.info(f"[{active}] LOSS -> GALE1 {direcao.upper()} R${vg:.2f} Vela4.")
    ok2, oid2 = place_order(api, active, vg, direcao, "GALE1 Vela4")
    if not ok2:
        return lucro
    res2, lucro2 = await_result(api, oid2)
    log.info(f"[{active}] Gale1: {res2} ({lucro2:+.2f})")
    return lucro + lucro2



def in_window(dt):
    return config.START_HOUR <= dt.hour <= config.END_HOUR


def main():
    log.info("EXP-Option M15 | reversao 2 velas + Gale1 | UTC-3")
    log.info(f"Ativos={config.ACTIVES} tipo={config.OPTION_TYPE} entrada={config.ENTRY_VALUE}")
    api = connect_with_retry()
    stats = {"pnl": 0.0, "ciclos": 0, "wins": 0, "losses": 0}
    try:
        while True:
            agora = now_local()
            if stats["pnl"] >= config.STOP_WIN:
                log.info(f"STOP WIN ({stats['pnl']:.2f}). Fim.")
                break
            if stats["pnl"] <= -config.STOP_LOSS:
                log.info(f"STOP LOSS ({stats['pnl']:.2f}). Fim.")
                break
            if stats["ciclos"] >= config.MAX_CYCLES_PER_DAY:
                log.info("Max ciclos do dia. Fim.")
                break
            if not in_window(agora):
                prox = agora.replace(hour=config.START_HOUR, minute=0, second=0, microsecond=0)
                if prox <= agora:
                    prox += timedelta(days=1)
                log.info(f"Fora da janela. Retoma {prox:%d/%m %H:%M}. PnL={stats['pnl']:.2f}")
                wait_until(prox, "janela")
                continue
            hour_start = agora.replace(minute=0, second=0, microsecond=0)
            if agora >= hour_start + timedelta(minutes=30, seconds=15):
                hour_start += timedelta(hours=1)
                wait_until(hour_start, "prox hora cheia")
            active = config.ACTIVES[0]
            try:
                if not api.check_connect():
                    api = connect_with_retry()
                pnl = run_hour_cycle(api, active, hour_start, stats)
                stats["pnl"] += pnl
                stats["ciclos"] += 1
                if pnl > 0:
                    stats["wins"] += 1
                elif pnl < 0:
                    stats["losses"] += 1
                log.info(f"Acumulado PnL={stats['pnl']:.2f} W={stats['wins']} L={stats['losses']}")
            except Exception as e:
                log.error(f"[{active}] Erro ciclo: {e}")
                time.sleep(5)
    except KeyboardInterrupt:
        log.info("Interrompido (Ctrl+C).")
    finally:
        log.info(f"FIM PnL={stats['pnl']:.2f} W={stats['wins']} L={stats['losses']}")


if __name__ == "__main__":
    main()
