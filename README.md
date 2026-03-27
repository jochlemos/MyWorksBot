# Mywork Ponto Bot (Desktop Windows)

Aplicativo desktop para automatizar registro de ponto (entrada, pausa, retorno, saida) com agendamento, execucao em background e empacotamento para `.exe`.

## Recursos

- Login por e-mail/senha com armazenamento local criptografado (DPAPI do Windows)
- Automacao web via navegador (Playwright)
- Agendamento com perfis por dia da semana
- Execucao em system tray e inicio com Windows
- Botao manual "Bater ponto agora"
- Logs de sucesso/erro no app
- Retry automatico e fila offline
- Protecao contra duplicidade por evento/perfil/dia

## Requisitos

- Windows 10/11
- Python 3.11+ (apenas para desenvolvimento/build)

## Instalar dependencias

```powershell
cd F:\Work\myworks\mywork-ponto-bot
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
```

## Executar em modo dev

```powershell
python main.py
```

## Build executavel .exe (standalone)

```powershell
pyinstaller --noconfirm --onefile --windowed --name MyworkPontoBot main.py
```

Saida:

- `dist\MyworkPontoBot.exe`

## Como configurar

1. Abrir app
2. Informar:
   - E-mail e senha
   - URL de login e URL da pagina de ponto
   - Seletores CSS dos campos e botoes
3. Ajustar tolerancia (ex.: 5 minutos)
4. Ajustar perfis de horario na aba de agendamentos
5. Salvar

## Observacoes importantes

- O teste de login valida automacao do navegador.
- O bot depende de seletores CSS corretos; se o layout mudar, atualize os seletores.
- Verifique e respeite a politica da empresa/sistema para automacao de ponto.
