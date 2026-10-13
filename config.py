"""
EXP-Option - Robô de Reversão M15 (2 velas + Gale 1)
====================================================
Arquivo central de configuração.

Preencha com suas credenciais ou use variáveis de ambiente (.env).
Prioridade: variável de ambiente > valor padrão abaixo.

Crie um arquivo `.env` na raiz (veja `.env.example`) para não expor senha no código.
"""
import os

# Tenta carregar .env automaticamente (sem quebrar se python-dotenv não instalado)
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass


def _get(key: str, default, cast=str):
    val = os.getenv(key, default)
    try:
        if cast is bool:
            if isinstance(val, bool):
                return val
            return str(val).strip().lower() in ("1", "true", "yes", "y", "sim")
        return cast(val)
    except Exception:
        return default


# ------------------------------------------------------------------
# CONTA
# ------------------------------------------------------------------
EMAIL: str = _get("IQ_EMAIL", "seu_email@gmail.com")
PASSWORD: str = _get("IQ_PASSWORD", "sua_senha")
ACCOUNT_TYPE: str = _get("IQ_ACCOUNT_TYPE", "PRACTICE").upper()  # PRACTICE ou REAL

# ------------------------------------------------------------------
# ATIVO E TRADE
# ------------------------------------------------------------------
# Ativo padrão. Ex: "EURUSD", "EURUSD-OTC", "GBPUSD", "USDJPY"
# Para operar múltiplos ativos, separe por vírgula: "EURUSD,GBPUSD"
ACTIVES: list = [a.strip().upper() for a in _get("IQ_ACTIVES", "EURUSD").split(",") if a.strip()]

# Tipo de opção: "binary" (recomendado p/ M15) ou "digital"
OPTION_TYPE: str = _get("IQ_OPTION_TYPE", "binary").lower()

ENTRY_VALUE: float = _get("IQ_ENTRY_VALUE", 10.0, float)       # valor da entrada principal
MARTINGALE_FACTOR: float = _get("IQ_MARTINGALE_FACTOR", 2.2, float)  # multiplicador do Gale 1
MAX_GALES: int = _get("IQ_MAX_GALES", 1, int)                  # fixo em 1 pela estratégia
EXPIRATION_MINUTES: int = 15                                   # fixo: velas M15

# Filtro de qualidade: só entra se payout >= mínimo (ex: 0.70 = 70%)
MIN_PAYOUT: float = _get("IQ_MIN_PAYOUT", 0.70, float)

# ------------------------------------------------------------------
# TEMPO / FUSO
# ------------------------------------------------------------------
# UTC-3 (Brasília). Use "America/Sao_Paulo" para respeitar horário de verão (quando houver).
TIMEZONE_NAME: str = _get("IQ_TIMEZONE", "America/Sao_Paulo")

# Janela de operação (hora cheia local). Ex: 08 -> 22 opera das 08:00 às 22:59.
START_HOUR: int = _get("IQ_START_HOUR", 8, int)
END_HOUR: int = _get("IQ_END_HOUR", 22, int)

# Tolerância de sincronismo p/ disparo na abertura da vela 3 (segundos)
ENTRY_TOLERANCE_SEC: int = _get("IQ_ENTRY_TOLERANCE_SEC", 3, int)

# ------------------------------------------------------------------
# GERENCIAMENTO DE RISCO
# ------------------------------------------------------------------
STOP_WIN: float = _get("IQ_STOP_WIN", 100.0, float)   # encerra o dia ao atingir lucro
STOP_LOSS: float = _get("IQ_STOP_LOSS", 100.0, float)  # encerra o dia ao atingir prejuízo
MAX_CYCLES_PER_DAY: int = _get("IQ_MAX_CYCLES_PER_DAY", 20, int)

# Reconexão
RECONNECT_ATTEMPTS: int = _get("IQ_RECONNECT_ATTEMPTS", 5, int)
RECONNECT_DELAY_SEC: int = _get("IQ_RECONNECT_DELAY_SEC", 5, int)

# Log
LOG_FILE: str = _get("IQ_LOG_FILE", "bot.log")
