# EXP-Option — Robô Reversão M15 (2 velas + Gale 1)

Opera reversão na Vela3 (HH:30–HH:45) quando Vela1+Veла2 mesma cor. LOSS → 1 Gale Vela4.

## 1. Instalação
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```
Edite `.env` ou `config.py`.

## 2. Execução
```bash
python bot.py
```
Sempre teste em `PRACTICE` antes de `REAL`.

## 3. Regras
- Fuso America/Sao_Paulo (UTC-3). Janela IQ_START_HOUR–IQ_END_HOUR.
- Sem gatilho se doji ou cores diferentes.
- Payout mínimo IQ_MIN_PAYOUT bloqueia entrada fraca.
- Stops: IQ_STOP_WIN / IQ_STOP_LOSS encerram o dia.
